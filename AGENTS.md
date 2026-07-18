# Flujos — Documentación Exhaustiva del Proyecto

Instalación interactiva que documenta un viaje Buenos Aires → Tucumán en bicicleta.
Pipeline de ingesta, enriquecimiento, consulta y exportación de metadatos multimedia
con SQLite como índice central y TouchDesigner como motor de reproducción.

> Idioma del proyecto: **español** (nombres de variables, comentarios, commits, menús).
> Toda la documentación para agentes está aquí. Si hay que buscar algo, primero leer esto.

---

## Stack y herramientas

| Herramienta    | Versión    | Comando / Uso                                  |
|----------------|------------|-------------------------------------------------|
| Python         | 3.13.14    | `python` (scripts en `scripts/`)               |
| ffmpeg         | 8.1.2      | `ffmpeg`, `ffprobe` (transcode, analysis)      |
| ExifTool       | 13.59      | `exiftool` (EXIF/IPTC/XMP)                     |
| Ollama         | 0.31.2     | `ollama` (servicio bg, modelos visión/texto)   |
| faster-whisper | 1.2.1      | `faster_whisper` (transcripción audio/video)   |
| Pillow         | —          | Procesamiento de imágenes (color, thumbnails)  |
| webcolors      | —          | Nombres de color CSS → español                 |
| SQLite         | —          | Base de datos embebida (`db/flujos.db`)        |

### Modelos Ollama instalados

| Modelo                    | Tamaño | Uso                               |
|---------------------------|--------|-----------------------------------|
| `qwen2.5vl:latest` (7b)   | 6.0 GB | Visión + lenguaje (principal)     |
| `qwen2.5vl:3b`            | 3.2 GB | Visión + lenguaje (liviano)       |
| `llama3.2-vision:latest`  | 7.8 GB | Análisis visual                   |
| `moondream:latest`         | 1.7 GB | Visión rápido y pequeño           |
| `gemma4:e4b`              | 9.6 GB | Multimodal                        |
| `qwen3.5:9b` / `qwen3.5:4b` | 6.6/3.4 GB | Texto / análisis            |
| `deepseek-r1:latest`      | 5.2 GB | Razonamiento                      |
| `llama3.1:8b` / `3.2:3b` | 4.9/2.0 GB | Propósito general              |
| `deepseek-coder-v2:16b`   | 8.9 GB | Código                            |
| `qwen3-coder:latest`      | 18 GB  | Código (grande)                   |
| `nomic-embed-text` / `-v2-moe` | 274/957 MB | Embeddings / búsquedas semánticas |

---

## Estructura completa del proyecto

```
/
├── opencode.json                    # Configuración de OpenCode
├── AGENTS.md                        # ← ESTE ARCHIVO (doc de referencia)
├── VISION.md                        # Concepto de la instalación y dérive
├── README.md                        # Documentación general del proyecto
├── ROADMAP.md                       # Prioridades y hoja de ruta
│
├── flujos.py                        # Entry point unificado (TUI + CLI routing, 1325 lines)
│
├── db/
│   └── schema.sql                   # Definición completa del schema SQLite
│   └── flujos.db                    # Base de datos (no versionada)
│
├── scripts/                         # Scripts Python del pipeline
│   ├── __init__.py
│   ├── ingest.py                    # Ingesta de medios (1375 lines)
│   ├── improve_db.py                # Post-procesamiento (7 pasos, 903 lines)
│   ├── query.py                     # Consultas a DB
│   ├── relocate.py                  # Relocalizar rutas
│   ├── geocode.py                   # Geocodificación inversa (Georef API)
│   ├── gradiente.py                 # Gradientes de ruta (Haversine, elevación)
│   ├── limpiar_tandas.py            # Limpieza de tandas (burst cleanup)
│   ├── fetch_weather.py             # Clima histórico (Open-Meteo ERA5-Land)
│   ├── dia_semana.py                # Día de la semana desde timestamp
│   ├── color_utils.py               # Extracción y naming de colores
│   ├── check_db.py                  # Inspección de DB
│   ├── check_gps.py                 # Verificación GPS en archivos
│   ├── check_db_data.py             # Helper: muestra clima, día, geocode
│   ├── mover_descartadas.py         # Mover descartadas a excluir/
│   └── test_gradiente.py            # Tests unitarios de gradiente
│
│   └── ai_media/                    # Scripts de IA para medios
│       ├── __init__.py
│       ├── ollama_client.py         # Cliente Ollama compartido (visión + texto)
│       ├── transcribe.py            # Transcripción vía faster-whisper (independiente)
│       ├── transcribe_media.py      # Transcripción desde DB (con awareness de media)
│       ├── image_analysis.py        # Keywords + descripción de imágenes
│       ├── video_analysis.py        # Análisis de videos (scene detect + frames)
│       ├── analyze_video.py         # Análisis visual de video
│       ├── tag_images.py            # Taggear imágenes (modo DB o sidecar)
│       ├── batch_selector.py        # Selección de mejor imagen de tanda
│       ├── clustering.py            # Agrupamiento por tags/embeddings
│       ├── generate_embeddings.py   # Embeddings vectoriales (nomic-embed-text)
│       └── proxy.py                 # Proxy: redimensiona imágenes a ~2MP para IA
│
├── docs/                            # Documentos de diseño
│   ├── arquitectura_motor.md        # TD puro vs híbrido TD+Python
│   ├── flujo_de_medios.md           # Flujo de medios en el motor
│   ├── linea_de_tiempo.md           # Timeline y navegación temporal
│   ├── geocodificacion_reversa.md   # Estrategias de geocodificación
│   ├── limpieza_tandas_resultados.md # Comparativa de estrategias de limpieza
│   └── ideas_externas.md            # Ideas de terceros
│
└── .opencode/
    ├── agents/                      # Subagentes especializados
    │   ├── orquestador.md           # Agente primario (default)
    │   ├── touchdesigner.md         # Experto TouchDesigner
    │   ├── gis.md                   # Experto GIS/geolocalización
    │   └── ia-media.md              # Experto IA para medios
    └── skills/                      # Skills reutilizables
        ├── sqlite/SKILL.md          # Base de datos SQLite
        ├── ffmpeg/SKILL.md          # Transcodificación y análisis
        ├── exiftools/SKILL.md       # Metadatos EXIF/IPTC/XMP
        ├── ia-media/SKILL.md        # Procesamiento con IA
        └── python-media/SKILL.md    # Python para multimedia
```

---

## Base de datos (`db/flujos.db`)

Schema completo en `db/schema.sql`. SQLite con WAL mode y foreign_keys=ON.

### Tabla: `media` (columna principal, ~55 columnas)

```sql
-- Identidad
id                    INTEGER PRIMARY KEY AUTOINCREMENT
filename_original     TEXT NOT NULL              -- nombre archivo original
filepath_absoluto     TEXT NOT NULL UNIQUE       -- ruta absoluta actual
filepath_relativo     TEXT NOT NULL              -- relativo a ingest_root
carpeta               TEXT                       -- directorio contenedor
type                  TEXT NOT NULL              -- image|video|audio|text
subtype               TEXT                       -- RAW|HEIF|360|timelapse|...

-- Huellas digitales
size_bytes            INTEGER
file_hash             TEXT UNIQUE                -- SHA-256 del archivo completo
content_hash          TEXT                       -- SHA-256 ignorando metadatos

-- Sidecar Sony XML
sidecar_xml           TEXT                       -- ruta al XML
sidecar_parsed        INTEGER DEFAULT 0          -- 1 si ya se parseó
sidecar_hash          TEXT                       -- hash del XML

-- Tiempo
timestamp_original    TEXT                       -- formato original del EXIF
timestamp_utc         TEXT                       -- normalizado a UTC (ISO 8601)
timezone_note         TEXT                       -- nota sobre timezone detectado
duration_secs         REAL                       -- duración (videos/audios)
end_time              TEXT                       -- timestamp_utc + duration_secs

-- GPS
latitude              REAL                       -- ±90°, NEGATIVO en Argentina
longitude             REAL                       -- ±180°, NEGATIVO en Argentina
altitude              REAL                       -- metros
geolocation_source    TEXT                       -- metadata|gpx|manual

-- Geocode (provincia, municipio, localidad)
provincia             TEXT
departamento          TEXT                       -- (poco usado en ARG)
municipio             TEXT
localidad             TEXT
geocode_source        TEXT                       -- georef_api|...
geocode_date          TEXT                       -- datetime de la geocodificación

-- Gradientes (esfuerzo físico entre puntos GPS consecutivos)
distance_from_prev_m    REAL                     -- distancia Haversine al punto anterior
elevation_gain_m        REAL                     -- cambio de elevación (m)
gradient_pct            REAL                     -- (elevation_gain / distance) * 100
cumul_distance_m        REAL                     -- distancia acumulada desde el inicio
cumul_elevation_gain_m  REAL                     -- ganancia de elevación acumulada

-- Autoría
author                TEXT
author_source         TEXT                       -- exif|gpx|xmp|manual

-- Colores dominantes (3 slots)
color_{1,2,3}_hex         TEXT                   -- #rrggbb
color_{1,2,3}_name_css    TEXT                   -- nombre CSS en español
color_{1,2,3}_name_basic  TEXT                   -- categoría: rojo|verde|azul|...

-- Control
ingested_at           TEXT DEFAULT (datetime('now'))
updated_at            TEXT
ingest_batch_id       INTEGER                    -- para undo-ingest
```

**10 índices**: type, carpeta, timestamp_utc, end_time, lat×lon (compuesto), ingest_batch_id, file_hash (UNIQUE), filepath_absoluto (UNIQUE), gps_time (WHERE lat IS NOT NULL), metadata/keypoints.

### Tabla: `media_metadata` (key-value)

```sql
media_id    INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE
key         TEXT NOT NULL              -- ej: ia_keywords, ia_description, transcript,
                                       --     weather_temp_c, dia_semana, ...
value       TEXT
UNIQUE(media_id, key)
```

Claves usadas actualmente:
- `ia_keywords` — palabras clave extraídas por IA
- `ia_description` — descripción generada por IA
- `transcript` — transcripción de audio/video
- `weather_temp_c`, `weather_humidity_pct`, `weather_precip_mm`,
  `weather_cloud_pct`, `weather_code`, `weather_label`, `weather_hour_utc`,
  `weather_source` — datos climáticos (Open-Meteo)
- `dia_semana` — lunes|martes|...|domingo

### Tabla: `media_keypoints`

```sql
media_id              INTEGER NOT NULL REFERENCES media(id)
timestamp_offset_secs REAL NOT NULL
timestamp_absolute    TEXT                    -- timestamp_utc + offset
key                   TEXT NOT NULL           -- ej: transcript_segment
value                 TEXT
source                TEXT
UNIQUE(media_id, timestamp_offset_secs, key)
```

### Tabla: `media_embeddings`

```sql
media_id    INTEGER NOT NULL REFERENCES media(id)
embedding   BLOB NOT NULL
modelo      TEXT NOT NULL DEFAULT 'nomic-embed-text'
fecha       TEXT DEFAULT (datetime('now'))
UNIQUE(media_id, modelo)
```

### Tabla: `config` (key-value global)

```sql
key         TEXT PRIMARY KEY
value       TEXT
```

Claves: `ingest_root`, `current_ingest_batch`, etc.

---

## Mapa de datos: qué se escribe y dónde

Cada script del pipeline escribe datos específicos en la DB. Esta tabla centraliza
**qué datos genera cada etapa, en qué tabla y en qué columnas/claves**:

| Etapa | Script | Datos | Tabla | Columnas / Claves |
|---|---|---|---|---|
| **INGESTA** | `ingest.py` | Metadatos de archivo (nombre, ruta, tamaño, tipo, subtipo) | `media` | filename_original, filepath_absoluto, filepath_relativo, carpeta, type, subtype, size_bytes |
| | | Huellas digitales (SHA-256) | `media` | file_hash, content_hash |
| | | Sidecar Sony XML | `media` | sidecar_xml, sidecar_parsed, sidecar_hash |
| | | Timestamp original + UTC normalizado | `media` | timestamp_original, timestamp_utc, timezone_note |
| | | Duración (videos/audios) | `media` | duration_secs |
| | | GPS (lat, lon, altitud, fuente) | `media` | latitude, longitude, altitude, geolocation_source |
| | | Autor | `media` | author, author_source |
| | | Colores dominantes (3 slots: hex, nombre CSS, categoría básica) | `media` | color_{1,2,3}_hex, color_{1,2,3}_name_css, color_{1,2,3}_name_basic |
| | | Control de ingesta (fecha, batch) | `media` | ingested_at, ingest_batch_id |
| **COLORES** | `improve_db.py --step colors` | Reprocesa colores dominantes (modos skip/update/replace) | `media` | color_{1,2,3}_hex, color_{1,2,3}_name_css, color_{1,2,3}_name_basic, updated_at |
| **KEYWORDS** | `improve_db.py --step keywords` | Palabras clave IA (5-7, incluye género fotográfico) | `media_metadata` | key=`ia_keywords`, value=JSON array |
| **DESCRIPTION** | `improve_db.py --step descriptions` | Descripción breve generada por IA | `media_metadata` | key=`ia_description`, value=texto |
| **TRANSCRIBE** | `improve_db.py --step transcribe` | Transcripción completa de audio/video | `media_metadata` | key=`transcript`, value=texto |
| **KEYPOINTS** | `improve_db.py --step keypoints` | Segmentos individuales de transcripción con timestamp | `media_keypoints` | media_id, timestamp_offset_secs, timestamp_absolute, key=`transcript_segment`, value=texto, source |
| **TIMESTAMPS** | `improve_db.py --step timestamps` | Timestamps inferidos desde EXIF/ExifTool | `media` | timestamp_original, timestamp_utc, timezone_note, updated_at |
| **GPS** | `improve_db.py --step gps` | GPS inferido desde EXIF/ExifTool | `media` | latitude, longitude, altitude, geolocation_source, updated_at |
| **GEOCODE** | `geocode.py` | Provincia, municipio, localidad (Georef API Argentina) | `media` | provincia, departamento, municipio, localidad, geocode_source, geocode_date |
| **WEATHER** | `fetch_weather.py` | Clima histórico (Open-Meteo ERA5-Land) | `media_metadata` | keys: weather_temp_c, weather_humidity_pct, weather_precip_mm, weather_cloud_pct, weather_code, weather_label, weather_hour_utc, weather_source |
| **DÍA SEMANA** | `dia_semana.py` | Día de la semana en español | `media_metadata` | key=`dia_semana`, value=lunes\|martes\|...\|domingo |
| **GRADIENTES** | `gradiente.py` | Distancia Haversine, cambio elevación, pendiente % y acumulados | `media` | distance_from_prev_m, elevation_gain_m, gradient_pct, cumul_distance_m, cumul_elevation_gain_m |
| **BACKFILL** | `flujos.py` backfill-end-time | Precalcula end_time = timestamp_utc + duration_secs | `media` | end_time, updated_at |
| **RELOCATE** | `relocate.py` | Actualiza rutas cuando los archivos se mudan de carpeta | `media` | filepath_absoluto, filepath_relativo, carpeta, sidecar_xml |

> **Nota**: todas las operaciones que modifican la DB soportan `--mode skip|update|replace`.
> - `skip`: solo procesa registros donde el dato es NULL
> - `update`: actualiza todos los registros (sobrescribe)
> - `replace`: limpia los datos existentes primero, luego regenera

---

## Catálogo de Scripts

### Entry point: `flujos.py`

**Archivo**: `flujos.py` (~1350 lines)
**Función**: Punto de entrada único. Dos modos:
- **TUI** (sin args o `--tui`): menú interactivo completo con 6 submenús.
- **CLI routing**: `python flujos.py <comando> [args]` → delega al script correspondiente.

#### TUI — Árbol de menú completo

```
1. Preparar medios
  └─ 1. Limpieza de tandas → scripts/limpiar_tandas.py

2. Ingesta
  ├─ 1. Hacer ingesta → scripts/ingest.py (pide root, verbose, dry-run)
  └─ 2. Deshacer ingesta → opcion_undo_ingest() interno

3. Mejorar base de datos
  ├─ Parte 1: IA y color
  │  ├─ 1. Todos los pasos (skip)      → improve_db con verificación Ollama
  │  ├─ 2. Elegir pasos manualmente     → pregunta pasos + modo
  │  ├─ 3. Colores dominantes           → improve_db --steps colors
  │  ├─ 4. Keywords con IA              → improve_db --steps keywords (verif. Ollama)
  │  ├─ 5. Descripción con IA           → improve_db --steps descriptions (verif. Ollama)
  │  ├─ 6. Keywords + Descripción       → improve_db --steps keywords,descriptions
  │  ├─ 7. Transcripción                → improve_db --steps transcribe (verif. Ollama)
  │  ├─ 8. Keypoints                    → improve_db --steps keypoints
  │  ├─ v. Ver modelos Ollama instalados → _listar_modelos_ollama()
  │  └─ 9. Siguiente >> → Parte 2
  └─ Parte 2: Inferencia y enriquecimiento
     ├─ 1. Inferir timestamps           → improve_db --steps timestamps
     ├─ 2. Inferir GPS                  → improve_db --steps gps
     ├─ 3. Localización (geocode)       → scripts/geocode.py (con modo)
     ├─ 4. Condiciones climáticas       → scripts/fetch_weather.py (con modo)
     ├─ 5. Día de la semana             → scripts/dia_semana.py (con modo)
     ├─ 6. Embeddings
     │   ├─ 1. Generar embeddings (solo pendientes)
     │   ├─ 2. Previsualizar (dry-run)
     │   ├─ 3. Ver modelos Ollama instalados
     │   └─ 0. Volver
     ├─ 9. << Anterior → Parte 1
     └─ 0. Volver

4. Consultar base de datos
  ├─ 1. Ver resumen de la DB           → opcion_check_db() (solo Total, Imágenes, Videos, Audios, Textos, Otros)
  └─ 2. Listar...
     ├─ 1. Tipos de medio
     ├─ 2. Autores
     ├─ 3. Carpetas
     ├─ 4. Colores básicos
     ├─ 5. Provincias (geocode)
     ├─ 6. Buscar texto
     ├─ 7. Consulta libre (flags a query.py)
     ├─ 8. Revisar GPS en archivos
     └─ 9. Detalle completo de registros (todas las columnas)

5. Mantenimiento DB
  ├─ 1. Relocalizar medios              → scripts/relocate.py
  ├─ 2. Calcular gradientes de ruta     → scripts/gradiente.py (con modo)
  ├─ 3. Backfill end_time               → opcion_backfill_end_time() (con modo)
  ├─ 4. Backup DB (solo backup)         → opcion_backup_db()
  ├─ 5. Restore DB desde backup         → opcion_restore_db()
  └─ 6. Resetear DB (backup + limpiar)  → opcion_reset_db()

6. Ayuda → opcion_ayuda() (ayuda detallada por comando)
```

#### CLI — Comandos disponibles

| Comando             | Delega a                         |
|---------------------|----------------------------------|
| `ingest`            | `scripts/ingest.py`              |
| `query`             | `scripts/query.py`               |
| `relocate`          | `scripts/relocate.py`            |
| `check-db`          | `opcion_check_db()` (interno)    |
| `check-gps`         | `opcion_check_gps()` (interno)   |
| `geocode`           | `scripts/geocode.py`             |
| `gradient`          | `scripts/gradiente.py`           |
| `improve-db`        | `scripts/improve_db.py`          |
| `backup-db/backup`  | `opcion_backup_db()` (interno)   |
| `restore-db/restore`| `opcion_restore_db()` (interno)  |
| `reset-db/reset`    | `opcion_reset_db()` (interno)    |
| `undo-ingest/undo`  | `opcion_undo_ingest()` (interno) |
| `backfill-end-time` | `opcion_backfill_end_time()` (int.) |

#### Funciones helper clave en flujos.py

| Función | Propósito |
|---------|-----------|
| `_verificar_ollama()` | Verifica que Ollama esté corriendo (GET localhost:11434/api/tags). Se llama antes de keywords/descriptions/transcribe. |
| `_preguntar_modo()` | Pregunta skip/update/replace y devuelve el string. Usada en TODAS las operaciones de DB. |
| `_ejecutar_improve_db()` | Wrapper que verifica Ollama si el paso lo requiere, luego llama a improve_db.main(). |
| `leer_db()` | Resuelve la ruta a la DB (default: `db/flujos.db`). |
| `resumen_db()` | Devuelve string con totales (6 líneas: Total, Imágenes, Videos, Audios, Textos, Otros). |

### Pipeline scripts (scripts/)

#### `ingest.py` (1375 lines)
- **Propósito**: Escanea una carpeta, extrae metadados (ExifTool, ffprobe), calcula hashes, extrae colores dominantes, inserta en DB.
- **Args CLI**: `--root` (obligatorio), `--full-hash`, `--sidecar-xml`, `--colors`, `--no-proxy`, `--verbose`, `--dry-run`, `--db`
- **DB que modifica**: `media` (insert), `media_metadata` (insert)
- **Dependencias**: Pillow, webcolors, subprocess (exiftool, ffprobe)
- **Notas**: 
  - `parse_gps_dms()` — convierte DMS a decimal. **ATENCIÓN**: ExifTool sin `-n` devuelve `"South"`/`"West"` (texto completo), NO `"S"`/`"W"`. La función ahora lo maneja con `_es_sur_oeste()` y `_parse_gps_position()`.
  - `extract_gps_from_exif()` — usa `Composite:GPSPosition` primero, fallback a `EXIF:GPSLatitude+Ref`.
  - `init_db()` — crea el schema desde cero (usado también por reset-db).

#### `improve_db.py` (903 lines)
- **Propósito**: Pipeline de 7 pasos post-ingesta con skip/update/replace.
- **Args CLI**: `--steps` (default: todos), `--mode` (skip|update|replace), `--db`, `--list`
- **Pasos**: `colors`, `keywords`, `descriptions`, `transcribe`, `keypoints`, `timestamps`, `gps`
- **DB que modifica**: `media` (UPDATE colores, timestamps, GPS), `media_metadata` (INSERT keywords, descriptions, transcripts), `media_keypoints`
- **Modos**: skip (solo pendientes), update (actualiza todos), replace (limpia y regenera)
- **Dependencias**: color_utils, ai_media/image_analysis, ai_media/transcribe_media
- **Notas**: Usa `ThreadPoolExecutor(max_workers=2)` para llamadas Ollama en paralelo.

#### `query.py`
- **Propósito**: Consultas a DB desde CLI.
- **Args CLI**: `--distinct`, `--search`, `--where`, `--count`, `--limit`, `--db`
- **DB que modifica**: solo lectura.

#### `relocate.py`
- **Propósito**: Actualizar `filepath_absoluto` cuando los archivos se mudan de carpeta.
- **Args CLI**: `--new-root`, `--dry-run`, `--db`
- **DB que modifica**: `media.filepath_absoluto`, `media.filepath_relativo`, `media.carpeta`

#### `geocode.py`
- **Propósito**: Geocodificación inversa (GPS → provincia/municipio/localidad) vía API Georef Argentina (batch).
- **Args CLI**: `--coords` (modo directo), `--db`, `--limit`, `--dry-run`, `--mode` (skip|update|replace)
- **DB que modifica**: `media.provincia`, `.departamento`, `.municipio`, `.localidad`, `.geocode_source`, `.geocode_date`
- **API**: `https://apis.datos.gob.ar/georef/api/ubicacion?lat=X&lon=Y`
- **Notas**: 
  - Modo replace: limpia columnas de geocode antes de reprocesar.
  - Agrupa coordenadas iguales para evitar llamadas duplicadas a la API.
  - **⚠️ Las coordenadas deben ser NEGATIVAS** (Argentina: lat < 0, lon < 0).

#### `gradiente.py`
- **Propósito**: Calcula distancia Haversine, cambio de elevación, pendiente % y acumulados entre puntos GPS consecutivos ordenados por timestamp.
- **Args CLI**: `--db`, `--dry-run`, `--verbose`, `--quiet`, `--mode` (skip|update|replace)
- **DB que modifica**: `media.distance_from_prev_m`, `.elevation_gain_m`, `.gradient_pct`, `.cumul_distance_m`, `.cumul_elevation_gain_m`
- **Dependencias**: solo Python estándar (math). **No** requiere numpy/gdal.
- **Notas**: Procesa TODOS los puntos con GPS en orden temporal. Modo replace: limpia columnas antes de recalcular.
- **Tests**: `test_gradiente.py` (309 lines, 10 puntos simulados).

#### `color_utils.py`
- **Propósito**: Extracción de colores dominantes (Pillow) y naming (webcolors CSS3 → español → categoría básica).
- **Funciones principales**:
  - `extract_dominant_colors(image_path, n_colors=3)` → lista de hex. Usa grilla ~16 celdas, cuantización MEDIANCUT, scoring con concentración² + centralidad + saturación relativa.
  - `get_color_names(hex_color)` → (nombre_css_es, nombre_basico)
  - `closest_css_color(hex_color)` → nombre CSS más cercano vía **distancia Redmean** (perceptual, no RGB euclídeo plano).
  - `_es_gris_o_negro(r, g, b)` → filtro de colores poco interesantes.
- **⚠️ Anti-gray bias**: si el match más cercano es gris/negro/blanco pero hay un color real dentro de 1.5× de distancia Redmean, prefiere el color real. Esto evita que marrones oscuros o verdes desaturados caigan en "gris".
- **Categorías básicas**: rojo, naranja, amarillo, verde, azul, violeta, rosa, marrón, blanco, gris, negro.
- **Novedades recientes**: 
  - Se agregaron variantes "grey" (dimgrey, slategrey, darkslategrey, etc.)
  - `olivedrab`, `olive`, `darkolivegreen` movidos de "amarillo" a "verde".
  - `fuchsia` agregado a "violeta".

#### `limpiar_tandas.py`
- **Propósito**: Limpieza de tandas/bursts de fotos. Detecta duplicados temporales y visualmente similares. Mueve descartados a carpeta `excluir/`.
- **Args CLI**: `--carpeta`, `--ventana-temporal`, `--dry-run`, `--no-proxy`, `--db`
- **DB que modifica**: ninguna (trabaja sobre el sistema de archivos).
- **Notas**: 
  - Mueve sidecars (.AAE, .json) junto con la imagen descartada.
  - `_mover_a_excluir()` recibe la ruta absoluta real (no duplica anidación de carpetas).

#### `fetch_weather.py`
- **Propósito**: Obtener datos climáticos históricos desde Open-Meteo ERA5-Land API.
- **Args CLI**: `--db`, `--dry-run`, `--limit`, `--replace` (deprecated), `--mode`, `--steps` (intervalo horario)
- **DB que modifica**: `media_metadata` (weather_temp_c, weather_humidity_pct, weather_precip_mm, weather_cloud_pct, weather_code, weather_label, weather_hour_utc, weather_source)
- **API**: Open-Meteo Historical API (gratis, sin API key).
- **Estrategia**: agrupa medios por (fecha, celda de 0.5° ≈ 55 km). Cada grupo hace una sola llamada a la API. Luego empareja cada medio con la hora más cercana disponible.
- **Notas**: `--steps` filtra horas (ej: --steps 3 = cada 3 horas). `--replace` es alias de `--mode replace`.

#### `dia_semana.py`
- **Propósito**: Calcula el día de la semana (lunes..domingo) desde `timestamp_utc` de cada medio.
- **Args CLI**: `--db`, `--dry-run`, `--replace` (deprecated), `--mode`, `--limit`
- **DB que modifica**: `media_metadata` (clave `dia_semana`, valor: lunes|martes|...|domingo)

#### Scripts de verificación

| Script | Propósito |
|--------|-----------|
| `check_db.py` | Inspecciona las 5 tablas con counts y muestras. Se ejecuta desde opcion_check_db() en flujos.py. |
| `check_gps.py` | Verifica GPS en archivos via ExifTool, compara con DB. |
| `check_db_data.py` | Helper: muestra stats de weather, dia_semana y geocode. |

### Scripts de IA (`scripts/ai_media/`)

| Script | Propósito | Dependencia principal |
|--------|-----------|----------------------|
| `ollama_client.py` | Cliente Ollama compartido. Clase `OllamaVisionClient(modelo, timeout)`. Métodos: `analizar_imagen()`, `analizar_imagenes()`, `generar_embedding()`. | ollama (Python) |
| `transcribe.py` | Transcripción vía faster-whisper (independiente, sin DB). Formatos: SRT, TXT, JSON. | faster-whisper |
| `transcribe_media.py` | Transcripción desde DB (lee de `media`, escribe en `media_metadata`). | faster-whisper |
| `image_analysis.py` | Keywords + descripción de imágenes vía Ollama (17 géneros). Usado por improve_db.py. | ollama_client |
| `video_analysis.py` | Análisis de videos (keyframes + descripción). | ollama_client |
| `analyze_video.py` | Scene-change detection + análisis visual de video. | ollama_client |
| `tag_images.py` | Taggear imágenes (modo DB o sidecar). | ollama_client |
| `batch_selector.py` | Selecciona la mejor imagen de una tanda usando IA. | ollama_client |
| `clustering.py` | Agrupa imágenes por tags o embeddings compartidos. | — |
| `generate_embeddings.py` | Genera embeddings vectoriales vía nomic-embed-text. | ollama_client |
| `proxy.py` | Redimensiona imágenes a ~2MP para procesamiento IA más rápido. | Pillow |

---

## Pipeline de procesamiento

```
[Medios crudos en disco]
       │
       ▼
1. PREPARAR: limpiar_tandas.py (opcional, elimina bursts)
       │
       ▼
2. INGESTAR: python flujos.py ingest --root D:/Medios
   ├── Escanea carpeta recursivamente
   ├── Agrupa por tipo (image/video/audio/text)
   ├── Extrae metadata: ExifTool (imágenes), ffprobe (video/audio)
   ├── Calcula hashes: file_hash (SHA-256), content_hash
   ├── Extrae GPS (con manejo de signo Sur/Oeste)
   ├── Extrae colores dominantes (Pillow + color_utils)
   └── Inserta en DB (tabla media, lote por batch)
       │
       ▼
3. MEJORAR DB: python flujos.py improve-db [--mode skip|update|replace]
   ├── 1. colors       → color_utils.extract_dominant_colors() + get_color_names()
   ├── 2. keywords     → image_analysis.py (Ollama visión, 17 géneros)
   ├── 3. descriptions → image_analysis.py (Ollama visión, descripción breve)
   ├── 4. transcribe   → transcribe_media.py (faster-whisper)
   ├── 5. keypoints    → poblado desde transcripciones
   ├── 6. timestamps   → inferir timestamp_utc desde EXIF/exiftool
   └── 7. gps          → inferir GPS desde EXIF/exiftool
       │
       ▼
4. ENRIQUECER (scripts independientes, con skip/update/replace):
   ├── dia_semana.py       → día de la semana en español
   ├── fetch_weather.py    → clima histórico Open-Meteo
   ├── geocode.py          → provincia/municipio/localidad (Georef API)
   └── gradiente.py        → distancia, elevación, pendiente entre puntos GPS
       │
       ▼
5. CONSULTAR: query.py / TUI opción 4 (listados, búsquedas, detalle)
       │
       ▼
6. EXPORTAR: relocate.py (actualizar rutas si los archivos se mudan)
```

---

## Convenciones y patrones de código

### Estilo
- Español para nombres de variables, funciones, comentarios y commits.
- Docstrings en español.
- Type hints obligatorios en funciones nuevas.
- `log = logging.getLogger(__name__)` al inicio de cada script.

### Patrón de script independiente
Cada script en `scripts/` tiene:
1. `def main(argv=None)` con `argparse.ArgumentParser`.
2. Puede ejecutarse standalone (`python scripts/foo.py --args`) o desde flujos.py.
3. Si modifica la DB, acepta `--mode skip|update|replace` (default: skip).
4. Si es pesado, acepta `--dry-run` para previsualizar sin escribir.

### Patrón de acceso a DB
```python
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
# ... operaciones ...
conn.commit()
conn.close()
```

### Manejo de --mode en scripts
```python
if mode == "replace":
    # Limpiar datos existentes primero
    conn.execute("UPDATE media SET columna = NULL WHERE ...")
    conn.commit()
elif mode == "skip":
    query += " AND columna IS NULL"  # solo pendientes
# mode == "update": procesa todos, sobreescribe
```

### Errores comunes que evitar
1. **Signo de GPS**: `ExifTool` sin `-n` devuelve `"South"`/`"West"` (texto completo), NO `"S"`/`"W"`. Usar `_es_sur_oeste()` que acepta ambos.
2. **`Composite:GPSPosition` sin `-n`**: el formato es `"31° S, 64° W"` (con coma), no `"31 64"`. Usar `_parse_gps_position()`.
3. **webcolors**: las variantes "grey" (inglés británico: `dimgrey`, `slategrey`, etc.) existen en CSS3 y hay que mapearlas explícitamente.
4. **CRLF en Windows**: Git muestra warnings de "LF will be replaced by CRLF". Es normal en Windows, no afecta la ejecución.
5. **Ollama timeout**: las llamadas a modelos de visión pueden tardar 30-60s por imagen. Usar timeout=120s en el cliente.

---

## Subagentes

| Agente | Archivo | Rol |
|--------|---------|-----|
| `@orquestador` | `.opencode/agents/orquestador.md` | **PRIMARY (DEFAULT)**. Orquestador principal. No implementa, delega. |
| `@touchdesigner` | `.opencode/agents/touchdesigner.md` | Experto TouchDesigner: operadores, Python/TD, OSC, MIDI, NDI, Spout, shaders, proyección. |
| `@gis` | `.opencode/agents/gis.md` | Experto GIS: geolocalización de medios, conversión de coordenadas, cálculos de distancia, ubicación relativa. |
| `@ia-media` | `.opencode/agents/ia-media.md` | Experto IA: Ollama visión, faster-whisper transcripción, análisis imágenes/video, selección inteligente. |

## Skills

| Skill | Cuándo usarlo |
|-------|---------------|
| `sqlite` | Crear/consultar BD, migraciones, insertar medios, queries complejas. |
| `ffmpeg` | Transcodificar, extraer metadata, analizar duración/resolución, thumbnails. |
| `exiftools` | Leer/escribir EXIF/IPTC/XMP en imágenes, videos y audios. |
| `ia-media` | Procesamiento con IA: transcripción (faster-whisper), análisis de imágenes (Ollama visión), selección inteligente. |
| `python-media` | Scripts ETL, automatización, pipeline de ingesta, procesamiento batch con Pillow/mutagen/etc. |

---

## Documentos de diseño

| Documento | Tema |
|-----------|------|
| `docs/arquitectura_motor.md` | Análisis de arquitectura: TouchDesigner puro vs híbrido TD+Python. |
| `docs/flujo_de_medios.md` | Flujo de medios dentro del motor de reproducción. |
| `docs/linea_de_tiempo.md` | Timeline y navegación temporal de medios. |
| `docs/geocodificacion_reversa.md` | Estrategias de geocodificación: Georef API batch, Georef offline, python-gazetteer. |
| `docs/limpieza_tandas_resultados.md` | Comparativa de 4 estrategias de limpieza de tandas (temporal, pHash, tags, embeddings). Embeddings fue la favorita. |
| `docs/semantica_color.md` | Capa semántica del color: significados emocionales/culturales, Kuleshov effect, cross-modal retrieval. |
| `docs/ideas_externas.md` | 22 ideas externas recopiladas para la instalación. |

## Archivos raíz

| Archivo | Propósito |
|---------|-----------|
| `VISION.md` | Concepto de la instalación y la dérive (deriva). |
| `README.md` | Documentación general del proyecto, pipeline, todos los comandos. |
| `ROADMAP.md` | Hoja de ruta priorizada en 4 etapas. |
| `opencode.json` | Configuración de OpenCode para el proyecto. |

---

## Notas históricas importantes

- **GPS Sign Bug (Jul 2026)**: durante semanas los GPS se guardaron con signo positivo (lat=+31 en vez de -31). La DB actual puede tener coordenadas incorrectas. Fixeado en `ingest.py` con `_es_sur_oeste()`.
- **Color anti-gray bias**: implementado después de que usuarios reportaran que verdes desaturados y marrones oscuros caían en "gris". La distancia Redmean + umbral 1.5x resolvió el caso.
- **Open-Meteo**: se eligió sobre otras APIs climáticas por ser gratuito, sin API key, y cubrir datos históricos desde 1940 (ERA5-Land).
- **Georef**: API del gobierno argentino, gratuita, sin key. Soporta batch de hasta 5000 coordenadas.
- **gradiente.py**: implementado en Python puro (Haversine, sin numpy/gdal) para mantener cero dependencias pesadas.
