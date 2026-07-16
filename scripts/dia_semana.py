#!/usr/bin/env python3
"""
dia_semana.py — Calcula el día de la semana de cada medio a partir
de su timestamp_utc y lo guarda en media_metadata.

Los días se guardan en español: lunes, martes, miércoles, jueves,
viernes, sábado, domingo.

Sirve para agrupar medios por día de la semana sin importar la fecha
(todos los lunes con los lunes, etc.).

Uso:
    python scripts/dia_semana.py                              # Pendientes
    python scripts/dia_semana.py --db db/flujos.db            # DB específica
    python scripts/dia_semana.py --dry-run                    # Solo simular
    python scripts/dia_semana.py --replace                    # Recalcular todos
"""

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dia_semana")

# Días de la semana en español
# datetime.weekday(): 0=lunes, 1=martes, ..., 6=domingo
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


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


def parsear_timestamp(ts: str | None) -> datetime | None:
    """Parsea timestamp_utc desde la DB (ISO 8601 o SQLite datetime)."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None


# ── Procesamiento ────────────────────────────────────────────────────────────

def procesar(
    db_path: str,
    dry_run: bool = False,
    replace: bool = False,
    limit: int | None = None,
):
    conn = conectar(db_path)

    # Obtener medios con timestamp_utc
    if replace:
        query = """
            SELECT id, timestamp_utc FROM media
            WHERE timestamp_utc IS NOT NULL
            ORDER BY id
        """
        rows = conn.execute(query).fetchall()
        log.info("Modo --replace: procesando TODOS los medios con timestamp (%d)", len(rows))
    else:
        query = """
            SELECT m.id, m.timestamp_utc FROM media m
            WHERE m.timestamp_utc IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM media_metadata mm
                  WHERE mm.media_id = m.id AND mm.key = 'dia_semana'
              )
            ORDER BY m.id
        """
        rows = conn.execute(query).fetchall()
        log.info("Medios sin dia_semana: %d", len(rows))

    if not rows:
        log.info("No hay medios para procesar.")
        conn.close()
        return

    if limit:
        rows = rows[:limit]
        log.info("  Limitado a %d registros.", limit)

    ok = 0
    skip = 0
    resultados: dict[str, int] = {}  # contador por día

    for row in rows:
        media_id = row["id"]
        ts = row["timestamp_utc"]

        dt = parsear_timestamp(ts)
        if dt is None:
            skip += 1
            continue

        dia = DIAS[dt.weekday()]
        resultados[dia] = resultados.get(dia, 0) + 1

        if dry_run:
            ok += 1
            continue

        if replace:
            conn.execute(
                "DELETE FROM media_metadata WHERE media_id = ? AND key = 'dia_semana'",
                (media_id,),
            )

        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
            (media_id, "dia_semana", dia),
        )
        ok += 1

    if not dry_run:
        conn.commit()

    # Reporte
    log.info("=" * 40)
    log.info("RESUMEN:")
    log.info("  Procesados: %d", ok)
    if skip:
        log.info("  Saltados (timestamp inválido): %d", skip)
    if resultados:
        log.info("")
        log.info("  Distribución por día:")
        for dia in DIAS:
            if dia in resultados:
                log.info("    %-10s → %d", dia.capitalize(), resultados[dia])

    conn.close()


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Calcular día de la semana de cada medio desde su timestamp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", help="Ruta a la base de datos SQLite")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo simular, no guardar",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="[DEPRECATED: usar --mode replace] Recalcular todos, incluso los ya procesados",
    )
    parser.add_argument(
        "--mode", default="skip", choices=["skip", "update", "replace"],
        help="Modo: skip (solo pendientes), update (todos), replace (limpiar y regenerar)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limitar cantidad de medios a procesar",
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
    procesar(
        db_path=db_path,
        dry_run=args.dry_run,
        replace=replace,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
