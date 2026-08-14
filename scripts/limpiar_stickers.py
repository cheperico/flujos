#!/usr/bin/env python3
"""
limpiar_stickers.py — Eliminar stickers de Telegram mal ingeridos en la tabla media.

Los stickers son decoración del chat: deben permanecer en telegram_messages /
telegram_media (documentan la conversación) pero NUNCA entrar en la tabla media
(que alimenta el pipeline de enriquecimiento: colores, transcripción, clima,
reproducción TouchDesigner, etc.).

Este script de limpieza puntual detecta los medios de la tabla media vinculados
desde una fila telegram_media con media_type='sticker' y los elimina de media,
sus tablas hijas (media_embeddings, media_metadata, media_keypoints) y
desvincula telegram_media.media_id (preservando el registro del chat).
Antes de escribir crea un backup automático en db/backups/.

Uso:
    python scripts/limpiar_stickers.py --dry-run    # previsualizar (sin escribir)
    python scripts/limpiar_stickers.py              # limpieza real (con backup)
    python scripts/limpiar_stickers.py -v --db otra.db

Args:
    --db          Ruta a la base de datos (default: db/flujos.db)
    --dry-run     Solo previsualizar, no escribir en DB
    --verbose / -v  Verbose
"""

import argparse
import datetime
import logging
import os
import shutil
import sqlite3
import sys

# ── Path fix para ejecución standalone ────────────────────────────────
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.util import abrir, resolver_db

log = logging.getLogger("limpiar_stickers")

# Medios ingeridos desde un sticker de Telegram (vínculo telegram_media → media)
QUERY_STICKERS_INGERIDOS = """
SELECT DISTINCT m.id, m.filename_original, m.filepath_absoluto, m.type
FROM media m
JOIN telegram_media tgm ON tgm.media_id = m.id
WHERE tgm.media_type = 'sticker'
ORDER BY m.id
"""


def detectar_stickers_ingeridos(conn: sqlite3.Connection) -> list[tuple]:
    """
    Devuelve los medios de la tabla media que llegaron desde un sticker
    de telegram_media (media_type='sticker').
    """
    return conn.execute(QUERY_STICKERS_INGERIDOS).fetchall()


def crear_backup(db_path: str) -> str:
    """
    Crea backup automático con timestamp en db/backups/ y devuelve su ruta.
    """
    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"flujos_auto_{ts}.db")
    shutil.copy2(db_path, backup_path)
    return backup_path


def limpiar_media_sticker(conn: sqlite3.Connection, media_id: int) -> int:
    """
    Desvincula y elimina un medio sticker de la DB.

    Orden seguro por foreign keys: primero se desvincula telegram_media.media_id
    (preserva el registro del chat), luego se borran las tablas hijas y por
    último la fila de media.
    Devuelve la cantidad de filas telegram_media desvinculadas.
    """
    # Desvincular telegram_media → media (el registro del chat queda intacto)
    cur = conn.execute(
        "UPDATE telegram_media SET media_id = NULL WHERE media_id = ?", (media_id,)
    )
    desvinculadas = cur.rowcount

    # Tablas hijas
    conn.execute("DELETE FROM media_embeddings WHERE media_id = ?", (media_id,))
    conn.execute("DELETE FROM media_metadata WHERE media_id = ?", (media_id,))
    conn.execute("DELETE FROM media_keypoints WHERE media_id = ?", (media_id,))

    # Eliminar el medio
    conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
    return desvinculadas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Eliminar stickers de Telegram mal ingeridos en la tabla media",
    )
    parser.add_argument("--db", help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo previsualizar, no escribir en DB",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Modo verbose")
    args = parser.parse_args(argv)

    nivel = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=nivel, format="%(levelname)s %(message)s", stream=sys.stderr)

    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("Base de datos no encontrada: %s", db_path)
        sys.exit(1)

    conn = abrir(db_path)
    try:
        stickers = detectar_stickers_ingeridos(conn)

        if not stickers:
            log.info("No hay stickers ingeridos en media: nada para limpiar.")
            return 0

        log.info("Stickers ingeridos en media detectados: %d", len(stickers))

        if args.dry_run:
            log.info("── DRY RUN (no se escribe nada) ──")
            for mid, filename, filepath, tipo in stickers:
                log.info("  [media id=%d] %s (%s)", mid, filename, tipo)
                log.debug("    ruta: %s", filepath)
            log.info(
                "Se eliminarían %d filas de media (más tablas hijas y vínculos telegram_media).",
                len(stickers),
            )
            return 0

        # Backup automático antes de la limpieza (destructiva)
        backup_path = crear_backup(db_path)
        log.info("Backup automático creado: %s", os.path.basename(backup_path))

        # Nota de consistencia: media con nombre de sticker que NO viene de
        # telegram_media (no debería existir; solo se informa, no se borra)
        huerfanos = conn.execute(
            """
            SELECT m.id, m.filename_original
            FROM media m
            WHERE (m.filename_original LIKE 'sticker%'
                   OR m.filename_original LIKE 'AnimatedSticker%')
              AND m.id NOT IN (SELECT media_id FROM telegram_media WHERE media_id IS NOT NULL)
            """
        ).fetchall()
        if huerfanos:
            log.info(
                "Nota de consistencia: %d media con nombre de sticker no vinculados "
                "a telegram_media (no se tocan):",
                len(huerfanos),
            )
            for mid, filename in huerfanos:
                log.info("  [media id=%d] %s", mid, filename)
        else:
            log.info(
                "Nota de consistencia: no hay media con nombre de sticker "
                "sin vínculo a telegram_media."
            )

        total_desvinculadas = 0
        for mid, filename, filepath, tipo in stickers:
            desvinculadas = limpiar_media_sticker(conn, mid)
            total_desvinculadas += desvinculadas
            # Commit por fila (consistente con import_telegram.py: no perder progreso)
            conn.commit()
            log.info(
                "  Eliminado media id=%d (%s); telegram_media desvinculadas: %d",
                mid,
                filename,
                desvinculadas,
            )

        log.info("")
        log.info("Resumen de limpieza:")
        log.info("  Media eliminados:      %d", len(stickers))
        log.info("  telegram_media desvinculadas: %d", total_desvinculadas)
        log.info("  Backup:                %s", backup_path)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    main()
