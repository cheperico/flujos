#!/usr/bin/env python3
"""
ingest_gpx.py — Ingesta de archivos GPX (tracks GPS) a la base de datos.

Tres funciones principales:
1. Almacena waypoints (puntos de interés) en la tabla `waypoints`
2. Registra el track en la tabla `tracks`
3. Backfill de altitud desde el track para medios existentes

Uso:
    python scripts/ingest_gpx.py --gpx tracks/Al_FaB_Tucuman.gpx
    python scripts/ingest_gpx.py --gpx tracks/mi_ruta.gpx --dry-run
    python scripts/ingest_gpx.py --gpx tracks/mi_ruta.gpx --no-altitude
    python scripts/ingest_gpx.py --gpx tracks/mi_ruta.gpx --mode replace
"""

import argparse
import logging
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_gpx")

NS_GPX = "http://www.topografix.com/GPX/1/1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolver_db(db_path: str | None = None) -> str:
    if db_path:
        return os.path.abspath(db_path)
    return os.path.join(os.path.dirname(__file__), "..", "db", "flujos.db")


def conectar(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _parse_timestamp(ts_str: str | None) -> str | None:
    """Normaliza timestamp ISO 8601 a formato SQLite (sin Z)."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except (ValueError, TypeError):
        return ts_str


# ---------------------------------------------------------------------------
# Parseo de GPX
# ---------------------------------------------------------------------------

def parsear_gpx(ruta: str) -> dict:
    """
    Parsea un archivo GPX 1.1 y devuelve un dict con:
        - name: str
        - source_url: str | None
        - waypoints: list[dict]
        - track_points: list[dict] (lat, lon, ele, time)
    """
    tree = ET.parse(ruta)
    root = tree.getroot()

    # Metadata
    meta = root.find(f"{{{NS_GPX}}}metadata")
    name = ""
    source_url = ""
    if meta is not None:
        n = meta.find(f"{{{NS_GPX}}}name")
        if n is not None and n.text:
            name = n.text
        link = meta.find(f"{{{NS_GPX}}}link")
        if link is not None:
            href = link.get("href", "")
            if href:
                source_url = href

    # Waypoints
    waypoints = []
    for wpt in root.findall(f"{{{NS_GPX}}}wpt"):
        lat = wpt.get("lat")
        lon = wpt.get("lon")
        if not lat or not lon:
            continue
        w = {
            "latitude": float(lat),
            "longitude": float(lon),
            "name": _tag_text(wpt, "name", ""),
            "description": _tag_text(wpt, "desc", ""),
            "category": _tag_text(wpt, "cmt", ""),
            "type": _tag_text(wpt, "type", ""),
            "timestamp": _parse_timestamp(_tag_text(wpt, "time", None)),
        }
        waypoints.append(w)

    # Track points
    track_points = []
    for trkpt in root.findall(f".//{{{NS_GPX}}}trkpt"):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if not lat or not lon:
            continue
        tp = {
            "latitude": float(lat),
            "longitude": float(lon),
            "elevation": _tag_float(trkpt, "ele"),
            "time": _parse_timestamp(_tag_text(trkpt, "time", None)),
        }
        track_points.append(tp)

    return {
        "name": name,
        "source_url": source_url or None,
        "waypoints": waypoints,
        "track_points": track_points,
    }


def _tag_text(parent, tag: str, default=None) -> str | None:
    el = parent.find(f"{{{NS_GPX}}}{tag}")
    if el is not None and el.text:
        return el.text.strip()
    return default


def _tag_float(parent, tag: str) -> float | None:
    el = parent.find(f"{{{NS_GPX}}}{tag}")
    if el is not None and el.text:
        try:
            return float(el.text.strip())
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def migrar_db(conn: sqlite3.Connection):
    """Crea las tablas tracks y waypoints si no existen."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracks (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL,
            filepath_absoluto TEXT NOT NULL,
            filepath_relativo TEXT NOT NULL,
            source_url        TEXT,
            start_time        TEXT,
            end_time          TEXT,
            total_points      INTEGER,
            ingested_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS waypoints (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id          INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
            name              TEXT NOT NULL,
            description       TEXT,
            category          TEXT,
            type              TEXT,
            latitude          REAL NOT NULL,
            longitude         REAL NOT NULL,
            timestamp         TEXT,
            ingested_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_waypoints_loc ON waypoints(latitude, longitude);
        CREATE INDEX IF NOT EXISTS idx_waypoints_track ON waypoints(track_id);
        CREATE INDEX IF NOT EXISTS idx_waypoints_type ON waypoints(type);
        CREATE INDEX IF NOT EXISTS idx_tracks_start ON tracks(start_time);
    """)
    conn.commit()


def registrar_track(conn, nombre: str, ruta_abs: str, ruta_rel: str,
                    source_url: str | None, start: str | None,
                    end: str | None, total_pts: int) -> int:
    cur = conn.execute(
        """INSERT INTO tracks (name, filepath_absoluto, filepath_relativo,
                               source_url, start_time, end_time, total_points)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (nombre, ruta_abs, ruta_rel, source_url, start, end, total_pts),
    )
    conn.commit()
    return cur.lastrowid


def insertar_waypoints(conn, track_id: int, waypoints: list[dict]):
    count = 0
    for w in waypoints:
        conn.execute(
            """INSERT INTO waypoints (track_id, name, description, category,
                                      type, latitude, longitude, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (track_id, w["name"], w["description"] or None,
             w["category"] or None, w["type"] or None,
             w["latitude"], w["longitude"], w["timestamp"]),
        )
        count += 1
    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Backfill de altitud desde track GPS
# ---------------------------------------------------------------------------

def backfill_altitud(conn, track_points: list[dict], mode: str = "skip",
                     dry_run: bool = False):
    """
    Asigna altitud a medios con GPS buscando el punto del track
    más cercano en el tiempo.
    """
    # Filtrar track points que tengan tiempo y elevación
    track_con_tiempo = [
        tp for tp in track_points
        if tp["time"] is not None and tp["elevation"] is not None
    ]
    if not track_con_tiempo:
        log.warning("  El track no tiene puntos con tiempo + elevación.")
        return 0

    # Convertir tiempos del track a objetos datetime para búsqueda binaria
    tiempos_track = []
    for tp in track_con_tiempo:
        try:
            dt = datetime.fromisoformat(tp["time"])
            tiempos_track.append((dt, tp["elevation"], tp["latitude"], tp["longitude"]))
        except (ValueError, TypeError):
            continue

    if len(tiempos_track) < 2:
        log.warning("  Muy pocos puntos track con tiempo válido.")
        return 0

    log.info("  Track con %d puntos con tiempo+elevación.", len(tiempos_track))

    # Obtener medios para backfill
    if mode == "replace":
        # Todos los medios con GPS, incluso los que ya tienen altitud
        rows = conn.execute("""
            SELECT id, timestamp_utc, latitude, longitude, altitude
            FROM media
            WHERE latitude IS NOT NULL AND timestamp_utc IS NOT NULL
            ORDER BY timestamp_utc
        """).fetchall()
        log.info("  Modo replace: procesando TODOS los %d medios con GPS.", len(rows))
    elif mode == "update":
        # Todos los medios con GPS (sobrescribe altitud)
        rows = conn.execute("""
            SELECT id, timestamp_utc, latitude, longitude, altitude
            FROM media
            WHERE latitude IS NOT NULL AND timestamp_utc IS NOT NULL
            ORDER BY timestamp_utc
        """).fetchall()
        log.info("  Modo update: actualizando altitud de %d medios.", len(rows))
    else:
        # skip: solo medios sin altitud
        rows = conn.execute("""
            SELECT id, timestamp_utc, latitude, longitude, altitude
            FROM media
            WHERE latitude IS NOT NULL AND timestamp_utc IS NOT NULL
              AND altitude IS NULL
            ORDER BY timestamp_utc
        """).fetchall()
        log.info("  Modo skip: %d medios sin altitud.", len(rows))

    if not rows:
        log.info("  No hay medios para backfill de altitud.")
        return 0

    # Para cada medio, buscar el punto track más cercano en el tiempo
    actualizados = 0
    sin_cobertura = 0
    errores = 0

    tiempos_arr = [t[0] for t in tiempos_track]

    import bisect

    for row in rows:
        mid = row["id"]
        ts = row["timestamp_utc"]
        try:
            dt_media = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            errores += 1
            continue

        # Búsqueda binaria del punto más cercano
        idx = bisect.bisect_left(tiempos_arr, dt_media)

        candidatos = []
        if idx < len(tiempos_arr):
            candidatos.append((abs(tiempos_arr[idx] - dt_media), idx))
        if idx > 0:
            candidatos.append((abs(tiempos_arr[idx - 1] - dt_media), idx - 1))

        if not candidatos:
            sin_cobertura += 1
            continue

        # Elegir el más cercano
        _, mejor_idx = min(candidatos, key=lambda x: x[0])
        _, alt, lat_track, lon_track = tiempos_track[mejor_idx]

        if dry_run:
            actualizados += 1
            continue

        conn.execute(
            "UPDATE media SET altitude = ?, geolocation_source = 'track_gps' WHERE id = ?",
            (alt, mid),
        )
        actualizados += 1

        # Reportar diferencias significativas
        alt_prev = row["altitude"]
        if alt_prev is not None and abs(alt_prev - alt) > 50:
            log.debug("  id=%d: altitud difiere %.0fm (era %.0f, ahora %.0f)",
                      mid, alt - alt_prev, alt_prev, alt)

    conn.commit()
    log.info("  Altitud actualizada: %d  |  Sin cobertura: %d  |  Errores: %d",
             actualizados, sin_cobertura, errores)
    return actualizados


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def reportar(conn, track_points: list[dict]):
    """Muestra un resumen de lo que hay en DB tras la ingesta."""
    cur = conn.execute("SELECT COUNT(*) FROM tracks")
    total_tracks = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM waypoints")
    total_wpts = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM media WHERE geolocation_source = 'track_gps'")
    alt_backfilled = cur.fetchone()[0]

    print()
    print("=" * 50)
    print("  RESUMEN TRAS INGESTA GPX")
    print("=" * 50)
    print(f"  Tracks en DB:          {total_tracks}")
    print(f"  Waypoints en DB:       {total_wpts}")
    print(f"  Medios con altitud:    {alt_backfilled} (via track_gps)")
    print(f"  Track points totales:  {len(track_points):,}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Ingerir archivo GPX (track GPS) a la base de datos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--gpx", required=True,
                        help="Ruta al archivo GPX")
    parser.add_argument("--db", default=None,
                        help="Ruta a la base de datos SQLite")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría, sin escribir")
    parser.add_argument("--mode", choices=["skip", "update", "replace"],
                        default="skip",
                        help="Modo para backfill de altitud (default: skip)")
    parser.add_argument("--no-altitude", action="store_true",
                        help="Omitir backfill de altitud")
    parser.add_argument("--no-waypoints", action="store_true",
                        help="Omitir ingesta de waypoints")

    args = parser.parse_args(argv)

    gpx_path = os.path.abspath(args.gpx)
    if not os.path.isfile(gpx_path):
        log.error("Archivo GPX no encontrado: %s", gpx_path)
        sys.exit(1)

    db_path = resolver_db(args.db)
    log.info("GPX:  %s", gpx_path)
    log.info("DB:   %s", db_path)

    # 1. Parsear GPX
    log.info("Parseando GPX...")
    try:
        datos = parsear_gpx(gpx_path)
    except ET.ParseError as e:
        log.error("Error parseando GPX: %s", e)
        sys.exit(1)

    nombre = datos["name"] or os.path.splitext(os.path.basename(gpx_path))[0]
    n_wpts = len(datos["waypoints"])
    n_trk = len(datos["track_points"])
    log.info('  Track: "%s"', nombre)
    log.info("  Waypoints: %d", n_wpts)
    log.info("  Track points: %d", n_trk)

    if datos["source_url"]:
        log.info("  Fuente: %s", datos["source_url"])

    # Rango temporal del track
    times_trk = [tp["time"] for tp in datos["track_points"] if tp["time"]]
    start_time = times_trk[0] if times_trk else None
    end_time = times_trk[-1] if times_trk else None
    if start_time and end_time:
        log.info("  Rango: %s → %s", start_time, end_time)

    # Resumen previo
    print()
    print("  Resumen de la operación:")
    print(f"    Waypoints a insertar:   {n_wpts}" if not args.no_waypoints else "    Waypoints: omitido")
    alt_mode = "ninguno" if args.no_altitude else args.mode
    print(f"    Backfill altitud:       modo {alt_mode}")
    if args.dry_run:
        print("    DRY RUN — no se escribirá nada")
    print()

    # 2. Conectar DB
    conn = conectar(db_path)
    migrar_db(conn)

    # 3. Registrar track
    if not args.dry_run:
        # Resolver ruta relativa al proyecto
        proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ruta_rel = os.path.relpath(gpx_path, proyecto)

        track_id = registrar_track(
            conn, nombre, gpx_path, ruta_rel,
            datos["source_url"], start_time, end_time, n_trk,
        )
        log.info("Track registrado en DB (id=%d)", track_id)
    else:
        track_id = None
        log.info("[DRY RUN] Track NO registrado")

    # 4. Insertar waypoints
    if not args.no_waypoints and datos["waypoints"]:
        if args.dry_run:
            log.info("[DRY RUN] Waypoints listos para insertar: %d", n_wpts)
            for w in datos["waypoints"]:
                print(f"    {w['name']:30s} | {w['category']:12s} | {w['type']:12s} | {w['latitude']:.6f}, {w['longitude']:.6f}")
        else:
            ok = insertar_waypoints(conn, track_id, datos["waypoints"])
            log.info("Waypoints insertados: %d", ok)
    else:
        log.info("Waypoints: omitido o no hay.")

    # 5. Backfill de altitud
    if not args.no_altitude and datos["track_points"]:
        backfill_altitud(conn, datos["track_points"], mode=args.mode, dry_run=args.dry_run)
    else:
        log.info("Backfill altitud: omitido.")

    # 6. Reporte final
    if not args.dry_run:
        reportar(conn, datos["track_points"])
    else:
        print()
        print("=" * 50)
        print("  DRY RUN COMPLETADO — no se modificó nada")
        print("=" * 50)

    conn.close()


if __name__ == "__main__":
    main()
