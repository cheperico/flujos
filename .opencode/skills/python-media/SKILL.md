---
name: python-media
description: Python para procesamiento multimedia — librerías estándar y de terceros para manipulación de archivos, metadatos, ETL y automatización de pipelines de medios.
---

# Skill: Python para multimedia

## Alcance
Este skill cubre el uso de Python en el proyecto **Flujos** para scripting de
procesamiento, análisis, transformación y carga de archivos multimedia.

## Librerías recomendadas

| Librería | Propósito | Instalación |
|----------|-----------|-------------|
| `sqlite3` | Base de datos de metadatos | built-in |
| `json` / `csv` | Formatos de datos | built-in |
| `hashlib` | SHA-256 para identificar archivos | built-in |
| `pathlib` | Manejo de rutas | built-in |
| `subprocess` | Llamar ffmpeg, exiftool | built-in |
| `Pillow` | Lectura de imágenes, metadatos EXIF | `pip install Pillow` |
| `mutagen` | Metadatos de audio | `pip install mutagen` |
| `tqdm` | Barras de progreso | `pip install tqdm` |
| `rich` | Logging y tablas en consola | `pip install rich` |
| `pydantic` | Validación de schemas | `pip install pydantic` |

## Operaciones principales

### 1. Escaneo de archivos multimedia
```python
from pathlib import Path
import hashlib

EXT_VIDEO = {'.mp4', '.mov', '.avi', '.mxf', '.mkv'}
EXT_IMAGEN = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.exr'}
EXT_AUDIO = {'.wav', '.mp3', '.aac', '.flac', '.ogg'}
EXT_TEXTO = {'.txt', '.md', '.json', '.csv', '.xml', '.srt'}

def escanear_medios(directorio):
    encontrados = []
    for f in Path(directorio).rglob("*"):
        if f.suffix.lower() in EXT_VIDEO | EXT_IMAGEN | EXT_AUDIO | EXT_TEXTO:
            encontrados.append(f)
    return encontrados

def sha256_archivo(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(65536), b''):
            h.update(bloque)
    return h.hexdigest()
```

### 2. Clasificación por tipo de medio
```python
def clasificar_archivo(ruta):
    ext = Path(ruta).suffix.lower()
    if ext in EXT_VIDEO:
        return 'video'
    if ext in EXT_IMAGEN:
        return 'imagen'
    if ext in EXT_AUDIO:
        return 'audio'
    if ext in EXT_TEXTO:
        return 'texto'
    return 'desconocido'
```

### 3. Pipeline ETL completo (esqueleto)
```python
import sqlite3
from pathlib import Path

def pipeline_ingesta(directorio_medio, db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    archivos = escanear_medios(directorio_medio)

    for archivo in archivos:
        ruta = str(archivo)
        tipo = clasificar_archivo(archivo)
        sha = sha256_archivo(ruta)
        stats = archivo.stat()

        cur.execute("""
            INSERT OR IGNORE INTO medios
                (archivo, tipo, sha256, tamano_bytes, fecha_creacion, fecha_modificacion)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            ruta, tipo, sha, stats.st_size,
            _fecha_iso(stats.st_ctime),
            _fecha_iso(stats.st_mtime)
        ))

    conn.commit()
    conn.close()

def _fecha_iso(timestamp):
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).isoformat()
```

### 4. Wrapper para llamar herramientas externas
```python
import subprocess, json, shutil

class HerramientasMedia:
    def __init__(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        self.exiftool = shutil.which("exiftool")

    def ffprobe(self, ruta):
        cmd = [self.ffprobe, "-v", "quiet", "-print_format", "json",
               "-show_format", "-show_streams", ruta]
        return json.loads(subprocess.check_output(cmd).decode())

    def exiftool(self, ruta):
        cmd = [self.exiftool, "-j", ruta]
        return json.loads(subprocess.check_output(cmd).decode())[0]

    def disponible(self):
        return all([self.ffmpeg, self.ffprobe, self.exiftool])
```

## Buenas prácticas
- Usar `pathlib.Path` en vez de `os.path`
- Usar `shutil.which()` para verificar herramientas externas
- Archivos grandes: leer en bloques (ej: SHA-256)
- Logging con `rich.console.Console` para feedback visual
- Separar ETL en etapas: extraer → transformar → cargar
- Usar `__name__ == "__main__"` para scripts ejecutables
