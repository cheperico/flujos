"""
ai_media — Procesamiento de medios con IA para el proyecto Flujos.

Módulos:
  - ollama_client: Cliente compartido para modelos de visión (Ollama)
  - transcribe: Transcripción de audio a texto con faster-whisper
  - image_analysis: Extracción de palabras clave desde imágenes (Ollama visión)
  - video_analysis: Extracción de palabras clave desde videos (frames + visión)
  - batch_selector: Identificación y selección de la mejor imagen de una tanda
"""

from . import ollama_client
from . import transcribe
from . import image_analysis
from . import video_analysis
from . import batch_selector

__all__ = ["ollama_client", "transcribe", "image_analysis", "video_analysis", "batch_selector"]
