"""
ai_media — Procesamiento de medios con IA para el proyecto Flujos.

Módulos:
  - ollama_client: Cliente compartido para modelos de visión (Ollama)
  - transcribe: Transcripción de audio a texto con faster-whisper
  - transcribe_media: Transcripción desde la DB (awareness de media)
  - image_analysis: Extracción de palabras clave desde imágenes (Ollama visión)
  - video_analysis: Extracción de palabras clave desde videos (frames + visión)
  - analyze_video: Scene-change detection + análisis visual de video
  - tag_images: Taggear imágenes (modo DB o sidecar)
  - batch_selector: Identificación y selección de la mejor imagen de una tanda
  - clustering: Agrupamiento por tags/embeddings
  - generate_embeddings: Embeddings vectoriales (nomic-embed-text)
  - proxy: Redimensiona imágenes a ~2MP para procesamiento IA
"""

from . import ollama_client
from . import transcribe
from . import transcribe_media
from . import image_analysis
from . import video_analysis
from . import analyze_video
from . import tag_images
from . import batch_selector
from . import clustering
from . import generate_embeddings
from . import proxy

__all__ = [
    "ollama_client", "transcribe", "transcribe_media",
    "image_analysis", "video_analysis", "analyze_video",
    "tag_images", "batch_selector", "clustering",
    "generate_embeddings", "proxy",
]
