#!/usr/bin/env python3
"""
fix_gps_sign.py — Repara el signo de coordenadas GPS con error histórico.

Contexto: Durante semanas las coordenadas GPS se guardaron con signo positivo
(lat=+31 en vez de -31) por un bug en el parseo de ExifTool sin -n.
El bug se corrigió en ingest.py pero los datos existentes quedaron con el
signo incorrecto.

Este script detecta coordenadas que caen dentro del bounding box de Argentina
pero tienen signo positivo, y las corrige (lat → -lat, lon → -lon).

Argentina bounding box (WGS84):
  Lat: -21.8 a -55.0
  Lon: -53.6 a -73.6
"""

import argparse
import logging
import os
import sqlite3
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fix_gps_sign")

# Bounding box de Argentina (aproximado)
ARG_BBOX = {
    "lat_min": -55.0,
    "lat_max": -21.8,
    "lon_min": -73.6,
    "lon_max": -53.6,
}


def _en_argentina(lat: float, lon: float) -> bool:
    """Verifica si una coordenada (positiva) caeria dentro de Argentina si se negativiza."""
    return (
        ARG_BBOX["lat_min"] <= -abs(lat) <= ARG_BBOX["lat_max"]
        and ARG_BBOX["lon_min"] <= -abs(lon) <= ARG_BBOX["lon_max"]
    )


def fix_gps_sign(db_path: str, dry_run: bool = False) -> int:
    """Corrige el signo de coordenadas GPS con valores positivos en Argentina."""
    if not os.path.isfile(db_path):
        log.error("Base de datos no encontrada: %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        # Buscar registros con latitud positiva
        rows = conn.execute("""
            SELECT id, latitude, longitude, altitude
            FROM media
            WHERE latitude IS NOT NULL
              AND latitude > 0
              AND longitude > 0
        """).fetchall()

        if not rows:
            log.info("No se encontraron coordenadas con signo positivo.")
            return 0

        # Filtrar solo las que caerian en Argentina si se negativizan
        a_corregir = []
        for row in rows:
            mid, lat, lon, alt = row
            if _en_argentina(lat, lon):
                a_corregir.append(row)
            else:
                log.warning(
                    "  #%d (lat=%.6f, lon=%.6f) no parece Argentina, se omite.",
                    mid, lat, lon,
                )

        if not a_corregir:
            log.info("Ninguna coordenada positiva cae dentro del bounding box de Argentina.")
            return 0

        log.info(
            "Coordenadas a corregir: %d (de %d positivas totales)",
            len(a_corregir), len(rows),
        )

        if dry_run:
            log.info("=== MODO DRY-RUN ===")
            for mid, lat, lon, alt in a_corregir[:10]:
                log.info("  #%d: lat %.6f → %.6f | lon %.6f → %.6f",
                         mid, lat, -lat, lon, -lon)
            if len(a_corregir) > 10:
                log.info("  ... y %d mas.", len(a_corregir) - 10)
            return 0

        # Corregir
        conn.execute("BEGIN TRANSACTION")
        for mid, lat, lon, alt in a_corregir:
            conn.execute("""
                UPDATE media
                SET latitude = -?,
                    longitude = -?,
                    altitude = NULLIF(?, 0),
                    geolocation_source = 'metadata_corregido',
                    provincia = NULL,
                    departamento = NULL,
                    municipio = NULL,
                    localidad = NULL,
                    geocode_source = NULL,
                    geocode_date = NULL,
                    distance_from_prev_m = NULL,
                    elevation_gain_m = NULL,
                    gradient_pct = NULL,
                    cumul_distance_m = NULL,
                    cumul_elevation_gain_m = NULL
                WHERE id = ?
            """, (abs(lat), abs(lon), alt, mid))
        conn.commit()

        log.info("Corregidas %d coordenadas.", len(a_corregir))
        log.info("Tambien se limpiaron provincia y gradientes previos para reprocesar.")
        return len(a_corregir)

    finally:
        conn.close()


def main(argv: list[str] = None):
    parser = argparse.ArgumentParser(
        description="Corrige el signo de coordenadas GPS con error historico (signo positivo en Argentina).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/fix_gps_sign.py
  python scripts/fix_gps_sign.py --db db/flujos.db --dry-run
  python scripts/fix_gps_sign.py --dry-run
        """,
    )
    parser.add_argument("--db", default=None,
                        help="Ruta a la base de datos SQLite")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra que se corregiria sin modificar")

    args = parser.parse_args(argv)

    db_path = args.db
    if not db_path:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        db_path = os.path.join(project_root, "db", "flujos.db")

    fix_gps_sign(db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
