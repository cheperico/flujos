# Flujos

Instalación interactiva basada en un viaje en bicicleta de Buenos Aires a
Tucumán. Procesamiento, gestión y flujo de medios audiovisuales (video 360°,
imágenes, audio, texto) con SQLite como base de datos central.

**Concepto curatorial:** la deriva. No hay algoritmo fijo. El sistema ofrece
medios según filtros (color, tiempo, lugar, autor) y la navegación emerge de
condiciones externas (un pico de ruido, un grito, el momento presente).

---

## Pipeline

```
Medios crudos → CURACIÓN → INGESTA → INFERENCIA → DB
                                                     ↓
                                              INSTALACIÓN
                                         (consulta la DB por
                                          color, tiempo, lugar,
                                          autor, keywords...)
```

Cada etapa puede correrse total o parcialmente.

---

## Entry point unificado

```powershell
python flujos.py                # Menú interactivo (TUI)
python flujos.py --tui          # Ídem
python flujos.py --help         # Ayuda general
python flujos.py --ayuda        # Ídem
```

### Subcomandos

| Comando | Qué hace |
|---------|----------|
| `ingest --root CARPETA` | Ingerir medios desde una carpeta |
| `query --distinct author --count` | Consultar la base de datos |
| `relocate --new-root CARPETA` | Actualizar rutas si los archivos se mudaron |
| `check-db` | Inspeccionar todos los registros |
| `check-gps` | Revisar qué archivos tienen GPS |
| `undo-ingest` | Deshacer una ingesta por batch ID |

Cada subcomando acepta `--help` para ver sus opciones específicas:

```powershell
python flujos.py query --help     # flags: --columns, --distinct, --key,
                                  #        --count, --where, --search, --limit
python flujos.py ingest --help    # flags: --verbose, --dry-run, --full-hash,
                                  #        --compute-video-hash, --exiftool
python flujos.py relocate --help  # flags: --old-root, --dry-run
```

---

## Scripts

| Script | Propósito | Pipeline |
|--------|-----------|----------|
| `flujos.py` | Entry point unificado con subcomandos y TUI | — |
| `scripts/ingest.py` | Escanea, extrae metadatos e ingiere en DB | Ingesta |
| `scripts/query.py` | Consultas a la DB (columnas, valores, búsqueda) | Consulta |
| `scripts/relocate.py` | Actualiza rutas absolutas cuando los archivos se mudan | Gestión |
| `scripts/color_utils.py` | Extracción y naming de colores (usado por ingest) | Ingesta |
| `scripts/limpiar_tandas.py` | Selección de mejor imagen por tanda con IA | Curación |
| `scripts/mover_descartadas.py` | Mueve imágenes descartadas a otra carpeta | Curación |
| `scripts/check_db.py` | Inspección general de la DB | Consulta |
| `scripts/check_gps.py` | Verifica GPS en archivos | Consulta |
| `scripts/ai_media/tag_images.py` | Etiqueta y describe imágenes con IA | Inferencia |
| `scripts/ai_media/analyze_video.py` | Análisis visual de video (scene detection + IA) | Inferencia |
| `scripts/ai_media/transcribe_media.py` | Transcripción de audio/video con IA | Inferencia |

---

## IA (Procesamiento de medios)

Dos subsistemas de IA complementarios:

### Visión (Ollama)

Usamos modelos de visión de [Ollama](https://ollama.com) para:
- **Etiquetar imágenes** — extraer 5-7 keywords (incluye género fotográfico) + descripción
- **Seleccionar la mejor imagen de una tanda** — evaluar calidad visual
- **Clasificar imágenes** por contenido

#### Instalación

```powershell
# Instalar Ollama (una sola vez)
winget install Ollama.Ollama

# Descargar modelos de visión (según la RAM disponible)
ollama pull moondream:latest          # 1.7 GB — recomendado, el que usamos
ollama pull qwen2.5vl:3b              # 3.2 GB — más preciso, liviano
ollama pull qwen2.5vl:latest          # 6.0 GB — buena calidad
ollama pull llama3.2-vision:latest    # 7.8 GB — buena calidad general
```

> **RAM:** con `moondream:latest` el uso de RAM sube ~40% sobre el idle.
> Modelos más grandes (qwen2.5vl, llama3.2-vision) requieren más RAM.
> Usar `--list-models` en los scripts para ver los modelos instalados.

#### Scripts que usan visión

| Script | Qué hace |
|--------|----------|
| `scripts/ai_media/tag_images.py` | Etiqueta y describe imágenes (DB o sidecar) |
| `scripts/ai_media/analyze_video.py` | Análisis visual de video: scene detection + fotogramas clave con IA |
| `scripts/ai_media/image_analysis.py` | Análisis individual (keywords, descripción, clasificación) |
| `scripts/limpiar_tandas.py` | Selección de mejor imagen por tanda |

#### Uso

```powershell
# Ver modelos disponibles
python scripts/ai_media/tag_images.py --list-models

# Etiquetar con un modelo específico
python scripts/ai_media/tag_images.py --folder D:/Fotos --modelo moondream:latest

# El flag --modelo acepta cualquier modelo instalado en Ollama
```

### Transcripción (faster-whisper)

Usamos [faster-whisper](https://github.com/SYSTRAN/faster-whisper) para
transcribir audios y pistas de audio de videos con timestamps.

#### Instalación

```powershell
pip install faster-whisper
```

Los modelos se descargan automáticamente la primera vez que se usan (tiny ~75 MB,
base ~150 MB, small ~500 MB, medium ~1.5 GB, large-v3 ~3 GB).

#### Scripts que usan transcripción

| Script | Qué hace |
|--------|----------|
| `scripts/ai_media/transcribe_media.py` | Transcripción automática (DB, carpeta o archivo individual) |
| `scripts/ai_media/analyze_video.py` | Análisis visual de video con scene detection + IA |
| `scripts/ai_media/transcribe.py` | Módulo base (exporta SRT/TXT/JSON) |

#### Uso

```powershell
# Transcribir un audio
python scripts/ai_media/transcribe_media.py --file audio.mp3 --modelo base

# Transcribir un video
python scripts/ai_media/transcribe_media.py --file video.mp4 --modelo small
```

---

## Base de datos

Se crea automáticamente en `db/flujos.db`.

### Tabla `media`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | INTEGER | Clave primaria |
| `filename_original` | TEXT | Nombre original del archivo |
| `filepath_absoluto` | TEXT | Ruta completa en disco |
| `filepath_relativo` | TEXT | Ruta relativa a la raíz de ingest |
| `carpeta` | TEXT | Carpeta contenedora |
| `type` | TEXT | image, video, audio, text, other |
| `subtype` | TEXT | 360, entrevista, paisaje, etc. |
| `size_bytes` | INTEGER | Tamaño del archivo |
| `file_hash` | TEXT | Fingerprint único (UNIQUE) |
| `content_hash` | TEXT | Hash del contenido puro |
| `sidecar_xml` | TEXT | Ruta al XML sidecar SONY |
| `sidecar_parsed` | INTEGER | 1 si ya se procesó el XML |
| `sidecar_hash` | TEXT | Hash del XML |
| `timestamp_original` | TEXT | Fecha/hora del archivo |
| `timestamp_utc` | TEXT | Normalizado a UTC |
| `timezone_note` | TEXT | Cómo se determinó la zona horaria |
| `duration_secs` | REAL | Duración en segundos (videos/audios) |
| `latitude` | REAL | Latitud (WGS84) |
| `longitude` | REAL | Longitud (WGS84) |
| `altitude` | REAL | Altitud en metros |
| `geolocation_source` | TEXT | metadata, inferido_tiempo, track_gps, manual |
| `author` | TEXT | Autor del medio |
| `author_source` | TEXT | exif, carpeta, modelo_camara |
| `color_1/2/3_hex` | TEXT | Colores dominantes en hex |
| `color_1/2/3_name_css` | TEXT | Nombre CSS en español |
| `color_1/2/3_name_basic` | TEXT | Nombre básico (rojo, azul...) |
| `ingested_at` | TEXT | Fecha de ingestión |
| `updated_at` | TEXT | Fecha de última actualización |
| `ingest_batch_id` | INTEGER | ID de la corrida de ingesta (para undo) |

### Tabla `media_metadata`

Metadatos variables en formato clave-valor.

### Tabla `config`

Configuración de la base de datos (`ingest_root`, `current_ingest_batch`, etc.).

---

## Requisitos del sistema

### Instalación de herramientas externas

```powershell
# ffmpeg — transcodificación, scene detection, extracción de fotogramas
winget install "FFmpeg (Essentials Build)"

# ExifTool — metadatos EXIF/IPTC/XMP
winget install ExifTool.ExifTool

# Ollama — modelos de visión (etiquetado, descripción, calidad)
winget install Ollama.Ollama
ollama pull moondream:latest          # 1.7 GB — recomendado
```

### Instalación de dependencias Python

```powershell
pip install faster-whisper            # Transcripción de audio
pip install Pillow                    # Colores dominantes, content hash
pip install webcolors                 # Nombres de colores CSS
pip install tqdm                      # Barras de progreso
pip install ollama                    # Cliente Python para Ollama
```

---

## Stack

| Componente | Versión | Propósito |
|------------|---------|-----------|
| **Python** | 3.13+ | Scripting principal |
| **SQLite** | 3.x (incluido) | Base de datos embebida |
| **ffmpeg** | 8.1.2+ | Análisis y transcodificación |
| **ExifTool** | 13.58+ | Metadatos EXIF/IPTC/XMP |
| **Pillow** | 12.2+ | Colores dominantes, content hash |
| **tqdm** | 4.68+ | Barras de progreso |
| **webcolors** | 25.10+ | Nombres de colores CSS |
| **Ollama** | 0.31+ | Modelos de visión (etiquetado, descripción, calidad) |
| **faster-whisper** | 1.2+ | Transcripción de audio con timestamps |

---

## Documentos de diseño

| Documento | Contenido |
|-----------|-----------|
| `VISION.md` | Visión del proyecto, concepto curatorial |
| `ROADMAP.md` | Estado de cada etapa del pipeline |
| `docs/flujo_de_medios.md` | Pipeline completo (curación, ingesta, inferencia) |
| `docs/linea_de_tiempo.md` | Diseño conceptual de la línea de tiempo |
| `docs/limpieza_tandas_resultados.md` | Comparativa de estrategias de limpieza |

---

## Estructura del proyecto

```
/
├── flujos.py                  # Entry point unificado
├── db/
│   ├── flujos.db              # Base de datos (se crea al ingerir)
│   └── schema.sql             # Schema SQL
├── scripts/
│   ├── ingest.py              # Ingesta de medios
│   ├── query.py               # Consultas a la DB
│   ├── relocate.py            # Relocalizar medios
│   ├── color_utils.py         # Colores dominantes
│   ├── limpiar_tandas.py      # Selección con IA
│   ├── mover_descartadas.py   # Mover descartadas
│   ├── check_db.py            # Inspeccionar DB
│   ├── check_gps.py           # Verificar GPS
│   └── ai_media/              # Scripts de IA (visión, transcripción)
├── docs/                      # Documentos de diseño
├── VISION.md                  # Visión del proyecto
├── ROADMAP.md                 # Estado y prioridades
├── AGENTS.md                  # Configuración de agentes OpenCode
└── README.md                  # Este archivo
```
