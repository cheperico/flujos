#!/usr/bin/env python3
"""
keypoints_contexto.py — Keypoints de contexto (devenir geográfico) para medios
video/audio, escritos en `media_keypoints`.

El devenir geográfico se reconstruye interpolando la posición del medio contra
los tracks GPX registrados en `tracks` (puede haber varios, uno por etapa; los
track points NO se persisten: se relee el .gpx original por ejecución, decisión
del plan Fase 4). Para cada medio se elige el track cuyo rango contiene su
intervalo (fallback: el más cercano; ver `_elegir_track`).

Pipeline F1 → F4:
  F1 — Interpolar posición (local, sin API): para cada video/audio con
       `timestamp_utc` y `end_time`, muestrear el intervalo cada `--intervalo`
       segundos (default 30) e interpolar (lat, lon, ele) linealmente entre los
       puntos del track GPX por timestamp (bisect). El GPS propio del medio
       (`media.latitude/longitude`) actúa solo como ancla si el track no cubre
       el punto. GPX sin `time` → estimación lineal start→end con
       `source='estimado'`.

  F2 — Transiciones baratas (sin API):
       - Elevación: cambio sostenido ±`--umbral-elevacion` m (default 50) entre
         muestras → keypoint `contexto_elevacion`.
       - Astronomía: `_posicion_sol` (NOAA, astronomia.py) + `clasificar_twilight`
         por muestra → cambios de día/crepúsculo/noche → `contexto_astronomia`.
       - Velocidad (opcional pero barata, con haversine): `en movimiento` vs
         `detenido` con `--umbral-movimiento` km/h (default 5) → `contexto_movimiento`.

  F3 — Enriquecer candidatos (API, frecuencia gruesa + cache): sobre las
       muestras en múltiplos de `--frecuencia-gruesa` (default 300 s):
       - Georef (`reverse_geocode` de geocode.py) → provincia/departamento/
         municipio; cache en memoria + archivo JSON en disco (default
         db/cache/keypoints_contexto.json). Lección del proyecto: `localidad`
         siempre NULL, no se insiste.
       - Clima (`fetch_horario` + `extraer_horarios` de fetch_weather.py) →
         condiciones por hora; transición si cambia la condición o la
         temperatura ≥ `--umbral-temperatura` °C (default 5).
       Si la API falla → log warning y se continúa (no aborta el batch).

  F4 — Escribir keypoints en `media_keypoints`:
       - key ∈ contexto_elevacion | contexto_astronomia | contexto_ubicacion |
         contexto_clima | contexto_movimiento
       - value = descripción breve en español
       - timestamp_offset_secs = offset relativo al inicio del medio
       - timestamp_absolute = timestamp_utc + offset
       - source = track_interpolado | estimado | gps_propio
       No escribe keypoints redundantes: solo marca cambios (idempotente).

Modos:
  skip    (default) solo medios sin keypoints de contexto ni sentinel de
          procesado (keypoints_contexto_estado = ok | sin_datos)
  update  reprocesa todos los medios (borra y reinserta sus contexto_*)
  replace limpia TODOS los keypoints contexto_* (+ sentinel) y regenera

Uso:
    python scripts/keypoints_contexto.py
    python scripts/keypoints_contexto.py --mode update
    python scripts/keypoints_contexto.py --dry-run --verbose
    python scripts/keypoints_contexto.py --solo-video --intervalo 60
    python scripts/keypoints_contexto.py --frecuencia-gruesa 600 --no-cache
"""

import argparse
import bisect
import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Permitir importar db.util y scripts hermanos desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.util import ModoHelper, abrir, resolver_db  # noqa: E402
from scripts.astronomia import _posicion_sol, clasificar_twilight  # noqa: E402
from scripts.fetch_weather import (  # noqa: E402
    codigo_wmo_a_texto,
    extraer_horarios,
    fetch_horario,
)
from scripts.geocode import reverse_geocode  # noqa: E402
from scripts.gradiente import haversine  # noqa: E402
from scripts.ingest_gpx import parsear_gpx  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

KEY_ELEVACION = "contexto_elevacion"
KEY_ASTRONOMIA = "contexto_astronomia"
KEY_UBICACION = "contexto_ubicacion"
KEY_CLIMA = "contexto_clima"
KEY_MOVIMIENTO = "contexto_movimiento"

CLAVES_CONTEXTO = (
    KEY_ELEVACION, KEY_ASTRONOMIA, KEY_UBICACION, KEY_CLIMA, KEY_MOVIMIENTO,
)

# Sentinel de procesado en media_metadata (M1): evita reprocesar en skip los
# medios que producen cero keypoints (sin posición / fuera de cobertura).
KEY_ESTADO_CONTEXTO = "keypoints_contexto_estado"
ESTADO_OK = "ok"
ESTADO_SIN_DATOS = "sin_datos"

SOURCE_TRACK = "track_interpolado"
SOURCE_ESTIMADO = "estimado"
SOURCE_GPS_PROPIO = "gps_propio"

RUTA_CACHE_DEFAULT = str(
    Path(__file__).resolve().parent.parent / "db" / "cache" / "keypoints_contexto.json"
)

_TWILIGHT_TEXTO = {
    "dia": "día",
    "golden_hour": "hora dorada",
    "blue_hour": "hora azul",
    "crepuculo_civil": "crepúsculo civil",
    "crepuculo_nautico": "crepúsculo náutico",
    "crepuculo_astronomico": "crepúsculo astronómico",
    "noche": "noche",
}


# ---------------------------------------------------------------------------
# Helpers de tiempo
# ---------------------------------------------------------------------------

def _normalizar_dt(ts: str | None) -> datetime | None:
    """Convierte un timestamp ISO a datetime aware UTC (maneja Z y naive)."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _muestrear_intervalo(inicio: datetime, fin: datetime, intervalo_s: int) -> list[datetime]:
    """Puntos de muestreo cada intervalo_s en [inicio, fin] (inclusive)."""
    muestras: list[datetime] = []
    t = inicio
    while t <= fin:
        muestras.append(t)
        t += timedelta(seconds=intervalo_s)
    return muestras


# ---------------------------------------------------------------------------
# F1 — Interpolación de posición sobre el track GPX
# ---------------------------------------------------------------------------

def _puntos_track_con_tiempo(
    track_points: list[dict],
) -> list[tuple[datetime, float, float, float | None]]:
    """Puntos del track con time ordenados: [(dt, lat, lon, ele)]."""
    pts: list[tuple[datetime, float, float, float | None]] = []
    for tp in track_points:
        dt = _normalizar_dt(tp.get("time"))
        if dt is None or tp.get("latitude") is None or tp.get("longitude") is None:
            continue
        pts.append((dt, tp["latitude"], tp["longitude"], tp.get("elevation")))
    pts.sort(key=lambda p: p[0])
    return pts


def _puntos_track_sin_tiempo(track_points: list[dict]) -> list[dict]:
    """Puntos del track SIN `time` (para estimación lineal start→end)."""
    return [
        tp for tp in track_points
        if not tp.get("time")
        and tp.get("latitude") is not None
        and tp.get("longitude") is not None
    ]


def _interpolar_lineal(
    p1: tuple[datetime, float, float, float | None],
    p2: tuple[datetime, float, float, float | None],
    t: datetime,
) -> tuple[float, float, float | None]:
    """Interpola (lat, lon, ele) entre dos puntos track en el instante t."""
    t1, lat1, lon1, ele1 = p1
    t2, lat2, lon2, ele2 = p2
    span = (t2 - t1).total_seconds()
    if span <= 0:
        return lat1, lon1, ele1
    frac = (t - t1).total_seconds() / span
    lat = lat1 + (lat2 - lat1) * frac
    lon = lon1 + (lon2 - lon1) * frac
    ele = None
    if ele1 is not None and ele2 is not None:
        ele = ele1 + (ele2 - ele1) * frac
    return lat, lon, ele


def _interpolar_en_track(
    puntos: list[tuple[datetime, float, float, float | None]],
    t: datetime,
) -> tuple[float, float, float | None] | None:
    """Posición (lat, lon, ele) interpolada en t, o None si t está fuera del rango."""
    if len(puntos) < 2:
        return None
    tiempos = [p[0] for p in puntos]
    idx = bisect.bisect_left(tiempos, t)
    if idx == 0:
        return None  # antes del primer punto del track
    if idx >= len(tiempos):
        return None  # después del último punto del track
    return _interpolar_lineal(puntos[idx - 1], puntos[idx], t)


def _estimar_en_track(
    puntos: list[dict],
    t: datetime,
    t0: datetime,
    t1: datetime,
) -> tuple[float, float, float | None] | None:
    """
    Estimación lineal start→end para GPX sin `time`: asume que el track
    cubre el intervalo [t0, t1] del medio con velocidad constante.
    """
    if len(puntos) < 2:
        return None
    total = (t1 - t0).total_seconds()
    if total <= 0:
        return None
    frac = (t - t0).total_seconds() / total
    idx_float = frac * (len(puntos) - 1)
    i = int(idx_float)
    j = min(i + 1, len(puntos) - 1)
    p1, p2 = puntos[i], puntos[j]
    frac2 = idx_float - i
    lat = p1["latitude"] + (p2["latitude"] - p1["latitude"]) * frac2
    lon = p1["longitude"] + (p2["longitude"] - p1["longitude"]) * frac2
    ele = None
    if p1.get("elevation") is not None and p2.get("elevation") is not None:
        ele = p1["elevation"] + (p2["elevation"] - p1["elevation"]) * frac2
    return lat, lon, ele


def _generar_muestras(
    medio: sqlite3.Row,
    puntos_tiempo: list[tuple[datetime, float, float, float | None]],
    puntos_sin_tiempo: list[dict],
    intervalo_s: int,
) -> list[dict]:
    """
    Muestras del medio: [{offset_s, dt, lat, lon, ele, source}].
    source ∈ track_interpolado | estimado | gps_propio | None.
    """
    inicio = _normalizar_dt(medio["timestamp_utc"])
    if inicio is None:
        return []

    fin = _normalizar_dt(medio["end_time"]) if medio["end_time"] else None
    if fin is None and medio["duration_secs"]:
        fin = inicio + timedelta(seconds=medio["duration_secs"])
    if fin is None or fin < inicio:
        fin = inicio

    muestras: list[dict] = []
    for dt in _muestrear_intervalo(inicio, fin, intervalo_s):
        offset_s = round((dt - inicio).total_seconds(), 1)
        lat = lon = ele = None
        source = None

        pos = _interpolar_en_track(puntos_tiempo, dt) if puntos_tiempo else None
        if pos is not None:
            lat, lon, ele = pos
            source = SOURCE_TRACK
        else:
            pos = _estimar_en_track(puntos_sin_tiempo, dt, inicio, fin) if puntos_sin_tiempo else None
            if pos is not None:
                lat, lon, ele = pos
                source = SOURCE_ESTIMADO
            elif medio["latitude"] is not None and medio["longitude"] is not None:
                lat = medio["latitude"]
                lon = medio["longitude"]
                ele = medio["altitude"]
                source = SOURCE_GPS_PROPIO

        muestras.append({
            "offset_s": offset_s,
            "dt": dt,
            "lat": lat,
            "lon": lon,
            "ele": ele,
            "source": source,
        })
    return muestras


# ---------------------------------------------------------------------------
# F2 — Transiciones baratas (sin API)
# ---------------------------------------------------------------------------

def _transiciones_elevacion(muestras: list[dict], umbral_m: float) -> list[dict]:
    """Cambio de elevación sostenido (|Δ| >= umbral) entre muestras consecutivas."""
    kps: list[dict] = []
    for i in range(1, len(muestras)):
        prev, cur = muestras[i - 1], muestras[i]
        if prev["ele"] is None or cur["ele"] is None:
            continue
        delta = cur["ele"] - prev["ele"]
        if abs(delta) >= umbral_m:
            sentido = "subida" if delta > 0 else "bajada"
            kps.append({
                "offset_s": cur["offset_s"],
                "dt": cur["dt"],
                "key": KEY_ELEVACION,
                "value": f"{sentido} sostenida {delta:+.0f}m",
                "source": cur["source"],
            })
    return kps


def _transiciones_astronomia(muestras: list[dict]) -> list[dict]:
    """Cambios de clasificación twilight entre muestras (algoritmo NOAA)."""
    kps: list[dict] = []
    prev_cls = None
    for m in muestras:
        if m["lat"] is None or m["lon"] is None:
            prev_cls = None
            continue
        elev, _, _ = _posicion_sol(m["lat"], m["lon"], m["dt"])
        cls_bruto = clasificar_twilight(elev)
        cls = _TWILIGHT_TEXTO.get(cls_bruto, cls_bruto)
        if cls != prev_cls:
            kps.append({
                "offset_s": m["offset_s"],
                "dt": m["dt"],
                "key": KEY_ASTRONOMIA,
                "value": cls,
                "source": m["source"],
            })
        prev_cls = cls
    return kps


def _transiciones_movimiento(muestras: list[dict], umbral_kmh: float) -> list[dict]:
    """Velocidad estimada entre muestras (haversine): 'en movimiento' vs 'detenido'."""
    kps: list[dict] = []
    prev_estado = None
    for i in range(1, len(muestras)):
        prev, cur = muestras[i - 1], muestras[i]
        if prev["lat"] is None or cur["lat"] is None:
            prev_estado = None
            continue
        dt_s = (cur["dt"] - prev["dt"]).total_seconds()
        if dt_s <= 0:
            continue
        dist_m = haversine(prev["lat"], prev["lon"], cur["lat"], cur["lon"])
        vel_kmh = dist_m / dt_s * 3.6
        estado = "en movimiento" if vel_kmh >= umbral_kmh else "detenido"
        if estado != prev_estado:
            kps.append({
                "offset_s": cur["offset_s"],
                "dt": cur["dt"],
                "key": KEY_MOVIMIENTO,
                "value": estado,
                "source": cur["source"],
            })
        prev_estado = estado
    return kps


# ---------------------------------------------------------------------------
# F3 — Enriquecimiento con APIs (frecuencia gruesa + cache)
# ---------------------------------------------------------------------------

def _seleccionar_gruesas(muestras: list[dict], frecuencia_s: int) -> list[dict]:
    """
    Muestras en múltiplos de la frecuencia gruesa (incluye la primera).

    En lugar de exigir el múltiplo exacto (fallaba si `intervalo` no divide a
    la frecuencia gruesa), elige para cada múltiplo la muestra MÁS CERCANA.
    `muestras` debe venir ordenadas por offset_s (garantía de _generar_muestras).
    """
    if frecuencia_s <= 0 or not muestras:
        return list(muestras)
    max_offset = muestras[-1]["offset_s"]
    seleccionadas: list[dict] = []
    multiple = 0.0
    while multiple <= max_offset + 1e-9:
        mejor = min(muestras, key=lambda m: abs(m["offset_s"] - multiple))
        if not seleccionadas or mejor["offset_s"] != seleccionadas[-1]["offset_s"]:
            seleccionadas.append(mejor)
        multiple += frecuencia_s
    return seleccionadas


def _clave_geo(lat: float, lon: float) -> str:
    """Clave de cache georef: redondeo a ~110 m para compartir entre tramos."""
    return f"{round(lat, 3):.3f},{round(lon, 3):.3f}"


def _clave_grupo_clima(fecha: str, lat: float, lon: float) -> str:
    """Clave de cache clima: celda ~11 km (mismo bin que fetch_weather)."""
    return f"{fecha}|{round(lat, 1)}|{round(lon, 1)}"


def _describir_ubicacion(geo: dict) -> str | None:
    """Descripción breve en español de una ubicación Georef."""
    provincia = geo.get("provincia")
    municipio = geo.get("municipio")
    if municipio and provincia:
        return f"municipio: {municipio} ({provincia})"
    if municipio:
        return f"municipio: {municipio}"
    if provincia:
        return f"provincia: {provincia}"
    return None


def _describir_clima(label: str, temp: float | None) -> str:
    """Descripción breve en español de una condición climática horaria."""
    if temp is None:
        return f"clima: {label}"
    return f"clima: {label}, {temp:g}°C"


def _enriquecer_gruesas(
    gruesas: list[dict],
    cache: dict,
    umbral_temp: float,
    permitir_api: bool = True,
) -> list[dict]:
    """
    Enriquece muestras gruesas con Georef + clima (usa cache en memoria).
    Devuelve keypoints de transición: contexto_ubicacion y contexto_clima.
    """
    # 1) Georef: coords únicas no cacheadas → un batch
    coords_faltantes: list[tuple[float, float]] = []
    for g in gruesas:
        if g["lat"] is None or g["lon"] is None:
            continue
        key = _clave_geo(g["lat"], g["lon"])
        if key not in cache.get("georef", {}):
            coords_faltantes.append((g["lat"], g["lon"]))

    if coords_faltantes and permitir_api:
        try:
            resultados = reverse_geocode(coords_faltantes)
            cache.setdefault("georef", {})
            for (lat, lon), detalle in resultados.items():
                cache["georef"][_clave_geo(lat, lon)] = detalle
        except Exception as e:
            log.warning("Georef falló (%d coords): %s — se continúa sin ubicación.",
                        len(coords_faltantes), e)

    # 2) Clima: grupos (fecha + celda ~11 km) no cacheados → 1 request por grupo
    grupos_faltantes: list[tuple[str, dict]] = []
    for g in gruesas:
        if g["lat"] is None or g["lon"] is None:
            continue
        fecha = g["dt"].strftime("%Y-%m-%d")
        clave = _clave_grupo_clima(fecha, g["lat"], g["lon"])
        if clave not in cache.get("clima", {}):
            grupos_faltantes.append((
                clave,
                {"date": fecha, "lat": round(g["lat"], 1), "lon": round(g["lon"], 1)},
            ))

    if grupos_faltantes and permitir_api:
        cache.setdefault("clima", {})
        for clave, grupo in grupos_faltantes:
            resp = fetch_horario(grupo)
            if resp is None:
                log.warning("Clima falló para %s — se continúa sin clima.", clave)
                continue
            cache["clima"][clave] = extraer_horarios(resp)

    # 3) Keypoints de transición
    kps: list[dict] = []
    prev_geo_desc = None
    prev_label = None
    prev_temp = None

    for g in gruesas:
        if g["lat"] is None or g["lon"] is None:
            prev_geo_desc = prev_label = prev_temp = None
            continue

        # Ubicación
        geo = cache.get("georef", {}).get(_clave_geo(g["lat"], g["lon"]))
        if geo:
            desc = _describir_ubicacion(geo)
            if desc and desc != prev_geo_desc:
                kps.append({
                    "offset_s": g["offset_s"],
                    "dt": g["dt"],
                    "key": KEY_UBICACION,
                    "value": desc,
                    "source": g["source"],
                })
            prev_geo_desc = desc
        else:
            prev_geo_desc = None

        # Clima
        fecha = g["dt"].strftime("%Y-%m-%d")
        horarios = cache.get("clima", {}).get(_clave_grupo_clima(fecha, g["lat"], g["lon"]), {})
        valores = horarios.get(g["dt"].hour)
        if valores:
            label = codigo_wmo_a_texto(valores.get("weather_code"))
            temp = valores.get("temperature_2m")
            cambia_label = label != prev_label
            cambia_temp = (
                temp is not None and prev_temp is not None
                and abs(temp - prev_temp) >= umbral_temp
            )
            if cambia_label or cambia_temp:
                kps.append({
                    "offset_s": g["offset_s"],
                    "dt": g["dt"],
                    "key": KEY_CLIMA,
                    "value": _describir_clima(label, temp),
                    "source": g["source"],
                })
            prev_label = label
            if temp is not None:
                prev_temp = temp
        else:
            prev_label = prev_temp = None

    return kps


# ---------------------------------------------------------------------------
# F4 — Escritura en media_keypoints
# ---------------------------------------------------------------------------

def _insertar_keypoints(conn: sqlite3.Connection, media_id: int, kps: list[dict]) -> None:
    """Inserta keypoints ya generados (con offset_s, dt, key, value, source)."""
    for kp in kps:
        conn.execute(
            """INSERT INTO media_keypoints
               (media_id, timestamp_offset_secs, timestamp_absolute, key, value, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (media_id, kp["offset_s"], kp["dt"].isoformat(),
             kp["key"], kp["value"], kp["source"]),
        )


def _query_medios(conn: sqlite3.Connection, filtro_tipo: str, mode: str) -> list[sqlite3.Row]:
    """Medios video/audio con timestamp_utc según el modo y filtro de tipo."""
    tipos = {
        "todo": ("video", "audio"),
        "solo-video": ("video", "video"),
        "solo-audio": ("audio", "audio"),
    }[filtro_tipo]

    base = """
        SELECT id, timestamp_utc, end_time, duration_secs,
               latitude, longitude, altitude
        FROM media
        WHERE type IN (?, ?) AND timestamp_utc IS NOT NULL
    """
    if mode == "skip":
        base += """ AND id NOT IN (
            SELECT DISTINCT media_id FROM media_keypoints
            WHERE key LIKE 'contexto_%'
        ) AND id NOT IN (
            SELECT media_id FROM media_metadata
            WHERE key = '""" + KEY_ESTADO_CONTEXTO + """'
              AND value IN ('""" + ESTADO_OK + """', '""" + ESTADO_SIN_DATOS + """')
        )"""
    return conn.execute(base, list(tipos)).fetchall()


def _marcar_estado(conn: sqlite3.Connection, media_id: int, estado: str) -> None:
    """Registra el estado de procesado del medio en media_metadata.

    M1: evita que en `--mode skip` un medio con cero keypoints (sin posición,
    fuera de cobertura) se reprocese en cada corrida.
    """
    conn.execute(
        "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
        (media_id, KEY_ESTADO_CONTEXTO, estado),
    )


def _obtener_tracks_gpx(conn: sqlite3.Connection) -> list[dict]:
    """
    Relee los .gpx de TODOS los tracks registrados en `tracks`
    (decisión del plan: los track points NO se persisten en DB).

    Returns:
        Lista de dicts con {"name", "ruta", "puntos_tiempo", "puntos_sin_tiempo",
        "start_dt", "end_dt"}. Los tracks sin archivo o sin puntos útiles
        se descartan con log warning.
    """
    conn.row_factory = sqlite3.Row  # idempotente; robusto a llamadas directas
    filas = conn.execute(
        "SELECT id, name, start_time, end_time, filepath_absoluto "
        "FROM tracks ORDER BY id"
    ).fetchall()
    tracks: list[dict] = []
    for fila in filas:
        ruta = fila["filepath_absoluto"]
        if not ruta or not Path(ruta).exists():
            log.warning("Archivo GPX no existe o sin ruta (track %s): %s",
                        fila["name"], ruta)
            continue
        try:
            gpx = parsear_gpx(ruta)
        except Exception as e:
            log.warning("No se pudo parsear GPX %s: %s", ruta, e)
            continue
        track_points = gpx.get("track_points") or []
        puntos_tiempo = _puntos_track_con_tiempo(track_points)
        puntos_sin_tiempo = _puntos_track_sin_tiempo(track_points)
        if not puntos_tiempo and not puntos_sin_tiempo:
            log.warning("Track sin puntos útiles: %s", ruta)
            continue
        # C2: el rango puede venir de la DB o derivarse del GPX (min/max de los
        # puntos CON tiempo). Solo quedan como `sin_rango` los GPX sin `time`.
        start_dt = _normalizar_dt(fila["start_time"])
        end_dt = _normalizar_dt(fila["end_time"])
        if start_dt is None and puntos_tiempo:
            start_dt = puntos_tiempo[0][0]
        if end_dt is None and puntos_tiempo:
            end_dt = puntos_tiempo[-1][0]
        tracks.append({
            "name": fila["name"],
            "ruta": ruta,
            "puntos_tiempo": puntos_tiempo,
            "puntos_sin_tiempo": puntos_sin_tiempo,
            "start_dt": start_dt,
            "end_dt": end_dt,
        })
        log.info("Track: %s (%s) — %d puntos con tiempo, %d sin tiempo.",
                 fila["name"], ruta, len(puntos_tiempo), len(puntos_sin_tiempo))
    return tracks


def _elegir_track(
    tracks: list[dict],
    inicio: datetime,
    fin: datetime,
) -> dict | None:
    """
    Elige el mejor track GPX para el intervalo [inicio, fin] de un medio.

    Prioridad:
      1. `contiene`: el rango [start_dt, end_dt] del track CONTIENE el
         intervalo del medio (de varios, el de rango más chico).
      2. `solapa`: solapamiento parcial (el de mayor solapamiento).
      3. `cercano`: ningún rango solapa; el de menor gap (fallback del plan).
      4. `sin_rango`: tracks sin start_time/end_time (comportamiento legacy).

    Returns:
        dict del track con la clave "modo" (contiene|solapa|cercano|sin_rango)
        y "gap_s" (distancia al intervalo en segundos; 0 si contiene/solapa).
        None si la lista de tracks está vacía.
    """
    if not tracks:
        return None

    candidatos: list[dict] = []
    sin_rango: list[dict] = []
    for t in tracks:
        if t["start_dt"] is None or t["end_dt"] is None:
            sin_rango.append(t)
            continue
        solape_inicio = max(inicio, t["start_dt"])
        solape_fin = min(fin, t["end_dt"])
        if solape_fin >= solape_inicio:
            t["_solape"] = (solape_fin - solape_inicio).total_seconds()
            t["_gap"] = 0.0
        else:
            t["_solape"] = 0.0
            gap_antes = (t["start_dt"] - fin).total_seconds()
            gap_despues = (inicio - t["end_dt"]).total_seconds()
            t["_gap"] = max(gap_antes, gap_despues)
        candidatos.append(t)

    if not candidatos:
        # Ningún track con rango: comportamiento legacy (el primero)
        elegido = sin_rango[0]
        elegido["modo"] = "sin_rango"
        elegido["gap_s"] = 0.0
        return elegido

    # 1) Contiene el intervalo completo del medio
    contienen = [t for t in candidatos
                 if t["start_dt"] <= inicio and fin <= t["end_dt"]]
    if contienen:
        elegido = min(
            contienen,
            key=lambda t: (t["end_dt"] - t["start_dt"]).total_seconds(),
        )
        elegido["modo"] = "contiene"
        elegido["gap_s"] = 0.0
        return elegido

    # 2) Solapa parcialmente: el de mayor solapamiento
    solapan = [t for t in candidatos if t["_solape"] > 0]
    if solapan:
        elegido = max(solapan, key=lambda t: t["_solape"])
        elegido["modo"] = "solapa"
        elegido["gap_s"] = 0.0
        return elegido

    # 3) El más cercano al intervalo (menor gap)
    elegido = min(candidatos, key=lambda t: t["_gap"])
    elegido["modo"] = "cercano"
    elegido["gap_s"] = elegido["_gap"]
    return elegido


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def procesar_conexion(
    conn: sqlite3.Connection,
    mode: str = "skip",
    intervalo_s: int = 30,
    frecuencia_gruesa: int = 300,
    umbral_elevacion: float = 50.0,
    umbral_movimiento: float = 5.0,
    umbral_temperatura: float = 5.0,
    filtro_tipo: str = "todo",
    dry_run: bool = False,
    cache: dict | None = None,
    permitir_api: bool = True,
) -> dict:
    """
    Pipeline F1→F4 sobre una conexión abierta (testeable con DB temporal).

    Returns:
        dict con estadísticas: medios, muestras, keypoints, con_track,
        con_ancla, sin_posicion.
    """
    conn.row_factory = sqlite3.Row
    if cache is None:
        cache = {"georef": {}, "clima": {}}

    stats = {
        "medios": 0,
        "muestras": 0,
        "keypoints": 0,
        "con_track": 0,
        "con_ancla": 0,
        "sin_posicion": 0,
    }

    # Modo replace: limpiar todos los keypoints de contexto + sentinel primero
    if mode == "replace":
        conn.execute("DELETE FROM media_keypoints WHERE key LIKE 'contexto_%'")
        conn.execute("DELETE FROM media_metadata WHERE key = ?", (KEY_ESTADO_CONTEXTO,))
        conn.commit()

    tracks = _obtener_tracks_gpx(conn)
    if not tracks:
        log.warning("Sin track GPX: no se puede interpolar posición.")
        return stats
    log.info("Tracks GPX disponibles: %d", len(tracks))

    rows = _query_medios(conn, filtro_tipo, mode)
    log.info("Medios a procesar (%s, %s): %d", filtro_tipo, mode, len(rows))

    for row in rows:
        mid = row["id"]

        # Intervalo del medio (misma lógica que _generar_muestras)
        inicio_medio = _normalizar_dt(row["timestamp_utc"])
        fin_medio = _normalizar_dt(row["end_time"]) if row["end_time"] else None
        if fin_medio is None and row["duration_secs"]:
            fin_medio = inicio_medio + timedelta(seconds=row["duration_secs"])
        if fin_medio is None or fin_medio < inicio_medio:
            fin_medio = inicio_medio

        # C2: elegir el track que mejor cubre ESTE medio (hay varios GPX)
        track = _elegir_track(tracks, inicio_medio, fin_medio)
        if track is None:
            continue
        if track["modo"] != "contiene":
            log.warning(
                "Ningún track cubre el medio (id=%s, ts=%s): se usa el track "
                "'%s' (modo=%s, gap=%.0fs). Verificar cobertura.",
                mid, row["timestamp_utc"], track["name"],
                track["modo"], track["gap_s"],
            )

        muestras = _generar_muestras(
            row, track["puntos_tiempo"], track["puntos_sin_tiempo"], intervalo_s,
        )
        if not muestras:
            if not dry_run:
                _marcar_estado(conn, mid, ESTADO_SIN_DATOS)
            continue

        stats["medios"] += 1
        stats["muestras"] += len(muestras)
        stats["con_track"] += sum(1 for m in muestras if m["source"] == SOURCE_TRACK)
        stats["con_ancla"] += sum(1 for m in muestras if m["source"] == SOURCE_GPS_PROPIO)
        stats["sin_posicion"] += sum(1 for m in muestras if m["lat"] is None)

        kps: list[dict] = []
        kps.extend(_transiciones_elevacion(muestras, umbral_elevacion))
        kps.extend(_transiciones_astronomia(muestras))
        kps.extend(_transiciones_movimiento(muestras, umbral_movimiento))

        gruesas = _seleccionar_gruesas(muestras, frecuencia_gruesa)
        kps.extend(_enriquecer_gruesas(gruesas, cache, umbral_temperatura, permitir_api))

        kps.sort(key=lambda k: k["offset_s"])
        stats["keypoints"] += len(kps)

        if dry_run:
            log.info("  [dry-run] media %d: %d keypoints", mid, len(kps))
            continue

        # update/replace: borrar keypoints de contexto previos del medio
        # (idempotencia: nunca duplicar contexto_* por medio)
        if mode in ("update", "replace"):
            conn.execute(
                "DELETE FROM media_keypoints WHERE media_id = ? AND key LIKE 'contexto_%'",
                (mid,),
            )
        if kps:
            _insertar_keypoints(conn, mid, kps)
            _marcar_estado(conn, mid, ESTADO_OK)
        else:
            # M1: medio sin keypoints → sentinel para no reprocesarlo en skip
            _marcar_estado(conn, mid, ESTADO_SIN_DATOS)

    if not dry_run:
        conn.commit()
    return stats


def procesar(db_path: str, **kwargs) -> dict:
    """Abre la DB real y ejecuta el pipeline F1→F4."""
    conn = abrir(resolver_db(db_path))
    try:
        return procesar_conexion(conn, **kwargs)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cache en disco
# ---------------------------------------------------------------------------

def _cargar_cache(ruta: str | None) -> dict:
    """Carga el cache JSON de georef+clima desde disco (o dict vacío)."""
    if not ruta:
        return {"georef": {}, "clima": {}}
    p = Path(ruta)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cache ilegible (%s), se arranca vacío: %s", ruta, e)
    return {"georef": {}, "clima": {}}


def _guardar_cache(ruta: str | None, cache: dict) -> None:
    """Persiste el cache JSON de georef+clima en disco."""
    if not ruta:
        return
    try:
        p = Path(ruta)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("No se pudo guardar el cache (%s): %s", ruta, e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def crear_parser() -> argparse.ArgumentParser:
    """Parser de argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description=(
            "Escribe keypoints de contexto (devenir geográfico) en media_keypoints: "
            "interpola posición contra el track GPX (F1), transiciones baratas "
            "elevación/astronomía/movimiento (F2), enriquece con Georef + clima "
            "con cache (F3) y escribe keypoints no redundantes (F4)."
        ),
    )
    parser.add_argument("--db", default=None, help="Ruta a la base de datos")
    parser.add_argument(
        "--mode", choices=["skip", "update", "replace"], default="skip",
        help="skip: solo pendientes (default) | update: reprocesa todos | replace: limpia y regenera",
    )
    parser.add_argument(
        "--intervalo", type=int, default=30,
        help="Muestreo fino en segundos (default 30)",
    )
    parser.add_argument(
        "--frecuencia-gruesa", type=int, default=300,
        help="Muestreo grueso para APIs (Georef/clima) en segundos (default 300 = 5 min)",
    )
    parser.add_argument(
        "--umbral-elevacion", type=float, default=50.0,
        help="Cambio sostenido de elevación para marcar transición, en metros (default 50)",
    )
    parser.add_argument(
        "--umbral-movimiento", type=float, default=5.0,
        help="Velocidad mínima para 'en movimiento', en km/h (default 5)",
    )
    parser.add_argument(
        "--umbral-temperatura", type=float, default=5.0,
        help="Cambio de temperatura para marcar transición climática, en °C (default 5)",
    )
    grupo_tipo = parser.add_mutually_exclusive_group()
    grupo_tipo.add_argument(
        "--solo-video", action="store_true",
        help="Procesar solo videos (default: videos + audios)",
    )
    grupo_tipo.add_argument(
        "--solo-audio", action="store_true",
        help="Procesar solo audios",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Previsualizar sin escribir en la DB ni llamar a APIs",
    )
    parser.add_argument(
        "--cache", default=RUTA_CACHE_DEFAULT,
        help="Archivo JSON de cache georef+clima (default: db/cache/keypoints_contexto.json)",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="No usar ni persistir cache en disco",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Logging detallado")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point del script (ejecutable standalone o desde flujos.py)."""
    args = crear_parser().parse_args(argv)

    # Limpiar handlers previos: los módulos importados pueden haber llamado
    # logging.basicConfig a nivel de módulo (ingest_gpx, geocode, fetch_weather).
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    filtro_tipo = (
        "solo-video" if args.solo_video
        else "solo-audio" if args.solo_audio
        else "todo"
    )
    ruta_cache = None if args.no_cache else args.cache
    cache = _cargar_cache(ruta_cache)

    log.info("=== KEYPOINTS DE CONTEXTO (devenir geográfico) ===")
    log.info("Modo: %s | tipo: %s | muestreo fino: %ds | grueso: %ds",
             args.mode, filtro_tipo, args.intervalo, args.frecuencia_gruesa)
    if args.dry_run:
        log.info("=== DRY RUN — no se escribirá en la DB ni se llamará a APIs ===")

    stats = procesar(
        args.db,
        mode=args.mode,
        intervalo_s=args.intervalo,
        frecuencia_gruesa=args.frecuencia_gruesa,
        umbral_elevacion=args.umbral_elevacion,
        umbral_movimiento=args.umbral_movimiento,
        umbral_temperatura=args.umbral_temperatura,
        filtro_tipo=filtro_tipo,
        dry_run=args.dry_run,
        cache=cache,
        permitir_api=not args.dry_run,
    )

    log.info("Resumen: %s", stats)
    if not args.dry_run and not args.no_cache:
        _guardar_cache(ruta_cache, cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
