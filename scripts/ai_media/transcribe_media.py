"""
Transcripción automática de audios y videos con faster-whisper.

Integra con la DB (post-ingesta) y/o genera sidecars .transcript.json.

Dos modos:
  1. --db: busca en la DB audios/videos sin transcribir, los procesa y guarda.
  2. --file / --folder: modo autónomo, genera sidecars.

Formato del sidecar .transcript.json:
    {
        "file_hash": "abc123def456",
        "modelo": "base",
        "idioma": "es",
        "probabilidad_idioma": 0.95,
        "duracion_seg": 120.5,
        "transcripcion": "Texto completo...",
        "segmentos": [
            {"inicio": 0.0, "fin": 5.2, "texto": "Hola mundo"},
            ...
        ]
    }

Uso:
    # Transcribir un archivo
    python scripts/ai_media/transcribe_media.py --file audio.mp3

    # Transcribir un video
    python scripts/ai_media/transcribe_media.py --file video.mp4

    # Transcribir desde DB (procesa audios/videos sin transcripción)
    python scripts/ai_media/transcribe_media.py --db db/flujos.db

    # Transcribir toda una carpeta
    python scripts/ai_media/transcribe_media.py --folder D:/Audios

    # Solo 5 archivos, con modelo small
    python scripts/ai_media/transcribe_media.py --db db/flujos.db --limit 5 --modelo small

    # Solo ver qué se haría
    python scripts/ai_media/transcribe_media.py --db db/flujos.db --dry-run
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Permitir importar scripts/ como paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.ai_media.transcribe import (
    transcribir_audio,
    es_archivo_audio,
    es_archivo_video,
    segmentos_a_srt,
    segmentos_a_txt,
    segmentos_a_json,
    obtener_texto_completo,
    MODELOS_WHISPER,
)

logger = logging.getLogger(__name__)

# Extensiones soportadas
EXT_AUDIO = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}
EXT_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mxf", ".mts", ".m2ts"}
EXT_SOPORTADAS = EXT_AUDIO | EXT_VIDEO

# Claves en media_metadata
KEY_TRANSCRIPT = "transcript"
KEY_TRANSCRIPT_SEGMENTS = "transcript_segments"
KEY_TRANSCRIPT_INFO = "transcript_info"


# ── Helpers de compatibilidad con info de faster-whisper ──────────────
# faster-whisper devuelve info como namedtuple en la mayoría de las
# versiones, pero en algunas configuraciones puede llegar como dict.
# Estos helpers normalizan el acceso para ambos casos.


def _get_idioma(info) -> str:
    """Extrae el idioma desde info (objeto o dict)."""
    if hasattr(info, "language"):
        return info.language
    if isinstance(info, dict):
        return info.get("language", "?")
    return "?"


def _get_probabilidad(info) -> float:
    """Extrae la probabilidad del idioma desde info (objeto o dict)."""
    if hasattr(info, "language_probability"):
        return info.language_probability
    if isinstance(info, dict):
        return info.get("language_probability", 0.0)
    return 0.0


# ═══════════════════════════════════════════════════════════════
#  UTILIDADES
# ═══════════════════════════════════════════════════════════════

def _hash_rapido(ruta: str) -> str:
    """Fingerprint rápido: tamaño + fecha modificación."""
    import hashlib
    stat = Path(ruta).stat()
    h = hashlib.md5()
    h.update(str(stat.st_size).encode())
    h.update(str(stat.st_mtime).encode())
    return h.hexdigest()[:12]


def _es_medio_valido(ruta: str) -> bool:
    """Verifica si un archivo es de audio o video."""
    return Path(ruta).suffix.lower() in EXT_SOPORTADAS


# ═══════════════════════════════════════════════════════════════
#  SIDECAR .transcript.json
# ═══════════════════════════════════════════════════════════════

def _ruta_sidecar(ruta_medio: str) -> str:
    """Ruta del sidecar .transcript.json para un archivo."""
    return f"{ruta_medio}.transcript.json"


def _sidecar_existe_valido(ruta_medio: str) -> Optional[dict]:
    """
    Verifica si existe un sidecar válido.

    Returns:
        Dict con transcripción si es válido, None si no.
    """
    sidecar = _ruta_sidecar(ruta_medio)
    if not Path(sidecar).exists():
        return None

    try:
        with open(sidecar, "r", encoding="utf-8") as f:
            data = json.load(f)

        hash_actual = _hash_rapido(ruta_medio)
        if data.get("file_hash") == hash_actual:
            return data
    except Exception:
        pass

    return None


def _escribir_sidecar(ruta_medio: str, segmentos: list[dict],
                       info, modelo: str):
    """Escribe el sidecar .transcript.json junto al archivo."""
    sidecar = _ruta_sidecar(ruta_medio)
    duracion = segmentos[-1]["fin"] if segmentos else 0.0

    data = {
        "file_hash": _hash_rapido(ruta_medio),
        "modelo": modelo,
        "idioma": _get_idioma(info),
        "probabilidad_idioma": round(_get_probabilidad(info), 2),
        "duracion_seg": round(duracion, 1),
        "transcripcion": obtener_texto_completo(segmentos),
        "segmentos": segmentos,
        "fecha": datetime.now().isoformat(),
    }

    try:
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("  -> Sidecar escrito: %s", Path(sidecar).name)
    except Exception as e:
        logger.warning("  -> Error escribiendo sidecar: %s", e)


# ═══════════════════════════════════════════════════════════════
#  BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

def conectar_db(ruta_db: str) -> sqlite3.Connection:
    """Conecta a la DB y verifica tablas."""
    if not Path(ruta_db).exists():
        raise FileNotFoundError(f"No se encuentra la DB: {ruta_db}")

    conn = sqlite3.connect(ruta_db)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='media'"
    )
    if not cursor.fetchone():
        raise RuntimeError(f"La DB {ruta_db} no contiene la tabla 'media'")

    return conn


def obtener_medios_sin_transcripcion(
    conn: sqlite3.Connection, limite: Optional[int] = None
) -> list[dict]:
    """
    Busca audios/videos en la DB que no tienen transcripción.

    Returns:
        Lista de dicts con id, filepath_absoluto, filename_original, type.
    """
    query = """
        SELECT m.id, m.filepath_absoluto, m.filename_original, m.type
        FROM media m
        WHERE m.type IN ('audio', 'video')
        AND m.id NOT IN (
            SELECT mm.media_id
            FROM media_metadata mm
            WHERE mm.key = ?
        )
        ORDER BY m.id
    """
    params = [KEY_TRANSCRIPT]

    if limite:
        query += " LIMIT ?"
        params.append(limite)

    cursor = conn.execute(query, params)
    filas = cursor.fetchall()

    resultado = []
    for fila in filas:
        ruta = fila["filepath_absoluto"]
        if Path(ruta).exists():
            resultado.append({
                "id": fila["id"],
                "ruta": ruta,
                "nombre": fila["filename_original"],
                "type": fila["type"],
            })
        else:
            logger.warning("  -> Archivo no encontrado en disco: %s", ruta)

    return resultado


def guardar_transcripcion_en_db(
    conn: sqlite3.Connection,
    media_id: int,
    segmentos: list[dict],
    info,
    modelo: str,
):
    """
    Guarda la transcripción en media_metadata.

    Tres claves:
      - transcript: texto completo
      - transcript_segments: JSON con segmentos con timestamps
      - transcript_info: JSON con metadatos (modelo, idioma, duración)
    """
    texto_completo = obtener_texto_completo(segmentos)
    duracion = segmentos[-1]["fin"] if segmentos else 0.0

    info_data = {
        "modelo": modelo,
        "idioma": _get_idioma(info),
        "probabilidad_idioma": round(_get_probabilidad(info), 2),
        "duracion_seg": round(duracion, 1),
        "segmentos": len(segmentos),
    }

    try:
        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
            "VALUES (?, ?, ?)",
            (media_id, KEY_TRANSCRIPT, texto_completo),
        )
        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
            "VALUES (?, ?, ?)",
            (media_id, KEY_TRANSCRIPT_SEGMENTS,
             json.dumps(segmentos, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
            "VALUES (?, ?, ?)",
            (media_id, KEY_TRANSCRIPT_INFO,
             json.dumps(info_data, ensure_ascii=False)),
        )
        conn.commit()
    except Exception as e:
        logger.error("  -> Error guardando en DB (id=%d): %s", media_id, e)


# ═══════════════════════════════════════════════════════════════
#  TRANSCRIPCIÓN
# ═══════════════════════════════════════════════════════════════

def transcribir_medio(
    ruta: str,
    modelo: str = "base",
    device: str = "auto",
    language: Optional[str] = None,
) -> tuple[list[dict], object]:
    """
    Transcribe un archivo de audio o video.

    Args:
        ruta: Ruta al archivo.
        modelo: Modelo whisper (tiny, base, small, medium, large).
        device: cpu / cuda / auto.
        language: Código de idioma (None = auto-detecta).

    Returns:
        (segmentos, info_deteccion)

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si no es audio/video.
        RuntimeError: Si falla la transcripción.
    """
    if not Path(ruta).exists():
        raise FileNotFoundError(f"No se encuentra: {ruta}")

    if not _es_medio_valido(ruta):
        raise ValueError(
            f"Formato no soportado: {Path(ruta).suffix}. "
            f"Extensiones: {', '.join(sorted(EXT_SOPORTADAS))}"
        )

    segmentos, info = transcribir_audio(
        ruta,
        modelo=modelo,
        device=device,
        language=language,
        word_timestamps=False,
        extraer_audio=True,
    )

    return segmentos, info


# ═══════════════════════════════════════════════════════════════
#  FLUJO PRINCIPAL
# ═══════════════════════════════════════════════════════════════

def procesar_archivo(
    ruta: str,
    modelo: str,
    device: str,
    language: Optional[str],
    sidecar: bool,
    dry_run: bool,
    conn: Optional[sqlite3.Connection] = None,
    media_id: Optional[int] = None,
) -> bool:
    """
    Procesa un archivo: transcribe y guarda resultado.

    Args:
        ruta: Ruta al archivo.
        modelo: Modelo whisper.
        device: Dispositivo de cómputo.
        language: Idioma (None = auto).
        sidecar: Si True, escribe sidecar.
        dry_run: Si True, solo muestra qué haría.
        conn: Conexión a DB (opcional, modo post-ingesta).
        media_id: ID en DB (opcional).

    Returns:
        True si se procesó OK, False si no.
    """
    nombre = Path(ruta).name

    # Verificar sidecar existente
    if sidecar and not dry_run:
        existente = _sidecar_existe_valido(ruta)
        if existente is not None:
            logger.info("  -> Ya tiene sidecar válido. Skip.")
            # Si además tenemos DB pendiente, copiar datos
            if conn is not None and media_id is not None:
                guardar_transcripcion_en_db(
                    conn, media_id,
                    existente.get("segmentos", []),
                    existente,
                    existente.get("modelo", modelo),
                )
                logger.info("  -> Transcripción copiada de sidecar a DB.")
            return True

    if dry_run:
        logger.info("  [DRY RUN] Se transcribiría: %s", nombre)
        return True

    try:
        logger.info("  Transcribiendo (%s)...", modelo)
        segmentos, info = transcribir_medio(
            ruta, modelo=modelo, device=device, language=language,
        )

        duracion = segmentos[-1]["fin"] if segmentos else 0.0
        logger.info(
            "  OK: %d segmentos, %.1fs, idioma=%s",
            len(segmentos), duracion,
            _get_idioma(info),
        )

        # Sidecar
        if sidecar:
            _escribir_sidecar(ruta, segmentos, info, modelo)

        # DB
        if conn is not None and media_id is not None:
            guardar_transcripcion_en_db(conn, media_id, segmentos, info, modelo)

        # Mostrar preview
        for seg in segmentos[:3]:
            print(f"    [{seg['inicio']:6.1f}s -> {seg['fin']:6.1f}s] {seg['texto'][:80]}")
        if len(segmentos) > 3:
            print(f"    ... y {len(segmentos) - 3} segmentos más")

        return True

    except Exception as e:
        logger.error("  Error transcribiendo %s: %s", nombre, e)
        return False


def procesar_desde_db(
    ruta_db: str,
    modelo: str = "base",
    device: str = "auto",
    language: Optional[str] = None,
    limite: Optional[int] = None,
    sidecar: bool = False,
    dry_run: bool = False,
):
    """
    Modo post-ingesta: transcribe audios/videos de la DB.
    """
    logger.info("Conectando a DB: %s", ruta_db)
    conn = conectar_db(ruta_db)

    medios = obtener_medios_sin_transcripcion(conn, limite=limite)

    if not medios:
        logger.info("No hay audios/videos sin transcribir en la DB.")
        conn.close()
        return

    logger.info(
        "Medios a procesar: %d%s",
        len(medios),
        " (dry run)" if dry_run else "",
    )

    ok = 0
    fail = 0

    for i, med in enumerate(medios, 1):
        logger.info("[%d/%d] %s (%s)", i, len(medios), med["nombre"], med["type"])

        if procesar_archivo(
            ruta=med["ruta"],
            modelo=modelo,
            device=device,
            language=language,
            sidecar=sidecar,
            dry_run=dry_run,
            conn=conn,
            media_id=med["id"],
        ):
            ok += 1
        else:
            fail += 1

    conn.close()

    logger.info(
        "=== RESUMEN: %d transcritas, %d fallos (de %d) ===",
        ok, fail, len(medios),
    )


def procesar_desde_carpeta(
    carpeta: str,
    modelo: str = "base",
    device: str = "auto",
    language: Optional[str] = None,
    dry_run: bool = False,
):
    """
    Modo autónomo: transcribe todos los audios/videos de una carpeta.
    """
    carpeta = Path(carpeta)
    if not carpeta.exists():
        raise FileNotFoundError(f"La carpeta no existe: {carpeta}")

    rutas = sorted(
        str(p) for p in carpeta.rglob("*")
        if _es_medio_valido(str(p))
    )

    if not rutas:
        logger.info("No se encontraron archivos de audio/video en %s", carpeta)
        return

    logger.info(
        "Archivos encontrados: %d%s",
        len(rutas),
        " (dry run)" if dry_run else "",
    )

    ok = 0
    fail = 0
    ya_transcritos = 0

    for i, ruta in enumerate(rutas, 1):
        nombre = Path(ruta).name
        logger.info("[%d/%d] %s", i, len(rutas), nombre)

        # Verificar sidecar
        if not dry_run:
            existente = _sidecar_existe_valido(ruta)
            if existente is not None:
                logger.info(
                    "  -> Ya tiene sidecar válido (%d segmentos). Skip.",
                    len(existente.get("segmentos", [])),
                )
                ya_transcritos += 1
                continue

        if dry_run:
            logger.info("  [DRY RUN] Se transcribiría: %s", nombre)
            ok += 1
            continue

        if procesar_archivo(
            ruta=ruta,
            modelo=modelo,
            device=device,
            language=language,
            sidecar=True,
            dry_run=False,
        ):
            ok += 1
        else:
            fail += 1

    logger.info(
        "=== RESUMEN: %d nuevas, %d ya tenían sidecar, %d fallos (de %d) ===",
        ok, ya_transcritos, fail, len(rutas),
    )


def procesar_archivo_individual(
    ruta: str,
    modelo: str = "base",
    device: str = "auto",
    language: Optional[str] = None,
    srt: Optional[str] = None,
    txt: Optional[str] = None,
    json_out: Optional[str] = None,
):
    """
    Modo individual: transcribe un archivo y muestra resultado.
    """
    if not Path(ruta).exists():
        raise FileNotFoundError(f"No se encuentra: {ruta}")

    # Detectar tipo
    if es_archivo_video(ruta):
        print("  Video detectado — se extraerá el audio automáticamente.")
    elif es_archivo_audio(ruta):
        print("  Audio detectado.")
    else:
        raise ValueError(f"Formato no soportado: {Path(ruta).suffix}")

    segmentos, info = transcribir_medio(
        ruta, modelo=modelo, device=device, language=language,
    )

    duracion = segmentos[-1]["fin"] if segmentos else 0.0
    print(f"\n  OK: {len(segmentos)} segmentos, {duracion:.1f}s")
    print(f"  Idioma: {_get_idioma(info)} (prob: {_get_probabilidad(info):.2f})")
    print()

    # Preview
    for seg in segmentos[:10]:
        print(f"  [{seg['inicio']:6.1f}s -> {seg['fin']:6.1f}s] {seg['texto']}")
    if len(segmentos) > 10:
        print(f"  ... y {len(segmentos) - 10} segmentos más")

    # Exportar
    if srt:
        segmentos_a_srt(segmentos, srt)
        print(f"  SRT exportado: {srt}")
    if txt:
        segmentos_a_txt(segmentos, txt)
        print(f"  TXT exportado: {txt}")
    if json_out:
        segmentos_a_json(segmentos, json_out)
        print(f"  JSON exportado: {json_out}")

    # Sidecar siempre
    _escribir_sidecar(ruta, segmentos, info, modelo)


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Transcripción automática de audios y videos con faster-whisper.\n\n"
                    "Modos:\n"
                    "  --file ruta    : transcribe un solo archivo\n"
                    "  --db ruta      : procesa audios/videos de la DB (post-ingesta)\n"
                    "  --folder ruta  : transcribe todos los archivos de una carpeta\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Modo
    modo = parser.add_argument_group("Modo de operación")
    modo.add_argument("--file", help="Ruta a un archivo de audio o video")
    modo.add_argument("--db", help="Ruta a la base de datos SQLite")
    modo.add_argument("--folder", help="Ruta a carpeta con audios/videos")

    # Opciones de transcripción
    parser.add_argument("--modelo", default="base", choices=MODELOS_WHISPER,
                        help="Modelo whisper (default: base)")
    parser.add_argument("--device", default="auto", choices=["cpu", "cuda", "auto"],
                        help="Dispositivo de cómputo (default: auto)")
    parser.add_argument("--language", default=None,
                        help="Código de idioma (ej: es, en). Por defecto auto-detecta")

    # Opciones modo DB / folder
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar cantidad (solo modo --db)")
    parser.add_argument("--sidecar", action="store_true",
                        help="Generar sidecar .transcript.json (solo modo --db)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría sin transcribir")

    # Exportación individual
    parser.add_argument("--srt", help="Exportar a SRT (solo modo --file)")
    parser.add_argument("--txt", help="Exportar a TXT (solo modo --file)")
    parser.add_argument("--json", help="Exportar a JSON (solo modo --file)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Validar modo
    modos = [args.file, args.db, args.folder]
    activos = sum(1 for m in modos if m)
    if activos == 0:
        parser.error("Debe especificar --file, --db o --folder")
    if activos > 1:
        parser.error("Use solo un modo a la vez (--file, --db o --folder)")

    try:
        if args.file:
            procesar_archivo_individual(
                ruta=args.file,
                modelo=args.modelo,
                device=args.device,
                language=args.language,
                srt=args.srt,
                txt=args.txt,
                json_out=args.json,
            )

        elif args.db:
            procesar_desde_db(
                ruta_db=args.db,
                modelo=args.modelo,
                device=args.device,
                language=args.language,
                limite=args.limit,
                sidecar=args.sidecar,
                dry_run=args.dry_run,
            )

        elif args.folder:
            procesar_desde_carpeta(
                carpeta=args.folder,
                modelo=args.modelo,
                device=args.device,
                language=args.language,
                dry_run=args.dry_run,
            )

    except KeyboardInterrupt:
        logger.info("\nProceso interrumpido por el usuario.")
        sys.exit(1)

    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
