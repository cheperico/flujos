#!/usr/bin/env python3
"""
audio_frame_crossref.py — Correlaciona el contenido de audio con los frames del video.

Para un archivo de video (o audio):
    1. ffmpeg extrae el audio a 16 kHz mono (en memoria).
    2. El audio se divide en ventanas de VENTANA_SECS (10 s) y cada ventana se
       clasifica con el modelo CED-mini de sherpa-onnx (audio tagging, 527
       clases AudioSet, local).
    3. Cada ventana con sonidos por encima de un umbral se mapea al intervalo
       de tiempo correspondiente y a los frames del video en ese rango
       (1 frame cada N segundos).
    4. Reporta: [timestamp] sonido (prob) → frames N-N.

Opcionalmente extrae los frames reales con ffmpeg a --frames-dir para
inspección visual de los momentos con sonido relevante.

Reutiliza el modelo y las funciones internas de audio_tagging.py (CED-mini).

Uso:
    python scripts/audio_frame_crossref.py --archivo D:/ruta/video.mp4
    python scripts/audio_frame_crossref.py --media-id 42
    python scripts/audio_frame_crossref.py --archivo D:/ruta/video.mp4 --frames-dir tmp/frames
    python scripts/audio_frame_crossref.py --archivo D:/ruta/video.mp4 --umbral 0.15 --top-k 3
    python scripts/audio_frame_crossref.py --archivo D:/ruta/video.mp4 --cada-segundos 2
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.util import abrir, resolver_db
from scripts.ai_media.audio_tagging import (
    _clasificar_ventana,
    _extraer_audio_ffmpeg,
    _resolver_modelo,
    _traducir_etiqueta,
    _ventanas_de_audio,
    ONNX_DEFAULT,
    LABELS_DEFAULT,
    VENTANA_SECS,
    UMBRAL_PROB,
)


# ═══════════════════════════════════════════════════════════════
#  UTILIDADES DE TIEMPO
# ═══════════════════════════════════════════════════════════════


def _formatear_ts(segundos: float) -> str:
    """Formatea segundos como mm:ss."""
    s = int(segundos)
    return f"{s // 60}:{s % 60:02d}"


def _rango_frames(inicio_s: float, fin_s: float, cada_segundos: float) -> list[int]:
    """Devuelve los números de frame (1-based) en el intervalo [inicio, fin).

    Los frames se numeran como los genera ffmpeg con fps=1/cada_segundos:
    frame N corresponde aproximadamente a t = (N-1) * cada_segundos.

    Args:
        inicio_s: Inicio del intervalo (segundos).
        fin_s: Fin del intervalo (segundos).
        cada_segundos: Intervalo entre frames (segundos).

    Returns:
        Lista de números de frame (1-based) dentro del rango.
    """
    if cada_segundos <= 0:
        return []
    primero = int(inicio_s // cada_segundos) + 1
    ultimo = max(primero, int((fin_s - 1e-6) // cada_segundos) + 1)
    return list(range(primero, ultimo + 1))


# ═══════════════════════════════════════════════════════════════
#  EXTRACCIÓN DE FRAMES
# ═══════════════════════════════════════════════════════════════


def _extraer_frame(ruta_archivo: str, tiempo_s: float, dir_salida: Path, nombre: str) -> Path | None:
    """Extrae un frame puntual de un video con ffmpeg (-ss + -frames:v 1).

    Args:
        ruta_archivo: Ruta absoluta al video.
        tiempo_s: Momento del video a capturar (segundos).
        dir_salida: Carpeta de salida.
        nombre: Nombre del archivo de salida (ej: "t0005.jpg").

    Returns:
        Ruta del frame extraído, o None si falló.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log.warning("  ffmpeg no está en el PATH; no se extraen frames.")
        return None
    dir_salida.mkdir(parents=True, exist_ok=True)
    salida = dir_salida / nombre
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{tiempo_s:.3f}",
        "-i", ruta_archivo,
        "-frames:v", "1", "-q:v", "2",
        str(salida),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        log.debug("  ffmpeg frame falló (%s): %s", nombre, proc.stderr.strip()[:200])
        return None
    return salida


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    """Entry point para correlacionar audio con frames.

    Args:
        argv: Lista de argumentos (sin el nombre del script).
               Si es None, usa sys.argv[1:].

    Returns:
        Código de salida (0 = ok, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Correlaciona el contenido de audio (CED-mini) con los frames "
                    "del video. Reporta qué sonido ocurre en qué frames.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None,
                        help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--archivo", default=None,
                        help="Ruta absoluta al archivo de video/audio a analizar")
    parser.add_argument("--media-id", type=int, default=None,
                        help="ID de media en la DB (toma filepath_absoluto)")
    parser.add_argument("--top-k", type=int, default=3,
                        help="Sonidos por ventana a reportar (default: 3)")
    parser.add_argument("--umbral", type=float, default=UMBRAL_PROB,
                        help=f"Probabilidad mínima de un sonido para reportarlo (default: {UMBRAL_PROB})")
    parser.add_argument("--cada-segundos", type=float, default=5.0,
                        help="Intervalo de frames del video (default: 5 s)")
    parser.add_argument("--frames-dir", default=None,
                        help="Si se pasa, extrae los frames relevantes a esta carpeta")
    parser.add_argument("--modelo", default=None,
                        help=f"Ruta al .onnx del modelo (default: {ONNX_DEFAULT})")
    parser.add_argument("--labels", default=None,
                        help=f"Ruta al CSV de etiquetas (default: {LABELS_DEFAULT})")
    parser.add_argument("--threads", type=int, default=4,
                        help="Hilos de CPU para el modelo (default: 4)")
    parser.add_argument("--no-descargar", action="store_true",
                        help="No descargar el modelo automáticamente si falta")
    parser.add_argument("--json", default=None,
                        help="Exportar el reporte a JSON")
    parser.add_argument("--verbose", action="store_true",
                        help="Log detallado")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Consola Windows: permitir caracteres UTF-8 (→, ↔, etc.) sin UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    # ── Resolver el archivo a analizar ──
    ruta_archivo: str | None = None
    if args.archivo:
        ruta_archivo = os.path.abspath(args.archivo)
        if not os.path.isfile(ruta_archivo):
            log.error("  No existe el archivo: %s", ruta_archivo)
            return 1
    elif args.media_id is not None:
        db_path = resolver_db(args.db)
        conn = abrir(db_path)
        try:
            fila = conn.execute(
                "SELECT filepath_absoluto, filename_original FROM media WHERE id = ?",
                (args.media_id,),
            ).fetchone()
        finally:
            conn.close()
        if not fila:
            log.error("  No existe media con id=%s", args.media_id)
            return 1
        ruta_archivo = fila[0]
        if not ruta_archivo or not os.path.isfile(ruta_archivo):
            log.error("  El archivo de media %s no existe: %s", args.media_id, ruta_archivo)
            return 1
    else:
        log.error("  Falta --archivo o --media-id para saber qué analizar.")
        return 1

    log.info("Analizando: %s", ruta_archivo)

    # ── Cargar modelo CED-mini (igual que audio_tagging.py) ──
    onnx_path = args.modelo or ONNX_DEFAULT
    labels_path = args.labels or LABELS_DEFAULT
    try:
        onnx_path, labels_path = _resolver_modelo(
            onnx_path, labels_path, no_descargar=args.no_descargar)
    except RuntimeError as e:
        log.error("  %s", e)
        return 1

    try:
        import sherpa_onnx
    except ImportError:
        log.error("Falta sherpa_onnx. Instalalo: pip install onnxruntime sherpa-onnx")
        return 1

    config = sherpa_onnx.AudioTaggingConfig(
        model=sherpa_onnx.AudioTaggingModelConfig(ced=onnx_path, num_threads=args.threads),
        labels=labels_path,
        top_k=args.top_k,
    )
    tagging = sherpa_onnx.AudioTagging(config)
    log.info("  Modelo cargado: %s (threads=%d, top_k=%d)",
             os.path.basename(onnx_path), args.threads, args.top_k)

    # ── Extraer audio y clasificar ventanas ──
    try:
        samples, rate = _extraer_audio_ffmpeg(ruta_archivo)
    except RuntimeError as e:
        log.error("  %s", e)
        return 1

    ventanas = _ventanas_de_audio(samples, rate)
    log.info("  Ventanas de audio a clasificar: %d (%.0f s c/u, máx %d)",
             len(ventanas), VENTANA_SECS, len(ventanas) * int(VENTANA_SECS))

    dir_frames: Path | None = None
    if args.frames_dir:
        dir_frames = Path(args.frames_dir)

    entradas: list[dict] = []
    for i, ventana in enumerate(ventanas):
        inicio_s = i * VENTANA_SECS
        fin_s = inicio_s + len(ventana) / rate
        try:
            resultados = _clasificar_ventana(tagging, ventana, rate)
        except Exception as e:
            log.debug("  Error clasificando ventana %d: %s", i, e)
            continue
        # Filtrar por umbral y traducir etiquetas a español
        relevantes = [
            {"sonido": _traducir_etiqueta(nombre), "probabilidad": round(prob, 3)}
            for nombre, prob in resultados
            if prob >= args.umbral
        ]
        if not relevantes:
            continue

        frames = _rango_frames(inicio_s, fin_s, args.cada_segundos)

        # Extraer frames relevantes si se pidió
        if dir_frames and frames:
            # Un frame representativo por ventana (el del medio)
            medio = inicio_s + (fin_s - inicio_s) / 2
            _extraer_frame(ruta_archivo, medio, dir_frames, f"t{int(inicio_s):04d}.jpg")

        entradas.append({
            "inicio_s": round(inicio_s, 1),
            "fin_s": round(fin_s, 1),
            "sonidos": relevantes,
            "frames": frames,
        })

    # ── Reporte ──
    print(f"\n  Ventanas con sonido relevante: {len(entradas)} / {len(ventanas)}")
    if not entradas:
        print("  No se detectaron sonidos por encima del umbral.")
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({"archivo": ruta_archivo, "entradas": []},
                          f, ensure_ascii=False, indent=2)
        return 0

    print("\n  Correlación audio <-> frames:")
    for e in entradas:
        sonidos_txt = ", ".join(
            f"{s['sonido']} ({s['probabilidad']:.2f})" for s in e["sonidos"]
        )
        frames_txt = f"frames {e['frames'][0]}-{e['frames'][-1]}" if e["frames"] else "sin frames"
        print(f"    [{_formatear_ts(e['inicio_s'])} → {_formatear_ts(e['fin_s'])}] "
              f"{sonidos_txt}  |  {frames_txt}")

    if dir_frames:
        n_frames = len(list(dir_frames.glob("*.jpg"))) if dir_frames.exists() else 0
        print(f"\n  Frames extraídos: {n_frames} en {dir_frames}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "archivo": ruta_archivo,
                "umbral": args.umbral,
                "cada_segundos": args.cada_segundos,
                "entradas": entradas,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n  Reporte exportado a: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
