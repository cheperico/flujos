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
│    └─ Limpieza de tandas de fotografías    │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ 2. INGESTAR                 │  python flujos.py ingest --root CARPETA
│    ├─ Hash + fingerprint    │
│    ├─ EXIF (GPS, timestamp) │
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
│    ├─ gps                   │  Inferir GPS desde EXIF
│    └─ video_metadata        │  Metadatos de cámara/360° en videos
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ 4. ENRIQUECER               │  Scripts independientes con --mode
│    ├─ dia_semana.py         │  Día de la semana (lunes..domingo)
│    ├─ fetch_weather.py      │  Clima histórico (Open-Meteo)
│    ├─ geocode.py            │  Provincia/municipio/localidad (Georef)
│    ├─ gradiente.py          │  Distancia, elevación, pendiente GPS
│    ├─ astronomia.py         │  Posición del sol, clasificación twilight
│    ├─ keywords_transcripciones.py │  Keywords del sentido (transcripciones y textos, Ollama texto)
│    └─ audio_tagging.py      │  Sonidos ambientales (sherpa-onnx CED-mini)
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ 5. CONSULTAR / EXPORTAR     │
│    ├─ query.py              │  Consultas por color, tiempo, lugar...
│    ├─ exportar_csv.py       │  Exportar DB a CSV
│    ├─ relocate.py           │  Actualizar rutas si los archivos se mudan
│    ├─ backup-db / restore   │  Backup y restore de la DB
│    └─ TouchDesigner         │  Motor de reproducción (vía puente_td.py)
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
| `ingest --root CARPETA [--types TIPOS] [--recursive] [--allow-no-timestamp] [--dry-run]` | Ingerir medios desde una carpeta. `--types` filtra por tipo (image,video,audio,text). `--allow-no-timestamp` ingiere archivos sin timestamp. |
| `improve-db [--mode] [--steps]` | Post-procesamiento (9 pasos: colors, keywords, descriptions, combinado, transcribe, keypoints, timestamps, gps, video_metadata) |
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
| `export-csv [--table] [--output]` | Exportar tablas de la DB a CSV |
| `import-telegram` / `tg` | Importar export de Telegram a la DB |
| `mover --new-root X --mode mover` | Mover/copiar medios y actualizar rutas en DB |
| `detectar-contenedores` / `contenedores` | Auditar contenedores de video/audio con ffprobe (streams faltantes) → `contenedor_estado` |
| `limpiar-descripciones` / `descripciones` | Limpiar descripciones con eco del prompt (meta-intros) → recorta prefijos en `ia_description_en`/`ia_description` |
| `repetir-contenido` / `repetidos` | Buscar contenido repetido por coincidencias de audio (solo reporta, no escribe) |
| `audio-frame` / `crossref` | Correlacionar contenido de audio con frames de video |
| `analizar-video` / `analizar` | Analizar videos con IA: escenas + keywords (scene detection → muestreo → visión) |
| `keypoints-contexto` / `keypoints` | Keypoints de contexto (devenir geográfico) contra los tracks GPX |

Cada subcomando acepta `--help` para ver sus opciones específicas.

---

## TUI — Menú interactivo

Al ejecutar `python flujos.py` sin argumentos se ingresa al menú TUI:

```
1. Preparar medios
  └─ 1. Limpieza de tandas de fotografias

2. Ingesta
  ├─ 1. Ingerir multimedia (fotos, sonidos, videos, etc.)
  ├─ 2. Ingerir track GPS (GPX)
  ├─ 3. Ingerir textos (.md)
  ├─ 4. Ingerir chat de Telegram
  └─ 5. Deshacer ingesta

3. Mejorar base de datos
  ├─ Hoja 1: IA y color
  │  ├─ 1. Todos los pasos (skip)
  │  ├─ 2. Elegir pasos manualmente
  │  ├─ 3. Colores dominantes
  │  ├─ 4. Keywords con IA
  │  ├─ 5. Descripcion con IA
  │  ├─ 6. Keywords + Descripcion (pasada unica, mas lenta)
  │  ├─ 7. Audio tagging (sonidos ambientales)
  │  ├─ 8. Transcripcion (audios/videos)
  │  ├─ 9. Keypoints de transcripciones
  │  ├─ n. Siguiente >> → Hoja 2
  │  └─ 0. Volver
  ├─ Hoja 2: Etiquetado + inferencia y ubicacion
  │  ├─ 1. Keywords desde textos y transcripciones
  │  │   ├─ 1. Desde transcripciones (audio/video)
  │  │   │   ├─ 1. Procesar (solo pendientes)
  │  │   │   ├─ 2. Re-procesar todos (update)
  │  │   │   ├─ 3. Limpiar y regenerar (replace)
  │  │   │   ├─ 4. Previsualizar (dry-run)
  │  │   │   └─ 0. Volver
  │  │   ├─ 2. Desde textos (.md ingresados)
  │  │   │   └─ (mismos 4 modos + 0. Volver)
  │  │   └─ 0. Volver
  │  ├─ 2. Refinar keywords (normalizar + sinonimos)
  │  │   ├─ 1. Imagenes (ia_keywords)
  │  │   │   ├─ 1. Refinar todos (update)
  │  │   │   ├─ 2. Previsualizar (dry-run)
  │  │   │   └─ 0. Volver
  │  │   ├─ 2. Transcripciones (ia_keywords_transcripcion)
  │  │   ├─ 3. Textos (ia_keywords_texto)
  │  │   └─ 0. Volver
  │  ├─ 3. Inferir timestamps
  │  ├─ 4. Inferir GPS
  │  ├─ 5. Calcular gradientes de ruta
  │  ├─ 6. Localizacion (provincia, municipio, localidad)
  │  ├─ 7. Condiciones climaticas
  │  ├─ 8. Dia de la semana
  │  ├─ 9. Posicion del sol (astronomia)
  │  ├─ p. << Anterior → Hoja 1
  │  ├─ n. Siguiente >> → Hoja 3
  │  └─ 0. Volver
  ├─ Hoja 3: Analisis de video
  │  ├─ 1. Analizar video (escenas + IA)
  │  │   ├─ 1. Analizar un video individual
  │  │   ├─ 2. Analizar todos los pendientes de la DB
  │  │   ├─ 3. Previsualizar (dry-run)
  │  │   └─ 0. Volver
  │  ├─ 2. Keypoints de contexto (devenir geografico)
  │  │   ├─ 1. Procesar (solo pendientes)
  │  │   ├─ 2. Re-procesar todos (update)
  │  │   ├─ 3. Limpiar y regenerar (replace)
  │  │   ├─ 4. Previsualizar (dry-run)
  │  │   └─ 0. Volver
  │  ├─ p. << Anterior → Hoja 2
  │  └─ 0. Volver

4. Consultar base de datos
  ├─ 1. Ver resumen de la DB
  └─ 2. Listar... (tipo, autor, carpeta, color, provincia, texto, GPS, detalle)

5. Mantenimiento DB
  ├─ Hoja 1: Mantenimiento general
  │  ├─ 1. Relocalizar medios (cambio de raiz)
  │  ├─ 2. Calcular posición del sol (astronomía)
  │  ├─ 3. Backfill end_time
  │  ├─ 4. Backup DB (solo backup, sin borrar)
  │  ├─ 5. Restore DB desde backup
  │  ├─ 6. Resetear DB (backup + limpiar)
  │  ├─ 7. Exportar DB a CSV
  │  ├─ 8. Mover/Copiar medios
  │  ├─ 9. Auditar contenedores (streams faltantes)
  │  │   ├─ 1. Ejecutar auditoría (anotar estado en DB)
  │  │   ├─ 2. Previsualizar (dry-run)
  │  │   └─ 0. Volver
  │  ├─ n. Siguiente >> → Hoja 2
  │  └─ 0. Volver
  ├─ Hoja 2: Auditoría de medios
  │  ├─ 1. Buscar contenido repetido (audio)
  │  │   ├─ 1. Comparar un archivo contra el resto
  │  │   ├─ 2. Todos contra todos
  │  │   └─ 0. Volver
  │  ├─ 2. Correlacionar audio con frames
  │  │   ├─ 1. Correlacionar audio con frames
  │  │   └─ 0. Volver
  │  ├─ p. << Anterior → Hoja 1
  │  └─ 0. Volver
  ├─ Hoja 3: Limpieza de datos
  │  ├─ 1. Limpiar descripciones (eco del prompt)
  │  │   ├─ 1. Ejecutar limpieza (con backup)
  │  │   ├─ 2. Previsualizar (dry-run)
  │  │   └─ 0. Volver
  │  ├─ p. << Anterior → Hoja 2
  │  └─ 0. Volver

6. Visualizaciones
  ├─ 1. Mapa de ruta (Folium)
  ├─ 2. Exportar visualización web (deploy)
      ├─ 1. Deploy a deploy/ (pregunta si transcodificar)
      ├─ 2. Deploy a otra carpeta (pregunta si transcodificar)
      ├─ 3. Re-exportar snapshot local (deploy/db, sin copiar medios)
      ├─ 4. Regenerar spec del loop (deploy/spec.json)
      ├─ 5. Previsualizar deploy (dry-run)
      └─ 0. Volver
  └─ 3. TouchDesigner (puente OSC)
      ├─ 1. Enviar elecciones (horas, municipios, colores, tags, días, clima)
      ├─ 2. Modo "Fluir" (recibir ráfaga de TD y generar loop)
      │   ├─ 1. Una ráfaga (prueba rápida)
      │   └─ 2. Modo instalación: escucha continua (Enter para detener)
      ├─ 3. Probar OSC (eco)
      └─ 0. Volver

9. Ayuda
```

Todas las operaciones que modifican la DB preguntan el modo
(`skip` / `update` / `replace`) antes de ejecutar.

---

## Scripts

| Script | Propósito | Pipeline |
|--------|-----------|----------|
| `flujos.py` | Entry point unificado con subcomandos y TUI | — |
| `scripts/ingest.py` | Escanea, extrae metadatos e ingiere en DB | Ingesta |
| `scripts/ingest_gpx.py` | Ingesta de tracks GPS (GPX): waypoints, registro, backfill de altitud | Ingesta |
| `scripts/import_telegram.py` | Importa exports de Telegram a la DB (chats, mensajes, multimedia vinculado y opcionalmente en `media`) | Ingesta |
| `scripts/improve_db.py` | 9 pasos post-`ingest` (colors, keywords, descriptions, combinado, transcribe, keypoints, timestamps, gps, video_metadata) | Mejora |
| `scripts/query.py` | Consultas a la DB | Consulta |
| `scripts/exportar_csv.py` | Exporta tablas de la DB a CSV | Consulta |
| `scripts/relocate.py` | Actualiza rutas absolutas cuando los archivos se mudan | Gestión |
| `scripts/mover_media.py` | Mueve/copia medios a nueva ubicación y actualiza rutas en DB | Gestión |
| `scripts/consolidar_medios.py` | Consolida medios de múltiples raíces absolutas en una estructura unificada (copiar/mover + actualizar DB + `ingest_root`) | Gestión |
| `scripts/color_utils.py` | Extracción y naming de colores (usado por ingest y improve-db) | Ingesta / Mejora |
| `scripts/geocode.py` | Geocodificación inversa vía Georef API Argentina | Enriquecimiento |
| `scripts/gradiente.py` | Cálculo de distancia Haversine, elevación y pendiente | Enriquecimiento |
| `scripts/fetch_weather.py` | Clima histórico (Open-Meteo ERA5-Land) | Enriquecimiento |
| `scripts/dia_semana.py` | Día de la semana desde timestamp | Enriquecimiento |
| `scripts/astronomia.py` | Posición del sol (NOAA), clasificación twilight | Enriquecimiento |
| `scripts/limpiar_tandas.py` | Selección de mejor imagen por tanda | Curación |
| `scripts/mover_descartadas.py` | Mueve imágenes descartadas a carpeta excluir/ | Curación |
| `scripts/td/puente_td.py` | Puente BD → TouchDesigner vía OSC | Instalación |
| `scripts/mapa_ruta.py` | Mapa interactivo con Folium | Consulta |
| `scripts/check_db.py` | Inspección de la DB | Consulta |
| `scripts/check_gps.py` | Verifica GPS en archivos via ExifTool | Consulta |
| `scripts/check_db_data.py` | Stats de weather, dia_semana y geocode | Consulta |
| `scripts/keypoints_contexto.py` | Keypoints de contexto (devenir geográfico): interpola track GPX, transiciones elevación/astronomía/movimiento, georef+clima con cache → `media_keypoints` (`contexto_*`) | Enriquecimiento |
| `scripts/detectar_contenedores.py` | Audita contenedores de video/audio con ffprobe (streams faltantes) → `contenedor_estado`/`contenedor_streams` | Auditoría |
| `scripts/repetir_contenido.py` | Detecta contenido repetido por audio (cross-correlación RMS; solo reporta, no escribe) | Auditoría |
| `scripts/audio_frame_crossref.py` | Correlaciona sonidos (CED-mini) con frames de video (solo reporta, no escribe) | Auditoría |
| `scripts/limpiar_descripciones.py` | Recorta meta-intros (eco del prompt) en `ia_description_en`/`ia_description` — determinista, sin IA, backup automático | Mantenimiento |
| `scripts/fix_gps_sign.py` | Corrección de signo GPS (herramienta de mantenimiento) | Mantenimiento |
| `scripts/test_gradiente.py` | Tests unitarios de gradiente.py | — |

### IA (`scripts/ai_media/`)

| Script | Propósito |
|--------|-----------|
| `ollama_client.py` | Cliente Ollama compartido (visión + texto + embeddings) |
| `image_analysis.py` | Keywords + descripción de imágenes vía Ollama (keywords libres, sin género); recorta meta-intros regurgitadas con `limpiar_meta_intro()` |
| `analyze_video.py` | Análisis de videos por escenas: scene detection → ~10 imgs/escena → nitidez → 1 llamada de visión por escena (keywords + descripción, máx 20 tags) |
| `keypoints_video.py` | Keypoints semánticos de video: `media_keypoints` key=`escena`/`keyword`, source `ollama` (desde `video_analysis`) |
| `tag_images.py` | Etiquetar imágenes (modo DB o sidecar) |
| `transcribe.py` | Transcripción vía faster-whisper (independiente, sin DB) — VAD + filtro de confianza |
| `transcribe_media.py` | Transcripción desde DB |
| `batch_selector.py` | Selección de mejor imagen de tanda con IA |
| `clustering.py` | Agrupamiento por tags o embeddings |
| `generate_embeddings.py` | Embeddings vectoriales (nomic-embed-text) — retirado del TUI, rediseño pendiente (ver ROADMAP) |
| `refinar_keywords.py` | Refina y unifica keywords IA por familia (léxico + sinónimos, sin género) — `--clave` (imágenes/transcripciones/textos) |
| `traducir_metadata.py` | Traduce metadata de IA EN → ES sobre la DB (keywords/descripciones) |
| `keywords_transcripciones.py` | Keywords del sentido (qwen2.5:3b): `--origen transcripcion` → `ia_keywords_transcripcion`; `--origen texto` → `ia_keywords_texto` |
| `audio_tagging.py` | Sonidos ambientales (sherpa-onnx CED-mini, local) → `ia_keywords_sonido` |
| `proxy.py` | Redimensiona imágenes a ~800px para IA |
| `loop_engine.py` | Motor de loop: núcleo puro (arcos horarios N→N−1, cruce de medianoche, posición de medios `t_loop`) |
| `loop_db.py` | Motor de loop integrado con DB (filtros + chiches consolidados + spec JSON) → ver `docs/motor_loop.md` |

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
| `altitude` | REAL | Altitud en metros | ingest / improve-db gps / ingest_gpx |
| `geolocation_source` | TEXT | metadata, gpx, manual, track_gps | ingest / improve-db gps / ingest_gpx |
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
| `sun_elevation` | REAL | Elevación del sol en grados | astronomia |
| `sun_azimuth` | REAL | Azimut del sol en grados | astronomia |
| `sun_distance_au` | REAL | Distancia al sol en UA | astronomia |
| `twilight_period` | TEXT | dia, golden_hour, blue_hour, crepuculo_*, noche | astronomia |
| `astronomy_source` | TEXT | noaa_solar_calculator | astronomia |
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
| `ia_keywords` | JSON array de 5-7 palabras clave libres (sin género comodín) | improve-db keywords |
| `ia_description` | Texto: descripción breve generada por IA | improve-db descriptions |
| `transcript` | Texto: transcripción completa de audio/video | improve-db transcribe |
| `dia_semana` | lunes\|martes\|...\|domingo | dia_semana.py |
| `weather_temp_c` | Temperatura en °C | fetch_weather.py |
| `weather_humidity_pct` | Humedad relativa % | fetch_weather.py |
| `weather_precip_mm` | Precipitación en mm | fetch_weather.py |
| `weather_cloud_pct` | Cobertura nubosa % | fetch_weather.py |
| `weather_code` | Código WMO de clima | fetch_weather.py |
| `weather_label` | Descripción textual del clima | fetch_weather.py |
| `weather_wind_speed_kmh` | Velocidad del viento a 10 m (km/h) | fetch_weather.py |
| `weather_wind_dir_deg` | Dirección del viento en grados (0-360) | fetch_weather.py |
| `weather_wind_dir_text` | Dirección del viento (N, NE, E, SE, S, SO, O, NO) | fetch_weather.py |
| `weather_pressure_hpa` | Presión atmosférica superficial (hPa) | fetch_weather.py |
| `weather_hour_utc` | Hora del dato climático | fetch_weather.py |
| `weather_source` | `open-meteo-era5` | fetch_weather.py |
| `video_analysis` | JSON del análisis de video por escenas (escenas, keywords, descripciones, fotogramas) | analyze_video.py |
| `contenedor_estado` | `ok`\|`sin_video`\|`sin_audio`\|`sin_contenido`\|`error_ffprobe`\|`archivo_faltante` | detectar_contenedores.py |
| `contenedor_streams` | JSON con el detalle de los streams detectados | detectar_contenedores.py |
| `keypoints_video_estado` | `ok`\|`sin_datos` — sentinel de procesado de keypoints de video | keypoints_video.py |
| `keypoints_contexto_estado` | `ok`\|`sin_datos` — sentinel de procesado de keypoints de contexto | keypoints_contexto.py |

### Tabla `media_keypoints`

Segmentos temporales con timestamp (ej: segmentos de transcripción):

| Columna | Descripción |
|---------|-------------|
| `media_id` | Referencia a media(id) |
| `timestamp_offset_secs` | Offset desde inicio del medio |
| `timestamp_absolute` | timestamp_utc + offset |
| `key` | Tipo de keypoint: `transcription` (whisper), `contexto_*` (contexto geográfico), `escena`/`keyword` (análisis de video) |
| `value` | Contenido del segmento |
| `source` | Origen (faster-whisper, ollama, track_interpolado, estimado, gps_propio, etc.) |

### Tabla `media_embeddings`

| Columna | Descripción |
|---------|-------------|
| `media_id` | Referencia a media(id) |
| `embedding` | Vector de embedding (BLOB) |
| `modelo` | Modelo usado (default: nomic-embed-text) |
| `fecha` | Fecha de generación del embedding |

### Tabla `config`

Configuración global de la DB: `ingest_root`, `current_ingest_batch`, `schema_version`.

### Tabla `tracks`

Tracks GPS ingestados desde archivos GPX:

| Columna | Descripción |
|---------|-------------|
| `id` | Clave primaria |
| `name` | Nombre del track |
| `filepath_absoluto` | Ruta al archivo GPX |
| `filepath_relativo` | Ruta relativa al proyecto |
| `source_url` | URL de origen (RideWithGPS, etc.) |
| `start_time` | Timestamp del primer punto |
| `end_time` | Timestamp del último punto |
| `total_points` | Cantidad de track points |

### Tabla `waypoints`

Puntos de interés de los tracks GPX:

| Columna | Descripción |
|---------|-------------|
| `id` | Clave primaria |
| `track_id` | Referencia a tracks(id) |
| `name` | Nombre del waypoint |
| `description` | Descripción textual |
| `category` | Categoría (bikeshare, stop, food, etc.) |
| `type` | Tipo (checkpoint, service, danger, etc.) |
| `latitude` | Latitud WGS84 |
| `longitude` | Longitud WGS84 |
| `timestamp` | Timestamp asociado |

---

## Enriquecimiento de datos

Estos scripts agregan capas de metadata a la DB después de la ingesta.
Todos soportan `--mode skip|update|replace`.

| Script | Qué agrega | Requisito |
|--------|-----------|-----------|
| `dia_semana.py` | Día de la semana (lunes..domingo) en `media_metadata` | `timestamp_utc` no NULL |
| `fetch_weather.py` | Clima histórico (temp, humedad, lluvia, nubes, viento, presión) en `media_metadata` | `timestamp_utc` y coordenadas GPS |
| `geocode.py` | Provincia, municipio, localidad en `media` | Coordenadas GPS (NEGATIVAS) |
| `gradiente.py` | Distancia, elevación, pendiente entre puntos GPS en `media` | Coordenadas GPS + 2+ puntos |
| `astronomia.py` | Posición del sol (elevación, azimut) y clasificación twilight en `media` | Coordenadas GPS + `timestamp_utc` |

---

## Mantenimiento de DB

| Comando / TUI opción | Qué hace |
|----------------------|----------|
| `relocate.py` | Actualiza rutas si los archivos se mudaron de carpeta |
| `backfill-end-time` | Precalcula end_time para registros existentes |
| `gradiente.py` | Calcula distancia, elevación y pendiente entre puntos GPS |
| `backup-db` | Crea copia timestampada de `db/flujos.db` en `db/backups/` |
| `restore-db` | Lista backups disponibles y restaura el seleccionado |
| `reset-db` | Hace backup, borra la DB y la recrea desde schema.sql |
| `exportar_csv.py` | Exporta tablas de la DB a CSV en `db/exports/<timestamp>/` |

---

## Stack

| Componente | Versión | Propósito |
|------------|---------|-----------|
| **Python** | 3.13+ | Scripting principal |
| **SQLite** | 3.x (incluido) | Base de datos embebida |
| **ffmpeg** | 8.1.2+ | Análisis y transcodificación de video/audio |
| **ExifTool** | 13.59+ | Metadatos EXIF/IPTC/XMP |
| **Pillow** | 12.2+ | Colores dominantes, content hash, thumbnails |
| **tqdm** | 4.68+ | Barras de progreso |
| **webcolors** | 25.10+ | Nombres de colores CSS en español |
| **python-osc** | 1.8+ | Comunicación OSC con TouchDesigner |
| **ollama** | 0.3+ | Cliente Python para Ollama (visión/texto/embeddings) |
| **faster-whisper** | 1.2+ | Transcripción de audio con timestamps |
| **numpy** | 1.24+ | Clustering y similitud de embeddings |
| **folium** | 0.15+ | Mapas interactivos (HTML Leaflet) |
| **imagehash** | 4.3+ | Hash perceptual para limpieza de tandas |
| **Ollama** | 0.31+ | Servicio de modelos de IA (visón, texto, embeddings) |
| **TouchDesigner** | 2022.28080+ | Motor de reproducción audiovisual (instalación) |

### Modelos Ollama

```powershell
# Modelos de visión
ollama pull moondream:latest          # 1.7 GB — rápido y pequeño
ollama pull qwen2.5vl:3b              # 3.2 GB — más preciso, liviano
ollama pull qwen2.5vl:latest          # 6.0 GB — buena calidad
ollama pull llama3.2-vision:latest    # 7.8 GB — buena calidad general

# Modelos de texto
ollama pull qwen3.5:9b                # 6.6 GB — análisis de texto
ollama pull qwen3.5:4b                # 3.4 GB — liviano
ollama pull deepseek-r1:latest        # 5.2 GB — razonamiento
ollama pull llama3.1:8b               # 4.9 GB — propósito general
ollama pull llama3.2:3b               # 2.0 GB — liviano

# Modelos de código
ollama pull deepseek-coder-v2:16b     # 8.9 GB — código
ollama pull qwen3-coder:latest        # 18 GB — código (grande)

# Embeddings
ollama pull nomic-embed-text           # 274 MB — embeddings / búsquedas semánticas
ollama pull nomic-embed-text-v2-moe    # 957 MB — embeddings mejorados
```

> **RAM:** con `moondream:latest` el uso de RAM sube ~40% sobre el idle.
> Modelos más grandes requieren más RAM.
> Usar `--list-models` en los scripts para ver los modelos instalados.

---

## Requerimientos

### Python 3.13+

```powershell
python --version
# Debería decir Python 3.13.x
```

> El proyecto usa Python 3.13.14. Versiones >=3.10 deberían funcionar,
> pero no están testeadas.

### Programas externos

#### ffmpeg + ffprobe (>= 6.0)

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

#### ExifTool (>= 13.0)

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

#### Ollama (>= 0.31)

```powershell
# Descargar e instalar: https://ollama.com/download
# Ollama corre como servicio en segundo plano.

# Verificar:
ollama --version

# Verificar que el servicio responda:
curl http://localhost:11434/api/tags
```

> Todos los modelos instalados se listan desde el TUI con:
> `python flujos.py` → `3. Mejorar DB` → se verifica automáticamente.

### Dependencias Python

#### Instalación rápida (todo junto)

```powershell
pip install Pillow webcolors tqdm python-osc ollama faster-whisper numpy folium imagehash
```

#### Instalación detallada (por librería)

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

#### Dependencias automáticas

Las siguientes se instalan como dependencia de las de arriba (no hace falta
instalarlas explícitamente):

| Librería | Instalada por | Para qué se usa en el proyecto |
|----------|---------------|-------------------------------|
| `branca` | folium | Mapas de colores en folium |
| `torch` | faster-whisper | Motor de inferencia de whisper (pesado: ~2 GB) |
| `ctranslate2` | faster-whisper | Inferencia optimizada de whisper |
| `jinja2` | folium | Template de mapas HTML |

#### Verificar instalación

```powershell
python -c "import PIL, webcolors, tqdm, pythonosc, ollama, faster_whisper, numpy, folium, imagehash; print('Todas las librerias OK')"
```

### TouchDesigner (solo para la instalación)

```powershell
# Descargar: https://derivative.ca/download
# Versión: 2022.28080 o superior (no probado en versiones anteriores)
```

Usado como motor de reproducción audiovisual de la instalación.
Recibe datos vía OSC desde `scripts/td/puente_td.py`.

### Notas sobre CUDA (opcional)

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
| `docs/semantica_color.md` | Capa semántica del color: significados, Kuleshov effect, cross-modal retrieval |
| `docs/calculo_astronomico.md` | Cálculo astronómico de posición de sol y luna |
| `docs/visualizaciones.md` | Decisiones de diseño de la visualización web (deploy) |
| `docs/diseno_instalacion.md` | Diseño de la instalación: flujo DB → elecciones → loop |
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
│   ├── migrate.py             # Migraciones centralizadas de schema
│   ├── util.py                # Conexiones DB (abrir, resolver_db, ModoHelper)
│   ├── test_migrate.py        # Tests de migraciones
│   ├── flujos.db              # Base de datos (no versionada)
│   ├── backups/               # Backups timestampados
│   └── exports/               # Exportaciones CSV
│
├── scripts/                   # Pipeline scripts
│   ├── __init__.py
│   ├── ingest.py              # Ingesta de medios
│   ├── ingest_gpx.py          # Ingesta de tracks GPS (GPX)
│   ├── import_telegram.py     # Importar export de Telegram
│   ├── improve_db.py          # Post-procesamiento (9 pasos)
│   ├── query.py               # Consultas a DB
│   ├── exportar_csv.py        # Exportar DB a CSV
│   ├── relocate.py            # Relocalizar medios
│   ├── mover_media.py         # Mover/copiar medios + actualizar DB
│   ├── consolidar_medios.py   # Consolidar medios de múltiples raíces
│   ├── geocode.py             # Geocodificación inversa
│   ├── gradiente.py           # Gradientes de ruta
│   ├── fetch_weather.py       # Clima histórico
│   ├── dia_semana.py          # Día de la semana
│   ├── astronomia.py          # Posición del sol, twilight
│   ├── color_utils.py         # Colores dominantes
│   ├── limpiar_tandas.py      # Limpieza de tandas de fotografías
│   ├── mover_descartadas.py   # Mover descartadas
│   ├── puente_td.py           # Puente BD → TouchDesigner (OSC)
│   ├── mapa_ruta.py           # Mapa interactivo (Folium)
│   ├── check_db.py            # Inspección de DB
│   ├── check_gps.py           # Verificación GPS
│   ├── check_db_data.py       # Helper: clima, día, geocode
│   ├── keypoints_contexto.py  # Keypoints de contexto (devenir geográfico)
│   ├── detectar_contenedores.py  # Auditoría de contenedores (ffprobe)
│   ├── repetir_contenido.py   # Contenido repetido por audio
│   ├── audio_frame_crossref.py  # Correlación audio ↔ frames
│   ├── fix_gps_sign.py        # Corrección de signo GPS
│   ├── test_gradiente.py      # Tests de gradiente
│   ├── ai_media/              # Scripts de IA
│       ├── __init__.py
│       ├── ollama_client.py
│       ├── image_analysis.py
│       ├── analyze_video.py
│       ├── keypoints_video.py
│       ├── tag_images.py
│       ├── transcribe.py
│       ├── transcribe_media.py
│       ├── traducir_metadata.py
│       ├── batch_selector.py
│       ├── clustering.py
│       ├── generate_embeddings.py
│       ├── refinar_keywords.py
│       ├── keywords_transcripciones.py
│       ├── audio_tagging.py
│       ├── loop_engine.py          # Motor de loop: núcleo puro
│       ├── loop_db.py              # Motor de loop: integración con DB
│       └── proxy.py
│   └── td/                    # Scripts TouchDesigner (Python)
│       ├── puente_td.py       # Puente BD → TouchDesigner (OSC)
│       ├── elecciones.py      # Nubes de elecciones (DB → TD)
│       └── osc_probe.py       # Eco OSC de diagnóstico
│
├── td/                        # Archivos TouchDesigner (.dat/.toe)
│   ├── osc_callbacks.dat      # Callbacks OSC In DAT
│   └── elecciones_ui.dat      # Generación de UI de elecciones (botones)
│
├── docs/                      # Documentos de diseño
└── .opencode/
    ├── agents/                # Subagentes OpenCode
    └── skills/                # Skills OpenCode
```
