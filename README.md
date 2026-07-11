# Flujos

Proyecto de instalación interactiva. Procesamiento, gestión y flujo de medios
audiovisuales (video, imágenes, audio, texto) con TouchDesigner como motor
principal.

## Stack

| Componente | Versión verificada | Propósito |
|---|---|---|
| **Python** | 3.13+ | Scripting principal (ETL, extracción de metadatos, color) |
| **ffmpeg** | 8.1.2+ | Análisis y transcodificación de video/audio |
| **ExifTool** | 13.58+ | Lectura de metadatos EXIF/IPTC/XMP en imágenes |
| **SQLite** | 3.x (incluido en Python) | Base de datos embebida |

## Dependencias del sistema

### ffmpeg

Descargar desde [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (build completo)
o desde [ffmpeg.org](https://ffmpeg.org/). Asegurarse de que `ffmpeg` y
`ffprobe` estén en el PATH del sistema.

Verificar:
```bash
ffmpeg -version
ffprobe -version
```

### ExifTool

Descargar desde [exiftool.org](https://exiftool.org/). En Windows se puede
instalar como parte de [digiKam](https://www.digikam.org/) en
`C:\Program Files\digiKam\exiftool.exe`, o descargar el ejecutable
independiente y agregarlo al PATH.

El script `ingest.py` busca automáticamente en ubicaciones comunes. También
se puede especificar la ruta con `--exiftool`.

Verificar:
```bash
exiftool -ver
```

## Dependencias de Python

Instalar con pip:

```bash
pip install Pillow tqdm webcolors
```

| Librería | Versión verificada | Propósito |
|---|---|---|
| **Pillow** | 12.2+ | Procesamiento de imágenes (content hash, colores dominantes) |
| **tqdm** | 4.68+ | Barras de progreso en scripts |
| **webcolors** | 25.10+ | Nombres de colores CSS estándar |
| **mutagen** | — | (Futuro) Metadatos de audio |

No requieren instalación (incluidas en Python estándar):
- `sqlite3` — Base de datos
- `hashlib` — SHA-256
- `xml.etree.ElementTree` — Parseo de XML SONY
- `json` — Parseo de metadatos
- `argparse` — Interfaz de línea de comandos
- `subprocess` — Llamadas a ffmpeg, exiftool, ffprobe
- `datetime` — Manejo de timestamps y husos horarios
- `re` — Expresiones regulares

## Scripts

### `scripts/ingest.py`

Escanea una carpeta de medios, extrae metadatos y los ingiere en la base de
datos SQLite.

```bash
# Ingest básico
python scripts/ingest.py --root D:/Flujos/Ingesta_1

# Con ExifTool (para metadatos EXIF y GPS)
python scripts/ingest.py --root D:/Flujos/Ingesta_1 --exiftool "C:/Program Files/digiKam/exiftool.exe"

# Modo verbose (debug logging)
python scripts/ingest.py --root D:/Flujos/Ingesta_1 --verbose

# Solo escanear (no escribe en DB)
python scripts/ingest.py --root D:/Flujos/Ingesta_1 --dry-run

# Calcular content_hash de videos (lento en archivos grandes)
python scripts/ingest.py --root D:/Flujos/Ingesta_1 --compute-video-hash
```

**Qué hace:**
1. Escanea recursivamente todos los archivos en `--root`
2. Por cada archivo calcula SHA-256 (file_hash)
3. Si el archivo ya existe en DB → lo salta
4. Detecta el tipo (image, video, audio, etc.)
5. Extrae metadatos según tipo:
   - **Imagen**: EXIF con ExifTool (GPS, fecha, cámara, autor) + colores dominantes
   - **Video**: ffprobe + XML sidecar SONY si existe
   - **Audio**: ffprobe
6. Calcula content_hash (contenido puro sin metadatos)
7. Detecta contenido duplicado con diferente metadata
8. Inserta todo en la base de datos

### `scripts/color_utils.py`

Módulo auxiliar para extracción y naming de colores. Usado por `ingest.py`.

- Extrae los 3 colores dominantes de una imagen (cuantización con Pillow)
- Asigna nombres CSS en español (140+ colores)
- Asigna nombres básicos (11 categorías: rojo, azul, verde, etc.)

### `scripts/check_gps.py`

(Prueba) Verifica qué imágenes tienen GPS en una carpeta.

### `scripts/check_db.py`

(Prueba) Inspecciona el contenido de la base de datos.

## Base de datos

La base de datos SQLite se crea automáticamente en `db/flujos.db` con el
schema definido en `db/schema.sql`.

### Tabla principal: `media`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER | Clave primaria |
| `filename_original` | TEXT | Nombre original del archivo |
| `filepath_absoluto` | TEXT | Ruta completa en disco |
| `filepath_relativo` | TEXT | Ruta relativa a la raíz de ingest |
| `carpeta` | TEXT | Nombre de la carpeta contenedora |
| `type` | TEXT | image, video, audio, text, other |
| `subtype` | TEXT | 360, entrevista, paisaje, etc. |
| `size_bytes` | INTEGER | Tamaño del archivo |
| `file_hash` | TEXT | SHA-256 del archivo completo (UNIQUE) |
| `content_hash` | TEXT | SHA-256 del contenido puro (sin metadatos) |
| `sidecar_xml` | TEXT | Ruta al XML sidecar SONY |
| `sidecar_parsed` | INTEGER | 1 si ya se procesó el XML |
| `sidecar_hash` | TEXT | SHA-256 del XML |
| `timestamp_original` | TEXT | Fecha/hora tal cual del archivo |
| `timestamp_utc` | TEXT | Normalizado a UTC |
| `timezone_note` | TEXT | Cómo se determinó la zona horaria |
| `latitude` | REAL | Latitud (WGS84) |
| `longitude` | REAL | Longitud (WGS84) |
| `altitude` | REAL | Altitud en metros |
| `geolocation_source` | TEXT | metadata, inferido_tiempo, track_gps, manual |
| `author` | TEXT | Autor del medio |
| `author_source` | TEXT | exif, carpeta, modelo_camara |
| `color_1_hex` | TEXT | Color dominante 1 (hex) |
| `color_1_name_css` | TEXT | Nombre CSS en español |
| `color_1_name_basic` | TEXT | Nombre básico (rojo, azul...) |
| `color_2_hex` | TEXT | Color dominante 2 |
| `color_2_name_css` | TEXT | Nombre CSS |
| `color_2_name_basic` | TEXT | Nombre básico |
| `color_3_hex` | TEXT | Color dominante 3 |
| `color_3_name_css` | TEXT | Nombre CSS |
| `color_3_name_basic` | TEXT | Nombre básico |
| `ingested_at` | TEXT | Fecha de ingestión |
| `updated_at` | TEXT | Fecha de última actualización |

### Tabla secundaria: `media_metadata`

Almacena metadatos variables según el tipo de medio en formato clave-valor:

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER | Clave primaria |
| `media_id` | INTEGER | Referencia a `media.id` |
| `key` | TEXT | Nombre del metadato |
| `value` | TEXT | Valor del metadato |

## Estructura del proyecto

```
/
├── db/
│   ├── flujos.db          # Base de datos SQLite (se crea al ingerir)
│   └── schema.sql         # Schema de la base de datos
├── scripts/
│   ├── __init__.py
│   ├── ingest.py          # Script principal de ingestión
│   ├── color_utils.py     # Utilidades de color
│   ├── check_db.py        # Inspeccionar DB
│   └── check_gps.py       # Verificar GPS en imágenes
├── logs/                  # Logs de ingestión
├── opencode.json          # Configuración del proyecto
├── AGENTS.md              # Documentación de agentes
└── README.md              # Este archivo
```
