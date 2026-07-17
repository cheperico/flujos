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
Medios crudos
     │
     ▼
┌─────────────────────────────┐
│ 1. PREPARAR                 │  limpiar_tandas.py (opcional, elimina bursts)
│    └─ Limpieza de tandas    │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ 2. INGESTAR                 │  python flujos.py ingest --root CARPETA
│    ├─ Hash + fingerprint    │
│    ├─ EXIF (GPS, timestamp) │
│    ├─ Colores dominantes    │
│    └─ Insert en DB          │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ 3. MEJORAR DB               │  python flujos.py improve-db [--mode]
│    ├─ colors                │  Colores dominantes (reprocesar)
│    ├─ keywords              │  Palabras clave con IA (Ollama)
│    ├─ descriptions          │  Descripción con IA (Ollama)
│    ├─ transcribe            │  Transcripción (faster-whisper)
│    ├─ keypoints             │  Segmentos de transcripción
│    ├─ timestamps            │  Inferir timestamp desde EXIF
│    └─ gps                   │  Inferir GPS desde EXIF
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ 4. ENRIQUECER               │  Scripts independientes con --mode
│    ├─ dia_semana.py         │  Día de la semana (lunes..domingo)
│    ├─ fetch_weather.py      │  Clima histórico (Open-Meteo)
│    ├─ geocode.py            │  Provincia/municipio/localidad (Georef)
│    └─ gradiente.py          │  Distancia, elevación, pendiente GPS
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ 5. CONSULTAR / EXPORTAR     │
│    ├─ query.py              │  Consultas por color, tiempo, lugar...
│    ├─ relocate.py           │  Actualizar rutas si los archivos se mudan
│    ├─ backup-db / restore   │  Backup y restore de la DB
│    └─ TouchDesigner         │  (próximamente) Motor de reproducción
└─────────────────────────────┘
```

Cada etapa puede correrse total o parcialmente.

---

## Entry point unificado

```powershell
python flujos.py                # Menú interactivo (TUI)
python flujos.py --tui          # Ídem
python flujos.py --help         # Ayuda general
```

### Subcomandos

| Comando | Qué hace |
|---------|----------|
| `ingest --root CARPETA` | Ingerir medios desde una carpeta |
| `improve-db [--mode] [--steps]` | Post-procesamiento (7 pasos: colors, keywords, descriptions, transcribe, keypoints, timestamps, gps) |
| `geocode [--mode]` | Geocodificación inversa (GPS → provincia/municipio/localidad) |
| `gradient [--mode]` | Calcular gradientes de ruta entre puntos GPS |
| `query [--distinct --where --search --count --limit]` | Consultar la base de datos |
| `relocate --new-root CARPETA` | Actualizar rutas si los archivos se mudaron |
| `check-db` | Resumen de la DB (totales por tipo) |
| `check-gps` | Revisar qué archivos tienen GPS |
| `undo-ingest` | Deshacer una ingesta por batch ID |
| `backfill-end-time [--mode]` | Precalcular end_time = timestamp_utc + duration_secs |
| `backup-db` / `backup` | Crear backup de la DB |
| `restore-db` / `restore` | Restaurar DB desde un backup |
| `reset-db` / `reset` | Resetear la DB (con backup previo) |

Cada subcomando acepta `--help` para ver sus opciones específicas.

---

## TUI — Menú interactivo

Al ejecutar `python flujos.py` sin argumentos se ingresa al menú TUI:

```
1. Preparar medios
  └─ 1. Limpieza de tandas

2. Ingesta
  ├─ 1. Hacer ingesta
  └─ 2. Deshacer ingesta

3. Mejorar base de datos
  ├─ Parte 1: IA y color
  │  ├─ 1. Todos los pasos (skip)
  │  ├─ 2. Elegir pasos manualmente
  │  ├─ 3. Colores dominantes
  │  ├─ 4. Keywords con IA
  │  ├─ 5. Descripción con IA
  │  ├─ 6. Keywords + Descripción
  │  ├─ 7. Transcripción
  │  ├─ 8. Keypoints
  │  ├─ v. Ver modelos Ollama instalados
  │  └─ 9. Siguiente >> → Parte 2
  └─ Parte 2: Inferencia y enriquecimiento
     ├─ 1. Inferir timestamps
     ├─ 2. Inferir GPS
     ├─ 3. Localización (geocode)
     ├─ 4. Condiciones climáticas
     ├─ 5. Día de la semana
     ├─ 6. Embeddings
     │   ├─ 1. Generar embeddings
     │   ├─ 2. Previsualizar (dry-run)
     │   ├─ 3. Ver modelos Ollama instalados
     │   └─ 0. Volver
     ├─ 9. << Anterior → Parte 1
     └─ 0. Volver

4. Consultar base de datos
  ├─ 1. Ver resumen de la DB
  └─ 2. Listar... (tipo, autor, carpeta, color, provincia, texto, GPS, detalle)

5. Mantenimiento DB
  ├─ 1. Relocalizar medios
  ├─ 2. Calcular gradientes de ruta
  ├─ 3. Backfill end_time
  ├─ 4. Backup DB
  ├─ 5. Restore DB desde backup
  └─ 6. Resetear DB

6. Ayuda
```

Todas las operaciones que modifican la DB preguntan el modo
(`skip` / `update` / `replace`) antes de ejecutar.

---

## Scripts

| Script | Propósito | Pipeline |
|--------|-----------|----------|
| `flujos.py` | Entry point unificado con subcomandos y TUI | — |
| `scripts/ingest.py` | Escanea, extrae metadatos e ingiere en DB | Ingesta |
| `scripts/improve_db.py` | 7 pasos post-ingesta (colors, keywords, descriptions, transcribe, keypoints, timestamps, gps) | Mejora |
| `scripts/query.py` | Consultas a la DB | Consulta |
| `scripts/relocate.py` | Actualiza rutas absolutas cuando los archivos se mudan | Gestión |
| `scripts/color_utils.py` | Extracción y naming de colores (usado por ingest y improve-db) | Ingesta / Mejora |
| `scripts/geocode.py` | Geocodificación inversa vía Georef API Argentina | Enriquecimiento |
| `scripts/gradiente.py` | Cálculo de distancia Haversine, elevación y pendiente | Enriquecimiento |
| `scripts/fetch_weather.py` | Clima histórico (Open-Meteo ERA5-Land) | Enriquecimiento |
| `scripts/dia_semana.py` | Día de la semana desde timestamp | Enriquecimiento |
| `scripts/limpiar_tandas.py` | Selección de mejor imagen por tanda | Curación |
| `scripts/mover_descartadas.py` | Mueve imágenes descartadas a carpeta excluir/ | Curación |
| `scripts/check_db.py` | Inspección de la DB | Consulta |
| `scripts/check_gps.py` | Verifica GPS en archivos via ExifTool | Consulta |
| `scripts/check_db_data.py` | Stats de weather, dia_semana y geocode | Consulta |
| `scripts/test_gradiente.py` | Tests unitarios de gradiente.py | — |

### IA (`scripts/ai_media/`)

| Script | Propósito |
|--------|-----------|
| `ollama_client.py` | Cliente Ollama compartido (visión + texto + embeddings) |
| `image_analysis.py` | Keywords + descripción de imágenes vía Ollama (17 géneros) |
| `video_analysis.py` | Análisis de videos (keyframes + descripción) |
| `analyze_video.py` | Scene-change detection + análisis visual |
| `tag_images.py` | Etiquetar imágenes (modo DB o sidecar) |
| `transcribe.py` | Transcripción vía faster-whisper (independiente, sin DB) |
| `transcribe_media.py` | Transcripción desde DB |
| `batch_selector.py` | Selección de mejor imagen de tanda con IA |
| `clustering.py` | Agrupamiento por tags o embeddings |
| `generate_embeddings.py` | Embeddings vectoriales (nomic-embed-text) |
| `proxy.py` | Redimensiona imágenes a ~2MP para IA |

---

## Base de datos

Se crea automáticamente en `db/flujos.db`. SQLite con WAL mode y foreign_keys=ON.

### Tabla `media` (~55 columnas)

| Columna | Tipo | Descripción | Escrito por |
|---------|------|-------------|-------------|
| `id` | INTEGER | Clave primaria | (automático) |
| `filename_original` | TEXT | Nombre original del archivo | ingest |
| `filepath_absoluto` | TEXT | Ruta completa en disco | ingest / relocate |
| `filepath_relativo` | TEXT | Ruta relativa a la raíz de ingest | ingest / relocate |
| `carpeta` | TEXT | Carpeta contenedora | ingest / relocate |
| `type` | TEXT | image, video, audio, text, other | ingest |
| `subtype` | TEXT | 360, entrevista, paisaje, etc. | ingest |
| `size_bytes` | INTEGER | Tamaño del archivo | ingest |
| `file_hash` | TEXT | SHA-256 del archivo completo (UNIQUE) | ingest |
| `content_hash` | TEXT | SHA-256 ignorando metadatos | ingest |
| `sidecar_xml` | TEXT | Ruta al XML sidecar SONY | ingest / relocate |
| `sidecar_parsed` | INTEGER | 1 si ya se procesó el XML | ingest |
| `sidecar_hash` | TEXT | Hash del XML | ingest |
| `timestamp_original` | TEXT | Fecha/hora original del EXIF | ingest / improve-db timestamps |
| `timestamp_utc` | TEXT | Normalizado a UTC (ISO 8601) | ingest / improve-db timestamps |
| `timezone_note` | TEXT | Cómo se determinó la zona horaria | ingest / improve-db timestamps |
| `duration_secs` | REAL | Duración en segundos (videos/audios) | ingest |
| `end_time` | TEXT | timestamp_utc + duration_secs | backfill-end-time |
| `latitude` | REAL | Latitud (±90°, NEGATIVO en Argentina) | ingest / improve-db gps |
| `longitude` | REAL | Longitud (±180°, NEGATIVO en Argentina) | ingest / improve-db gps |
| `altitude` | REAL | Altitud en metros | ingest / improve-db gps |
| `geolocation_source` | TEXT | metadata, gpx, manual | ingest / improve-db gps |
| `provincia` | TEXT | Provincia (geocodificación) | geocode |
| `departamento` | TEXT | Departamento (poco usado en ARG) | geocode |
| `municipio` | TEXT | Municipio (geocodificación) | geocode |
| `localidad` | TEXT | Localidad (geocodificación) | geocode |
| `geocode_source` | TEXT | georef_api, etc. | geocode |
| `geocode_date` | TEXT | Fecha de geocodificación | geocode |
| `distance_from_prev_m` | REAL | Distancia Haversine al punto anterior | gradiente |
| `elevation_gain_m` | REAL | Cambio de elevación (m) | gradiente |
| `gradient_pct` | REAL | (elevation_gain / distance) × 100 | gradiente |
| `cumul_distance_m` | REAL | Distancia acumulada desde el inicio | gradiente |
| `cumul_elevation_gain_m` | REAL | Ganancia de elevación acumulada | gradiente |
| `author` | TEXT | Autor del medio | ingest |
| `author_source` | TEXT | exif, carpeta, modelo_camara | ingest |
| `color_1_hex` | TEXT | Color dominante 1 en #rrggbb | ingest / improve-db colors |
| `color_1_name_css` | TEXT | Nombre CSS en español | ingest / improve-db colors |
| `color_1_name_basic` | TEXT | Categoría (rojo, azul...) | ingest / improve-db colors |
| `color_2_hex` | TEXT | Color dominante 2 | ingest / improve-db colors |
| `color_2_name_css` | TEXT | Nombre CSS en español | ingest / improve-db colors |
| `color_2_name_basic` | TEXT | Categoría | ingest / improve-db colors |
| `color_3_hex` | TEXT | Color dominante 3 | ingest / improve-db colors |
| `color_3_name_css` | TEXT | Nombre CSS en español | ingest / improve-db colors |
| `color_3_name_basic` | TEXT | Categoría | ingest / improve-db colors |
| `ingested_at` | TEXT | Fecha de ingestión | ingest |
| `updated_at` | TEXT | Fecha de última actualización | improve-db / geocode / etc. |
| `ingest_batch_id` | INTEGER | ID de la corrida de ingesta (para undo) | ingest |

### Tabla `media_metadata`

Metadatos variables en formato clave-valor:

| Clave | Valor | Escrito por |
|-------|-------|-------------|
| `ia_keywords` | JSON array de 5-7 palabras clave (incluye género) | improve-db keywords |
| `ia_description` | Texto: descripción breve generada por IA | improve-db descriptions |
| `transcript` | Texto: transcripción completa de audio/video | improve-db transcribe |
| `dia_semana` | lunes\|martes\|...\|domingo | dia_semana.py |
| `weather_temp_c` | Temperatura en °C | fetch_weather.py |
| `weather_humidity_pct` | Humedad relativa % | fetch_weather.py |
| `weather_precip_mm` | Precipitación en mm | fetch_weather.py |
| `weather_cloud_pct` | Cobertura nubosa % | fetch_weather.py |
| `weather_code` | Código WMO de clima | fetch_weather.py |
| `weather_label` | Descripción textual del clima | fetch_weather.py |
| `weather_hour_utc` | Hora del dato climático | fetch_weather.py |
| `weather_source` | `open-meteo-era5` | fetch_weather.py |

### Tabla `media_keypoints`

Segmentos temporales con timestamp (ej: segmentos de transcripción):

| Columna | Descripción |
|---------|-------------|
| `media_id` | Referencia a media(id) |
| `timestamp_offset_secs` | Offset desde inicio del medio |
| `timestamp_absolute` | timestamp_utc + offset |
| `key` | Tipo de keypoint (ej: `transcript_segment`) |
| `value` | Contenido del segmento |
| `source` | Origen (faster-whisper, etc.) |

### Tabla `media_embeddings`

| Columna | Descripción |
|---------|-------------|
| `media_id` | Referencia a media(id) |
| `embedding` | Vector de embedding (BLOB) |
| `modelo` | Modelo usado (default: nomic-embed-text) |

### Tabla `config`

Configuración global de la DB: `ingest_root`, `current_ingest_batch`, etc.

---

## Enriquecimiento de datos

Estos scripts agregan capas de metadata a la DB después de la ingesta.
Todos soportan `--mode skip|update|replace`.

| Script | Qué agrega | Requisito |
|--------|-----------|-----------|
| `dia_semana.py` | Día de la semana (lunes..domingo) en `media_metadata` | `timestamp_utc` no NULL |
| `fetch_weather.py` | Clima histórico (temp, humedad, lluvia, nubes) en `media_metadata` | `timestamp_utc` y coordenadas GPS |
| `geocode.py` | Provincia, municipio, localidad en `media` | Coordenadas GPS (NEGATIVAS) |
| `gradiente.py` | Distancia, elevación, pendiente entre puntos GPS en `media` | Coordenadas GPS + 2+ puntos |

---

## Mantenimiento de DB

| Comando / TUI opción | Qué hace |
|----------------------|----------|
| `relocate.py` | Actualiza rutas si los archivos se mudaron de carpeta |
| `backfill-end-time` | Precalcula end_time para registros existentes |
| `backup-db` | Crea copia timestampada de `db/flujos.db` en `db/backups/` |
| `restore-db` | Lista backups disponibles y restaura el seleccionado |
| `reset-db` | Hace backup, borra la DB y la recrea desde schema.sql |

---

## IA (Procesamiento de medios)

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
ollama pull moondream:latest          # 1.7 GB — rápido y pequeño
ollama pull qwen2.5vl:3b              # 3.2 GB — más preciso, liviano
ollama pull qwen2.5vl:latest          # 6.0 GB — buena calidad
ollama pull llama3.2-vision:latest    # 7.8 GB — buena calidad general
```

> **RAM:** con `moondream:latest` el uso de RAM sube ~40% sobre el idle.
> Modelos más grandes requieren más RAM.
> Usar `--list-models` en los scripts para ver los modelos instalados.

#### Scripts que usan visión

| Script | Qué hace |
|--------|----------|
| `scripts/ai_media/tag_images.py` | Etiqueta y describe imágenes (DB o sidecar) |
| `scripts/ai_media/analyze_video.py` | Análisis visual de video: scene detection + keyframes con IA |
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

Los modelos se descargan automáticamente la primera vez que se usan.

#### Scripts que usan transcripción

| Script | Qué hace |
|--------|----------|
| `scripts/ai_media/transcribe_media.py` | Transcripción automática (DB, carpeta o archivo) |
| `scripts/ai_media/analyze_video.py` | Análisis visual de video con scene detection + IA |
| `scripts/ai_media/transcribe.py` | Módulo base (exporta SRT/TXT/JSON) |

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
| **Ollama** | 0.31+ | Modelos de visión (etiquetado, descripción) |
| **faster-whisper** | 1.2+ | Transcripción de audio con timestamps |

### Instalación de herramientas externas

```powershell
# ffmpeg — transcodificación, scene detection, extracción de fotogramas
winget install "FFmpeg (Essentials Build)"

# ExifTool — metadatos EXIF/IPTC/XMP
winget install ExifTool.ExifTool

# Ollama — modelos de visión (etiquetado, descripción, calidad)
winget install Ollama.Ollama
ollama pull moondream:latest          # 1.7 GB — rápido y pequeño
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

## Documentos de diseño

| Documento | Contenido |
|-----------|-----------|
| `VISION.md` | Visión del proyecto, concepto curatorial |
| `ROADMAP.md` | Estado de cada etapa del pipeline |
| `AGENTS.md` | Documentación exhaustiva del proyecto (schema, mapa de datos, scripts, convenciones) |
| `docs/arquitectura_motor.md` | TD puro vs híbrido TD+Python |
| `docs/flujo_de_medios.md` | Pipeline completo en el motor de reproducción |
| `docs/linea_de_tiempo.md` | Diseño conceptual de la línea de tiempo |
| `docs/geocodificacion_reversa.md` | Estrategias de geocodificación |
| `docs/limpieza_tandas_resultados.md` | Comparativa de estrategias de limpieza |
| `docs/ideas_externas.md` | Ideas de terceros para la instalación |

---

## Estructura del proyecto

```
/
├── flujos.py                  # Entry point unificado (TUI + CLI)
├── AGENTS.md                  # Documentación exhaustiva del proyecto
├── VISION.md                  # Concepto de la instalación
├── ROADMAP.md                 # Estado y prioridades
├── README.md                  # Este archivo
│
├── db/
│   ├── schema.sql             # Definición completa del schema
│   └── flujos.db              # Base de datos (no versionada)
│
├── scripts/                   # Pipeline scripts
│   ├── ingest.py              # Ingesta de medios
│   ├── improve_db.py          # Post-procesamiento (7 pasos)
│   ├── query.py               # Consultas a DB
│   ├── relocate.py            # Relocalizar medios
│   ├── geocode.py             # Geocodificación inversa
│   ├── gradiente.py           # Gradientes de ruta
│   ├── fetch_weather.py       # Clima histórico
│   ├── dia_semana.py          # Día de la semana
│   ├── color_utils.py         # Colores dominantes
│   ├── limpiar_tandas.py      # Limpieza de tandas
│   ├── mover_descartadas.py   # Mover descartadas
│   ├── check_db.py            # Inspección de DB
│   ├── check_gps.py           # Verificación GPS
│   ├── check_db_data.py       # Helper: clima, día, geocode
│   ├── test_gradiente.py      # Tests de gradiente
│   └── ai_media/              # Scripts de IA
│       ├── ollama_client.py
│       ├── image_analysis.py
│       ├── video_analysis.py
│       ├── analyze_video.py
│       ├── tag_images.py
│       ├── transcribe.py
│       ├── transcribe_media.py
│       ├── batch_selector.py
│       ├── clustering.py
│       ├── generate_embeddings.py
│       └── proxy.py
│
├── docs/                      # Documentos de diseño
└── .opencode/
    ├── agents/                # Subagentes OpenCode
    └── skills/                # Skills OpenCode
```
