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
SCHEMA_VERSION = 3

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
    (3, "Schema canónico para media_embeddings: UNIQUE(media_id, modelo) en vez de media_id PK", [
        # Callable: maneja tabla existente y DB nueva
        lambda conn: _migrar_media_embeddings(conn),
    ]),
]


def _migrar_media_embeddings(conn: sqlite3.Connection):
    """
    Migración v3: unifica el schema de media_embeddings.

    - Si la tabla ya existe (creada por generate_embeddings.py viejo):
      recrea con UNIQUE(media_id, modelo) y ON DELETE CASCADE.
    - Si no existe (DB nueva): crea directamente el schema canónico.
    """
    # Verificar si la tabla existe
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='media_embeddings'"
    )
    tabla_existe = cur.fetchone() is not None

    if not tabla_existe:
        # DB nueva: crear con schema canónico directamente
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media_embeddings (
                media_id    INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                embedding   BLOB NOT NULL,
                modelo      TEXT NOT NULL DEFAULT 'nomic-embed-text',
                fecha       TEXT DEFAULT (datetime('now')),
                UNIQUE(media_id, modelo)
            )
        """)
        log.info("  → Creada tabla media_embeddings (schema canónico, DB nueva)")
        return

    # Tabla existe: migrar datos del schema viejo al nuevo
    # Schema viejo: media_id INTEGER PRIMARY KEY, media_id_ref, embedding, modelo, fecha
    # Schema nuevo: media_id INTEGER NOT NULL, embedding, modelo, fecha, UNIQUE(media_id, modelo)
    log.info("  → Migrando tabla media_embeddings existente al schema canónico...")
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("""
        CREATE TABLE media_embeddings_nuevo (
            media_id    INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
            embedding   BLOB NOT NULL,
            modelo      TEXT NOT NULL DEFAULT 'nomic-embed-text',
            fecha       TEXT DEFAULT (datetime('now')),
            UNIQUE(media_id, modelo)
        )
    """)
    conn.execute("""
        INSERT INTO media_embeddings_nuevo (media_id, embedding, modelo, fecha)
        SELECT media_id, embedding, COALESCE(modelo, 'nomic-embed-text'), COALESCE(fecha, datetime('now'))
        FROM media_embeddings
    """)
    conn.execute("DROP TABLE media_embeddings")
    conn.execute("ALTER TABLE media_embeddings_nuevo RENAME TO media_embeddings")
    conn.execute("PRAGMA foreign_keys=ON")
    log.info("  → Migración de media_embeddings completada: %s registros migrados",
             conn.execute("SELECT COUNT(*) FROM media_embeddings").fetchone()[0])



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

    for version, desc, acciones in _MIGRACIONES:
        if version <= actual:
            continue
        log.info("Migrando schema a versión %d: %s", version, desc)
        for accion in acciones:
            if callable(accion):
                accion(conn)
            elif isinstance(accion, str) and accion.strip():
                conn.execute(accion)
        _set_version(conn, version)
        log.info("  → Versión %d aplicada.", version)
