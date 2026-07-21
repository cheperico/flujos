#!/usr/bin/env python3
"""
migrate.py — Sistema centralizado de migraciones de schema para Flujos.

Cada versión del schema tiene un número y un conjunto de sentencias SQL.
`verificar_schema()` detecta en qué versión está la DB y aplica las
migraciones faltantes en orden.

Uso:
    from db.migrate import verificar_schema
    verificar_schema(conn)  # al abrir la conexión
"""

import logging
import sqlite3

log = logging.getLogger("migrate")

# Versión actual del schema (incrementar al agregar migraciones)
SCHEMA_VERSION = 2

# Migraciones: cada entrada es (versión, descripción, [sentencias SQL])
_MIGRACIONES = [
    (1, "Schema inicial: media, media_metadata, media_keypoints, config", [
        # Se crean con init_db() / schema.sql — no repetimos las sentencias
        # Esta migración solo marca la versión 1 como existente.
    ]),
    (2, "Tablas tracks y waypoints para GPX", [
        """
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
        )
        """,
        """
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
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_waypoints_loc ON waypoints(latitude, longitude)",
        "CREATE INDEX IF NOT EXISTS idx_waypoints_track ON waypoints(track_id)",
        "CREATE INDEX IF NOT EXISTS idx_waypoints_type ON waypoints(type)",
        "CREATE INDEX IF NOT EXISTS idx_tracks_start ON tracks(start_time)",
    ]),
]


def schema_version(conn: sqlite3.Connection) -> int:
    """Retorna la versión actual del schema (0 si no existe)."""
    try:
        cur = conn.execute("SELECT value FROM config WHERE key = 'schema_version'")
        row = cur.fetchone()
        if row:
            return int(row[0])
    except (sqlite3.OperationalError, ValueError, TypeError):
        pass
    return 0


def _set_version(conn: sqlite3.Connection, version: int):
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )
    conn.commit()


def verificar_schema(conn: sqlite3.Connection):
    """
    Verifica la versión del schema y aplica migraciones pendientes.
    Es seguro llamarlo múltiples veces (usa IF NOT EXISTS).
    """
    actual = schema_version(conn)
    if actual >= SCHEMA_VERSION:
        return

    if actual == 0:
        log.info("Schema sin versionar. Se asume versión 1 (schema.sql inicial).")
        _set_version(conn, 1)
        actual = 1

    for version, desc, sqls in _MIGRACIONES:
        if version <= actual:
            continue
        log.info("Migrando schema a versión %d: %s", version, desc)
        for sql in sqls:
            if sql.strip():
                conn.execute(sql)
        _set_version(conn, version)
        log.info("  → Versión %d aplicada.", version)
