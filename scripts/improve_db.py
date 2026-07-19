#!/usr/bin/env python3
"""
improve_db.py — Mejora la base de datos de Flujos con pasos de post-procesamiento.

Uso:
    python scripts/improve_db.py                          # Todos los pasos (modo skip)
    python scripts/improve_db.py --all                    # Ídem
    python scripts/improve_db.py --list                   # Listar pasos disponibles
    python scripts/improve_db.py --steps colors,keywords  # Solo esos pasos
    python scripts/improve_db.py --mode update            # Re-ejecutar y actualizar
    python scripts/improve_db.py --mode replace           # Borrar y regenerar
    python scripts/improve_db.py --db ruta/a/flujos.db    # DB personalizada

Modos:
    skip    (default) Saltar medios que ya tienen el dato procesado
    update  Re-ejecutar el paso (actualiza lo existente)
    replace Borra todo lo generado por el paso y lo regenera desde cero

Pasos:
    colors        Extraer colores dominantes de imágenes
    keywords      Etiquetar imágenes con IA (Ollama)
    descriptions  Describir imágenes con IA (Ollama)
    transcribe    Transcribir audios/videos (faster-whisper)
    keypoints     Poblar media_keypoints desde transcripciones
    timestamps    Inferir timestamps faltantes por clúster + orden
    gps           Inferir GPS desde medios cercanos en el tiempo
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

from tqdm import tqdm

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("improve_db")

# ── Helpers ──────────────────────────────────────────────────────────────────

def conectar(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def resolver_db(db_path: str | None) -> str:
    if db_path:
        return os.path.abspath(db_path)
    return os.path.join(os.path.dirname(__file__), "..", "db", "flujos.db")


# ==============================================================================
# CHECK: determinar cuánto trabajo pendiente hay para cada paso
# ==============================================================================

def check_colors(conn) -> dict:
    """Cuenta imágenes que faltan procesar."""
    total = conn.execute("SELECT COUNT(*) FROM media WHERE type='image'").fetchone()[0]
    pendientes = conn.execute(
        "SELECT COUNT(*) FROM media WHERE type='image' AND color_1_hex IS NULL"
    ).fetchone()[0]
    return {"total": total, "pendientes": pendientes, "hecho": total - pendientes}


def check_keywords(conn) -> dict:
    """Cuenta imágenes sin keywords en media_metadata."""
    total = conn.execute("SELECT COUNT(*) FROM media WHERE type='image'").fetchone()[0]
    pendientes = conn.execute("""
        SELECT COUNT(*) FROM media m
        WHERE m.type='image'
          AND NOT EXISTS (
              SELECT 1 FROM media_metadata mm
              WHERE mm.media_id = m.id AND mm.key = 'ia_keywords'
          )
    """).fetchone()[0]
    return {"total": total, "pendientes": pendientes, "hecho": total - pendientes}


def check_descriptions(conn) -> dict:
    """Cuenta imágenes sin descripción en media_metadata."""
    total = conn.execute("SELECT COUNT(*) FROM media WHERE type='image'").fetchone()[0]
    pendientes = conn.execute("""
        SELECT COUNT(*) FROM media m
        WHERE m.type='image'
          AND NOT EXISTS (
              SELECT 1 FROM media_metadata mm
              WHERE mm.media_id = m.id AND mm.key = 'ia_description'
          )
    """).fetchone()[0]
    return {"total": total, "pendientes": pendientes, "hecho": total - pendientes}


def check_transcribe(conn) -> dict:
    """Cuenta videos/audios sin transcripción en media_metadata."""
    total = conn.execute(
        "SELECT COUNT(*) FROM media WHERE type IN ('video', 'audio')"
    ).fetchone()[0]
    pendientes = conn.execute("""
        SELECT COUNT(*) FROM media m
        WHERE m.type IN ('video', 'audio')
          AND NOT EXISTS (
              SELECT 1 FROM media_metadata mm
              WHERE mm.media_id = m.id AND mm.key = 'whisper_segments'
          )
    """).fetchone()[0]
    return {"total": total, "pendientes": pendientes, "hecho": total - pendientes}


def check_keypoints(conn) -> dict:
    """Cuenta transcripciones que aún no tienen keypoints."""
    # Medios que tienen transcripciones en media_metadata
    transcritos = conn.execute("""
        SELECT COUNT(*) FROM media m
        WHERE EXISTS (
            SELECT 1 FROM media_metadata mm
            WHERE mm.media_id = m.id AND mm.key = 'whisper_segments'
        )
    """).fetchone()[0]
    # De esos, cuántos ya tienen keypoints
    con_kp = conn.execute("""
        SELECT COUNT(DISTINCT media_id) FROM media_keypoints
    """).fetchone()[0]
    return {"total": transcritos, "pendientes": transcritos - con_kp, "hecho": con_kp}


def check_timestamps(conn) -> dict:
    """Cuenta medios con timestamp inferido o fallback (mejorables)."""
    total = conn.execute(
        "SELECT COUNT(*) FROM media WHERE timestamp_utc IS NOT NULL"
    ).fetchone()[0]
    # Los que tienen timestamp_utc pero vía fallback (modified_at) o están NULL
    mejorables = conn.execute("""
        SELECT COUNT(*) FROM media
        WHERE timestamp_utc IS NULL
           OR timezone_note LIKE '%fallback%'
           OR timezone_note LIKE '%no se pudo%'
    """).fetchone()[0]
    return {"total": total, "pendientes": mejorables, "hecho": total - mejorables}


def check_gps(conn) -> dict:
    """Cuenta medios sin GPS."""
    total = conn.execute(
        "SELECT COUNT(*) FROM media WHERE type IN ('image', 'video')"
    ).fetchone()[0]
    pendientes = conn.execute("""
        SELECT COUNT(*) FROM media
        WHERE type IN ('image', 'video')
          AND latitude IS NULL
    """).fetchone()[0]
    return {"total": total, "pendientes": pendientes, "hecho": total - pendientes}


# ==============================================================================
# RUN: ejecución de cada paso
# ==============================================================================

def run_colors(conn, db_path, mode, stats):
    """
    Extrae colores dominantes de imágenes que aún no los tienen.
    Re-implementación local para evitar el bug de webcolors en ingest.py.
    """
    log.info("Paso: colors — Extrayendo colores dominantes")

    from color_utils import extract_dominant_colors, get_color_names

    # Determinar qué imágenes procesar según modo
    if mode == "replace":
        conn.execute("""
            UPDATE media SET
                color_1_hex = NULL, color_1_name_css = NULL, color_1_name_basic = NULL,
                color_2_hex = NULL, color_2_name_css = NULL, color_2_name_basic = NULL,
                color_3_hex = NULL, color_3_name_css = NULL, color_3_name_basic = NULL
            WHERE type='image'
        """)
        conn.commit()
        query = "SELECT id, filepath_absoluto FROM media WHERE type='image'"
    elif mode == "update":
        query = "SELECT id, filepath_absoluto FROM media WHERE type='image'"
    else:  # skip
        query = """
            SELECT id, filepath_absoluto FROM media
            WHERE type='image' AND color_1_hex IS NULL
        """

    rows = conn.execute(query).fetchall()
    if not rows:
        log.info("  No hay imágenes pendientes.")
        return

    ok = 0
    errors = 0
    for mid, fpath in tqdm(rows, desc="  Colores", unit="img", ncols=80):
        if not os.path.isfile(fpath):
            log.warning("  Archivo no encontrado: %s", fpath)
            stats["warnings"] += 1
            continue
        try:
            colors = extract_dominant_colors(fpath, n_colors=3)
            for i, hex_color in enumerate(colors, 1):
                name_css, name_basic = get_color_names(hex_color)
                conn.execute(
                    f"UPDATE media SET color_{i}_hex=?, color_{i}_name_css=?, "
                    f"color_{i}_name_basic=? WHERE id=?",
                    (hex_color, name_css, name_basic, mid),
                )
            ok += 1
        except Exception as e:
            log.debug("  Error en media id=%s: %s", mid, e)
            errors += 1

    conn.commit()
    log.info("  ✅ Colores extraídos: %d  |  Errores: %d", ok, errors)
    stats["colors_ok"] = ok
    stats["colors_err"] = errors


def run_keywords(conn, db_path, mode, stats):
    """Etiqueta imágenes con IA (Ollama)."""
    log.info("Paso: keywords — Etiquetando imágenes con IA")

    # Determinar imágenes a procesar
    if mode == "replace":
        conn.execute("DELETE FROM media_metadata WHERE key = 'ia_keywords'")
        conn.commit()
        query = "SELECT id, filepath_absoluto FROM media WHERE type='image'"
    elif mode == "update":
        query = "SELECT id, filepath_absoluto FROM media WHERE type='image'"
    else:  # skip
        query = """
            SELECT m.id, m.filepath_absoluto FROM media m
            WHERE m.type='image'
              AND NOT EXISTS (
                  SELECT 1 FROM media_metadata mm
                  WHERE mm.media_id = m.id AND mm.key = 'ia_keywords'
              )
        """

    rows = conn.execute(query).fetchall()
    if not rows:
        log.info("  No hay imágenes pendientes.")
        return

    try:
        from scripts.ai_media.image_analysis import extraer_keywords, MODELO_VISION_DEFAULT
    except ImportError:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from scripts.ai_media.image_analysis import extraer_keywords, MODELO_VISION_DEFAULT
        except ImportError as e:
            log.error("  No se pudo importar extraer_keywords: %s", e)
            log.error("  Asegurate de que scripts/ai_media/image_analysis.py existe.")
            stats["errors"] += 1
            return

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _process_one(mid, fpath):
        if not os.path.isfile(fpath):
            return "warning", fpath
        try:
            keywords = extraer_keywords(fpath, modelo=MODELO_VISION_DEFAULT)
            return "ok", (mid, keywords)
        except Exception as e:
            return "error", (fpath, e)

    ok = 0
    errors = 0
    warnings = 0
    batch = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_process_one, mid, fpath): (mid, fpath)
                   for mid, fpath in rows}
        for f in tqdm(as_completed(futures), total=len(futures),
                      desc="  Keywords", unit="img", ncols=80):
            result, data = f.result()
            if result == "warning":
                log.warning("  Archivo no encontrado: %s", data)
                warnings += 1
            elif result == "ok":
                mid, keywords = data
                if keywords:
                    batch.append((mid, keywords if isinstance(keywords, str)
                                  else ", ".join(keywords)))
                ok += 1
            else:
                fpath, exc = data
                log.debug("  Error en imagen %s: %s", fpath, exc)
                errors += 1

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
            "VALUES (?, 'ia_keywords', ?)", batch)
        conn.commit()

    stats["warnings"] += warnings
    log.info("  ✅ Keywords generadas: %d  |  Errores: %d", ok, errors)
    stats["keywords_ok"] = ok
    stats["keywords_err"] = errors


def run_descriptions(conn, db_path, mode, stats):
    """Describe imágenes con IA (Ollama)."""
    log.info("Paso: descriptions — Describiendo imágenes con IA")

    if mode == "replace":
        conn.execute("DELETE FROM media_metadata WHERE key = 'ia_description'")
        conn.commit()
        query = "SELECT id, filepath_absoluto FROM media WHERE type='image'"
    elif mode == "update":
        query = "SELECT id, filepath_absoluto FROM media WHERE type='image'"
    else:
        query = """
            SELECT m.id, m.filepath_absoluto FROM media m
            WHERE m.type='image'
              AND NOT EXISTS (
                  SELECT 1 FROM media_metadata mm
                  WHERE mm.media_id = m.id AND mm.key = 'ia_description'
              )
        """

    rows = conn.execute(query).fetchall()
    if not rows:
        log.info("  No hay imágenes pendientes.")
        return

    try:
        from scripts.ai_media.image_analysis import describir_imagen, MODELO_VISION_DEFAULT
    except ImportError:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from scripts.ai_media.image_analysis import describir_imagen, MODELO_VISION_DEFAULT
        except ImportError as e:
            log.error("  No se pudo importar describir_imagen: %s", e)
            stats["errors"] += 1
            return

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _process_one(mid, fpath):
        if not os.path.isfile(fpath):
            return "warning", fpath
        try:
            desc = describir_imagen(fpath, modelo=MODELO_VISION_DEFAULT)
            return "ok", (mid, desc)
        except Exception as e:
            return "error", (fpath, e)

    ok = 0
    errors = 0
    warnings = 0
    batch = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_process_one, mid, fpath): (mid, fpath)
                   for mid, fpath in rows}
        for f in tqdm(as_completed(futures), total=len(futures),
                      desc="  Descripciones", unit="img", ncols=80):
            result, data = f.result()
            if result == "warning":
                log.warning("  Archivo no encontrado: %s", data)
                warnings += 1
            elif result == "ok":
                mid, desc = data
                if desc:
                    batch.append((mid, desc if isinstance(desc, str) else str(desc)))
                ok += 1
            else:
                fpath, exc = data
                log.debug("  Error en imagen %s: %s", fpath, exc)
                errors += 1

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
            "VALUES (?, 'ia_description', ?)", batch)
        conn.commit()

    stats["warnings"] += warnings
    log.info("  ✅ Descripciones generadas: %d  |  Errores: %d", ok, errors)
    stats["descriptions_ok"] = ok
    stats["descriptions_err"] = errors


def run_transcribe(conn, db_path, mode, stats):
    """Transcribe audios y videos con faster-whisper."""
    log.info("Paso: transcribe — Transcribiendo audios/videos")

    if mode == "replace":
        conn.execute("DELETE FROM media_metadata WHERE key = 'whisper_segments'")
        conn.execute("DELETE FROM media_metadata WHERE key = 'whisper_info'")
        conn.commit()
        query = "SELECT id, filepath_absoluto FROM media WHERE type IN ('video', 'audio')"
    elif mode == "update":
        query = "SELECT id, filepath_absoluto FROM media WHERE type IN ('video', 'audio')"
    else:
        query = """
            SELECT m.id, m.filepath_absoluto FROM media m
            WHERE m.type IN ('video', 'audio')
              AND NOT EXISTS (
                  SELECT 1 FROM media_metadata mm
                  WHERE mm.media_id = m.id AND mm.key = 'whisper_segments'
              )
        """

    rows = conn.execute(query).fetchall()
    if not rows:
        log.info("  No hay audios/videos pendientes.")
        return

    try:
        from scripts.ai_media.transcribe import transcribir_audio
    except ImportError:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from scripts.ai_media.transcribe import transcribir_audio
        except ImportError as e:
            log.error("  No se pudo importar transcribir_audio: %s", e)
            stats["errors"] += 1
            return

    ok = 0
    errors = 0
    for mid, fpath in tqdm(rows, desc="  Transcribe", unit="arch", ncols=80):
        if not os.path.isfile(fpath):
            log.warning("  Archivo no encontrado: %s", fpath)
            stats["warnings"] += 1
            continue
        try:
            segmentos, info = transcribir_audio(fpath, modelo="base")
            if segmentos:
                conn.execute(
                    "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, 'whisper_segments', ?)",
                    (mid, json.dumps(segmentos, ensure_ascii=False)),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, 'whisper_info', ?)",
                    (mid, json.dumps({
                        "language": str(info.language),
                        "language_probability": float(info.language_probability),
                    })),
                )
            ok += 1
        except Exception as e:
            log.debug("  Error transcribiendo %s: %s", fpath, e)
            errors += 1

    conn.commit()
    log.info("  ✅ Transcripciones: %d  |  Errores: %d", ok, errors)
    stats["transcribe_ok"] = ok
    stats["transcribe_err"] = errors


def run_keypoints(conn, db_path, mode, stats):
    """
    Puebla media_keypoints desde transcripciones almacenadas en media_metadata.
    Calcula timestamp_absolute como timestamp_utc + offset.
    """
    log.info("Paso: keypoints — Poblando keypoints desde transcripciones")

    if mode in ("replace", "update"):
        conn.execute("DELETE FROM media_keypoints")
        conn.commit()

    # Medios transcritos que aún no tienen keypoints
    rows = conn.execute("""
        SELECT m.id, m.filepath_absoluto, m.timestamp_utc, mm.value AS segments_json
        FROM media m
        JOIN media_metadata mm ON mm.media_id = m.id AND mm.key = 'whisper_segments'
        WHERE m.id NOT IN (
            SELECT DISTINCT media_id FROM media_keypoints
        )
    """).fetchall()

    if not rows:
        log.info("  No hay transcripciones pendientes para keypoints.")
        return

    inserted = 0
    errors = 0
    for mid, fpath, ts_utc, segments_json in tqdm(
        rows, desc="  Keypoints", unit="arch", ncols=80
    ):
        if not ts_utc:
            log.warning("  media id=%s no tiene timestamp_utc, skip.", mid)
            stats["warnings"] += 1
            continue

        try:
            dt_base = datetime.fromisoformat(ts_utc)
            segmentos = json.loads(segments_json)
            batch = []
            for seg in segmentos:
                offset = seg.get("inicio", 0)
                texto = seg.get("texto", "").strip()
                if not texto:
                    continue
                ts_abs = (dt_base + timedelta(seconds=offset)).isoformat()
                batch.append((mid, offset, ts_abs, "transcription", texto, "whisper"))

            conn.executemany(
                "INSERT INTO media_keypoints (media_id, timestamp_offset_secs, timestamp_absolute, key, value, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )
            inserted += len(batch)
        except Exception as e:
            log.debug("  Error generando keypoints para media id=%s: %s", mid, e)
            errors += 1

    conn.commit()
    log.info("  ✅ Keypoints insertados: %d  |  Errores: %d", inserted, errors)
    stats["keypoints_ok"] = inserted
    stats["keypoints_err"] = errors


def run_timestamps(conn, db_path, mode, stats):
    """
    Infiere timestamps faltantes agrupando por clúster (misma carpeta, mismo día)
    y ordenando por nombre de archivo. Interpola entre medios con timestamp conocido.
    """
    log.info("Paso: timestamps — Infiriendo timestamps faltantes")

    if mode in ("replace", "update"):
        # Marcar los inferidos para reprocesarlos
        conn.execute("""
            UPDATE media SET
                timestamp_original = NULL,
                timestamp_utc = NULL,
                timezone_note = NULL
            WHERE timezone_note LIKE 'inferido:%'
        """)
        conn.commit()

    # Medios sin timestamp_utc o con fallback
    rows = conn.execute("""
        SELECT id, filepath_absoluto, filepath_relativo, carpeta,
               timestamp_utc, timezone_note
        FROM media
        WHERE timestamp_utc IS NULL
           OR timezone_note LIKE '%fallback%'
           OR timezone_note LIKE '%no se pudo%'
        ORDER BY carpeta, filepath_relativo
    """).fetchall()

    if not rows:
        log.info("  No hay medios con timestamp mejorable.")
        return

    # Agrupar por carpeta
    from collections import defaultdict
    clusters = defaultdict(list)
    for row in rows:
        clusters[row[3]].append(row)  # row[3] = carpeta

    inferidos = 0
    sin_referencia = 0

    for carpeta, miembros in clusters.items():
        if not carpeta:
            continue

        # Ordenar por filepath_relativo (orden lexicográfico ≈ orden de captura)
        miembros.sort(key=lambda r: r[2])

        # Separar los que tienen timestamp real vs los que no
        conocidos = [(i, r) for i, r in enumerate(miembros) if r[4] and "fallback" not in (r[5] or "") and "no se pudo" not in (r[5] or "")]
        # conocidos: (indice_en_miembros, row)

        if len(conocidos) < 2:
            # Con menos de 2 referencias no podemos interpolar bien
            sin_referencia += len(miembros)
            continue

        # Interpolar: entre cada par de conocidos, distribuir los desconocidos
        for idx in range(len(conocidos) - 1):
            i1, r1 = conocidos[idx]
            i2, r2 = conocidos[idx + 1]
            t1 = datetime.fromisoformat(r1[4])
            t2 = datetime.fromisoformat(r2[4])
            gap = i2 - i1  # cuántos índices hay entre conocidos
            if gap <= 1:
                continue  # consecutivos, no hay nada que interpolar

            dt_desconocidos = (t2 - t1) / gap
            for j in range(1, gap):
                row = miembros[i1 + j]
                mid = row[0]
                t_inferido = t1 + dt_desconocidos * j
                t_orig = t_inferido.astimezone(timezone(timedelta(hours=-3)))
                conn.execute(
                    "UPDATE media SET timestamp_original=?, timestamp_utc=?, "
                    "timezone_note=? WHERE id=?",
                    (
                        t_orig.isoformat(),
                        t_inferido.isoformat(),
                        f"inferido: interpolado entre {r1[4]} y {r2[4]}",
                        mid,
                    ),
                )
                inferidos += 1

    conn.commit()
    log.info("  ✅ Timestamps inferidos: %d  |  Sin referencia suficiente: %d",
              inferidos, sin_referencia)
    stats["timestamps_ok"] = inferidos
    stats["timestamps_no_ref"] = sin_referencia


def run_gps(conn, db_path, mode, stats):
    """
    Infiere GPS desde medios cercanos en el tiempo que sí tienen coordenadas.
    Agrupa por fecha y asigna coordenadas interpoladas según el orden temporal.
    """
    log.info("Paso: gps — Infiriendo GPS desde medios cercanos")

    if mode in ("replace", "update"):
        # Marcar inferidos como NULL para reprocesarlos
        conn.execute("""
            UPDATE media SET latitude = NULL, longitude = NULL, altitude = NULL,
                             geolocation_source = NULL
            WHERE geolocation_source = 'inferido_tiempo'
        """)
        conn.commit()

    # Medios sin GPS pero con timestamp
    rows = conn.execute("""
        SELECT id, timestamp_utc, filepath_relativo
        FROM media
        WHERE latitude IS NULL AND timestamp_utc IS NOT NULL
        ORDER BY timestamp_utc
    """).fetchall()

    if not rows:
        log.info("  No hay medios sin GPS con timestamp.")
        return

    inferidos = 0
    sin_ref = 0

    for row in rows:
        mid, ts_utc, _ = row
        # Buscar el medio con GPS más cercano antes y después en el tiempo
        anterior = conn.execute("""
            SELECT latitude, longitude, timestamp_utc FROM media
            WHERE latitude IS NOT NULL AND timestamp_utc <= ?
            ORDER BY timestamp_utc DESC LIMIT 1
        """, (ts_utc,)).fetchone()

        siguiente = conn.execute("""
            SELECT latitude, longitude, timestamp_utc FROM media
            WHERE latitude IS NOT NULL AND timestamp_utc >= ?
            ORDER BY timestamp_utc ASC LIMIT 1
        """, (ts_utc,)).fetchone()

        if anterior and siguiente:
            # Interpolar linealmente entre las dos coordenadas
            lat1, lon1, t1 = anterior
            lat2, lon2, t2 = siguiente
            dt1 = datetime.fromisoformat(t1)
            dt2 = datetime.fromisoformat(t2)
            dt_target = datetime.fromisoformat(ts_utc)

            if dt2 == dt1:
                lat, lon = lat1, lon1
            else:
                frac = (dt_target - dt1).total_seconds() / (dt2 - dt1).total_seconds()
                lat = lat1 + (lat2 - lat1) * frac
                lon = lon1 + (lon2 - lon1) * frac

            conn.execute(
                "UPDATE media SET latitude=?, longitude=?, geolocation_source=? WHERE id=?",
                (lat, lon, "inferido_tiempo", mid),
            )
            inferidos += 1
        elif anterior:
            # Solo hay referencia anterior
            conn.execute(
                "UPDATE media SET latitude=?, longitude=?, geolocation_source=? WHERE id=?",
                (anterior[0], anterior[1], "inferido_tiempo", mid),
            )
            inferidos += 1
        elif siguiente:
            conn.execute(
                "UPDATE media SET latitude=?, longitude=?, geolocation_source=? WHERE id=?",
                (siguiente[0], siguiente[1], "inferido_tiempo", mid),
            )
            inferidos += 1
        else:
            sin_ref += 1

    conn.commit()
    log.info("  ✅ GPS inferidos: %d  |  Sin referencia: %d", inferidos, sin_ref)
    stats["gps_ok"] = inferidos
    stats["gps_no_ref"] = sin_ref


# ==============================================================================
# Registro de pasos
# ==============================================================================

REGISTRY = {
    "colors": {
        "description": "Extraer colores dominantes de imágenes",
        "dependencies": [],
        "check": check_colors,
        "run": run_colors,
    },
    "keywords": {
        "description": "Etiquetar imágenes con IA (Ollama)",
        "dependencies": [],
        "check": check_keywords,
        "run": run_keywords,
    },
    "descriptions": {
        "description": "Describir imágenes con IA (Ollama)",
        "dependencies": [],
        "check": check_descriptions,
        "run": run_descriptions,
    },
    "transcribe": {
        "description": "Transcribir audios/videos con faster-whisper",
        "dependencies": [],
        "check": check_transcribe,
        "run": run_transcribe,
    },
    "keypoints": {
        "description": "Poblar media_keypoints desde transcripciones",
        "dependencies": ["transcribe"],
        "check": check_keypoints,
        "run": run_keypoints,
    },
    "timestamps": {
        "description": "Inferir timestamps faltantes por clúster + orden",
        "dependencies": [],
        "check": check_timestamps,
        "run": run_timestamps,
    },
    "gps": {
        "description": "Inferir GPS desde medios cercanos en el tiempo",
        "dependencies": [],
        "check": check_gps,
        "run": run_gps,
    },
}

DEP_ORDER = ["colors", "keywords", "descriptions", "transcribe", "keypoints",
             "timestamps", "gps"]


def listar_pasos():
    """Muestra los pasos disponibles con su estado."""
    print("Pasos disponibles:\n")
    for name in DEP_ORDER:
        meta = REGISTRY[name]
        deps = meta["dependencies"]
        dep_str = f" (requiere: {', '.join(deps)})" if deps else ""
        print(f"  {name:15s}  {meta['description']}{dep_str}")
    print()
    print("Modos:")
    print("  skip     Saltar medios que ya tienen el dato procesado")
    print("  update   Re-ejecutar el paso (actualiza lo existente)")
    print("  replace  Borrar todo lo generado y regenerar desde cero")


def check_dependencias(pasos_seleccionados: list[str]) -> list[str]:
    """Verifica dependencias y las agrega si faltan."""
    result = set(pasos_seleccionados)
    for paso in pasos_seleccionados:
        deps = REGISTRY[paso]["dependencies"]
        for d in deps:
            if d not in result:
                log.warning("  %s requiere %s — se agrega automáticamente.", paso, d)
                result.add(d)
    # Devolver en orden de dependencia
    return [p for p in DEP_ORDER if p in result]


# ==============================================================================
# Main
# ==============================================================================

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mejora la base de datos de Flujos con pasos de post-procesamiento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/improve_db.py                              # todos los pasos (skip)
  python scripts/improve_db.py --steps colors,keywords      # solo esos
  python scripts/improve_db.py --steps keypoints --mode replace  # regenerar keypoints
  python scripts/improve_db.py --list                       # listar pasos
  python scripts/improve_db.py --db db/flujos.db            # DB personalizada
        """,
    )
    parser.add_argument(
        "--steps",
        help="Pasos a ejecutar separados por coma (default: todos)",
    )
    parser.add_argument(
        "--mode",
        default="skip",
        choices=["skip", "update", "replace"],
        help="Modo de ejecución (default: skip)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Ruta a la base de datos (default: ./db/flujos.db)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="Listar pasos disponibles",
    )

    args = parser.parse_args(argv)

    if args.list:
        listar_pasos()
        return

    # Resolver DB
    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("Base de datos no encontrada: %s", db_path)
        sys.exit(1)

    # Determinar pasos
    if args.steps:
        pasos = [s.strip() for s in args.steps.split(",") if s.strip()]
        invalidos = [p for p in pasos if p not in REGISTRY]
        if invalidos:
            log.error("Pasos inválidos: %s", ", ".join(invalidos))
            log.error("Usá --list para ver los pasos disponibles.")
            sys.exit(1)
    else:
        pasos = list(DEP_ORDER)

    # Resolver dependencias
    pasos = check_dependencias(pasos)
    log.info("Pasos a ejecutar: %s", ", ".join(pasos))
    log.info("Modo: %s", args.mode)

    conn = conectar(db_path)

    # Verificar que la tabla media existe
    try:
        conn.execute("SELECT COUNT(*) FROM media").fetchone()
    except sqlite3.OperationalError as e:
        log.error("Error: la DB no tiene la tabla 'media'. ¿Ejecutaste ingest primero?")
        log.error("  %s", e)
        conn.close()
        sys.exit(1)

    # Reportar trabajo pendiente
    print()
    log.info("=== ESTADO PREVIO ===")
    for paso in pasos:
        meta = REGISTRY[paso]
        try:
            chk = meta["check"](conn)
            pct = (chk["hecho"] / chk["total"] * 100) if chk["total"] else 100
            print(f"  {paso:15s}  {chk['pendientes']:>5d} pendientes  ({chk['hecho']:>5d}/{chk['total']:>5d} = {pct:5.1f}%)")
        except Exception as e:
            print(f"  {paso:15s}  no se pudo verificar: {e}")
    print()

    # Ejecutar pasos
    stats = {"warnings": 0, "errors": 0}
    for paso in pasos:
        print()
        meta = REGISTRY[paso]
        try:
            meta["run"](conn, db_path, args.mode, stats)
        except Exception as e:
            log.error("  ❌ Error en paso '%s': %s", paso, e)
            stats["errors"] += 1

    # Resumen final
    print()
    log.info("=" * 50)
    log.info("  IMPROVE DB COMPLETADO")
    log.info("=" * 50)
    log.info("  Advertencias:  %d", stats.get("warnings", 0))
    log.info("  Errores:       %d", stats.get("errors", 0))

    conn.close()


if __name__ == "__main__":
    main()
