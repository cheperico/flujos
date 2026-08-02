#!/usr/bin/env python3
"""
loop_db.py — Construcción del motor de loop integrado con la DB de Flujos.

Lee la base `db/flujos.db` (SOLO LECTURA), aplica los filtros elegidos por el
usuario (municipios, colores, tags, días, clima), calcula la hora de día de
cada medio desde `timestamp_utc`, genera los chiches ambientales y produce el
spec JSON del loop agnóstico del renderizador (web / TouchDesigner). No
escribe nada en la DB.

Pipeline de `generar_loop`:
    1. Normaliza las horas (menos de 2 → modo "todas las horas", 0..23).
    2. Recupera los N−1 segmentos temporales del motor puro (`loop_engine`).
    3. Consulta `media` (+ `media_metadata`) con los filtros (AND).
    4. Ordena según `modalidad_ubicaciones` (geo por cumul_distance_m, o
       eleccion respetando el orden natural).
    5. Calcula la hora de día (float 0..24) desde `timestamp_utc`.
    6. Genera los chiches desde los campos calculados (weather_*, sun_*).
    7. Llama `loop_engine.armar_spec` y devuelve la spec.

Uso:
    python scripts/ai_media/loop_db.py --horas 7 16 13 18 --salida spec.json
    python scripts/ai_media/loop_db.py --horas 7 16 13 18 --municipios Inriville
    python scripts/ai_media/loop_db.py --colores rojo,azul --tags paisaje --dry-run

Requiere: db.util (abrir, resolver_db) y loop_engine.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any, Optional

log = logging.getLogger(__name__)

# Directorios en sys.path para ejecución standalone desde cualquier lugar:
#  - proyecto raíz (raíz/): permite `from db.util import ...`
#  - scripts/ai_media/    : permite `import loop_engine` sin disparar el
#                           costoso __init__.py del paquete ai_media (que
#                           importaría ollama_client y demás).
_AI_MEDIA_DIR = os.path.dirname(os.path.abspath(__file__))
# Proyecto raíz: scripts/ai_media/ → subir 2 niveles (scripts/ → raíz/)
sys.path.insert(0, os.path.dirname(os.path.dirname(_AI_MEDIA_DIR)))
sys.path.insert(0, _AI_MEDIA_DIR)

from db.util import abrir, resolver_db  # noqa: E402
import loop_engine  # noqa: E402

# ── Umbrales de chiches (ver docs/motor_loop.md §5) ─────────────────────────
MEDIODIA_UMBRAL_SEG = 900.0     # secs_since_noon ≈ 0 → ±15 min del cenit
TEMP_CALOR = 30.0               # weather_temp_c > 30  → "Hace calor"
TEMP_FRIO = 10.0                # weather_temp_c < 10  → "Hace frío"
VIENTO_ALTO = 30.0              # weather_wind_speed_kmh > 30 → "Hay mucho viento"
PRECIP_LLUVIA = 0.0             # weather_precip_mm > 0 → "Está lloviendo"
ELEVACION_ALBA_BAJA = 0.0       # sun_elevation cruza 0° al alba
ELEVACION_ALBA_ALTA = 3.0

# Períodos de twilight considerados "noche"
NOCHE_PERIODOS = {
    "noche", "crepuculo_civil", "crepuculo_nautico", "crepuculo_astronomico",
}
# Período del amanecer (refuerzo de "Salió el sol")
ALBA_PERIODOS = {"golden_hour", "blue_hour"}

# Claves de media_metadata que se incorporan al spec
CLAVES_METADATA = [
    "ia_keywords",
    "ia_description",
    "weather_temp_c",
    "weather_wind_speed_kmh",
    "weather_precip_mm",
    "weather_label",
]


# ── Timestamps UTC (formato mixto Z / +00:00) ────────────────────────────────


def _parsear_timestamp(valor: Optional[str]) -> Optional[datetime]:
    """
    Parsea un `timestamp_utc` a datetime.

    Los timestamps vienen en formato mixto: algunos terminan en 'Z' y otros en
    '+00:00'. Aunque Python 3.11+ ya soporta 'Z' en `fromisoformat`, por
    robustez se reemplaza 'Z' por '+00:00' antes de parsear.

    Args:
        valor: timestamp_utc en texto (o None).

    Returns:
        datetime, o None si es vacío o no se puede parsear.
    """
    texto = (valor or "").strip()
    if not texto:
        return None
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        log.debug("  timestamp_utc no parseable: %r", valor)
        return None


def _extraer_hora(timestamp_utc: Optional[str]) -> Optional[float]:
    """
    Calcula la hora de día (float 0..23.99) desde un timestamp_utc.

    Ej: 08:00 → 8.0; 14:30 → 14.5.

    Args:
        timestamp_utc: valor de media.timestamp_utc.

    Returns:
        Hora en fracción, o None si no hay timestamp válido.
    """
    dt = _parsear_timestamp(timestamp_utc)
    if dt is None:
        return None
    return dt.hour + dt.minute / 60.0 + dt.second / 3600.0


# ── Consultas a DB ───────────────────────────────────────────────────────────


def _consultar_metadata(conn: sqlite3.Connection,
                        media_ids: list[int]) -> dict[int, dict[str, str]]:
    """
    Recupera las claves de metadata de interés para una lista de media_ids.

    Args:
        conn: conexión SQLite (row_factory = sqlite3.Row).
        media_ids: ids de medios.

    Returns:
        {media_id: {clave: valor}}.
    """
    if not media_ids:
        return {}
    marcadores = ",".join("?" * len(media_ids))
    claves_ph = ",".join("?" * len(CLAVES_METADATA))
    filas = conn.execute(
        f"SELECT media_id, key, value FROM media_metadata "
        f"WHERE media_id IN ({marcadores}) AND key IN ({claves_ph})",
        [*media_ids, *CLAVES_METADATA],
    ).fetchall()
    resultado: dict[int, dict[str, str]] = {mid: {} for mid in media_ids}
    for fila in filas:
        resultado[fila["media_id"]][fila["key"]] = fila["value"]
    return resultado


def _filtrar_media(conn: sqlite3.Connection, filtros: dict) -> list[sqlite3.Row]:
    """
    Arma y ejecuta la query de selección de medios con todos los filtros (AND).

    Args:
        conn: conexión SQLite.
        filtros: dict opcional: municipios, colores, tags, dias, clima.

    Returns:
        Lista de filas (sqlite3.Row) de `media` que cumplen los filtros.
    """
    base = """
        SELECT m.id AS media_id, m.type AS tipo, m.subtype,
               m.filename_original, m.filepath_absoluto AS ruta,
               m.duration_secs, m.latitude AS lat, m.longitude AS lon,
               m.municipio, m.color_1_name_basic AS color, m.author,
               m.cumul_distance_m, m.sun_elevation, m.secs_since_noon,
               m.twilight_period, m.timestamp_utc
        FROM media m
    """
    condiciones: list[str] = []

    municipios = filtros.get("municipios") or []
    colores = filtros.get("colores") or []
    tags = filtros.get("tags") or []
    dias = filtros.get("dias") or []
    clima = filtros.get("clima") or []

    # municipios: AND, IN (...)
    cond_media: list[str] = []
    params_media: list[Any] = []

    if municipios:
        cond_media.append(f"m.municipio IN ({','.join('?' * len(municipios))})")
        params_media.extend(municipios)

    if colores:
        # Color en cualquiera de los 3 slots dominantes (OR interno, AND global)
        slots = " OR ".join(
            f"m.color_{slot}_name_basic IN ({','.join('?' * len(colores))})"
            for slot in (1, 2, 3))
        cond_media.append(f"({slots})")
        params_media.extend(colores * 3)

    # tags: EXISTS por tag (AND)
    cond_meta: list[str] = []
    params_meta: list[Any] = []

    for tag in tags:
        cond_meta.append(
            "EXISTS (SELECT 1 FROM media_metadata md "
            "WHERE md.media_id = m.id AND md.key = 'ia_keywords' "
            "AND md.value LIKE ?)")
        params_meta.append(f"%{tag}%")

    if dias:
        cond_meta.append(
            "EXISTS (SELECT 1 FROM media_metadata md_d "
            "WHERE md_d.media_id = m.id AND md_d.key = 'dia_semana' "
            f"AND md_d.value IN ({','.join('?' * len(dias))}))")
        params_meta.extend(dias)

    if clima:
        cond_meta.append(
            "EXISTS (SELECT 1 FROM media_metadata md_c "
            "WHERE md_c.media_id = m.id AND md_c.key = 'weather_label' "
            f"AND md_c.value IN ({','.join('?' * len(clima))}))")
        params_meta.extend(clima)

    condiciones = cond_media + cond_meta
    params = params_media + params_meta

    query = base
    if condiciones:
        query += " WHERE " + " AND ".join(condiciones)
    query += " ORDER BY m.id"
    return conn.execute(query, params).fetchall()


def _flotante(v: Optional[str]) -> Optional[float]:
    """Convierte un valor a float, o None si no es numérico."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_tags(valor: Optional[str]) -> list[str]:
    """Divide keywords coma-separadas en lista limpia."""
    if not valor:
        return []
    return [t.strip() for t in valor.split(",") if t.strip()]


# ── Chiches (eventos ambientales) ────────────────────────────────────────────


def _chiches_de_medios(campos: dict) -> list[str]:
    """
    Evalúa las condiciones ambientales de un medio y devuelve los textos de
    los chiches activos (docs/motor_loop.md §5).

    `campos` debe contener: sun_elevation, secs_since_noon, twilight_period,
    weather_temp_c, weather_wind_speed_kmh, weather_precip_mm (float o None).

    Args:
        campos: dict con los campos calculados del medio.

    Returns:
        Lista de textos de chiches activos.
    """
    textos: list[str] = []

    # "Salió el sol": sun_elevation cruza 0° al alba (elevación pequeña > 0)
    elev = campos.get("sun_elevation")
    if elev is not None and ELEVACION_ALBA_BAJA <= elev <= ELEVACION_ALBA_ALTA:
        textos.append("Salió el sol")

    # "Es el mediodía": secs_since_noon ≈ 0
    ssn = campos.get("secs_since_noon")
    if ssn is not None and abs(ssn) <= MEDIODIA_UMBRAL_SEG:
        textos.append("Es el mediodía")

    # Térmico
    temp = campos.get("weather_temp_c")
    if temp is not None:
        if temp > TEMP_CALOR:
            textos.append("Hace calor")
        elif temp < TEMP_FRIO:
            textos.append("Hace frío")

    # Viento
    viento = campos.get("weather_wind_speed_kmh")
    if viento is not None and viento > VIENTO_ALTO:
        textos.append("Hay mucho viento")

    # Lluvia
    precip = campos.get("weather_precip_mm")
    if precip is not None and precip > PRECIP_LLUVIA:
        textos.append("Está lloviendo")

    # Noche
    twi = campos.get("twilight_period") or ""
    if twi in NOCHE_PERIODOS:
        textos.append("Es la noche")

    return textos


# ── Generación del loop ──────────────────────────────────────────────────────


def generar_loop(
    db_path: str,
    horas: list[int],
    loop_secs: float = 300.0,
    modalidad_ubicaciones: str = "geo",
    filtros: Optional[dict] = None,
    salida: Optional[str] = None,
) -> dict:
    """
    Genera el spec JSON del loop a partir de las elecciones (solo lectura).

    Args:
        db_path: Ruta a la base de datos.
        horas: Horas elegidas (orden). Si < 2 → todas (0..23).
        loop_secs: Duración del loop (default 300 s).
        modalidad_ubicaciones: 'geo' (por cumul_distance_m) o 'eleccion'.
        filtros: dict opcional: municipios/colores/tags/dias/clima/ideas.
        salida: ruta de archivo JSON opcional para volcar el spec.

    Returns:
        Spec dict: loop_secs, segmentos, medios, chiches.

    Raises:
        FileNotFoundError: si la DB no existe.
    """
    # 1. Normalizar horas
    horas_norm = [int(h) for h in horas]
    if len(horas_norm) < 2:
        log.info("  Menos de 2 horas → modo 'todas las horas' (0..23).")
        horas_norm = list(range(0, 24))

    filtros = filtros or {}
    if filtros.get("ideas"):
        log.warning("  Filtro 'ideas' documentado pero NO implementado "
                    "(requiere embeddings semánticos).")

    # 2. Segmentos del motor puro (validación temprana)
    loop_engine.calcular_segmentos(horas_norm, loop_secs)

    conn = abrir(db_path)
    conn.row_factory = sqlite3.Row
    try:
        filas = _filtrar_media(conn, filtros)

        # 3. Orden según modalidad
        if modalidad_ubicaciones == "geo":
            filas = sorted(filas, key=lambda r: (r["cumul_distance_m"] is None,
                                                 _flotante(r["cumul_distance_m"]) or 0.0))
        else:
            filas = sorted(filas, key=lambda r: (r["media_id"] is None, r["media_id"] or 0))

        media_ids = [r["media_id"] for r in filas]
        metadata = _consultar_metadata(conn, media_ids)

        # 4 + 5: armar medios y chiches
        medios: list[dict] = []
        chiches: list[dict] = []
        # Los chiches se consolsidan por (texto, hora ENTERA) para no
        # disparar un evento por cada medio: "Salió el sol" aparece una vez
        # por hora de día, no 33 veces. Clave: texto + int(hora).
        chiches_vistos: set[tuple[str, int]] = set()
        for fila in filas:
            hora = _extraer_hora(fila["timestamp_utc"])
            if hora is None:
                continue
            mid = fila["media_id"]
            meta = metadata.get(mid, {})

            medio = {
                "media_id": mid,
                "tipo": fila["tipo"],
                "ruta": fila["ruta"],
                "hora": hora,
                "duracion": fila["duration_secs"] or 0.0,
                "municipio": fila["municipio"],
                "color": fila["color"],
                "tags": _parse_tags(meta.get("ia_keywords")),
                "desc": meta.get("ia_description", ""),
                "ubicacion": (
                    {"lat": fila["lat"], "lon": fila["lon"]}
                    if fila["lat"] is not None else None),
                "clima": {
                    "temp_c": _flotante(meta.get("weather_temp_c")),
                    "viento_kmh": _flotante(meta.get("weather_wind_speed_kmh")),
                    "precip_mm": _flotante(meta.get("weather_precip_mm")),
                    "etiqueta": meta.get("weather_label", ""),
                },
            }
            medios.append(medio)

            # Chiches ambientales (consolidados por texto + hora en punto)
            campos = {
                "sun_elevation": fila["sun_elevation"],
                "secs_since_noon": fila["secs_since_noon"],
                "twilight_period": fila["twilight_period"],
                "weather_temp_c": _flotante(meta.get("weather_temp_c")),
                "weather_wind_speed_kmh": _flotante(meta.get("weather_wind_speed_kmh")),
                "weather_precip_mm": _flotante(meta.get("weather_precip_mm")),
            }
            hora_entera = int(hora)
            for texto in _chiches_de_medios(campos):
                clave = (texto, hora_entera)
                if clave not in chiches_vistos:
                    chiches_vistos.add(clave)
                    chiches.append({"hora": hora, "texto": texto})
    finally:
        conn.close()

    # 5. armar_spec (posiciona los que caen en el arco)
    spec = loop_engine.armar_spec(horas_norm, loop_secs, medios, chiches)

    if salida:
        with open(salida, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        log.info("  Spec escrita en: %s", salida)

    return spec


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Genera el spec JSON del motor de loop de Flujos a partir de "
                    "las elecciones (horas, municipios, colores, tags, días, clima). ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--horas", nargs="+", type=int, default=None,
                        help="Horas elegidas en orden (ej: 7 16 13 18). Si no se dan "
                             "o hay menos de 2, se usan todas (0..23).")
    parser.add_argument("--loop-secs", type=float, default=300.0,
                        help="Duración del loop en segundos (default: 300).")
    parser.add_argument("--municipios", default=None,
                        help="Municipios separados por coma.")
    parser.add_argument("--colores", default=None,
                        help="Colores básicos separados por coma (ej: 'rojo,azul').")
    parser.add_argument("--tags", default=None,
                        help="Tags separados por ';' (ej: 'paisaje;bici').")
    parser.add_argument("--dias", default=None,
                        help="Días separados por coma (ej: 'lunes,martes').")
    parser.add_argument("--clima", default=None,
                        help="Etiquetas de clima separadas por coma.")
    parser.add_argument("--modalidad", default="geo", choices=["geo", "eleccion"],
                        help="Orden de medios: geo (recorrido real) o eleccion.")
    parser.add_argument("--db", default=None, help="Ruta a la DB (default: db/flujos.db).")
    parser.add_argument("--salida", default=None,
                        help="Ruta de archivo JSON donde volcar el spec.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Previsualizar configuración sin generar el spec.")
    parser.add_argument("--verbose", action="store_true", help="Log detallado.")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("  No existe la DB: %s", db_path)
        sys.exit(1)

    horas = [int(h) for h in args.horas] if args.horas else []
    filtros: dict[str, Any] = {}
    if args.municipios:
        filtros["municipios"] = [s.strip() for s in args.municipios.split(",") if s.strip()]
    if args.colores:
        filtros["colores"] = [s.strip() for s in args.colores.split(",") if s.strip()]
    if args.tags:
        filtros["tags"] = [s.strip() for s in args.tags.split(";") if s.strip()]
    if args.dias:
        filtros["dias"] = [s.strip() for s in args.dias.split(",") if s.strip()]
    if args.clima:
        filtros["clima"] = [s.strip() for s in args.clima.split(",") if s.strip()]

    horas_display = horas if len(horas) >= 2 else list(range(0, 24))

    print("\n  ── Motor de loop ───────────────────────────────")
    print(f"  DB:    {db_path}")
    print(f"  Horas: {horas_display}")
    print(f"  Loop:  {args.loop_secs}s | modalidad: {args.modalidad}")
    if filtros:
        for key, val in filtros.items():
            print(f"  Filtro {key}: {val}")
    segs = loop_engine.calcular_segmentos(horas_display, args.loop_secs)
    print(f"  Segmentos: {len(segs)}  (arco total = {sum(s['arco_horas'] for s in segs):.1f}h)")

    if args.dry_run:
        print("\n  [DRY-RUN] Configuración OK. No se generó el spec.")
        return

    spec = generar_loop(
        db_path=db_path,
        horas=horas_display,
        loop_secs=args.loop_secs,
        modalidad_ubicaciones=args.modalidad,
        filtros=filtros,
        salida=args.salida,
    )

    n_medios = len(spec["medios"])
    n_chiches = len(spec["chiches"])
    print(f"\n  Medios posicionados: {n_medios}")
    print(f"  Chiches generados:   {n_chiches}")
    print("\n  Segmentos:")
    for s in spec["segmentos"]:
        print(f"    seg {s['i']}: {s['from']:>4.0f}h → {s['to']:>4.0f}h "
              f"(arco {s['arco_horas']:.1f}h) t=[{s['t_start']:.1f}..{s['t_end']:.1f}]s")
    print(f"\n  Spec completa: {args.salida or '(en memoria)'}")
    if args.salida:
        print(f"  ✔ Guardado en: {args.salida}")


if __name__ == "__main__":
    main()