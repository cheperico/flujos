#!/usr/bin/env python3
"""
keypoints_video.py — Genera keypoints semánticos a partir del análisis de video.

Para cada video con `video_analysis` en media_metadata (generado por
analyze_video.py), recorre las escenas detectadas y escribe en
`media_keypoints`:

    - Por cada escena con keywords:
        key   = 'escena'
        value = keywords de la escena (coma separada)
        timestamp_offset_secs = inicio de la escena
        timestamp_absolute    = timestamp_utc + offset
        source = 'ollama'

    - Por cada keyword de la escena:
        key   = 'keyword'
        value = keyword individual
        timestamp_offset_secs = inicio de la escena
        timestamp_absolute    = timestamp_utc + offset
        source = 'ollama'

Esto permite buscar "cuándo aparece X en el video" consultando
media_keypoints por key='keyword' y value='X'.

NO toca los keypoints de transcripción (key='transcription', source='whisper'):
esa lógica vive en improve_db.run_keypoints y queda intacta.

Uso:
    python scripts/ai_media/keypoints_video.py                  # skip: solo pendientes
    python scripts/ai_media/keypoints_video.py --mode update    # regenera todos
    python scripts/ai_media/keypoints_video.py --mode replace   # limpia y regenera
    python scripts/ai_media/keypoints_video.py --dry-run        # previsualiza sin escribir

Modos:
    skip    → solo videos con video_analysis que aún no tienen keypoints de
              escena ni sentinel de procesado (keypoints_video_estado = ok | sin_datos)
    update  → regenera keypoints de escena/keyword para TODOS los videos con análisis
    replace → limpia keypoints de escena/keyword existentes y regenera
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.util import abrir, resolver_db

# Claves que maneja este script (para limpiar en update/replace)
KEY_VIDEO_ANALYSIS = "video_analysis"
KEY_ESCENA = "escena"
KEY_KEYWORD = "keyword"
SOURCE = "ollama"

# Sentinel de procesado en media_metadata (M1): evita reprocesar en skip los
# videos que producen cero keypoints (escenas sin keywords / sin timestamp).
KEY_ESTADO = "keypoints_video_estado"
ESTADO_OK = "ok"
ESTADO_SIN_DATOS = "sin_datos"


def _normalizar_ts_utc(ts_utc: str) -> datetime:
    """Normaliza un timestamp_utc (aware) a datetime aware UTC.

    Args:
        ts_utc: Timestamp en ISO (puede terminar en Z o ser naive).

    Returns:
        datetime aware UTC.
    """
    ts = ts_utc.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _consultar_videos_con_analisis(
    conn: sqlite3.Connection, mode: str
) -> list[tuple[int, str, str]]:
    """Lista videos con video_analysis según el modo.

    Args:
        conn: Conexión abierta a la DB.
        mode: "skip" | "update" | "replace".

    Returns:
        Lista de (media_id, timestamp_utc, analysis_json).
    """
    # Configurar row_factory para acceso por nombre (idempotente)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT m.id, m.timestamp_utc, mm.value AS analysis_json
        FROM media m
        JOIN media_metadata mm ON mm.media_id = m.id AND mm.key = ?
    """
    params: list = [KEY_VIDEO_ANALYSIS]

    if mode == "skip":
        query += """
            WHERE m.id NOT IN (
                SELECT DISTINCT media_id FROM media_keypoints
                WHERE key IN (?, ?)
            )
            AND m.id NOT IN (
                SELECT media_id FROM media_metadata
                WHERE key = '""" + KEY_ESTADO + """'
                  AND value IN ('""" + ESTADO_OK + """', '""" + ESTADO_SIN_DATOS + """')
            )
        """
        params += [KEY_ESCENA, KEY_KEYWORD]

    return conn.execute(query, params).fetchall()


def _escenas_desde_analisis(analysis: str) -> list[dict]:
    """Parsea el JSON de video_analysis y devuelve las escenas con keywords.

    Soportado el formato actual (dict con "escenas") y el legacy
    (array plano de fotogramas sin escenas → lista vacía).

    Args:
        analysis: JSON de media_metadata (video_analysis).

    Returns:
        Lista de dicts de escena (los que tienen keywords no vacías).
    """
    try:
        data = json.loads(analysis)
    except (json.JSONDecodeError, TypeError):
        return []

    escenas = data.get("escenas", []) if isinstance(data, dict) else []
    return [e for e in escenas if e.get("keywords")]


def _generar_batch(media_id: int, ts_utc: str, analysis: str) -> list[tuple]:
    """Genera los keypoints de video para un medio.

    Args:
        media_id: ID del medio.
        ts_utc: timestamp_utc del medio (puede ser None).
        analysis: JSON de video_analysis.

    Returns:
        Lista de tuplas (media_id, offset, ts_abs, key, value, source).
        Vacía si no hay escenas con keywords o falta timestamp_utc.
    """
    escenas = _escenas_desde_analisis(analysis)
    if not escenas:
        return []

    if not ts_utc:
        log.warning("  media id=%s tiene video_analysis pero no timestamp_utc; skip.", media_id)
        return []

    dt_base = _normalizar_ts_utc(ts_utc)
    batch: list[tuple] = []

    for escena in escenas:
        offset = float(escena.get("inicio", 0.0))
        keywords = escena.get("keywords", [])
        keywords_limpias = [k.strip() for k in keywords if k and k.strip()]
        if not keywords_limpias:
            continue

        ts_abs = (dt_base + timedelta(seconds=offset)).isoformat()

        # Keypoint por escena: keywords agregadas
        batch.append((
            media_id, offset, ts_abs,
            KEY_ESCENA, ", ".join(keywords_limpias), SOURCE,
        ))

        # Keypoint por keyword individual (para buscar "cuándo aparece X")
        for kw in keywords_limpias:
            batch.append((
                media_id, offset, ts_abs,
                KEY_KEYWORD, kw, SOURCE,
            ))

    return batch


def main(argv: list[str] | None = None) -> int:
    """Entry point para keypoints semánticos de video.

    Args:
        argv: Lista de argumentos (sin el nombre del script).

    Returns:
        Código de salida (0 = ok, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Genera keypoints semánticos de video (escenas y keywords) "
                    "en media_keypoints a partir de video_analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None,
                        help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="skip: solo pendientes (default) | update: regenera todos | "
                             "replace: limpia y regenera")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo previsualizar sin escribir")
    parser.add_argument("--verbose", action="store_true",
                        help="Log detallado")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("No existe la DB: %s", db_path)
        return 1

    conn = abrir(db_path)
    conn.row_factory = sqlite3.Row

    # ── Limpiar en replace (y update: regenerar todo) ──
    if args.mode in ("replace", "update"):
        conn.execute(
            "DELETE FROM media_keypoints WHERE key IN (?, ?)",
            (KEY_ESCENA, KEY_KEYWORD),
        )
        conn.commit()
        log.info("  [%s] Limpiados keypoints %s/%s de la DB.",
                 args.mode, KEY_ESCENA, KEY_KEYWORD)
    if args.mode == "replace":
        conn.execute("DELETE FROM media_metadata WHERE key = ?", (KEY_ESTADO,))
        conn.commit()

    # ── Listar videos con análisis ──
    rows = _consultar_videos_con_analisis(conn, args.mode)
    if not rows:
        print("  No hay videos con video_analysis para procesar (mode=%s)." % args.mode)
        conn.close()
        return 0

    log.info("  Videos con análisis: %d (mode=%s)", len(rows), args.mode)

    # ── Dry-run ──
    if args.dry_run:
        total_escenas = 0
        total_keypoints = 0
        print("\n  [DRY-RUN] Videos a procesar (máx 10):")
        for r in rows[:10]:
            escenas = _escenas_desde_analisis(r["analysis_json"])
            batch = _generar_batch(r["id"], r["timestamp_utc"], r["analysis_json"])
            n_escenas = len(escenas)
            n_kp = len(batch)
            total_escenas += n_escenas
            total_keypoints += n_kp
            print(f"  media {r['id']} — {n_escenas} escenas con keywords, "
                  f"{n_kp} keypoints a escribir")
        for r in rows[10:]:
            batch = _generar_batch(r["id"], r["timestamp_utc"], r["analysis_json"])
            total_escenas += len(_escenas_desde_analisis(r["analysis_json"]))
            total_keypoints += len(batch)
        print(f"\n  Total: {len(rows)} videos, {total_escenas} escenas, "
              f"{total_keypoints} keypoints")
        conn.close()
        return 0

    # ── Generar y escribir keypoints ──
    inserted = 0
    errores = 0
    for r in rows:
        try:
            batch = _generar_batch(r["id"], r["timestamp_utc"], r["analysis_json"])
            if not batch:
                # M1: sentinel para no reprocesar en skip (cero keypoints)
                conn.execute(
                    "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
                    "VALUES (?, ?, ?)",
                    (r["id"], KEY_ESTADO, ESTADO_SIN_DATOS),
                )
                continue
            conn.executemany(
                "INSERT INTO media_keypoints "
                "(media_id, timestamp_offset_secs, timestamp_absolute, key, value, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )
            conn.execute(
                "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
                "VALUES (?, ?, ?)",
                (r["id"], KEY_ESTADO, ESTADO_OK),
            )
            inserted += len(batch)
        except Exception as e:
            log.warning("  ⚠ Error generando keypoints para media id=%s: %s", r["id"], e)
            errores += 1

    conn.commit()
    log.info("  ✅ Keypoints de video insertados: %d  |  Errores: %d", inserted, errores)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
