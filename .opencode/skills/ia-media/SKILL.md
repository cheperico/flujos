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

## Stack

| Componente | Tecnología | Uso |
|------------|-----------|-----|
| Visión | Ollama + modelos (qwen2.5vl, moondream, llama3.2-vision, gemma4) | Keywords, descripción, clasificación, OCR |
| Audio | faster-whisper 1.2.1 | Transcripción de audio a texto |
| Video | ffmpeg + Ollama visión | Extracción de frames + análisis |
| Texto | Ollama modelos de lenguaje | Post-procesamiento, clasificación, razonamiento |
| Embeddings | `nomic-embed-text` / `-v2-moe` | Búsqueda semántica |
| Cliente Python | librería `ollama` 0.6.2 | Comunicación con Ollama |

## Modelos de visión disponibles

| Modelo | Tamaño | Ideal para |
|--------|--------|------------|
| `moondream:latest` | 1.7 GB | Keywords rápidas, clasificación simple, primera pasada |
| `qwen2.5vl:3b` | 3.2 GB | Análisis balance calidad/velocidad, OCR básico |
| `qwen2.5vl:latest` | 6.0 GB | Descripción detallada, OCR fino, razonamiento visual |
| `llama3.2-vision:latest` | 7.8 GB | Análisis visual general de alta calidad |
| `gemma4:e4b` | 9.6 GB | Análisis multimodal complejo |

## Estrategias de prompting para visión

### Keywords
```
Prompt: "Describí esta imagen con 5-10 palabras clave separadas por coma.
         Solo las palabras clave, sin puntuación ni explicación."
```

### Descripción detallada (para metadatos)
```
Prompt: "Describí esta imagen con precisión. Incluí:
         - Tipo de escena (interior/exterior/naturaleza/urbano)
         - Elementos principales y secundarios
         - Colores dominantes y paleta general
         - Iluminación (natural/artificial, dirección, calidad)
         - Composición (planos, simetría, profundidad)
         - Estado de ánimo o atmósfera
         Respuesta en español."
```

### Clasificación
```
Prompt: "Clasificá esta imagen en UNA categoría: [naturaleza, urbano,
         retrato, abstracto, documental, nocturno]. Solo el nombre."
```

### Análisis de color
```
Prompt: "Analizá los colores dominantes. Decime:
         1. Color principal
         2. Paleta (cálida/fría/neutra/mixta)
         3. Contraste (alto/medio/bajo)
         4. Saturación general (alta/media/baja)"
```

## Uso desde Python

### 1. Transcripción de audio
```python
from scripts.ai_media.transcribe import transcribir_audio, segmentos_a_srt

segmentos, info = transcribir_audio("audio.wav", modelo="small")
print(f"Idioma: {info.language}")

# Exportar
segmentos_a_srt(segmentos, "transcripcion.srt")
segmentos_a_txt(segmentos, "transcripcion.txt")
texto = obtener_texto_completo(segmentos)
```

### 2. Análisis de imágenes
```python
from scripts.ai_media.image_analysis import extraer_keywords, describir_imagen, clasificar_imagen

# Keywords rápidas (moondream recomendado)
keywords = extraer_keywords("foto.jpg", modelo="moondream:latest")

# Descripción detallada (qwen2.5vl recomendado)
desc = describir_imagen("foto.jpg", modelo="qwen2.5vl:latest")

# Clasificación por categorías
categoria = clasificar_imagen("foto.jpg", categorias=["naturaleza", "urbano", "gente"])
```

### 3. Análisis de videos
```python
from scripts.ai_media.video_analysis import analizar_video_keywords, analizar_video_descripcion

# Keywords generales
resultado = analizar_video_keywords("video.mp4", modelo="moondream:latest")

# Descripción narrativa
resultado = analizar_video_descripcion("video.mp4")

# Control de frames
resultado = analizar_video_keywords("video.mp4", fps=1.0, max_frames=30)
```

### 4. Selección inteligente de imágenes
```python
from scripts.ai_media.batch_selector import seleccionar_mejor_imagen, seleccionar_mejores_n

# Por calidad visual
mejor = seleccionar_mejor_imagen(["f1.jpg", "f2.jpg", "f3.jpg"], criterio="calidad")

# Por tema
mejor = seleccionar_mejor_imagen(
    ["f1.jpg", "f2.jpg"],
    criterio="tema",
    tema="paisaje de montaña con nieve"
)

# Top N
top3 = seleccionar_mejores_n(imagenes, n=3)
```

### 5. Cliente directo Ollama
```python
from scripts.ai_media.ollama_client import OllamaVision, OllamaTexto

# Visión con temperatura controlada
vision = OllamaVision(modelo="qwen2.5vl:latest", temperatura=0.1)
desc = vision.analizar_imagen("foto.jpg", "Describí esta imagen")

# Texto
texto = OllamaTexto(modelo="qwen3.5:9b")
respuesta = texto.consultar("Resumí:", sistema="Sé conciso.")
```

### 6. Embeddings
```python
import ollama

def embedding(texto, modelo="nomic-embed-text"):
    resp = ollama.embeddings(model=modelo, prompt=texto)
    return resp["embedding"]
```

## Guía rápida de selección

| Tarea | Recomendado |
|-------|-------------|
| Keywords rápidas | `moondream` |
| Descripción detallada | `qwen2.5vl:latest` |
| OCR / texto en imagen | `qwen2.5vl:latest` |
| Análisis de color | `qwen2.5vl:3b` |
| Transcripción audio | faster-whisper `small` o `medium` |
| Clasificar texto | `qwen3.5:4b` |
| Embeddings | `nomic-embed-text` |

## Buenas prácticas

- **Prompt específico > genérico**: cuanto más detalle en el prompt, mejor resultado
- **Temperatura baja** (0.1-0.2) para clasificación y keywords
- **Temperatura media** (0.3-0.5) para descripciones
- **Modelo rápido primero**: moondream para primera pasada, qwen2.5vl para profundizar
- **Redimensionar imágenes** >2000px antes de enviar
- **Una tarea por llamada**: no mezclar keywords + descripción + clasificación
- **Fallback**: si un modelo da resultados pobres, probar con uno más grande
- **Errores**: todos los módulos devuelven resultados parciales con campo `"error"`
- **Frames**: `video_analysis.py` limpia automáticamente; `--keep-frames` para debug

## Integración con TouchDesigner

```python
# En un Script DAT de TouchDesigner
import sys
sys.path.insert(0, 'C:\\Users\\Federico\\Documents\\OpenCode\\Flujos')

from scripts.ai_media.image_analysis import extraer_keywords
from scripts.ai_media.transcribe import transcribir_audio

# Ejecutar en thread separado para no bloquear el render
```

## Dependencias

```bash
# Instaladas
pip install faster-whisper ollama pillow tqdm pydantic
# Opcionales
pip install rich
```
