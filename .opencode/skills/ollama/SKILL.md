---
name: ollama
description: Ollama — modelos de IA locales para análisis de imágenes, texto, audio y generación de embeddings. Inferencia multimodal, gestión de modelos e integración Python.
---

# Skill: Ollama para análisis de medios

## Alcance
Este skill cubre el uso de Ollama en el proyecto **Flujos** para analizar
medios multimedia con modelos de IA locales: descripción de imágenes,
clasificación de texto, embeddings para búsquedas semánticas y más.

## Modelos disponibles

| Modelo | Tamaño | Capacidades |
|--------|--------|-------------|
| `qwen2.5vl:latest` | 6.0 GB | Visión + texto (descripción detallada, OCR) |
| `qwen2.5vl:3b` | 3.2 GB | Visión + texto (liviano) |
| `llama3.2-vision:latest` | 7.8 GB | Visión + texto |
| `moondream:latest` | 1.7 GB | Visión (rápido) |
| `gemma4:e4b` | 9.6 GB | Multimodal |
| `qwen3.5:9b` / `qwen3.5:4b` | 6.6 / 3.4 GB | Texto |
| `deepseek-r1:latest` | 5.2 GB | Razonamiento |
| `llama3.1:8b` / `llama3.2:3b` | 4.9 / 2.0 GB | Texto propósito general |
| `nomic-embed-text` / `-v2-moe` | 274 / 957 MB | Embeddings |

## Operaciones principales

### 1. Analizar imagen
```python
import ollama

def describir_imagen(ruta, modelo="qwen2.5vl:3b", prompt="Describí esta imagen en detalle"):
    respuesta = ollama.chat(
        model=modelo,
        messages=[{
            "role": "user",
            "content": prompt,
            "images": [ruta]
        }]
    )
    return respuesta["message"]["content"]
```

### 2. Analizar texto
```python
def analizar_texto(texto, modelo="qwen3.5:4b", instrucciones="Resumí este texto"):
    respuesta = ollama.chat(
        model=modelo,
        messages=[
            {"role": "system", "content": instrucciones},
            {"role": "user", "content": texto}
        ]
    )
    return respuesta["message"]["content"]
```

### 3. Embeddings
```python
def obtener_embedding(texto, modelo="nomic-embed-text"):
    respuesta = ollama.embeddings(model=modelo, prompt=texto)
    return respuesta["embedding"]
```

### 4. Análisis batch de medios
```python
from pathlib import Path
import ollama

def analizar_lote(directorio, modelo_vision, modelo_texto):
    resultados = []

    for img in Path(directorio).glob("*.jpg"):
        desc = ollama.chat(model=modelo_vision, messages=[{
            "role": "user", "content": "Describí esta imagen",
            "images": [str(img)]
        }])["message"]["content"]

        # Clasificar la descripción con modelo de texto
        clasif = ollama.chat(model=modelo_texto, messages=[{
            "role": "user",
            "content": f"Clasificá esta descripción en una categoría:\n{desc}"
        }])["message"]["content"]

        resultados.append({"archivo": img.name, "descripcion": desc, "categoria": clasif})

    return resultados
```

### 5. Verificar estado de Ollama
```python
import subprocess

def ollama_ps():
    """Modelos actualmente cargados en memoria."""
    result = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
    return result.stdout

def ollama_version():
    result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
    return result.stdout.strip()
```

## Buenas prácticas
- La primera llamada a un modelo tarda porque lo carga en memoria
- Para respuestas consistentes, usar `temperature=0` en análisis
- Los modelos de visión aceptan rutas de archivo locales como `images`
- No enviar imágenes muy grandes (redimensionar a ~1024px si es necesario)
- Si hay poca RAM/VRAM, preferir modelos cuantizados (Q4, Q8)
- Monitorear con `ollama ps` qué modelos están en memoria
