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
│   ├── schema.sql                   # Definición completa del schema SQLite
│   ├── migrate.py                   # Migraciones centralizadas de schema (version 1→2→3)
│   ├── util.py                      # Conexiones DB (abrir, conectar, resolver_db) + ModoHelper
│   └── flujos.db                    # Base de datos (no versionada)
│
├── scripts/                         # Scripts Python del pipeline
│   ├── __init__.py
│   ├── ingest.py                    # Ingesta de medios (1375 lines)
│   ├── improve_db.py                # Post-procesamiento (8 pasos, 903 lines)
│   ├── query.py                     # Consultas a DB
│   ├── relocate.py                  # Relocalizar rutas
│   ├── geocode.py                   # Geocodificación inversa (Georef API)
│   ├── gradiente.py                 # Gradientes de ruta (Haversine, elevación)
│   ├── astronomia.py                # Posición del sol (NOAA) y clasificación twilight
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
│               └── proxy.py                 # Proxy: redimensiona imágenes a ~2MP para IA
│
├── td/                              # Scripts vinculados desde TouchDesigner
│   ├── osc_callbacks.dat            # Callbacks OSC In DAT (recibe msgs de Python)
│   └── nube_generar.dat             # Genera nube de etiquetas en TD
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

### Tabla: `tracks` (archivos GPX)

```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
name              TEXT NOT NULL              -- nombre del track (del GPX)
filepath_absoluto TEXT NOT NULL              -- ruta absoluta al archivo GPX
filepath_relativo TEXT NOT NULL              -- ruta relativa al proyecto
source_url        TEXT                       -- URL de origen (RideWithGPS, etc.)
start_time        TEXT                       -- timestamp del primer punto
end_time          TEXT                       -- timestamp del último punto
total_points      INTEGER                    -- cantidad de track points
ingested_at       TEXT DEFAULT (datetime('now'))
```

### Tabla: `waypoints` (puntos de interés)

```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
track_id          INTEGER REFERENCES tracks(id) ON DELETE CASCADE
name              TEXT NOT NULL              -- nombre del waypoint
description       TEXT                       -- descripción textual
category          TEXT                       -- cmt: bikeshare, stop, caution, food, etc.
type              TEXT                       -- type: checkpoint, service, danger, food, etc.
latitude          REAL NOT NULL              -- WGS84
longitude         REAL NOT NULL              -- WGS84
timestamp         TEXT                       -- si tiene timestamp asociado
ingested_at       TEXT DEFAULT (datetime('now'))
```

### Tablas: Telegram (`telegram_chats`, `telegram_messages`, `telegram_media`)

Importadas desde exports de Telegram. Los multimedia de Telegram se ingieren también en `media` y se vinculan bidireccionalmente.

**`telegram_chats`** — metadatos del chat
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
telegram_id       INTEGER NOT NULL UNIQUE    -- chat id de Telegram
name              TEXT NOT NULL              -- nombre del grupo
chat_type         TEXT NOT NULL              -- private_group|supergroup|channel
export_path       TEXT NOT NULL              -- ruta absoluta al export
exported_at       TEXT                       -- fecha del export
imported_at       TEXT DEFAULT (datetime('now'))
```

**`telegram_messages`** — cada mensaje individual
```sql
id                    INTEGER PRIMARY KEY AUTOINCREMENT
chat_id               INTEGER NOT NULL REFERENCES telegram_chats(id) ON DELETE CASCADE
message_id            INTEGER NOT NULL       -- id de Telegram (único por chat)
type                  TEXT DEFAULT 'message'  -- message|service
message_type          TEXT DEFAULT 'text'     -- text|photo|video|voice|animation|sticker|document|location|poll|system
es_sistema            INTEGER DEFAULT 0       -- 1 si es service message
from_name             TEXT
from_id               TEXT
text                  TEXT                    -- texto plano (caption si aplica)
date_unixtime         INTEGER NOT NULL
date_utc              TEXT NOT NULL           -- ISO 8601 UTC
edited_unixtime       INTEGER
reply_to_message_id   INTEGER
media_group_id        TEXT                    -- grouped_id (álbumes)
reactions             TEXT                    -- JSON string
hashtags              TEXT                    -- tags separados por espacio
action                TEXT                    -- service: invite_members, join_group_by_link, etc.
actor_name            TEXT
actor_id              TEXT
members               TEXT                    -- JSON array de nombres
UNIQUE(chat_id, message_id)
```

**`telegram_media`** — archivos multimedia adjuntos a mensajes
```sql
id                  INTEGER PRIMARY KEY AUTOINCREMENT
message_id          INTEGER NOT NULL REFERENCES telegram_messages(id) ON DELETE CASCADE
media_order         INTEGER DEFAULT 0        -- orden dentro del mensaje
media_type          TEXT NOT NULL            -- photo|video_file|voice_message|animation|sticker|document
file_relative_path  TEXT NOT NULL            -- relativo al export (photos/photo_1@....jpg)
file_name           TEXT
mime_type           TEXT
file_size           INTEGER
width               INTEGER
height              INTEGER
duration_seconds    REAL
thumbnail_path      TEXT
media_id            INTEGER REFERENCES media(id) ON DELETE SET NULL  -- link a media table
```

**Columna agregada a `media`**:
```sql
telegram_message_id  INTEGER REFERENCES telegram_messages(id) ON DELETE SET NULL
```

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
| **VIDEO_METADATA** | `improve_db.py --step video_metadata` | ExifTool en videos (cámara, 360°, author) | `media` + `media_metadata` | subtype, author, xml_devicemanufacturer, xml_devicemodelname, xmp_spherical |
| **GEOCODE** | `geocode.py` | Provincia, departamento, municipio (Georef API Argentina; ⚠️ localidad siempre NULL, la API no la devuelve) | `media` | provincia, departamento, municipio, localidad (NULL), geocode_source, geocode_date |
| **WEATHER** | `fetch_weather.py` | Clima histórico (Open-Meteo ERA5-Land) | `media_metadata` | keys: weather_temp_c, weather_humidity_pct, weather_precip_mm, weather_cloud_pct, weather_code, weather_label, weather_wind_speed_kmh, weather_wind_dir_deg, weather_wind_dir_text, weather_pressure_hpa, weather_hour_utc, weather_source |
| **DÍA SEMANA** | `dia_semana.py` | Día de la semana en español | `media_metadata` | key=`dia_semana`, value=lunes\|martes\|...\|domingo |
| **GRADIENTES** | `gradiente.py` | Distancia Haversine, cambio elevación, pendiente % y acumulados | `media` | distance_from_prev_m, elevation_gain_m, gradient_pct, cumul_distance_m, cumul_elevation_gain_m |
| **ASTRONOMÍA** | `astronomia.py` | Posición del sol (NOAA), clasificación twilight, amanecer/atardecer/cenit, tiempos relativos | `media` | sun_elevation, sun_azimuth, sun_distance_au, twilight_period, sunrise_ts, sunset_ts, solar_noon_ts, secs_since_sunrise, secs_to_sunset, secs_since_noon, astronomy_source |
| **BACKFILL** | `flujos.py` backfill-end-time | Precalcula end_time = timestamp_utc + duration_secs | `media` | end_time, updated_at |
| **RELOCATE** | `relocate.py` | Actualiza rutas cuando los archivos se mudan de carpeta | `media` | filepath_absoluto, filepath_relativo, carpeta, sidecar_xml |
| **GPX** | `ingest_gpx.py` | Ingesta de archivo GPX: waypoints, registro de track y backfill de altitud | `tracks` | name, filepath_absoluto, filepath_relativo, source_url, start_time, end_time, total_points |
| | | | `waypoints` | name, description, category, type, latitude, longitude |
| | | | `media` | altitude, geolocation_source='track_gps' |
| **TELEGRAM** | `import_telegram.py` | Importa export de Telegram: chats, mensajes, multimedia vinculado | `telegram_chats` | telegram_id, name, chat_type, export_path |
| | | | `telegram_messages` | message_id, type, message_type, es_sistema, from_name, from_id, text, date_unixtime, date_utc, edited_unixtime, reply_to_message_id, reactions, hashtags, action, members |
| | | | `telegram_media` | media_type, file_relative_path, mime_type, file_size, width, height, duration_seconds, media_id |
| | | | `media` | telegram_message_id (FK), columna agregada vía ALTER TABLE |

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
  ├─ 2. Ingerir track GPS (GPX) → opcion_ingestar_gpx()
  ├─ 3. Deshacer ingesta → opcion_undo_ingest() (medios por batch + tracks GPX)
  └─ 4. Importar chat de Telegram → opcion_importar_telegram() (export result.json)

3. Mejorar base de datos
  ├─ Hoja 1: IA y color
  │  ├─ 1. Todos los pasos              → improve_db con verificación Ollama (pregunta modo)
  │  ├─ 2. Elegir pasos manualmente     → pregunta pasos + modo
  │  ├─ 3. Colores dominantes           → improve_db --steps colors
  │  ├─ 4. Keywords con IA              → improve_db --steps keywords (verif. Ollama)
  │  ├─ 5. Descripción con IA           → improve_db --steps descriptions (verif. Ollama)
  │  ├─ 6. Keywords + Descripción       → improve_db --steps keywords,descriptions
  │  ├─ 7. Refinar keywords             → scripts/ai_media/refinar_keywords.py (normaliza + sinónimos)
  │  ├─ 8. Transcripción                → improve_db --steps transcribe (verif. Ollama)
  │  ├─ 9. Keypoints                    → improve_db --steps keypoints
  │  ├─ n. Siguiente >> → Hoja 2
  │  └─ 0. Volver
  └─ Hoja 2: Inferencia y enriquecimiento (agrupado por temática)
     ├─ 1. Inferir timestamps           → improve_db --steps timestamps
     ├─ 2. Inferir GPS                  → improve_db --steps gps
     ├─ 3. Localización (geocode)       → scripts/geocode.py (con modo)
     ├─ 4. Condiciones climáticas       → scripts/fetch_weather.py (con modo)
     ├─ 5. Día de la semana             → scripts/dia_semana.py (con modo)
     ├─ 6. Posición del sol (astronomía) → scripts/astronomia.py (con modo)
     ├─ 7. Embeddings
     │   ├─ 1. Generar embeddings (solo pendientes)
     │   ├─ 2. Previsualizar (dry-run)
     │   └─ 0. Volver
     ├─ p. << Anterior → Hoja 1
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
  ├─ 3. Posición del sol (astronomía)   → scripts/astronomia.py (con modo)
  ├─ 4. Backfill end_time               → opcion_backfill_end_time() (con modo)
  ├─ 5. Backup DB (solo backup)         → opcion_backup_db()
  ├─ 6. Restore DB desde backup         → opcion_restore_db()
  ├─ 7. Resetear DB (backup + limpiar)  → opcion_reset_db()
  ├─ 8. Exportar CSV                    → exportar_csv.main()
  └─ 9. Mover/Copiar medios             → scripts/mover_media.py

6. Mapa de ruta (Folium) → opcion_mapa() (mapa HTML con Folium)

9. Ayuda → opcion_ayuda() (ayuda detallada por comando)
```

##### Filosofía de agrupación del menú TUI

El menú TUI organiza las opciones por **temática**, no por complejidad o cronología del pipeline. Esto significa que operaciones relacionadas aparecen siempre cerca unas de otras, aunque en el pipeline de procesamiento ocurran en momentos distintos.

**Criterios de agrupación:**

| Grupo temático | Menú | Opciones |
|---|---|---|
| **Ingesta** (traer datos al proyecto) | 2. Ingesta | Ingesta de medios, GPX, Telegram, deshacer |
| **IA y Color** (contenido semántico) | 3. Mejorar DB — Hoja 1 | Colores, keywords, descripciones, refinar keywords, transcripción, keypoints |
| **Inferencia básica** (timestamps/GPS) | 3. Mejorar DB — Hoja 2 (1-2) | Inferir timestamps, inferir GPS |
| **Ubicación y tiempo** (contexto geo-temporal) | 3. Mejorar DB — Hoja 2 (3-6) | Localización, clima, día de la semana, astronomía |
| **Búsqueda semántica** | 3. Mejorar DB — Hoja 2 (7) | Embeddings |
| **Mantenimiento** (operaciones técnicas) | 5. Mantenimiento DB | Relocalizar, gradientes, astronomía, backfill, backup, restore, reset, export |

> **Regla de agrupación**: siempre que se agregue una opción nueva al TUI, debe insertarse cerca de opciones temáticamente relacionadas, no al final de la lista.

> **Regla de paginación**: cada hoja soporta hasta **9 opciones** (1-9). Solo cuando se superan las 9 opciones se crea una hoja nueva (la hoja 2 puede tener menos de 9 si no hay más opciones). La navegación es: **n = Siguiente >>**, **p = << Anterior**, **0 = Volver** al menú superior. Las opciones nuevas se insertan cerca de las temáticamente relacionadas; si la hoja correspondiente está llena, se reparten en la hoja siguiente.

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
| `astronomia`        | `scripts/astronomia.py`          |
| `improve-db`        | `scripts/improve_db.py`          |
| `backup-db/backup`  | `opcion_backup_db()` (interno)   |
| `restore-db/restore`| `opcion_restore_db()` (interno)  |
| `reset-db/reset`    | `opcion_reset_db()` (interno)    |
| `undo-ingest/undo`  | `opcion_undo_ingest()` (interno) |
| `export-csv`        | `exportar_csv.main()`           |
| `backfill-end-time` | `opcion_backfill_end_time()` (int.) |
| `import-telegram` / `tg` | `scripts/import_telegram.main()` |

#### Funciones helper clave en flujos.py

| Función | Propósito |
|---------|-----------|
| `_verificar_ollama()` | Verifica que Ollama esté corriendo (GET localhost:11434/api/tags). Se llama antes de keywords y descriptions (pasos que requieren visión). **No** se llama para transcribe (faster-whisper es independiente de Ollama). |
| `_preguntar_modo(db_path)` | Pregunta skip/update/replace y devuelve el string. Usada en TODAS las operaciones de DB. Si el modo es "replace" y db_path es válido, llama a `_auto_backup()`. |
| `_auto_backup(db_path)` | Crea backup automático con timestamp en `db/backups/`. Retorna la ruta o None. |
| `_ejecutar_improve_db()` | Wrapper que verifica Ollama si el paso lo requiere, luego llama a improve_db.main(). |
| `leer_db()` | Resuelve la ruta a la DB (default: `db/flujos.db`). |
| `resumen_db()` | Devuelve string con totales (6 líneas: Total, Imágenes, Videos, Audios, Textos, Otros). |

### Utilidades compartidas (`db/`)

#### `db/util.py` (181 lines)
- **Propósito**: Funciones de conexión DB y helpers centralizados para evitar duplicación en todos los scripts.
- **Funciones**:
  - `abrir(db_path)` → `sqlite3.Connection`: abre conexión con WAL mode + foreign_keys ON. Lanza `FileNotFoundError` si la DB no existe.
  - `conectar(db_path)` → context manager: igual que `abrir()` pero con commit automático al salir y rollback en excepción.
  - `resolver_db(db_path)` → `str`: resuelve ruta absoluta a la DB. Si es `None`, devuelve `db/flujos.db` absoluto.
- **Clase** `ModoHelper(mode)`: lógica skip/update/replace centralizada con métodos `clean()`, `build_query()`, `update_flag_cols()`.
- **Uso**: `from db.util import abrir, resolver_db, ModoHelper`

### Pipeline scripts (scripts/)

#### `ingest.py` (~1485 lines)
- **Propósito**: Escanea una carpeta, extrae metadados (ExifTool, ffprobe), calcula hashes, inserta en DB. La extracción de colores dominantes se eliminó de la ingesta (delegada a `improve_db.py --step colors`).
- **Args CLI**: `--root` (obligatorio), `--recursive`/`-r`, `--types` (image,video,audio,text), `--allow-no-timestamp`, `--full-hash`, `--dry-run`, `--verbose`, `--db`, `--exiftool`, `--compute-video-hash`
- **DB que modifica**: `media` (insert), `media_metadata` (insert)
- **Dependencias**: subprocess (exiftool, ffprobe), Pillow (proxy)
- **Notas**: 
  - `parse_gps_dms()` — convierte DMS a decimal. **ATENCIÓN**: ExifTool sin `-n` devuelve `"South"`/`"West"` (texto completo), NO `"S"`/`"W"`. La función ahora lo maneja con `_es_sur_oeste()` y `_parse_gps_position()`.
  - `extract_gps_from_exif()` — usa `Composite:GPSPosition` primero, fallback a `EXIF:GPSLatitude+Ref`.
  - `init_db()` — crea el schema desde cero (usado también por reset-db).
  - `parse_timestamp_from_filename()` — extrae timestamp de nombres con formato `YYYY-MM-DD-HH-MM-SS_`.
  - `--types` filtra por tipo de medio al ingerir (default: todos los tipos).
  - `--allow-no-timestamp`: por defecto los archivos sin timestamp se saltan. Con este flag se ingieren igual.
  - `--recursive` escanea subcarpetas (default: solo raíz). Carpetas `excluir/` y ocultas siempre se excluyen.
  - Color extraction removido de ingest (ver `improve_db.py --step colors`).

#### `improve_db.py` (903 lines)
- **Propósito**: Pipeline de 8 pasos post-ingesta con skip/update/replace.
- **Args CLI**: `--steps` (default: todos), `--mode` (skip|update|replace), `--db`, `--list`
- **Pasos**: `colors`, `keywords`, `descriptions`, `transcribe`, `keypoints`, `timestamps`, `gps`, `video_metadata`
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
- **Propósito**: Geocodificación inversa (GPS → provincia/departamento/municipio) vía API Georef Argentina (batch).
- **Args CLI**: `--coords` (modo directo), `--db`, `--limit`, `--dry-run`, `--mode` (skip|update|replace)
- **DB que modifica**: `media.provincia`, `.departamento`, `.municipio`, `.localidad`, `.geocode_source`, `.geocode_date`
- **API**: `https://apis.datos.gob.ar/georef/api/ubicacion?lat=X&lon=Y`
- **⚠️ La API NO devuelve `localidad`**: verificada la documentación y probada empíricamente (Jul 2026), el endpoint `/ubicacion` solo devuelve `provincia`, `departamento` y `municipio`. Ni `campos=localidad` (400), ni `campos=completo`, ni Georef v2.1 (`/api/v2.1/ubicacion`, que renombra `municipio` → `gobierno_local`) incluyen localidad. Por eso la columna `media.localidad` queda NULL. Jerarquía real argentina: **provincia → departamento → localidad**, con el municipio como gobierno local del tercer nivel (en pueblos, municipio ≈ localidad). Ver `docs/geocodificacion_reversa.md` para alternativas de localidad (dataset INDEC offline).
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

#### `astronomia.py`
- **Propósito**: Calcula la posición del sol (elevación, azimut) y clasifica el momento del día (twilight) usando el algoritmo NOAA Solar Calculator. También calcula amanecer, atardecer y cenit solar para cada registro.
- **Args CLI**: `--db`, `--dry-run`, `--verbose`, `--mode` (skip|update|replace)
- **DB que modifica**: `media.sun_elevation`, `.sun_azimuth`, `.sun_distance_au`, `.twilight_period`, `.sunrise_ts`, `.sunset_ts`, `.solar_noon_ts`, `.secs_since_sunrise`, `.secs_to_sunset`, `.secs_since_noon`, `.astronomy_source`
- **Dependencias**: solo Python estándar (math, datetime). **Cero dependencias externas**.
- **Algoritmo**: NOAA Solar Calculator (2017) — https://gml.noaa.gov/grad/solcalc/
- **Clasificación twilight**:
  - `dia`: elevación >= 12°
  - `golden_hour`: elevación 6°-12°
  - `blue_hour`: elevación 0°-6°
  - `crepuculo_civil`: elevación -6° a 0°
  - `crepuculo_nautico`: elevación -12° a -6°
  - `crepuculo_astronomico`: elevación -18° a -12°
  - `noche`: elevación < -18°
- **Eventos solares**: amanecer (sunrise_ts), atardecer (sunset_ts), cenit (solar_noon_ts). Maneja sol de medianoche y noche polar.
- **Notas**: Requiere registros con GPS y timestamp_utc. Precisión ~0.01°.

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
- **DB que modifica**: `media_metadata` (weather_temp_c, weather_humidity_pct, weather_precip_mm, weather_cloud_pct, weather_code, weather_label, weather_wind_speed_kmh, weather_wind_dir_deg, weather_wind_dir_text, weather_pressure_hpa, weather_hour_utc, weather_source)
- **API**: Open-Meteo Historical API (gratis, sin API key).
- **Estrategia**: agrupa medios por (fecha, celda de 0.5° ≈ 55 km). Cada grupo hace una sola llamada a la API. Luego empareja cada medio con la hora más cercana disponible.
- **Notas**: `--steps` filtra horas (ej: --steps 3 = cada 3 horas). `--replace` es alias de `--mode replace`. La velocidad del viento se convierte de m/s a km/h. La dirección se guarda en grados (0-360) y como texto cardinal (N, NE, E, etc.).

#### `dia_semana.py`
- **Propósito**: Calcula el día de la semana (lunes..domingo) desde `timestamp_utc` de cada medio.
- **Args CLI**: `--db`, `--dry-run`, `--replace` (deprecated), `--mode`, `--limit`
- **DB que modifica**: `media_metadata` (clave `dia_semana`, valor: lunes|martes|...|domingo)

#### `refinar_keywords.py` (scripts/ai_media/)
- **Propósito**: Refina y unifica las keywords generadas por IA (`media_metadata.ia_keywords`). Corrige los problemas típicos de los modelos de visión: artículos pegados (`la montaña`), géneros mal formateados, mezclas de géneros, basura regurgitada del prompt, sinónimos duplicados (`bici` vs `bicicleta`).
- **Args CLI**: `--db`, `--mode` (skip|update|replace), `--usar-embeddings`, `--umbral` (default 0.87), `--dry-run`, `--verbose`
- **DB que modifica**: `media_metadata` (sobrescribe `ia_keywords` con la lista refinada)
- **3 capas de refinamiento**:
  1. **Léxica**: `normalizar_palabra()` (quita artículos `la/el/los/las/un/una/unos/unas` iniciales), `singularizar()` (plural→singular), `es_basura()` (filtra `PATRONES_BASURA`: `sa_\d+`, `dsc\d+`, restos del prompt, etc.)
  2. **Diccionario de sinónimos**: `SINONIMOS` (términos canónicos del dominio: bicicleta, motocicleta, automóvil, ruta, montaña, etc.) + `GENEROS_FOTOGRAFICOS` con `VARIANTES_GENERO` (nocturno→nocturna, street→callejera, etc.)
  3. **Semántica (opcional, `--usar-embeddings`)**: agrupa sinónimos con `paraphrase-multilingual:latest` (coseno ≥ `--umbral`, default 0.87). El modelo se eligió tras evaluar varios: `bicicleta~bici` 0.993, `auto~automóvil` 0.985, `bici~perro` 0.146. El umbral se subió de 0.82 a 0.87 porque palabras truncadas generaban falsos positivos (`monta~obra` 0.844, `monta~cerro` 0.869); los sinónimos reales están ≥ 0.88.
- **Reglas del género**: el primer keyword debe ser un género fotográfico. `_tiene_mezcla_generos()` detecta basura como `retrato grupal paisaje`. `refinar_lista_keywords()` busca el género en cualquier posición, promueve el género a la primera posición y lo elimina del resto. Si no hay género → `otras`. La capa semántica NUNCA re-mapea el género (posición 0 protegida) y excluye los géneros del clustering para evitar `naturaleza`→`paisaje`.
- **Modos**: skip (solo registros con keywords), update/replace (reprocesa todos).
- **Integración**: TUI (Mejorar DB → Hoja 1 → 7. Refinar keywords), CLI (`python scripts/ai_media/refinar_keywords.py`)

#### `exportar_csv.py`
- **Propósito**: Exporta todas las tablas de la DB a CSVs dentro de `db/exports/<timestamp>/`.
- **Args CLI**: `--db`, `--output/-o`, `--table/-t`, `--dry-run`, `--list-tables`
- **Tablas**: media, media_metadata, media_keypoints, media_embeddings (sin columna BLOB), config, tracks, waypoints
- **Notas**:
  - `media_embeddings.csv` exporta TODAS las filas **sin** la columna `embedding` (BLOB binario)
  - `media_metadata.csv` excluye las claves `transcript` y `transcript_segments` (valores muy grandes para CSV)
  - Todos los CSVs usan `encoding="utf-8-sig"` (con BOM) para que LibreOffice/Excel detecten UTF-8 automáticamente
  - Genera `_resumen.txt` con conteo de registros por tabla
  - Accesible desde TUI (Mantenimiento DB → Exportar CSV) y CLI (`python flujos.py export-csv`)

#### Scripts de verificación

| Script | Propósito |
|--------|-----------|
| `check_db.py` | Inspecciona las 5 tablas con counts y muestras. Se ejecuta desde opcion_check_db() en flujos.py. |
| `check_gps.py` | Verifica GPS en archivos via ExifTool, compara con DB. |
| `check_db_data.py` | Helper: muestra stats de weather, dia_semana y geocode. |

#### `puente_td.py` (324 lines)
- **Propósito**: Puente BD → TouchDesigner vía OSC. El cerebro Python que consulta la DB y envía datos a TD para la instalación interactiva.
- **Args CLI**: `enviar` (loop completo), `colores` (solo envía colores), `enviar_imgs <color>` (envía N imágenes), `nube` (nube de tags). Args: `--db`, `--cant`, `--max-tags`, `--host`, `--port`, `--verbose`
- **OSC**: Escucha en puerto 9001 (TD → Python), envía a puerto 9000 (Python → TD)
- **Modos**:
  - `enviar`: envía colores a TD → espera selección → envía imágenes del color elegido
  - `colores`: solo lista de colores disponibles (desde color_1_name_basic)
  - `enviar_imgs <color>`: envía N imágenes al azar de un color específico
  - `nube`: cuenta keywords en DB y envía top N con frecuencia y peso normalizado
- **Dependencias**: python-osc, sqlite3

#### `import_telegram.py`
- **Propósito**: Importa exports de Telegram (result.json) a la base de datos. Procesa chats, mensajes (texto y multimedia) y sus archivos adjuntos. Opcionalmente ingiere los multimedia en la tabla `media` para que pasen por el pipeline de enriquecimiento.
- **Args CLI**: `--export-path`/`-e` (obligatorio), `--include-system`/`--no-system`, `--ingest-media`/`--no-ingest`, `--mode` (skip|update|replace), `--dry-run`, `--db`, `--verbose`, `--destino`/`-d` (carpeta canónica para copiar los archivos)
- **DB que modifica**: `telegram_chats` (INSERT/UPDATE), `telegram_messages` (INSERT/UPDATE), `telegram_media` (INSERT), `media` (INSERT/UPDATE con vínculo telefónico), `media_metadata` (INSERT)
- **Estrategia**:
  - Parsea `result.json` (repara JSON truncado automáticamente con conteo de brackets)
  - Registra/actualiza el chat en `telegram_chats`
  - Cada mensaje → `telegram_messages` (con tipo: text/photo/video/voice/animation/sticker/document/location/poll/system)
  - Mensajes de sistema marcados con `es_sistema=1`
  - Multimedia → `telegram_media` (ruta relativa al export)
  - Si `--ingest-media` (default): también ingiere en `media` con SHA-256, timestamp del mensaje, type mapeado (photo→image, video_file→video, voice_message→audio, etc.)
  - Si `--destino`: copia el archivo a `{destino}/telegram/{filename}` en vez de mantener la ruta dentro del export temporal. Resuelve colisiones con `_1`, `_2`, etc.
  - Vinculación bidireccional: `telegram_media.media_id` → `media.id`, y `media.telegram_message_id` → `telegram_messages.id`
  - JSON se repara si está truncado (el export de Telegram a veces no cierra el array/objeto)
  - **Recuperación de media pendiente**: al re-importar con `--mode skip`, los mensajes existentes se saltan pero se ejecuta una etapa que busca `telegram_media` con `media_id=NULL` (archivos no disponibles en corridas previas) e intenta ingerirlos. Permite N re-ejecuciones hasta que todos los archivos estén descargados.
- **Integración**: TUI (Ingesta → opción 4, pregunta por destino), CLI (`python flujos.py import-telegram` o `python flujos.py tg`)

#### `mover_media.py`
- **Propósito**: Mueve o copia archivos de medios a una nueva ubicación y actualiza las rutas en la DB automáticamente. Dos modos: `mover` (mueve + actualiza DB) y `copiar` (copia, opcionalmente actualiza DB con `--update-db`).
- **Args CLI**: `--new-root` (obligatorio), `--mode` (mover|copiar), `--old-root`, `--update-db`, `--dry-run`, `--db`
- **DB que modifica**: `media.filepath_absoluto`, `media.filepath_relativo`, `media.carpeta`, `media.sidecar_xml`
- **Estrategia**:
  - Lee `old_root` de `config.ingest_root` en DB (o se pasa `--old-root`)
  - Reemplaza prefijo en rutas: `abs_path.replace(old_root, new_root, 1)`
  - Colisiones de nombre resueltas con sufijo `_1`, `_2`, etc.
  - Sidecars (.AAE, .json, .xml, .XMP) se mueven/copian desde el directorio fuente original
  - Actualiza `sidecar_xml` en DB si corresponde
  - Dry-run previsualiza cambios sin escribir
- **Integración**: TUI (Mantenimiento DB → opción 9), CLI (`python flujos.py mover --new-root X --mode mover`)

### Scripts de IA (`scripts/ai_media/`)
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
| `refinar_keywords.py` | Refina y unifica keywords de IA (3 capas: léxica, diccionario de sinónimos, semántica con embeddings). Sobrescribe `media_metadata.ia_keywords`. | ollama_client |
| `proxy.py` | Redimensiona imágenes a ~2MP para procesamiento IA más rápido. | Pillow |

### Scripts TouchDesigner (`td/`)

| Archivo | Se vincula en | Parámetros |
|---------|---------------|------------|
| `td/osc_callbacks.dat` | `osc_in1/osc_in1_callbacks` (DAT interno del OSC In DAT) | `File` = `td/osc_callbacks.dat`, `Sync to File` = ON |
| `td/nube_generar.dat` | `generar_nube/generar_nube_callbacks` (DAT interno del Script DAT) | `File` = `td/nube_generar.dat`, `Sync to File` = ON |

**Estructura de nombres de operadores TD esperados:**
- `osc_in1` — OSC In DAT (puerto 9000)
- `osc_in1/osc_in1_callbacks` — DAT interno donde va el código (File → `td/osc_callbacks.dat`)
- `tabla_colores` — Table DAT con lista de colores
- `nube_datos` — Table DAT con columnas [palabra, frecuencia, peso]
- `movie1` — Movie File In TOP para slideshow de imágenes
- `generar_nube` — Script DAT
- `generar_nube/generar_nube_callbacks` — DAT interno donde va el código (File → `td/nube_generar.dat`)
- `nube_container` — Base COMP contenedor de Text TOPs de la nube
- `color_actual`, `seleccion_actual`, `info_imagen` — Text DATs para estado

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
   ├── 7. gps          → inferir GPS desde EXIF/exiftool
   └── 8. video_metadata → ExifTool en videos (cámara, 360°, author)
       │
       ▼
4. ENRIQUECER (scripts independientes, con skip/update/replace):
   ├── dia_semana.py       → día de la semana en español
   ├── fetch_weather.py    → clima histórico Open-Meteo
   ├── geocode.py          → provincia/municipio/localidad (Georef API)
   ├── gradiente.py        → distancia, elevación, pendiente entre puntos GPS
   └── astronomia.py       → posición del sol, clasificación twilight (NOAA)
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

Usar `db/util.py` para conexiones:

```python
from db.util import abrir, resolver_db, conectar

# Opción 1: abrir/cerrar manual
conn = abrir("db/flujos.db")
# ... operaciones ...
conn.close()

# Opción 2: context manager (commit automático)
with conectar(resolver_db(args.db)) as conn:
    conn.execute("INSERT ...")
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
| `docs/visualizaciones.md` | Decisiones de diseño de la visualización web3 (bloques, colocación, chips, Fluir). |
| `docs/diseno_instalacion.md` | **Diseño de la instalación**: flujo completo DB → elecciones → filtros → loop de 5 min. Grupos de metadatos (7), modalidad de horas/ubicaciones, posicionamiento de medios, chiches. Próximo paso: motor de loop en Python. |
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

- **GPS Sign Bug (Jul 2026)**: durante semanas los GPS se guardaron con signo positivo (lat=+31 en vez de -31). La DB actual puede tener coordenadas incorrectas. Fixeado en `ingest.py` con `_es_sur_oeste()`. (Nota: verificado que los 226 registros con GPS tienen signo negativo correcto.)
- **Color anti-gray bias**: implementado después de que usuarios reportaran que verdes desaturados y marrones oscuros caían en "gris". La distancia Redmean + umbral 1.5x resolvió el caso.
- **webcolors 25.x rompió color_utils (Ago 2026)**: la versión 25.10.0 removió la constante `CSS3_HEX_TO_NAMES` (dict). `extract_dominant_colors` seguía funcionando, pero `get_color_names` fallaba con `AttributeError`. El pipeline lo tragaba silenciosamente: `run_colors` contaba los fallos en `stats["colors_err"]` pero el resumen final solo sumaba `stats["errors"]`, mostrando "Errores: 0" pese a 626 imágenes fallidas (además los errores individuales estaban en `log.debug`). Fix en `color_utils.py`: mapa cacheado `CSS3_HEX_TO_NAMES` construido con la API nueva (`webcolors.names(spec=CSS3)` + `name_to_hex`) con fallback a la API vieja. Fix en `improve_db.py`: el resumen final ahora suma los `*_err` individuales de cada paso, y los errores por archivo pasaron de `log.debug` a `log.warning`. Se re-procesaron las 626 imágenes pendientes (852/852 con colores, 100%).
- **Open-Meteo**: se eligió sobre otras APIs climáticas por ser gratuito, sin API key, y cubrir datos históricos desde 1940 (ERA5-Land).
- **Georef**: API del gobierno argentino, gratuita, sin key. Soporta batch de hasta 5000 coordenadas.
- **Georef no devuelve localidad (Jul 2026)**: el endpoint `/api/ubicacion` (georreferencia inversa) solo devuelve `provincia`, `departamento` y `municipio`. Se verificó empíricamente que `campos=localidad` da HTTP 400, `campos=completo` solo agrega `fuente`, y Georef v2.1 (`/api/v2.1/ubicacion`) renombra `municipio` → `gobierno_local` sin agregar localidad. La columna `media.localidad` queda NULL. La jerarquía territorial argentina es provincia → departamento → localidad (municipio = gobierno local de tercer nivel, en pueblos ≈ localidad). Documentado en `docs/geocodificacion_reversa.md` y en el agente `.opencode/agents/gis.md`.
- **gradiente.py**: implementado en Python puro (Haversine, sin numpy/gdal) para mantener cero dependencias pesadas. Fix: `min(a, 1.0)` en `asin` para evitar NaN por error de punto flotante.
- **astronomia.py (Jul 2026)**: implementado algoritmo NOAA Solar Calculator en Python puro (math, datetime). Calcula elevación, azimut y distancia del sol para cada registro GPS. Clasifica twilight: día, golden_hour, blue_hour, crepúsculos (civil/náutico/astronómico), noche. También calcula amanecer, atardecer y cenit solar para cada fecha/ubicación. Maneja sol de medianoche y noche polar. Cero dependencias externas. Precisión ~0.01°.
- **--types filter (Jul 2026)**: se corrigió el filtro de tipos en `ingest.py` para que XML no-sidecar no pase cuando se usan `--types image,video` (antes cualquier `.xml` pasaba por ser extensión de sidecar).
- **mode update vs replace (Jul 2026)**: se unificó el comportamiento en `improve_db.py` (`run_keypoints`, `run_timestamps`, `run_gps`), `fetch_weather.py` y `dia_semana.py`: `--mode update` reprocesa todos los registros sin limpiar primero, `--mode replace` limpia y regenera.
- **gradiente NULL timestamp (Jul 2026)**: se agregó `AND timestamp_utc IS NOT NULL` a la query de `gradiente.py` para evitar que puntos GPS sin timestamp se ordenen al inicio (NULLs primero en SQLite) generando distancias sin sentido.
- **viento_direccion_a_texto (Jul 2026)**: helper que convierte grados (0-360) a punto cardinal (N, NE, E, etc.) usando 16 rumbos. Agregado en `fetch_weather.py` junto con las variables `wind_speed_10m`, `wind_direction_10m`, `surface_pressure`.
- **Schema versioning (Jul 2026)**: se creó `db/migrate.py` con migraciones centralizadas. Versión 1 = schema inicial, versión 2 = tracks + waypoints, versión 3 = embeddings schema canónico, versión 4 = tablas Telegram. `ingest_gpx.py` ahora usa el sistema central en vez de su propio `migrar_db()`.
- **Auto-backup en replace (Jul 2026)**: `_preguntar_modo(db_path)` ahora crea backup automático en `db/backups/` cuando se elige modo "replace". El usuario ve el nombre del backup creado.
- **Undo GPX (Jul 2026)**: `opcion_undo_ingest()` ahora lista también tracks GPX (prefijo `t<id>`) junto con batches de medios (prefijo `b<id>`). Al deshacer un track, se borra el track + sus waypoints (CASCADE) y se revierte la altitud de medios con `geolocation_source='track_gps'`.
- **Puente TD (Jul 2026)**: se creó `scripts/puente_td.py` como puente Python ↔ TD vía OSC (puertos 9000→TD, 9001←TD). Arquitectura híbrida: Python = cerebro (DB, lógica de deriva), TD = músculo (reproducción audiovisual). Scripts TD externalizados a `td/osc_callbacks.dat` (OSC callbacks) y `td/nube_generar.dat` (tag cloud), vinculables desde TD via Text DAT con File + Sync to File = ON.
- **Export CSV (Jul 2026)**: `scripts/exportar_csv.py` exporta todas las tablas a CSV en `db/exports/<timestamp>/`. Opción 7 en TUI Mantenimiento DB, también `python flujos.py export-csv`.
- **BOM UTF-8 en CSV (Jul 2026)**: se cambió `encoding="utf-8"` por `encoding="utf-8-sig"` en todos los `open()` de `exportar_csv.py`. El BOM (`\xef\xbb\xbf`) hace que LibreOffice y Excel detecten UTF-8 automáticamente, evitando mojibake (`Ã¡` en vez de `á`).
- **Filtro transcript/segments en CSV (Jul 2026)**: `exportar_csv.py` excluye las claves `transcript` y `transcript_segments` de `media_metadata.csv` por ser valores demasiado grandes para CSV útil. Definido en `MEDIA_METADATA_EXCLUIR_VALORES_GRANDES`.
- **Migración v3 con callables (Jul 2026)**: `db/migrate.py` ahora soporta callables como acciones de migración (no solo SQL strings). La migración v3 usa un callable `_migrar_media_embeddings` que maneja tanto DB nueva (crea tabla) como DB existente (migra datos del schema viejo al canónico). Testeado en simulación v2→v3 y en DB real (`db/flujos.db`).
- **CHANGELOG.md (Jul 2026)**: registro cronológico de todos los cambios del proyecto.
- **db/util.py (Jul 2026)**: utilidades de DB centralizadas (`abrir`, `resolver_db`, `conectar`, `ModoHelper`) extraídas de 9 scripts que tenían sus propias versiones duplicadas. La refactorización incluye un fix para ejecución standalone (`if __name__ == "__main__" and __package__ is None: sys.path.insert(0, ...)`) para que `python scripts/foo.py` funcione desde cualquier directorio.
- **import_telegram.py (Jul 2026)**: nuevo script para importar exports de Telegram. Crea tablas `telegram_chats`, `telegram_messages`, `telegram_media`. Opcionalmente ingiere multimedia en `media` table con vinculación bidireccional. Repara JSON truncado automáticamente. Integrado en TUI (Ingesta → 4) y CLI (`python flujos.py import-telegram` / `tg`). Migración v4.
- **--destino en Telegram (Jul 2026)**: `import_telegram.py` ahora acepta `--destino` para copiar automáticamente los archivos a una carpeta canónica (`{destino}/telegram/`) durante la importación, evitando que queden atados al export temporal. Resuelve colisiones con `_1`, `_2`.
- **Recuperación media pendiente Telegram (Jul 2026)**: al re-importar con `--mode skip`, los mensajes existentes se saltan pero se ejecuta una etapa de recuperación que busca `telegram_media` con `media_id=NULL` e intenta ingerir los archivos ahora disponibles. Permite N re-ejecuciones hasta completar.
- **mover_media.py (Jul 2026)**: script para mover/copiar archivos de medios a nueva ubicación y actualizar DB automáticamente. Soporta sidecars (.AAE, .json, .xml, .XMP) moviéndolos desde el directorio fuente. Integrado en TUI (Mantenimiento DB → 9) y CLI (`python flujos.py mover`).
- **moondream no apto para keywords (Jul 2026)**: se detectó que `moondream:latest` regurgita el prompt y devuelve keywords basura (géneros solos, textos del prompt). Se cambió `MODELO_VISION_DEFAULT` a `qwen2.5vl:3b` en `image_analysis.py` y el default de `OllamaVision` en `ollama_client.py` (timeout 120→180s). Los prompts `PROMPT_KEYWORDS`/`PROMPT_COMBINADO` se simplificaron a "exactamente 5 keywords, género primero" y `_validar_genero()` ahora busca el género en cualquier posición.
- **refinar_keywords.py (Jul 2026)**: script de 3 capas para limpiar/unificar `ia_keywords`. Evalúa sinónimos con `paraphrase-multilingual:latest` (coseno ≥ 0.87; `bicicleta~bici` 0.993, `bici~perro` 0.146; falsos positivos de palabras truncadas `monta~obra` 0.844 quedan fuera). Se descartó `nextfire/paraphrase-multilingual-minilm` por confundir no-sinónimos. Integrado en TUI (Mejorar DB → Parte 1 → 9).

---

## Riesgos conocidos

### 1. Suspensión de la computadora durante procesos largos

Si la PC entra en suspensión (S3 Sleep o Modern Standby S0) durante un proceso del pipeline:

| Componente | Comportamiento | Riesgo |
|---|---|---|
| **Ollama** (localhost) | La conexión loopback a `127.0.0.1:11434` revive al despertar, pero el handler del modelo pierde contexto. La request HTTP puede colgar hasta el timeout (120s). | Bajo — timeout maneja el caso |
| **Open-Meteo / Georef API** | Socket TCP muerto durante el sueño. `CLOSE_WAIT` hasta que Python detecte el error. | Medio — puede colgar 60-120s |
| **faster-whisper** (local) | La computación se congela y reanuda limpio. | Muy bajo |
| **ExifTool / ffprobe** (subprocess) | El hijo se congela con el padre, reanuda normal. | Muy bajo |
| **SQLite WAL** | Transacciones atómicas, WAL checkpoint recupera al reanudar. | Muy bajo |
| **ThreadPoolExecutor** (`keywords`, `descriptions`) | **Riesgo mayor**: un worker colgado en un `as_completed()` sin timeout puede congelar el pool **para siempre**. El script nunca termina, el usuario debe matarlo manualmente. | **Alto** |

**Qué se pierde**: solo el tiempo de procesamiento. Los datos ya commiteados sobreviven. Al reiniciar con `--mode skip` se retoman los pendientes.

**Fix pendiente**: agregar `timeout=` en `as_completed()` para `run_keywords` y `run_descriptions`, y verificar que `ollama_client.py` tenga `timeout=` en todos los `requests.post()`.

### 2. Archivos movidos externamente

Si los archivos se mueven/renombran por fuera del proyecto (explorador de archivos, Lightroom, etc.), la DB queda con rutas obsoletas. Solución: `relocate.py` o `mover_media.py`.

### 3. Timeouts de API externas

- **Open-Meteo**: sin API key, gratuito, pero puede rate-limit si se llaman muchas coordenadas seguidas. El agrupamiento por celda de 0.5° mitiga esto.
- **Georef API**: gratuita, batch hasta 5000 coordenadas. Si falla, reintentar más tarde.

### 4. Espacio en disco

Los modelos Ollama ocupan ~50 GB totales. `faster-whisper` descarga modelos ~2 GB al primer uso. Las transcripciones y embeddings se guardan en DB (el archivo `.db` puede crecer significativamente).
