# Changelog

Todos los cambios significativos del proyecto Flujos.

Formato basado en [Keep a Changelog](https://keepachangelog.com/).
Las versiones corresponden a entregas funcionales, no a releases semánticas.

---

## [Entrega 14] — 2026-08-01

### Añadido
- **Pipeline IA EN→ES** (`improve_db.py`, `image_analysis.py`, `traducir_metadata.py`): los modelos de visión multilingües (minicpm-v4.6) responden mejor en inglés. El pipeline de keywords/descripciones es ahora **2 fases**:
  1. **Fase A (visión)**: minicpm genera EN → se guarda en `ia_keywords_en` / `ia_description_en`.
  2. **Fase B (traducción)**: qwen2.5:3b traduce a ES sobre la DB (sin re-procesar imágenes) → `ia_keywords` / `ia_description` (**ES definitivo, lo que consume la interfaz**).
  El EN queda persistido para re-traducir sin re-correr visión (`--mode update`). Al regenerar el EN SIEMPRE se invalida el ES viejo (incluido skip).
- **Paso `combinado`** en `improve_db.py`: keywords + descripción en UNA llamada de visión (JSON) + 1 de traducción (JSON). Recomendado para la pasada masiva (~10s visión + ~9s traducción por imagen).
- **`traducir_metadata.py`**: script independiente reutilizable para traducir EN→ES sobre la DB (glosario de cicloturismo, prompts anti-portugués, modo JSON combinado). CLI con `--paso`, `--mode`, `--dry-run`, `--limit`, `--modelo`.
- **`_reparar_json`** en `image_analysis.py`: reparación robusta de JSON truncado que devuelven los modelos (recorte de basura, cierre de brackets, array de keywords cerrado con `}` en vez de `]`).
- **Auto-inicio de Ollama** (`ollama_client.py`): `asegurar_ollama()`, `ollama_responde()`, `iniciar_ollama()`. Todos los scripts que requieren Ollama verifican primero si el servidor responde y, si no, lo arrancan con `ollama serve` en background (`CREATE_NO_WINDOW` en Windows, sin bloquear la terminal). Cubre `OllamaVision`, `OllamaEmbedding` (en constructor) y los scripts que usan ollama directo: `traducir_metadata.py`, `improve_db.py`, `refinar_keywords.py`, `image_analysis.py --list-models`, `analyze_video.py`, `tag_images.py`, `generate_embeddings.py`. `flujos.py _verificar_ollama()` usa la función central y avisa "✅ Ollama iniciado automáticamente".
- **Términos EN en SINONIMOS** (`refinar_keywords.py`): red de seguridad para keywords que queden en inglés tras la traducción (`tree`→árbol, `repair`→reparación, `bike`→bicicleta, etc.). Stopwords EN agregadas.

### Cambiado
- **`MODELO_VISION_DEFAULT` → `minicpm-v4.6:latest`** en `image_analysis.py`: ganador de la comparativa de modelos. Grilla fija ~340 tokens (la resolución NO infla el contexto), keywords conceptuales + descripciones largas, ~13-19s por imagen a 800px.
- **Prompts de visión en inglés y mínimos**: `PROMPT_KEYWORDS` = "Give me exactly 5 keywords for this image, comma-separated.", `PROMPT_DESCRIBIR` = "Give me a long description of this image.", `PROMPT_COMBINADO` = JSON mínimo. Validado: los prompts complejos en español degradaban la calidad de minicpm (keywords genéricas, descripciones vacías).
- **Género fotográfico pendiente**: `_validar_genero()` desactivado en el flujo de keywords (minicpm no fuerza la lista controlada). Las keywords son libres; `refinar_keywords.py` fuerza "otras" si no hay género.
- **`flujos.py` TUI Mejorar DB**: reestructurado a 2 hojas paginadas (IA y color / Inferencia y enriquecimiento) con navegación `n) Siguiente >>` / `p) << Anterior`.

### Corregido
- **Bug en fase B**: `_crear_cliente_texto()` ahora llama `asegurar_ollama()` y lanza `RuntimeError` si no hay servidor (antes fallaba con error oscuro del cliente).
- **`_reparar_json`** aplicado en `_parsear_combinado` (antes solo se intentaba `json.loads` directo).
- **Gradientes de ruta reubicados en el TUI**: se movió la opción "Calcular gradientes de ruta" de `Mantenimiento DB` (donde estaba como opción 2) a `Mejorar DB → Hoja 2` (nueva opción 8, junto a inferencia/enriquecimiento). Coherente con la filosofía de agrupación temática (gradientes son enriquecimiento, como geocode/clima/astronomía). `Mantenimiento DB` quedó renumerado (ahora 8 opciones, sin gradientes).
- **6 bugs de robustez en `image_analysis.py` / `tag_images.py` / `puente_td.py`** (revisión de código):
  - `_validar_genero` ya no pierde la primera keyword descriptiva: `keywords[0] = "otras"` (sobrescribía) → `keywords.insert(0, "otras")`.
  - `_parsear_keywords` ahora maneja JSON objeto `{"keywords": [...]}` (qwen2.5vl responde así a veces), no solo listas planas.
  - `_reparar_json` limpia trailing commas (`["playa", "mar",]` → `["playa", "mar"]`) antes de intentar parsear.
  - `_es_genero` y la 2da pasada de match reconocen flexión de género (`nocturno` ↔ `nocturna`, `urbana` ↔ `urbano`).
  - Nuevo helper `_descripcion_utilizable`: filtra JSON crudo, texto < 5 chars y restos del prompt regurgitado en los fallbacks de `analizar_imagen_completo`/`_batch` (antes el fallback guardaba la respuesta cruda como descripción).
  - `tag_images.py` escribe `ia_keywords` en **texto plano** (`, ".join`) en vez de `json.dumps`, unificando el formato con `improve_db.py`/`traducir_metadata.py`. `puente_td.py` gana `_partes_keywords()` que soporta ambos formatos (texto y JSON array) para no romper con datos históricos.
  - `tag_images.py` renombra `file_hash` → `fingerprint` en los sidecars `.tags.json` (el MD5 rápido no es el SHA-256 de la DB; el nuevo helper `_fingerprint_valido` soporta ambos nombres para compatibilidad con sidecars viejos).

---

## [Entrega 13] — 2026-08-01

### Cambiado
- **Proxy a 800px** (`scripts/ai_media/proxy.py`): `MAX_LADO_PX` pasó de 1600 a 800. Medido con `qwen2.5vl:3b`: ~4x menos tokens de visión (1085 vs 2500 por imagen), ~2.5x más rápido por imagen, y menos presión sobre el umbral de degradación acumulativa (swap). La calidad de tags/descripciones se mantiene para este modelo.
- **`num_ctx=4096` fijado en `ollama_client.py`** (`NUM_CTX_DEFAULT`): sin `num_ctx`, Ollama reserva el contexto máximo del modelo (128000) → 8.2 GB RAM, saturando la memoria y disparando el swapping en máquinas sin GPU. 4096 cubre los ~2718 tokens de una imagen 1600px + prompt, con margen para datos extra en el prompt (estilo de descripción, keywords obligatorias), usando ~2.9 GB.
- Documentación y docstrings actualizados (`AGENTS.md`, `README.md`, `__init__.py`, `image_analysis.py`, `proxy.py`) para reflejar el nuevo tamaño de proxy.

### Pendiente (próxima sesión)
- **Investigar el umbral de degradación acumulativa**: el problema parece ser la acumulación de píxeles analizados (imágenes chicas → más imágenes antes del problema; grandes → menos). Estrategia propuesta: procesar en tandas de ~20 imágenes y sacar el modelo de la memoria entre tandas (esperando que se vacíe el swap). No se descarta throttling térmico del CPU como causa raíz.
- **Probar reinicio completo de `ollama.exe`** (nunca se hizo; todas las pruebas fueron sobre la misma sesión del proceso) para ver si restaura la velocidad inicial de ~4-5s/imagen.

---

## [Entrega 12] — 2026-07-31

### Añadido
- **Refinamiento de keywords IA** (`scripts/ai_media/refinar_keywords.py`): 3 capas para limpiar y unificar `media_metadata.ia_keywords`:
  1. **Léxica**: normaliza (quita artículos `la/el/...`, singulariza plurales), filtra basura (`sa_\d+`, `dsc\d+`, restos del prompt).
  2. **Diccionario de sinónimos**: unifica variantes del dominio (`bici`→`bicicleta`, `auto`→`automóvil`, variantes de género `street`→`callejera`).
  3. **Semántica (opcional `--usar-embeddings`)**: agrupa sinónimos con `paraphrase-multilingual:latest` (coseno ≥ 0.87, configurable con `--umbral`). Se subió de 0.82 a 0.87 porque palabras truncadas generaban falsos positivos (`monta~obra` 0.844); los sinónimos reales están ≥ 0.88.
- **Opción en TUI**: `Mejorar DB > Parte 1 > 9) Refinar keywords` con submenú (léxico, +embeddings, dry-runs).
- **CLI**: `python scripts/ai_media/refinar_keywords.py [--usar-embeddings] [--umbral N] [--mode skip|update|replace] [--dry-run]`.

### Cambiado
- **Modelo de visión por defecto**: `MODELO_VISION_DEFAULT` pasó de `moondream:latest` a `qwen2.5vl:3b` (moondream regurgita el prompt en keywords). También en `ollama_client.py` (`OllamaVision`, timeout 120→180s).
- **Prompts de keywords simplificados**: `PROMPT_KEYWORDS`/`PROMPT_COMBINADO` piden "exactamente 5 keywords, género primero"; `_validar_genero()` busca el género en cualquier posición y lo promueve.
- **Navegación del menú Mejorar DB**: Parte 1 usa `n) Siguiente >>` y Parte 2 `p) << Anterior` (antes teclas 9/9); `0` sigue siendo Volver.

### Corregido
- **Modelo de sinónimos descartado**: `nextfire/paraphrase-multilingual-minilm` confundía no-sinónimos (`bici~perro` 0.771). Borrado de Ollama; se eligió `paraphrase-multilingual:latest` (`bici~perro` 0.146).

---

## [Entrega 11] — 2026-07-28

### Añadido
- **`--destino` / `-d`** en `import_telegram.py`: copia automáticamente los archivos multimedia a una carpeta canónica (`{destino}/telegram/`) durante la importación, en vez de dejarlos atados al export temporal de Telegram. Resuelve colisiones de nombre con sufijo `_1`, `_2`.
- **Recuperación de media pendiente** en re-import: al re-ejecutar con `--mode skip`, los mensajes existentes se saltan pero se ejecuta una etapa de recuperación que busca `telegram_media` con `media_id=NULL` (archivos no disponibles en corridas previas) e intenta ingerirlos. Se puede ejecutar N veces.
- **Integración TUI**: pregunta por `--destino` en Ingesta → 4. Importar chat de Telegram.
- **SIDECAR_EXTS** como constante compartida en `mover_media.py`.

### Corregido
- **Sidecars en mover_media.py**: `ejecutar_movimiento()` y `ejecutar_copia()` buscaban sidecars en el directorio de destino en vez del directorio de origen (no movían/copiaban los sidecars). Ambos corregidos.
- **Límite en `_resolver_colision`**: loop infinito potencial con `while True` reemplazado por `for n in range(1, MAX_INTENTOS+1)` con fallback timestamp.
- **`reparar_json`**: reemplazada heurística frágil (`endswith("]")`/`endswith("}")`) por conteo de brackets.
- **`import shutil`/`datetime` inline**: movidos al tope del archivo (antipatrón eliminado).
- **`detectar_message_type`**: condición siempre True simplificada a `return "text"`.

## [Entrega 10] — 2026-07-28

### Añadido
- **Importación de Telegram** (`scripts/import_telegram.py`): nuevo script que importa exports de Telegram a la base de datos. Lee `result.json`, repara JSON truncado automáticamente, registra chats en `telegram_chats`, mensajes en `telegram_messages`, y multimedia en `telegram_media`.
- **Migración v4** (`db/migrate.py`): tres nuevas tablas (`telegram_chats`, `telegram_messages`, `telegram_media`) + columna `telegram_message_id` en `media`.
- **Integración flujos.py**: TUI (Ingesta → 4. Importar chat de Telegram), CLI (`python flujos.py import-telegram` / `tg`).
- **Vinculación bidireccional**: `telegram_media.media_id` → `media.id` y `media.telegram_message_id` → `telegram_messages.id`. Los multimedia de Telegram se ingieren en `media` table opcionalmente (`--no-ingest` para solo metadata).
- **Manejo de service messages**: se marcan con `es_sistema=1` para filtrado posterior.

### Cambiado
- `db/schema.sql`: agregadas tablas `telegram_chats`, `telegram_messages`, `telegram_media` y columna `telegram_message_id` en `media`.
- `AGENTS.md`: documentación completa de las nuevas tablas, script, CLI y mapa de datos.
- `flujos.py`: AYUDA actualizada con `import-telegram` y `mover`.

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
