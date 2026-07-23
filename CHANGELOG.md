# Changelog

Todos los cambios significativos del proyecto Flujos.

Formato basado en [Keep a Changelog](https://keepachangelog.com/).
Las versiones corresponden a entregas funcionales, no a releases semánticas.

---

## [Entrega 9] — 2026-07-23

### Añadido
- **Utilidades de DB centralizadas** (`db/util.py`): `abrir()` (conexión con WAL + foreign_keys), `resolver_db()` (resolución de ruta a `db/flujos.db`), `conectar()` (context manager), `ModoHelper` (lógica skip/update/replace centralizada).
- **Migraciones con callables** (`db/migrate.py`): `_MIGRACIONES` ahora acepta strings SQL y callables. Migración v3 (`_migrar_media_embeddings`) es un callable que maneja tanto DB nueva como DB con tabla existente.
- **Sys.path fix para standalone**: los 8 scripts refactorizados agregan la raíz del proyecto a `sys.path` cuando se ejecutan como script principal.

### Cambiado
- **Refactorización masiva de conexiones DB**: 8 scripts ahora importan `abrir` y `resolver_db` desde `db/util.py` en vez de tener funciones duplicadas:
  `fetch_weather.py`, `gradiente.py`, `geocode.py`, `relocate.py`, `ingest_gpx.py`, `exportar_csv.py`, `puente_td.py`, `query.py`.
- También se refactorizó `dia_semana.py` (sys.path fix agregado).
- `ingest_gpx.py`: conserva `verificar_schema()` tras `abrir()` para migración automática.
- `geocode.py`: `_conectar()` reemplazada por `abrir()` + `migrar_db()`.

### Corregido
- **Import `db.util` en scripts standalone**: scripts ejecutados como `python scripts/foo.py` fallaban con `ModuleNotFoundError: No module named 'db'` porque `sys.path[0]` apunta a `scripts/`. Agregado bloque `if __name__ == "__main__" and __package__ is None: sys.path.insert(0, ...)` en los 8 scripts + `dia_semana.py`.

---

## [Entrega 8] — 2026-07-23

### Añadido
- **Exportación DB a CSV** (`scripts/exportar_csv.py`): exporta cada tabla de la DB a un archivo CSV separado dentro de `db/exports/<timestamp>/`. Soporta `--table`, `--output`, `--dry-run`, `--list-tables`. Incluye `_resumen.txt` con conteo por tabla.
- **Opción en TUI**: `Mantenimiento DB > 7) Exportar DB a CSV` con submenú para elegir tablas (todas, media, metadata, o selección manual).
- **CLI**: `python flujos.py export-csv [--table media,config] [--output dir]`.
- **Migración v3** en `db/migrate.py`: schema canónico para `media_embeddings` (UNIQUE(media_id, modelo) en vez de media_id PK, ON DELETE CASCADE).
- **`generate_embeddings.py`** ahora llama a `verificar_schema()` para aplicar migraciones pendientes al conectar DB.
- **`db/exports/`** y **`db/backups/`** agregados a `.gitignore`.
- **CHANGELOG.md**: este archivo.

### Cambiado
- `exportar_csv.py`: `media_embeddings` ahora exporta TODAS las filas (sin la columna BLOB), en vez de solo 10 de muestra.

### Corregido
- `exportar_csv.py`: emoji `✅` reemplazado por `->` para compatibilidad con CP1252 en Windows.

---

## [Entrega 7] — 2026-07-22

### Añadido
- **Puente TouchDesigner** (`scripts/puente_td.py`): cerebro Python que consulta la DB y envía datos a TD vía OSC. Modos: `enviar` (loop colores→selección→imágenes), `colores`, `enviar_imgs`, `nube` (genera nube de tags desde keywords).
- **Scripts TD externalizados** en `td/`: `osc_callbacks.dat` (callbacks OSC In DAT) y `nube_generar.dat` (generación de nube de etiquetas en TD). Se vinculan desde DATs internos con `File` + `Sync to File = ON`.
- **`.opencode/` y `opencode.json`** ignorados por git (config local del agente).

### Documentación
- `AGENTS.md`: sección completa del puente TD (scripts, OSC, estructura de operadores TD esperados).

---

## [Entrega 6] — 2026-07-21

### Añadido
- **Extracción de metadatos de cámara y 360° con ExifTool en videos** (antes solo se corría en imágenes):
  - `process_file()` ahora corre ExifTool también en videos → captura `xml_devicemanufacturer`, `xml_devicemodelname`, `xmp_spherical`, `xmp_projectiontype`.
  - `detect_360()` extendida para cubrir XMP `ProjectionType` desde ExifTool.
  - `infer_author()` para videos usa marca/modelo detectados vía ExifTool.
- **Backfill** en `improve_db.py`: nuevo paso `video_metadata` que corre ExifTool sobre videos ya ingestados, guarda metadatos en `media_metadata`, actualiza `subtype = '360'`, y backfillea `author` si está vacío.

### Cambiado
- `infer_author()` para videos: ahora prioriza `xml_devicemanufacturer`/`xml_devicemodelname`.

### Corregido
- `ingest_gpx.py`: `migrar_db()` reemplazado por `verificar_schema()` centralizado de `db/migrate.py`.
- `scripts/ai_media/__init__.py`: imports faltantes agregados.
- `flujos.py`: `opcion_gradient()` ya no duplica `leer_db()`.
- `flujos.py`: submenú de mejora DB ahora recibe `db_path` desde `tui()`.
- `flujos.py`: batch IDs ahora usan `int(time.time() * 1000) % 1000000` en vez de `random.randint`.
- `improve_db.py`: `run_keypoints` modo `update` ya no borra TODOS los keypoints (solo los de medios con whisper_segments).

---

## [Entrega 5] — 2026-07-20

### Añadido
- **Ingesta de track GPS** (`scripts/ingest_gpx.py`): parsea GPX, extrae waypoints, backfill de altitud en `media.altitude` vía búsqueda binaria temporal.
- **Track real ingestado**: `tracks/Al_FaB_Tucuman.gpx` (28 waypoints, 3920 track points, altitud backfilleada en 226 medios).
- **Opción en TUI**: `Ingesta > 2) Ingerir track GPS (GPX)` con selección de modo de backfill y opciones (omitir waypoints/altitud, dry-run).
- **Schema versioning centralizado** (`db/migrate.py`): migraciones v1→v2 (tracks + waypoints). `verificar_schema()` es idempotente.
- **Tests de migraciones** (`db/test_migrate.py`): 8 tests (versión 0, idempotencia, orden, DB real).
- **Undo GPX**: `opcion_undo_ingest()` ahora lista batches (prefijo `b<id>`) y tracks (prefijo `t<id>`). Al deshacer un track se borra (CASCADE a waypoints) y revierte altitud de medios con `geolocation_source='track_gps'`.
- **Auto-backup**: `_preguntar_modo(db_path)` crea backup automático en `db/backups/` cuando se elige modo `replace`.

### Cambiado
- `flujos.py`: `_preguntar_modo(db_path)` ahora acepta `db_path` y llama a `_auto_backup()` en modo replace.
- `ingest_gpx.py`: `conectar()` llama automáticamente a `verificar_schema()`; `migrar_db()` eliminada (código muerto).
- `db/schema.sql`: tabla `media_embeddings` documentada.

---

## [Entrega 4] — 2026-07-18

### Añadido
- **Datos climáticos extendidos**: velocidad del viento (km/h), dirección del viento (grados + texto cardinal N/NE/E/etc), presión atmosférica (hPa). 226/226 registros actualizados.
- **Modo update en weather y día_semana**: ahora no limpia antes de reprocesar (consistente con el resto del pipeline).

### Corregido
- `gradiente.py`: `min(a, 1.0)` en Haversine para evitar NaN por error de punto flotante. Agregado `AND timestamp_utc IS NOT NULL` para evitar que NULLs se ordenen al inicio.
- `fetch_weather.py`: función `viento_direccion_a_texto()` para convertir grados a 16 rumbos.
- Modo update en `fetch_weather.py` y `dia_semana.py`: ya no borra datos existentes antes de reprocesar.

---

## [Entrega 3] — 2026-07-15

### Añadido
- **Filtro `--types`** en ingesta: permite seleccionar qué tipos de medio ingerir (`--types image,video`). No-sidecar XML correctamente excluido cuando se usan tipos específicos.
- **Flag `--allow-no-timestamp`**: ingerir archivos aunque no tengan timestamp.
- **Parseo de timestamp desde nombre de archivo**: formato `YYYY-MM-DD-HH-MM-SS_` (lectura de derecha a izquierda, completa con 00).
- **Menú interactivo mejorado**: opción Cancelar en `_preguntar_modo()`, navegación entre partes 1 y 2 en mejora DB, menú principal reordenado.

### Cambiado
- `ingest.py`: color extraction removido de la ingesta (delegado a `improve_db.py --step colors`).
- TUI: "Mas..." renombrado a "Siguiente >>" con navegación bidireccional entre partes.

---

## [Entrega 2] — 2026-07-10

### Añadido
- **Geocodificación inversa** (`scripts/geocode.py`): API Georef Argentina (batch), modo skip/update/replace.
- **Clima histórico** (`scripts/fetch_weather.py`): Open-Meteo ERA5-Land, agrupación por fecha+celda 0.5°, matching horario.
- **Día de la semana** (`scripts/dia_semana.py`): lunes–domingo desde timestamp_utc.
- **Gradientes de ruta** (`scripts/gradiente.py`): distancia Haversine, cambio elevación, pendiente %, acumulados.
- **Mapa interactivo** (`scripts/mapa_ruta.py`): Folium con puntos GPS, heatmap, colores por pendiente.
- **Color utils mejorado**: extracción por grilla, concentración cuadrática, centralidad + saturación relativa, distancia Redmean, anti-gray bias, variantes grey.
- **Modo skip/update/replace** en todas las operaciones DB.

### Corregido
- **GPS sign bug**: ExifTool sin `-n` devuelve `"South"`/`"West"` (texto completo), no `"S"`/`"W"`. `parse_gps_dms()` ahora usa `_es_sur_oeste()` aceptando ambos formatos. Verificado: 226 registros con GPS tienen signo negativo correcto.
- `color_utils.py`: `olivedrab`/`olive`/`darkolivegreen` movidos de "amarillo" a "verde". `fuchsia` agregado a "violeta".

---

## [Entrega 1] — 2026-07-05

### Añadido
- **Pipeline completo de ingesta** (`scripts/ingest.py`): escanea carpetas, extrae metadatos (ExifTool, ffprobe), calcula hashes (fingerprint rápido o SHA-256), inserta en DB con batch_id.
- **Post-procesamiento** (`scripts/improve_db.py`): 7 pasos (colors, keywords, descriptions, transcribe, keypoints, timestamps, gps) con skip/update/replace y resolución automática de dependencias.
- **Entry point unificado** (`flujos.py`): TUI interactivo + CLI routing con 15+ comandos.
- **Base de datos SQLite**: schema completo con ~55 columnas en `media`, `media_metadata` (key-value), `media_keypoints`, `config`, índices.
- **Columna `end_time`**: precalcula `timestamp_utc + duration_secs` para consultas por rango temporal.
- **Backup/Restore DB**: backup manual, restore desde backup, reset (backup + schema limpio).

---

## [Fundación] — 2026-06-28

### Añadido
- Estructura inicial del proyecto.
- Schema SQLite base (`db/schema.sql`).
- `AGENTS.md` como documentación exhaustiva para agentes de código.
- `VISION.md`: concepto de la instalación y la dérive.
- `README.md` y `ROADMAP.md`.
- Scripts de IA: `ollama_client.py`, `transcribe.py`, `image_analysis.py`, `proxy.py`, `tag_images.py`, `batch_selector.py`, `clustering.py`, `generate_embeddings.py`, `video_analysis.py`, `analyze_video.py`.
- Documentos de diseño: `docs/arquitectura_motor.md`, `docs/flujo_de_medios.md`, `docs/linea_de_tiempo.md`, `docs/geocodificacion_reversa.md`, `docs/limpieza_tandas_resultados.md`, `docs/semantica_color.md`, `docs/ideas_externas.md`.
