#!/usr/bin/env python3
"""
fetch_weather.py — Obtiene datos climáticos históricos de Open-Meteo
y los asocia a cada medio en la base de datos.

Para cada medio con coordenadas GPS y timestamp, busca el dato horario
más cercano (ERA5-Land, resolución ~11 km) y lo guarda en media_metadata.

Uso:
    python scripts/fetch_weather.py                              # TODO
    python scripts/fetch_weather.py --db db/flujos.db            # DB específica
    python scripts/fetch_weather.py --dry-run                    # Solo simular
    python scripts/fetch_weather.py --limit 100                  # Procesar 100
    python scripts/fetch_weather.py --replace                    # Re-fetch aunque ya tenga datos
    python scripts/fetch_weather.py --steps 3                    # Intervalo horario (default: 1 = cada hora)

Variables climáticas guardadas en media_metadata:
    weather_temp_c          Temperatura a 2 m (°C)
    weather_humidity_pct    Humedad relativa (%)
    weather_precip_mm       Precipitación (mm)
    weather_cloud_pct       Cobertura nubosa (%)
    weather_code            Código WMO (0=despejado, 61=lluvia, etc.)
    weather_wind_speed_kmh  Velocidad del viento a 10 m (km/h)
    weather_wind_dir_deg    Dirección del viento a 10 m (°)
    weather_wind_dir_text   Dirección del viento (punto cardinal: N, S, SO, etc.)
    weather_pressure_hpa    Presión atmosférica superficial (hPa)
    weather_hour_utc        Hora UTC del dato
    weather_source          Siempre "open-meteo"
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch_weather")

OPENMETEO_BASE = "https://archive-api.open-meteo.com/v1/archive"

# Variables horarias que pedimos a Open-Meteo
HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "cloud_cover",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
]

# Códigos WMO que nos interesa etiquetar
WMO_LABELS = {
    0: "despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "niebla",
    48: "niebla con escarcha",
    51: "llovizna ligera",
    53: "llovizna moderada",
    55: "llovizna densa",
    56: "llovizna helada",
    57: "llovizna helada densa",
    61: "lluvia ligera",
    63: "lluvia moderada",
    65: "lluvia intensa",
    66: "lluvia helada ligera",
    67: "lluvia helada intensa",
    71: "nieve ligera",
    73: "nieve moderada",
    75: "nieve intensa",
    80: "tormenta ligera",
    81: "tormenta moderada",
    82: "tormenta intensa",
    95: "tormenta eléctrica",
    96: "tormenta con granizo ligero",
    99: "tormenta con granizo intenso",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def conectar(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def resolver_db(db_path: str | None) -> str:
    if db_path:
        return os.path.abspath(db_path)
    return os.path.join(os.path.dirname(__file__), "..", "db", "flujos.db")


def codigo_wmo_a_texto(code: int | None) -> str:
    """Traduce código WMO a texto descriptivo."""
    if code is None:
        return "desconocido"
    return WMO_LABELS.get(int(code), f"codigo_{code}")


def viento_direccion_a_texto(grados: int | float | None) -> str:
    """Convierte grados (0-360) a punto cardinal en español."""
    if grados is None:
        return "desconocida"
    # 16 rumbos
    rumbos = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSO", "SO", "OSO",
        "O", "ONO", "NO", "NNO",
    ]
    idx = round(int(grados) % 360 / 22.5) % 16
    return rumbos[idx]


# ── Query de medios pendientes ──────────────────────────────────────────────

def medios_sin_clima(conn, limit: int | None = None) -> list[sqlite3.Row]:
    """Retorna medios con GPS + timestamp que NO tienen datos climáticos."""
    query = """
        SELECT m.id, m.timestamp_utc, m.latitude, m.longitude,
               m.filename_original, m.type
        FROM media m
        WHERE m.latitude IS NOT NULL
          AND m.longitude IS NOT NULL
          AND m.timestamp_utc IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM media_metadata mm
              WHERE mm.media_id = m.id AND mm.key = 'weather_source'
          )
        ORDER BY m.timestamp_utc
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def todos_los_medios(conn, limit: int | None = None) -> list[sqlite3.Row]:
    """Retorna TODOS los medios con GPS + timestamp (para --replace)."""
    query = """
        SELECT m.id, m.timestamp_utc, m.latitude, m.longitude,
               m.filename_original, m.type
        FROM media m
        WHERE m.latitude IS NOT NULL
          AND m.longitude IS NOT NULL
          AND m.timestamp_utc IS NOT NULL
        ORDER BY m.timestamp_utc
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    return conn.execute(query).fetchall()


def agrupar_medios(rows: list[sqlite3.Row]) -> list[dict]:
    """
    Agrupa medios por (fecha, lat_bin, lon_bin).
    lat_bin = round(lat, 1), lon_bin = round(lon, 1) → ~11 km celdas.

    Retorna lista de grupos, cada grupo con:
        - date: str YYYY-MM-DD
        - lat: float (centro de celda)
        - lon: float (centro de celda)
        - media_ids: list[int]
        - hours: dict[int, list[int]]  # hora_utc → [media_id, ...]
    """
    grupos: dict[tuple[str, float, float], dict] = {}

    for row in rows:
        ts = row["timestamp_utc"]
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue

        fecha = dt.strftime("%Y-%m-%d")
        lat_bin = round(row["latitude"], 1)
        lon_bin = round(row["longitude"], 1)
        hora = dt.hour

        clave = (fecha, lat_bin, lon_bin)
        if clave not in grupos:
            grupos[clave] = {
                "date": fecha,
                "lat": lat_bin,
                "lon": lon_bin,
                "media_ids": [],
                "hours": {},
            }
        grupos[clave]["media_ids"].append(row["id"])
        if hora not in grupos[clave]["hours"]:
            grupos[clave]["hours"][hora] = []
        grupos[clave]["hours"][hora].append(row["id"])

    return list(grupos.values())


# ── Llamada a Open-Meteo ────────────────────────────────────────────────────

def fetch_horario(grupo: dict) -> dict | None:
    """
    Llama a Open-Meteo Historical API para un grupo (fecha + ubicación).
    Retorna dict con arrays horarios, o None si falla.
    """
    params = (
        f"latitude={grupo['lat']}&longitude={grupo['lon']}"
        f"&start_date={grupo['date']}&end_date={grupo['date']}"
        f"&hourly={','.join(HOURLY_VARS)}"
        f"&timeformat=iso8601&timezone=GMT"
    )
    url = f"{OPENMETEO_BASE}?{params}"

    log.debug("  GET %s", url)
    try:
        req = Request(url, headers={"User-Agent": "Flujos/1.0 (instalacion interactiva)"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        log.error("  HTTP %s: %s", e.code, e.reason)
        return None
    except URLError as e:
        log.error("  Error de red: %s", e.reason)
        return None
    except json.JSONDecodeError as e:
        log.error("  Error decodificando JSON: %s", e)
        return None
    except Exception as e:
        log.error("  Error inesperado: %s", e)
        return None

    return data


def extraer_horarios(resp: dict) -> dict[int, dict]:
    """
    Convierte la respuesta de Open-Meteo en un dict {hora_utc: {var: valor}}.
    """
    hourly = resp.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return {}

    resultado = {}
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(t)
            hora = dt.hour
        except (ValueError, TypeError):
            continue

        valores = {}
        for var in HOURLY_VARS:
            arr = hourly.get(var, [])
            raw = arr[i] if i < len(arr) else None
            if raw is not None:
                valores[var] = raw

        resultado[hora] = valores

    return resultado


# ── Guardado en DB ──────────────────────────────────────────────────────────

def guardar_clima(conn, media_id: int, hora: int, valores: dict):
    """Guarda los datos climáticos de una hora en media_metadata."""
    # Velocidad del viento: convertir m/s → km/h (redondear a 1 decimal)
    wind_ms = valores.get("wind_speed_10m")
    wind_kmh = round(wind_ms * 3.6, 1) if wind_ms is not None else None

    wind_dir = valores.get("wind_direction_10m")

    pairs = [
        ("weather_temp_c", valores.get("temperature_2m")),
        ("weather_humidity_pct", valores.get("relative_humidity_2m")),
        ("weather_precip_mm", valores.get("precipitation")),
        ("weather_cloud_pct", valores.get("cloud_cover")),
        ("weather_code", valores.get("weather_code")),
        ("weather_label", codigo_wmo_a_texto(valores.get("weather_code"))),
        ("weather_wind_speed_kmh", wind_kmh),
        ("weather_wind_dir_deg", wind_dir),
        ("weather_wind_dir_text", viento_direccion_a_texto(wind_dir)),
        ("weather_pressure_hpa", valores.get("surface_pressure")),
        ("weather_hour_utc", hora),
        ("weather_source", "open-meteo"),
    ]

    for key, value in pairs:
        if value is not None:
            conn.execute(
                "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
                (media_id, key, str(value)),
            )


def limpiar_clima(conn, media_id: int):
    """Borra datos climáticos existentes de un medio (para --replace)."""
    conn.execute(
        "DELETE FROM media_metadata WHERE media_id = ? AND key LIKE 'weather_%'",
        (media_id,),
    )


# ── Procesamiento principal ─────────────────────────────────────────────────

def procesar(
    db_path: str,
    dry_run: bool = False,
    limit: int | None = None,
    replace: bool = False,
    step_hours: int = 1,
):
    """Pipeline principal: agrupa, fetchea, guarda."""
    conn = conectar(db_path)

    # 1. Obtener medios
    if replace:
        rows = todos_los_medios(conn, limit=limit)
        log.info("Modo --replace: procesando TODOS los medios con GPS (%d)", len(rows))
    else:
        rows = medios_sin_clima(conn, limit=limit)
        log.info("Medios sin datos climáticos: %d", len(rows))

    if not rows:
        log.info("No hay medios para procesar.")
        conn.close()
        return

    # 2. Agrupar
    grupos = agrupar_medios(rows)
    log.info(
        "Agrupados en %d grupos (fecha + celda ~11 km)",
        len(grupos),
    )

    if dry_run:
        log.info("=== DRY RUN — no se ejecutarán llamadas ni guardados ===")
        if step_hours > 1:
            log.info("  (step_hours=%d: solo se guardarian horas multiplo de %d)", step_hours, step_hours)
        for g in sorted(grupos, key=lambda x: x["date"]):
            horas = sorted(g["hours"].keys())
            if step_hours > 1:
                horas = [h for h in horas if h % step_hours == 0]
            log.info(
                "  %s  (%.1f, %.1f)  → %d medios, %d horas: %s",
                g["date"], g["lat"], g["lon"],
                len(g["media_ids"]),
                len(horas),
                ", ".join(f"{h}:00" for h in horas[:6]) + ("..." if len(horas) > 6 else ""),
            )
        conn.close()
        return

    # 3. Fetch + guardar
    total_ok = 0
    total_skip = 0
    total_media = 0

    # Dict de lookup rápido por id
    rows_por_id = {r["id"]: r for r in rows}

    for g_idx, grupo in enumerate(grupos, 1):
        log.info(
            "[%d/%d] %s  (%.1f, %.1f) — %d medios",
            g_idx, len(grupos),
            grupo["date"], grupo["lat"], grupo["lon"],
            len(grupo["media_ids"]),
        )

        # Llamar a Open-Meteo
        resp = fetch_horario(grupo)
        if resp is None:
            log.warning("  ⚠ Se saltea el grupo por error en la llamada.")
            total_skip += 1
            continue

        horarios = extraer_horarios(resp)
        if not horarios:
            log.warning("  ⚠ Respuesta vacía de Open-Meteo.")
            total_skip += 1
            continue

        # Para cada medio, buscar la hora correspondiente
        for media_id in grupo["media_ids"]:
            # Buscar el timestamp original para determinar hora exacta
            media_row = rows_por_id.get(media_id)
            if not media_row:
                continue
            ts = media_row["timestamp_utc"]
            try:
                dt = datetime.fromisoformat(ts)
                hora = dt.hour
            except (ValueError, TypeError):
                continue

            # Encontrar la hora más cercana disponible
            if hora in horarios:
                hora_usar = hora
            elif horarios:
                # Si no está exactamente, buscar la más cercana
                hora_usar = min(horarios.keys(), key=lambda h: abs(h - hora))
            else:
                continue

            # Si step_hours > 1, solo guardar si la hora es multiplo del intervalo
            if step_hours > 1 and hora_usar % step_hours != 0:
                continue

            valores = horarios[hora_usar]
            if not valores:
                continue

            # Si es --replace, limpiar datos viejos
            if replace:
                limpiar_clima(conn, media_id)

            guardar_clima(conn, media_id, hora_usar, valores)
            total_media += 1

        conn.commit()
        total_ok += 1

        # Pequeña pausa para no saturar la API
        if g_idx < len(grupos):
            time.sleep(0.5)

    # Resumen
    log.info("=" * 50)
    log.info("RESUMEN:")
    log.info("  Grupos procesados: %d", total_ok)
    log.info("  Grupos saltados:   %d", total_skip)
    log.info("  Medios con clima:  %d", total_media)

    conn.close()


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Obtener datos climáticos históricos desde Open-Meteo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", help="Ruta a la base de datos SQLite")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo mostrar qué se haría, sin llamar API ni guardar",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limitar cantidad de medios a procesar",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="[DEPRECATED: usar --mode replace] Re-fetch incluso para medios que ya tienen datos climáticos",
    )
    parser.add_argument(
        "--mode", default="skip", choices=["skip", "update", "replace"],
        help="Modo: skip (solo pendientes), update (todos), replace (limpiar y regenerar)",
    )
    parser.add_argument(
        "--steps", type=int, default=1,
        help="Intervalo horario de los datos (default: 1 = cada hora)",
    )

    args = parser.parse_args()
    db_path = resolver_db(args.db)

    if not os.path.isfile(db_path):
        log.error("Base de datos no encontrada: %s", db_path)
        log.error("Creala con: python scripts/ingest.py o ejecutá el schema.sql")
        sys.exit(1)

    # --replace es alias de --mode replace
    replace = args.replace or args.mode in ("update", "replace")

    log.info("Base de datos: %s", db_path)
    log.info("Modo: %s", "DRY RUN" if args.dry_run else "normal")
    if replace:
        log.info("  --mode %s: se re-fetchearán todos los medios", args.mode if not args.replace else "replace")

    procesar(
        db_path=db_path,
        dry_run=args.dry_run,
        limit=args.limit,
        replace=replace,
        step_hours=args.steps,
    )


if __name__ == "__main__":
    main()
