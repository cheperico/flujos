"""
Transcripción de audio a texto usando faster-whisper.

Soporta archivos de audio (WAV, MP3, FLAC, OGG, M4A, AAC, etc.)
y **videos** (MP4, MOV, AVI, MKV, etc.): si se pasa un video,
automáticamente extrae la pista de audio con ffmpeg antes de transcribir.

Exportación a SRT (subtítulos), TXT (texto plano) y JSON (con timestamps).

Uso básico:
    from scripts.ai_media.transcribe import transcribir_audio, segmentos_a_srt

    # Desde audio
    segmentos, info = transcribir_audio("audio.wav", modelo="small")
    print(f"Idioma: {info.language}")

    # Desde video (extrae audio automáticamente)
    segmentos, info = transcribir_audio("video.mp4")

    # Exportar
    segmentos_a_srt(segmentos, "transcripcion.srt")
    segmentos_a_txt(segmentos, "transcripcion.txt")

Línea de comandos:
    python -m scripts.ai_media.transcribe audio.wav --modelo small --srt salida.srt
    python -m scripts.ai_media.transcribe video.mp4 --modelo small --srt salida.srt
"""

import json
import logging
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Optional

import faster_whisper

logger = logging.getLogger(__name__)

# Extensiones de audio que faster-whisper puede leer directamente
EXT_AUDIO = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

# Extensiones de video que requieren extracción de audio
EXT_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mxf", ".mts", ".m2ts"}

# Tamaños de modelo whisper disponibles
MODELOS_WHISPER = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]


def es_archivo_video(ruta: str) -> bool:
    """Detecta si un archivo es un video por su extensión."""
    return Path(ruta).suffix.lower() in EXT_VIDEO


def es_archivo_audio(ruta: str) -> bool:
    """Detecta si un archivo es de audio por su extensión."""
    return Path(ruta).suffix.lower() in EXT_AUDIO


def extraer_audio_de_video(
    ruta_video: str,
    formato_salida: str = "wav",
    sample_rate: int = 16000,
    canales: int = 1,
    directorio_salida: Optional[str] = None,
) -> str:
    """
    Extrae la pista de audio de un video usando ffmpeg.

    Convierte a WAV mono 16kHz (formato óptimo para whisper).

    Args:
        ruta_video: Ruta al archivo de video.
        formato_salida: Formato de audio ("wav", "mp3", "flac").
        sample_rate: Frecuencia de muestreo (whisper funciona mejor con 16kHz).
        canales: 1 = mono, 2 = stereo.
        directorio_salida: Directorio para el audio extraído.
                          Si es None, usa directorio temporal.

    Returns:
        Ruta al archivo de audio extraído.

    Raises:
        FileNotFoundError: Si el video no existe o ffmpeg no está instalado.
        RuntimeError: Si falla la extracción.
    """
    ruta = Path(ruta_video)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el video: {ruta_video}")

    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg no está disponible. Instalalo o extraé el audio manualmente."
        )

    # Crear directorio de salida
    if directorio_salida:
        out_dir = Path(directorio_salida)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_salida = out_dir / f"{ruta.stem}.{formato_salida}"
    else:
        out_dir = Path(tempfile.mkdtemp(prefix="flujos_audio_"))
        audio_salida = out_dir / f"{ruta.stem}.{formato_salida}"

    logger.info(
        "Extrayendo audio de %s -> %s (%d Hz, %d canales)",
        ruta.name, audio_salida.name, sample_rate, canales
    )

    # Mapear formato a codec de audio
    codec_map = {
        "wav": "pcm_s16le",
        "mp3": "libmp3lame",
        "flac": "flac",
    }
    codec = codec_map.get(formato_salida, "pcm_s16le")

    try:
        cmd = [
            ffmpeg, "-i", str(ruta),
            "-vn",                          # sin video
            "-acodec", codec,
            "-ar", str(sample_rate),        # frecuencia de muestreo
            "-ac", str(canales),            # canales
            "-y",                           # sobrescribir
            str(audio_salida),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            logger.error("ffmpeg error: %s", result.stderr[:500])
            raise RuntimeError(
                f"ffmpeg falló al extraer audio: {result.stderr[:200]}"
            )

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Timeout extrayendo audio de {ruta_video}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg no encontrado en el sistema")

    if not audio_salida.exists():
        raise RuntimeError(
            f"No se generó el archivo de audio: {audio_salida}"
        )

    logger.info("Audio extraído: %s (%.1f MB)", audio_salida.name,
                audio_salida.stat().st_size / 1_048_576)
    return str(audio_salida)


def transcribir_audio(
    ruta_audio: str,
    modelo: str = "base",
    device: str = "auto",
    compute_type: str = "int8",
    beam_size: int = 5,
    language: Optional[str] = None,
    word_timestamps: bool = False,
    extraer_audio: bool = True,
) -> tuple[list[dict], object]:
    """
    Transcribe un archivo de audio o video a texto usando faster-whisper.

    Si el archivo es un video, extrae automáticamente la pista de audio
    con ffmpeg antes de transcribir.

    Args:
        ruta_audio: Ruta al archivo de audio o video.
        modelo: Tamaño del modelo whisper ("tiny", "base", "small", "medium", "large").
        device: "cpu", "cuda" o "auto" (detecta GPU disponible).
        compute_type: Precisión ("int8", "float16", "float32"). int8 recomendado para CPU.
        beam_size: Tamaño del beam search (mayor = más preciso pero más lento).
        language: Código de idioma (ej: "es", "en"). None = detección automática.
        word_timestamps: Si True, incluye marcas por palabra.
        extraer_audio: Si True y el archivo es un video, extrae audio automáticamente.
                       Si False, pasa el video directamente a whisper (puede fallar).

    Returns:
        Tuple de (segmentos, info_deteccion).
        segmentos: lista de dicts con "inicio", "fin", "texto".
        info_deteccion: objeto con .language y .language_probability.

    Raises:
        FileNotFoundError: Si no existe el archivo de entrada.
        RuntimeError: Si falla la transcripción o extracción de audio.
    """
    ruta = Path(ruta_audio)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el archivo: {ruta_audio}")

    # --- Paso 1: Si es video, extraer audio ---
    ruta_a_transcribir = str(ruta)
    audio_temporal = None

    if es_archivo_video(str(ruta)) and extraer_audio:
        try:
            ruta_a_transcribir = extraer_audio_de_video(str(ruta))
            audio_temporal = ruta_a_transcribir
        except Exception as e:
            logger.warning(
                "No se pudo extraer audio del video, intentando con whisper directo: %s", e
            )
            ruta_a_transcribir = str(ruta)

    logger.info(
        "Transcribiendo: %s (modelo=%s, device=%s, language=%s)",
        Path(ruta_a_transcribir).name, modelo, device, language or "auto"
    )

    # --- Paso 2: Detectar dispositivo ---
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Dispositivo detectado: %s", device)
        except ImportError:
            device = "cpu"

    # --- Paso 3: Transcribir ---
    try:
        model = faster_whisper.WhisperModel(
            modelo, device=device, compute_type=compute_type
        )

        segments, info = model.transcribe(
            ruta_a_transcribir,
            beam_size=beam_size,
            language=language,
            word_timestamps=word_timestamps,
        )

        logger.info(
            "Idioma detectado: %s (probabilidad: %.2f)",
            info.language, info.language_probability
        )

        resultado = []
        for segment in segments:
            resultado.append({
                "inicio": segment.start,
                "fin": segment.end,
                "texto": segment.text.strip(),
            })

        logger.info("Transcripción completa: %d segmentos", len(resultado))
        return resultado, info

    except Exception as e:
        logger.error("Error en transcripción: %s", e)
        raise RuntimeError(f"Fallo la transcripción de {ruta_audio}") from e

    finally:
        # Limpiar archivo de audio temporal si se generó
        if audio_temporal and Path(audio_temporal).exists():
            try:
                Path(audio_temporal).unlink()
                # Intentar limpiar directorio temporal también
                parent = Path(audio_temporal).parent
                if "flujos_audio_" in str(parent):
                    parent.rmdir()
            except Exception:
                pass


def segmentos_a_srt(segmentos: list[dict], archivo_salida: str):
    """
    Convierte segmentos de transcripción a formato SRT (subtítulos).

    Args:
        segmentos: Lista de dicts con "inicio", "fin", "texto".
        archivo_salida: Ruta del archivo .srt a escribir.
    """
    def _formatear_ts(segundos: float) -> str:
        td = timedelta(seconds=segundos)
        total = td.total_seconds()
        h = int(total // 3600)
        m = int((total % 3600) // 60)
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    with open(archivo_salida, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segmentos, 1):
            inicio = _formatear_ts(seg["inicio"])
            fin = _formatear_ts(seg["fin"])
            f.write(f"{i}\n{inicio} --> {fin}\n{seg['texto']}\n\n")

    logger.info("SRT exportado: %s (%d líneas)", archivo_salida, len(segmentos))


def segmentos_a_txt(segmentos: list[dict], archivo_salida: str):
    """
    Exporta transcripción a texto plano (solo texto, sin timestamps).

    Args:
        segmentos: Lista de dicts con "inicio", "fin", "texto".
        archivo_salida: Ruta del archivo .txt a escribir.
    """
    with open(archivo_salida, "w", encoding="utf-8") as f:
        for seg in segmentos:
            f.write(seg["texto"] + "\n")

    logger.info("TXT exportado: %s", archivo_salida)


def segmentos_a_json(segmentos: list[dict], archivo_salida: str):
    """
    Exporta transcripción a JSON con timestamps.

    Args:
        segmentos: Lista de dicts con "inicio", "fin", "texto".
        archivo_salida: Ruta del archivo .json a escribir.
    """
    with open(archivo_salida, "w", encoding="utf-8") as f:
        json.dump(segmentos, f, ensure_ascii=False, indent=2)

    logger.info("JSON exportado: %s", archivo_salida)


def obtener_texto_completo(segmentos: list[dict]) -> str:
    """Concatena todos los segmentos en un solo string."""
    return " ".join(seg["texto"] for seg in segmentos)


# ---- CLI ----
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Transcribir audio (o audio de video) a texto con faster-whisper"
    )
    parser.add_argument("entrada", help="Ruta al archivo de audio o video")
    parser.add_argument("--modelo", default="base", choices=MODELOS_WHISPER,
                        help="Tamaño del modelo whisper")
    parser.add_argument("--device", default="auto", choices=["cpu", "cuda", "auto"],
                        help="Dispositivo de cómputo")
    parser.add_argument("--language", default=None,
                        help="Código de idioma (ej: es, en). Por defecto auto-detecta")
    parser.add_argument("--no-extraer-audio", action="store_true",
                        help="No extraer audio de video (pasar directo a whisper)")
    parser.add_argument("--srt", help="Exportar a SRT (subtítulos)")
    parser.add_argument("--txt", help="Exportar a TXT (texto plano)")
    parser.add_argument("--json", help="Exportar a JSON")

    args = parser.parse_args()

    # Detectar si es video y avisar
    if es_archivo_video(args.entrada):
        if args.no_extraer_audio:
            print("ℹ️  Pasando video directamente a whisper (puede fallar según codec)")
        else:
            print("ℹ️  Se extraerá el audio del video automáticamente")

    segmentos, info = transcribir_audio(
        args.entrada,
        modelo=args.modelo,
        device=args.device,
        language=args.language,
        extraer_audio=not args.no_extraer_audio,
    )

    duracion = f"{segmentos[-1]['fin']:.1f}s" if segmentos else "0s"

    print(f"\n✅ Transcripción completada")
    print(f"   Idioma: {info.language} (prob: {info.language_probability:.2f})")
    print(f"   Segmentos: {len(segmentos)}")
    print(f"   Duración: {duracion}")
    print()

    if args.srt:
        segmentos_a_srt(segmentos, args.srt)
    if args.txt:
        segmentos_a_txt(segmentos, args.txt)
    if args.json:
        segmentos_a_json(segmentos, args.json)

    # Mostrar preview
    for seg in segmentos[:5]:
        print(f"  [{seg['inicio']:6.1f}s -> {seg['fin']:6.1f}s] {seg['texto']}")
    if len(segmentos) > 5:
        print(f"  ... y {len(segmentos) - 5} segmentos más")
