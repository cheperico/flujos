"""
Análisis de videos con modelos de visión de Ollama.

Estrategia:
  1. Extraer frames clave del video con ffmpeg (1 frame cada N segundos)
  2. Analizar cada frame con el modelo de visión (keywords, descripción)
  3. Consolidar resultados por video

Uso básico:
    from scripts.ai_media.video_analysis import analizar_video_keywords

    resultado = analizar_video_keywords("video.mp4")
    print(resultado["keywords"])

Línea de comandos:
    python -m scripts.ai_media.video_analysis video.mp4 --modelo moondream:latest
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from scripts.ai_media.ollama_client import OllamaVision
from scripts.ai_media.image_analysis import _parsear_keywords, MODELO_VISION_DEFAULT

logger = logging.getLogger(__name__)

# Prompt para keywords de video (se pasa por cada frame)
PROMPT_KEYWORDS_VIDEO = (
    "Este es un frame de un video. Devolvé únicamente una lista de 5 a 7 palabras clave "
    "en español que describan lo que se ve en este frame. "
    "Separalas con comas. No incluyas explicación."
)


def extraer_frames(
    ruta_video: str,
    fps: float = 0.5,
    max_frames: int = 20,
    directorio_salida: Optional[str] = None,
) -> list[str]:
    """
    Extrae frames de un video usando ffmpeg.

    Args:
        ruta_video: Ruta al archivo de video.
        fps: Frames por segundo a extraer (0.5 = 1 frame cada 2 segundos).
        max_frames: Máximo número de frames a extraer.
        directorio_salida: Directorio donde guardar los frames.
                          Si es None, usa un directorio temporal.

    Returns:
        Lista de rutas a los frames extraídos.

    Raises:
        RuntimeError: Si ffmpeg no está disponible o falla la extracción.
        FileNotFoundError: Si el video no existe.
    """
    ruta = Path(ruta_video)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el video: {ruta_video}")

    # Verificar ffmpeg
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg no está disponible en el sistema")

    # Crear directorio de salida
    if directorio_salida:
        out_dir = Path(directorio_salida)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path(tempfile.mkdtemp(prefix="flujos_frames_"))

    # Patrón de nombres de frames
    pattern = str(out_dir / "frame_%04d.jpg")

    logger.info(
        "Extrayendo frames de %s (fps=%s, max=%s, dir=%s)",
        ruta.name, fps, max_frames, out_dir
    )

    try:
        cmd = [
            ffmpeg, "-i", str(ruta),
            "-vf", f"fps={fps},scale=-1:720",
            "-vframes", str(max_frames),
            "-q:v", "2",
            "-y", pattern,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            logger.error("ffmpeg stderr: %s", result.stderr[:500])
            raise RuntimeError(f"ffmpeg falló al extraer frames: {result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Timeout extrayendo frames de {ruta_video}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg no encontrado. Verificá que esté instalado.")

    # Listar frames generados
    frames = sorted(out_dir.glob("frame_*.jpg"))
    logger.info("Frames extraídos: %d", len(frames))

    if not frames:
        raise RuntimeError(
            f"No se generaron frames. ¿{ruta_video} es un archivo de video válido?"
        )

    return [str(f) for f in frames]


def _limpiar_frames(frames: list[str]):
    """Elimina archivos de frames y su directorio temporal si corresponde."""
    for f in frames:
        try:
            Path(f).unlink()
        except Exception:
            pass
    if frames:
        frames_dir = Path(frames[0]).parent
        if "flujos_frames_" in str(frames_dir):
            try:
                frames_dir.rmdir()
            except Exception:
                pass


def _consolidar_keywords(resultados_por_frame: list[dict]) -> list[str]:
    """
    Consolida keywords de múltiples frames, eliminando duplicados.
    Preserva el orden de aparición.
    """
    todas = []
    for item in resultados_por_frame:
        todas.extend(item["keywords"])

    keywords_unicas = []
    vistos = set()
    for kw in todas:
        kw_norm = kw.lower().strip().rstrip(".,;")
        if kw_norm and kw_norm not in vistos and len(kw_norm) > 1:
            vistos.add(kw_norm)
            keywords_unicas.append(kw)

    return keywords_unicas


def analizar_video_keywords(
    ruta_video: str,
    modelo: str = MODELO_VISION_DEFAULT,
    fps: float = 0.5,
    max_frames: int = 20,
    limpiar_frames: bool = True,
) -> dict:
    """
    Analiza un video y devuelve palabras clave consolidadas.

    Estrategia:
      1. Extrae frames del video
      2. Analiza cada frame con el modelo de visión
      3. Consolida todas las keywords (elimina duplicados)
      4. Limpia los frames temporales

    Args:
        ruta_video: Ruta al archivo de video.
        modelo: Modelo de visión a usar.
        fps: Frames por segundo a extraer.
        max_frames: Máximo de frames a analizar.
        limpiar_frames: Si True, elimina los frames temporales al terminar.

    Returns:
        Dict con:
          - "keywords": lista de palabras clave únicas
          - "keywords_por_frame": lista de dicts por frame
          - "total_frames": cantidad de frames analizados
          - "duracion_estimada": duración estimada en segundos (basada en fps)
    """
    ruta = Path(ruta_video)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el video: {ruta_video}")

    logger.info("Analizando video: %s (modelo=%s)", ruta.name, modelo)

    # 1. Extraer frames
    frames = extraer_frames(
        str(ruta),
        fps=fps,
        max_frames=max_frames,
    )

    try:
        # 2. Analizar cada frame
        cliente = OllamaVision(modelo=modelo)
        resultados_por_frame = []

        for i, frame_path in enumerate(frames):
            logger.info("Analizando frame %d/%d: %s",
                        i + 1, len(frames), Path(frame_path).name)

            # Inicializar valores por defecto ANTES del try
            respuesta = None
            keywords_frame = []
            error_frame = None

            try:
                respuesta = cliente.analizar_imagen(
                    frame_path,
                    prompt=PROMPT_KEYWORDS_VIDEO,
                    temperatura=0.2,
                )
                keywords_frame = _parsear_keywords(respuesta)
            except Exception as e:
                error_frame = str(e)
                logger.warning("Error en frame %s: %s", frame_path, e)

            resultados_por_frame.append({
                "frame": frame_path,
                "keywords": keywords_frame,
                "respuesta_original": respuesta,
                "error": error_frame,
            })

        # 3. Consolidar keywords
        keywords_unicas = _consolidar_keywords(resultados_por_frame)

        logger.info(
            "Video analizado: %d frames, %d keywords únicas",
            len(frames), len(keywords_unicas)
        )

        resultado = {
            "video": str(ruta),
            "keywords": keywords_unicas,
            "keywords_por_frame": resultados_por_frame,
            "total_frames": len(frames),
            "duracion_estimada": len(frames) / fps if fps > 0 else 0,
            "modelo": modelo,
        }

    finally:
        # 4. Limpiar frames temporales (siempre se ejecuta, incluso si hay error)
        if limpiar_frames:
            _limpiar_frames(frames)

    return resultado


def analizar_video_descripcion(
    ruta_video: str,
    modelo: str = MODELO_VISION_DEFAULT,
    fps: float = 0.5,
    max_frames: int = 10,
) -> str:
    """
    Genera una descripción general del video analizando frames clave.

    Args:
        ruta_video: Ruta al archivo de video.
        modelo: Modelo de visión.
        fps: Frames por segundo.
        max_frames: Máximo de frames.

    Returns:
        Descripción textual del video.
    """
    ruta = Path(ruta_video)
    frames = extraer_frames(str(ruta), fps=fps, max_frames=max_frames)

    descripciones = []
    errores = []

    try:
        cliente = OllamaVision(modelo=modelo)
        for frame_path in frames:
            try:
                desc = cliente.analizar_imagen(
                    frame_path,
                    prompt="Describí este frame de un video en una frase breve en español.",
                    temperatura=0.3,
                )
                descripciones.append(desc)
            except Exception as e:
                errores.append(str(e))
                logger.warning("Error en frame %s: %s", frame_path, e)
    finally:
        # Siempre limpiar frames
        _limpiar_frames(frames)

    if descripciones:
        return "El video muestra: " + " ".join(descripciones)
    elif errores:
        return f"No se pudo analizar el video. Errores: {'; '.join(errores[:3])}"
    else:
        return "No se pudo analizar el video."


# ---- CLI ----
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Analizar videos con modelos de visión Ollama"
    )
    parser.add_argument("video", help="Ruta al archivo de video")
    parser.add_argument("--modelo", default=MODELO_VISION_DEFAULT,
                        help=f"Modelo de visión (default: {MODELO_VISION_DEFAULT})")
    parser.add_argument("--fps", type=float, default=0.5,
                        help="Frames por segundo a extraer (0.5 = 1 cada 2s)")
    parser.add_argument("--max-frames", type=int, default=20,
                        help="Máximo número de frames a analizar")
    parser.add_argument("--action", default="keywords",
                        choices=["keywords", "describir"],
                        help="Acción a realizar")
    parser.add_argument("--json", help="Exportar resultados a JSON")
    parser.add_argument("--keep-frames", action="store_true",
                        help="No limpiar frames temporales")

    args = parser.parse_args()

    if args.action == "keywords":
        resultado = analizar_video_keywords(
            args.video,
            modelo=args.modelo,
            fps=args.fps,
            max_frames=args.max_frames,
            limpiar_frames=not args.keep_frames,
        )

        print(f"\nVideo: {resultado['video']}")
        print(f"Frames analizados: {resultado['total_frames']}")
        print(f"Duración estimada: {resultado['duracion_estimada']:.1f}s")
        print(f"Keywords ({len(resultado['keywords'])}):")
        for kw in resultado['keywords']:
            print(f"  - {kw}")

        if args.json:
            output = resultado.copy()
            if not args.keep_frames:
                output.pop("keywords_por_frame", None)
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"\nExportado a: {args.json}")

    elif args.action == "describir":
        desc = analizar_video_descripcion(
            args.video,
            modelo=args.modelo,
            fps=args.fps,
            max_frames=args.max_frames,
        )
        print(f"\nVideo: {args.video}")
        print(f"Descripción: {desc}")
