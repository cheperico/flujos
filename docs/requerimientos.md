# Requerimientos del proyecto Flujos

Todo lo necesario para correr el pipeline de ingesta, enriquecimiento y
exportación de la instalación interactiva Buenos Aires → Tucumán.

---

## 1. Python 3.13+

```powershell
# Verificar versión
python --version
# Debería decir Python 3.13.x
```

> El proyecto usa Python 3.13.14. Versiones >=3.10 deberían funcionar,
> pero no están testeadas.

---

## 2. Programas externos

### ffmpeg + ffprobe (>= 6.0)

```powershell
# Descargar: https://www.gyan.dev/ffmpeg/builds/ (release full build)
# Descomprimir en C:\ffmpeg\ y agregar al PATH:
#   Panel de Control → Sistema → Configuración avanzada → Variables de entorno
#   Agregar C:\ffmpeg\bin\ a PATH

# Verificar:
ffmpeg -version
ffprobe -version
```

Usado para: extraer metadata de videos/audios, content_hash de videos,
scene detection, transcoding, thumbnails.

### ExifTool (>= 13.0)

```powershell
# Descargar: https://exiftool.org/
# Instalar en C:\Program Files\exiftool.exe  (renombrar exiftool(-k).exe → exiftool.exe)
# O usar la version de digiKam:
#   https://www.digikam.org/download/
#   → C:\Program Files\digiKam\exiftool.exe

# Verificar:
exiftool -ver
```

Usado para: extraer EXIF/IPTC/XMP de imágenes y videos (GPS, cámara,
timestamp, metadatos 360°).

### Ollama (>= 0.31)

```powershell
# Descargar e instalar: https://ollama.com/download
# Ollama corre como servicio en segundo plano.

# Verificar:
ollama --version

# Modelos necesarios (instalar los que se vayan a usar):
ollama pull qwen2.5vl:latest       # Visión + lenguaje (7b, ~6 GB)
ollama pull moondream              # Visión rápido y pequeño (~1.7 GB)
ollama pull nomic-embed-text       # Embeddings vectoriales (~274 MB)
ollama pull deepseek-r1:latest     # Razonamiento (~5.2 GB)
ollama pull qwen3.5:9b             # Texto (~6.6 GB)

# Verificar que el servicio responda:
curl http://localhost:11434/api/tags
```

> Todos los modelos instalados se listan desde el TUI con:
> `python flujos.py` → `3. Mejorar DB` → se verifica automáticamente.

---

## 3. Librerías Python

### Instalación rápida (todo junto)

```powershell
pip install Pillow webcolors tqdm python-osc ollama faster-whisper numpy folium imagehash
```

### Instalación detallada (por librería)

| Librería | Comando | Versión | Uso |
|----------|---------|---------|-----|
| **Pillow** | `pip install Pillow` | >=10.0 | Procesamiento de imágenes, extracción de colores, proxy para IA |
| **webcolors** | `pip install webcolors` | >=1.13 | Nombres de color CSS3 en español |
| **tqdm** | `pip install tqdm` | >=4.60 | Barras de progreso en terminal |
| **python-osc** | `pip install python-osc` | >=1.8 | Comunicación OSC con TouchDesigner |
| **ollama** | `pip install ollama` | >=0.3 | Cliente Python para Ollama (modelos de visión/texto/embeddings) |
| **faster-whisper** | `pip install faster-whisper` | >=1.0 | Transcripción de audio/video (local, GPU si hay CUDA) |
| **numpy** | `pip install numpy` | >=1.24 | Clustering y similitud de embeddings |
| **folium** | `pip install folium` | >=0.15 | Mapas interactivos (HTML Leaflet) |
| **imagehash** | `pip install imagehash` | >=4.3 | Hash perceptual para limpieza de tandas |

### Dependencias automáticas

Las siguientes se instalan como dependencia de las de arriba (no hace falta
instalarlas explícitamente):

| Librería | Instalada por | Para qué se usa en el proyecto |
|----------|---------------|-------------------------------|
| `branca` | folium | Mapas de colores en folium |
| `torch` | faster-whisper | Motor de inferencia de whisper (pesado: ~2 GB) |
| `ctranslate2` | faster-whisper | Inferencia optimizada de whisper |
| `jinja2` | folium | Template de mapas HTML |
| `numpy` | faster-whisper, folium | (ya listada arriba) |

### Verificar instalación

```powershell
python -c "import PIL, webcolors, tqdm, pythonosc, ollama, faster_whisper, numpy, folium, imagehash; print('Todas las librerias OK')"
```

---

## 4. TouchDesigner (solo para la instalación)

```powershell
# Descargar: https://derivative.ca/download
# Versión: 2022.28080 o superior (no probado en versiones anteriores)
```

Usado como motor de reproducción audiovisual de la instalación.
Recibe datos vía OSC desde `scripts/puente_td.py`.

---

## 5. Notas sobre CUDA (opcional)

Si tenés GPU NVIDIA, faster-whisper puede usar CUDA para acelerar
transcripciones. Necesitás:

```powershell
# 1. NVIDIA drivers actualizados
# 2. CUDA Toolkit 12.x: https://developer.nvidia.com/cuda-downloads
# 3. CuDNN: https://developer.nvidia.com/cudnn

# Verificar que PyTorch vea la GPU:
python -c "import torch; print(f'CUDA disponible: {torch.cuda.is_available()}')"
# → Debería decir True

# Si no, reinstalar PyTorch con CUDA:
pip uninstall torch -y
pip install torch --index-url https://download.pytorch.org/whl/cu121
```
