---
name: exiftools
description: ExifTool — lectura/escritura de metadatos EXIF, IPTC, XMP en imágenes, videos y audios. Extracción de datos de cámara, geolocalización, fechas, descripciones y palabras clave.
---

# Skill: ExifTool para metadatos

## Alcance
Este skill cubre el uso de ExifTool en el proyecto **Flujos** para extraer y
manipular metadatos de archivos multimedia.

## Operaciones principales

### 1. Extraer todos los metadatos
```bash
exiftool -json "archivo.jpg"
exiftool -j "archivo.jpg"                # shorthand

# Solo ciertos tags
exiftool -j -DateTimeOriginal -Model -GPSLatitude -GPSLongitude "archivo.jpg"
```

### 2. Extraer con Python
```python
import subprocess, json

def exiftool_metadata(ruta):
    cmd = ["exiftool", "-j", ruta]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return data[0] if data else {}
```

### 3. Tags clave por tipo de archivo

**Imágenes:**
```
EXIF: DateTimeOriginal     → fecha y hora de disparo
EXIF: Make / Model         → cámara
EXIF: ISOSpeedRatings      → ISO
EXIF: FNumber              → apertura
EXIF: ExposureTime         → velocidad de obturación
EXIF: FocalLength          → distancia focal
EXIF: GPSLatitude/GPSLongitude → geolocalización
IPTC: Keywords             → palabras clave (array)
IPTC: Caption-Abstract     → descripción
IPTC: By-line              → autor
XMP:  Title                → título
XMP:  Description          → descripción
```

**Videos:**
```
QuickTime: CreateDate      → fecha de creación
QuickTime: Duration        → duración
QuickTime: ImageWidth/Height → resolución
QuickTime: VideoCodecType  → codec
```

**Audios:**
```
QuickTime: Duration
QuickTime: AudioChannels
QuickTime: AudioSampleRate
```

### 4. Parseo de geolocalización
```python
def geo_a_decimal(gps_ref, gps_coord):
    """Convierte GPS EXIF (grados, minutos, segundos) a decimal."""
    if not gps_coord:
        return None
    ref = -1 if gps_ref in ('S', 'W') else 1
    deg, min, sec = [float(x) for x in gps_coord]
    return ref * (deg + min/60 + sec/3600)

# Uso:
lat = geo_a_decimal(meta.get('GPSLatitudeRef'), meta.get('GPSLatitude'))
lon = geo_a_decimal(meta.get('GPSLongitudeRef'), meta.get('GPSLongitude'))
```

### 5. Batch processing
```python
from pathlib import Path
import subprocess, json

def scan_metadatos(directorio, patron="*.*"):
    archivos = list(Path(directorio).rglob(patron))
    resultados = []
    for f in archivos:
        try:
            meta = exiftool_metadata(str(f))
            meta["_ruta"] = str(f)
            resultados.append(meta)
        except:
            pass
    return resultados
```

## Buenas prácticas
- Usar `-j` (JSON) para integrar fácilmente con Python
- Los tags pueden tener nombres distintos según el formato; usar `-G` para
  agrupar por grupo (ej: `EXIF:DateTimeOriginal`)
- ExifTool es de solo lectura en este skill; no se escribe metadata
- Para archivos muy grandes, considerar leer solo tags específicos para
  mejorar performance
- Algunos metadatos pueden no estar presentes en todos los archivos; siempre
  verificar con `.get()` en Python
