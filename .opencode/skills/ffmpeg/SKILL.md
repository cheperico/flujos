---
name: ffmpeg
description: FFmpeg — transcodificación, análisis, extracción de metadata y manipulación de archivos multimedia (video, audio, imágenes). Procesamiento por lote y pipelines.
---

# Skill: FFmpeg para medios

## Alcance
Este skill cubre el uso de FFmpeg en el proyecto **Flujos** para análisis,
conversión y extracción de metadatos de archivos multimedia.

## Operaciones principales

### 1. Análisis de archivos
```bash
# Información detallada (formato, streams, codecs, duración)
ffprobe -v quiet -print_format json -show_format -show_streams "archivo.mp4"

# Duración en segundos
ffprobe -v error -show_entries format=duration -of csv=p=0 "archivo.mp4"

# Resolución, codec, fps
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,codec_name,r_frame_rate -of json "archivo.mp4"

# Metadata general
ffprobe -v error -show_entries format_tags -of json "archivo.mp4"
```

### 2. Extraer metadata con script wrapper (Python)
```python
import subprocess, json

def ffprobe_metadata(ruta):
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        ruta
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)
```

### 3. Transcodificación
```bash
# Video H.264 a H.265 (eficiente)
ffmpeg -i "input.mp4" -c:v libx265 -crf 23 -c:a aac -b:a 128k "output.mp4"

# Crear proxy (720p, liviano)
ffmpeg -i "input.mp4" -vf "scale=-2:720" -c:v libx264 -crf 28 -preset fast "proxy.mp4"

# Extraer audio a WAV
ffmpeg -i "input.mp4" -vn -acodec pcm_s16le "audio.wav"

# Extraer frames como imágenes
ffmpeg -i "input.mp4" -vf "fps=1" "frames/frame_%04d.png"
```

### 4. Obtener duración programáticamente
```python
def duracion_segundos(ruta):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "csv=p=0", ruta]
    return float(subprocess.check_output(cmd).decode().strip())
```

### 5. Batch processing
```python
import subprocess
from pathlib import Path

def transcode_videos(origen, destino, ext=".mp4"):
    for f in Path(origen).rglob(f"*{ext}"):
        out = Path(destino) / f.with_suffix(".hevc.mp4").name
        subprocess.run([
            "ffmpeg", "-i", str(f),
            "-c:v", "libx265", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-y", str(out)
        ])
```

## Buenas prácticas
- Usar `-y` para sobrescribir sin preguntar (en scripts)
- En pipelines grandes, verificar código de retorno: `result.returncode == 0`
- Preferir `-preset fast` para proxies, `-preset medium` para masters
- Para lotes grandes, considerar `tqdm` para barra de progreso
- No re-codificar si no es necesario: `-c copy` para cambio de contenedor
