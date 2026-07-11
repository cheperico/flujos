---
name: ia-media
description: Procesamiento de medios con IA — transcripción de audio (faster-whisper), análisis de imágenes y videos con modelos de visión (Ollama), y selección inteligente de imágenes.
---

# Skill: IA para medios audiovisuales

## Alcance
Este skill cubre el uso de modelos de IA (Ollama para visión, faster-whisper para
audio) para procesar, analizar y seleccionar medios en el proyecto **Flujos**.

## Stack

| Componente | Tecnología | Uso |
|------------|-----------|-----|
| Visión | Ollama + modelos (qwen2.5vl, moondream, llama3.2-vision, gemma4) | Keywords, descripción, clasificación de imágenes y videos |
| Audio | faster-whisper 1.2.1 | Transcripción de audio a texto |
| Video | ffmpeg + Ollama visión | Extracción de frames + análisis |
| Cliente Python | `ollama` 0.6.2 | Comunicación con Ollama |

## Módulos disponibles

Todos los módulos están en `scripts/ai_media/`:

| Módulo | Funcionalidad |
|--------|--------------|
| `ollama_client.py` | Cliente compartido para modelos Ollama (visión y texto) |
| `transcribe.py` | Transcripción de audio a texto con faster-whisper |
| `image_analysis.py` | Keywords, descripción y clasificación de imágenes |
| `video_analysis.py` | Keywords y descripción de videos (frames + visión) |
| `batch_selector.py` | Selección de la mejor imagen de una tanda |

## Modelos recomendados

### Visión (Ollama)

| Modelo | Tamaño | Cuándo usarlo |
|--------|--------|--------------|
| `moondream:latest` | 1.7 GB | Por defecto para keywords de imágenes — rápido y preciso |
| `qwen2.5vl:latest` | 6.0 GB | Cuando se necesita máxima calidad en descripción |
| `qwen2.5vl:3b` | 3.2 GB | Alternativa liviana a qwen2.5vl |
| `llama3.2-vision:latest` | 7.8 GB | Buena calidad general |
| `gemma4:e4b` | 9.6 GB | Multimodal, para análisis complejos |

### Transcripción (faster-whisper)

| Modelo | Tamaño | Cuándo usarlo |
|--------|--------|--------------|
| `tiny` | ~150 MB | Pruebas rápidas, poca precisión |
| `base` | ~300 MB | Balance calidad/velocidad (default) |
| `small` | ~500 MB | Buena precisión |
| `medium` | ~1.5 GB | Alta precisión |
| `large` | ~3 GB | Máxima precisión |

## Uso desde Python

### Transcripción de audio
```python
from scripts.ai_media.transcribe import transcribir_audio, segmentos_a_srt

segmentos, info = transcribir_audio("audio.wav", modelo="small")
print(f"Idioma: {info.language}")

# Exportar
segmentos_a_srt(segmentos, "transcripcion.srt")
segmentos_a_txt(segmentos, "transcripcion.txt")

# Texto completo
from scripts.ai_media.transcribe import obtener_texto_completo
texto = obtener_texto_completo(segmentos)
```

### Palabras clave de una imagen
```python
from scripts.ai_media.image_analysis import extraer_keywords

keywords = extraer_keywords("foto.jpg", modelo="moondream:latest")
# -> ["atardecer", "playa", "mar", "palmeras", "cielo", "nubes"]
```

### Palabras clave de un video
```python
from scripts.ai_media.video_analysis import analizar_video_keywords

resultado = analizar_video_keywords("video.mp4", modelo="moondream:latest")
# resultado["keywords"] -> ["gente", "playa", "ola", "sol"]

# Control de frames
resultado = analizar_video_keywords(
    "video.mp4",
    fps=1.0,           # 1 frame por segundo
    max_frames=30,      # máximo 30 frames
)
```

### Seleccionar mejor imagen de una tanda
```python
from scripts.ai_media.batch_selector import seleccionar_mejor_imagen, seleccionar_mejores_n

# Por calidad visual
mejor = seleccionar_mejor_imagen(["f1.jpg", "f2.jpg", "f3.jpg"], criterio="calidad")
print(mejor["ruta"], mejor["razon"])

# Por tema
mejor = seleccionar_mejor_imagen(
    ["f1.jpg", "f2.jpg"],
    criterio="tema",
    tema="paisaje de montaña con nieve"
)

# Top N
top3 = seleccionar_mejores_n(imagenes, n=3)
```

### Cliente Ollama directo
```python
from scripts.ai_media.ollama_client import OllamaVision, OllamaTexto

vision = OllamaVision(modelo="qwen2.5vl:latest")
desc = vision.analizar_imagen("foto.jpg", "Describí esta imagen")

texto = OllamaTexto(modelo="qwen3.5:9b")
respuesta = texto.consultar("Resumí este texto: ...", sistema="Sé conciso.")
```

## Línea de comandos

```bash
# Transcripción
python -m scripts.ai_media.transcribe audio.wav --modelo small --srt salida.srt --txt salida.txt

# Keywords de imágenes (una o varias)
python -m scripts.ai_media.image_analysis foto1.jpg foto2.jpg
python -m scripts.ai_media.image_analysis foto.jpg --action describir
python -m scripts.ai_media.image_analysis foto.jpg --action clasificar

# Keywords de video
python -m scripts.ai_media.video_analysis video.mp4 --modelo moondream:latest
python -m scripts.ai_media.video_analysis video.mp4 --action describir

# Selección de mejor imagen
python -m scripts.ai_media.batch_selector *.jpg --criterio calidad
python -m scripts.ai_media.batch_selector *.jpg --criterio tema --tema "paisaje natural"
python -m scripts.ai_media.batch_selector *.jpg --criterio calidad --n 3
```

## Buenas prácticas

- **Elegí el modelo según la tarea**: `moondream` para keywords rápidas,
  `qwen2.5vl` para descripciones detalladas.
- **Temperatura baja** (0.1-0.2) para keywords o clasificación; más alta (0.3-0.5)
  para descripciones creativas.
- **Videos largos**: aumentá `fps` para capturar más dinámica o reducí
  `max_frames` para procesar más rápido.
- **Manejo de errores**: todos los módulos wrappean errores y devuelven
  resultados parciales con campo `"error"`.
- **Frames temporales**: `video_analysis.py` limpia automáticamente los frames
  extraídos. Usá `--keep-frames` para depuración.

## Integración con TouchDesigner

Los módulos se pueden importar directamente desde un Script DAT en TouchDesigner:

```python
# En un Script DAT de TouchDesigner
import sys
sys.path.insert(0, 'C:\\Users\\Federico\\Documents\\OpenCode\\Flujos')

from scripts.ai_media.image_analysis import extraer_keywords
from scripts.ai_media.transcribe import transcribir_audio

# Se puede ejecutar en un thread separado para no bloquear el render
```

## Dependencias

```bash
# Instaladas
pip install faster-whisper ollama pillow tqdm pydantic

# Opcionales (para mejor logging)
pip install rich
```
