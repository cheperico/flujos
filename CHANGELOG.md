# Changelog

Todos los cambios significativos del proyecto Flujos.

Formato basado en [Keep a Changelog](https://keepachangelog.com/).
Las versiones corresponden a entregas funcionales, no a releases semánticas.

---

## [Entrega 19] — 2026-08-04

### Cambiado
- **Traductor EN→ES cambiado a `translategemma`** (`traducir_metadata.py`, `improve_db.py` `_traducir_metadata`): auditoría cruzada de keywords EN (crudo de visión) vs ES reveló que la basura (`户外`, `ripio/grava`, checklist de `banquina/manubrio/...`) la generaba el **traductor qwen2.5:3b** (colapso en checklist/chino), NO la visión (minicpm da EN limpio). Batería de 11 casos reales de la DB: qwen2.5:3b **score −2.3** (3 chino, 5 checklist, 5 slash) vs **translategemma +1.6** (0/0/0, fiel, 10/11 conteo exacto). Modelos grandes sin ventaja y más pesados (requisito: hardware limitado) → se eligió translategemma (3.3GB, 4.3B, especializado). Nuevo `MODELO_TRADUCCION_DEFAULT = "translategemma"`.
- **Re-traducción masiva aplicada**: `traducir_metadata.py --paso keywords --mode update` → **702 ok / 0 errores**. Verificado en DB: chino 15+ → 0, slash 55 → 1, checklist 90 → 1.
- **GLOSARIO eliminado** de `traducir_metadata.py`: test A/B demostró que era **decorativo** (0 términos usados por translategemma en 11 casos con/sin) y su regla "usá EXACTAMENTE" empujaba al modelo viejo al checklist/slash. Se quitaron la constante `GLOSARIO` y la regla 5 de `PROMPT_TRADUCIR_AMBOS`/`PROMPT_TRADUCIR_KEYWORDS`.
- **Capa semántica eliminada de `refinar_keywords.py`** (ahora 2 capas: léxica + diccionario): `--usar-embeddings` con `paraphrase-multilingual:latest` introducía **falsos sinónimos** que degradaban el dominio (`ciclismo→deporte`, `nublado→soleado`, `parche→parque`, `cesta→ruta`). Se quitó por completo (no queda ni como opción): `refinar_con_embeddings()`, `similitud_coseno()`, `MODELO_EMBEDDINGS`, args `--usar-embeddings`/`--umbral`, e import `math`.
- **`ciclismo`/`ciclista(s)` dejaron de colapsar** a `deporte`/`personas` en `SINONIMOS` de `refinar_keywords.py`: `ciclismo` pasó a término canónico propio (variantes: ciclista, ciclistas, cycling, cyclist, cyclists, pedaleando).
- **TUI `opcion_refinar_keywords`** (`flujos.py`): se eliminaron las opciones de embeddings (antes 2 "capa semántica" y 4 "dry-run con embeddings"); ahora opción 1 "Refinar todos (update)" y 2 "Previsualizar (dry-run)".

---

### Cambiado
- **Transcripción con VAD + filtro de alucinaciones** (`transcribe.py`, `improve_db.py`): auditoría de las 217 transcripciones detectó **alucinaciones masivas de Whisper** — solo 144/217 (66%) en español; 73 en idiomas aleatorios (noruego-nynorsk 28, inglés 36, italiano 4, javanés 2, coreano 1, portugués 1, turco 1), 58 de los 73 con confianza de idioma < 0.5. Causa raíz: faster-whisper corría **sin VAD** sobre clips de **ruido ambiental (cámaras GoPro sin habla)**, con `language=None` y `condition_on_previous_text=True` → inventaba basura repetitiva ("I'm going to finish it" ×10, "Bu ne? Bu ne?"), incluso con `language_probability` alta (0.79 → "4-5-6-7-8"). Factores desencadenados: idioma aleatorio en silencio, sin detección de voz, lazo de repetición auto-alimentado y sin filtro de texto.
- **Removido el paso `transcribe_zg`** de `improve_db.py`: era redundante — con el `run_transcribe` nuevo (VAD + autoidioma + filtro de confianza + no guarda basura en `sin_voz`) ya no queda "zona gris" que arreglar: mismo motor y parámetros, en una regeneración completa (`--mode replace`) `transcribe` cubre todo. Se eliminaron `_query_zona_gris`, `check_transcribe_zg`, `run_transcribe_zg`, la entrada del REGISTRY, de `DEP_ORDER` y del docstring. La doc (AGENTS.md, README.md, mapa de datos, catálogo, nota histórica) quedó sincronizada.
- **Fix import `clasificar_estado`** (`improve_db.py` `run_transcribe`): el paso usaba `clasificar_estado()` pero el import solo traía `transcribir_audio` → NameError al guardar (`name 'clasificar_estado' is not defined`), por lo que las transcripciones se procesaban (VAD OK) pero **no se escribían en la DB**. Se agregó `clasificar_estado` a ambos imports (normal + fallback con `sys.path`).
- **`skip` auto-recuperable en `run_transcribe`**: la query de modo `skip` ahora considera pendiente **solo** a los archivos **sin `whisper_estado`** (ni tocados, ni corte a mitad de batch / checkpoint), retomando cualquier corrida interrumpida (Ctrl+C/cuelgue) en la siguiente pasada con `--mode skip`. El marcador de "terminado" es `whisper_estado` y **no** `whisper_segments`, porque con el ajuste de abajo un archivo `sin_voz` queda con estado pero sin segmentos (usar `whisper_segments` re-transcribiría los `sin_voz` en cada corrida).

### Añadido
- **`transcribe.py` gana soporte VAD + confianza**: parámetros `vad_filter`/`vad_parameters`, `condition_on_previous_text`, umbrales (`no_speech_threshold`, `compression_ratio_threshold`, `log_prob_threshold`), y `incluir_metricas` → cada segmento lleva `promedio_logprob`, `no_hay_habla_prob`, `ratio_compresion`. Nuevos helpers `filtrar_segmentos_confiables()` (logprob ≥ -0.8, no_habla < 0.6, compresión < 2.4, duración ≥ 1.5 s) y `clasificar_estado()` (`ok` | `sin_voz`). Retrocompatible con segmentos sin métricas.
- **`run_transcribe` en `improve_db.py`** mejorado: ahora usa modelo `small` + VAD + autodetección + filtro de confianza, escribe `whisper_estado`, y usa checkpoint incremental (`Checkpoint` cada 20) en vez de un único commit final.
- **`run_transcribe` no guarda basura en `sin_voz`**: ahora `run_transcribe` solo persiste `whisper_segments`/`whisper_info` cuando clasifica `ok`; en ruido/silencio (`sin_voz`) deja únicamente la marca `whisper_estado=sin_voz`.
- **Docs**: `AGENTS.md` sincronizado (mapa de datos, catálogo, nota histórica).

---

## [Entrega 20] — 2026-08-05

### Cambiado
- **Eliminado el género fotográfico de las keywords** (era el comodín "otras"): la auditoría mostró que el 77% de los medios (544/702) tenía "otras" como primera keyword porque la visión ya no pide género (prompts con keywords libres desde Ago 2026) pero `refinar_keywords.py` seguía forzándolo en post-proceso. Se eliminó la lógica completa de género:
  - `image_analysis.py`: eliminados `GENEROS_FOTOGRAFICOS`, `_GENEROS_STR` y `_validar_genero()` (y su llamada en el fallback de `analizar_imagen_completo`). Verificado: `PROMPT_KEYWORDS`/`PROMPT_COMBINADO` ya no pedían género; `PROMPT_CLASIFICAR` conserva categorías (utilidad CLI `clasificar_imagen`, aparte del pipeline).
  - `refinar_keywords.py`: eliminados `GENEROS_FOTOGRAFICOS`, `VARIANTES_GENERO`, `es_genero()` y `_tiene_mezcla_generos()`; `refinar_lista_keywords()` ya no busca género ni inserta "otras" al inicio — ahora solo normaliza, singulariza, aplica sinónimos, deduplica y recorta a máx 7.
- **Limpieza de la DB**: se confirmó que "otras" fue insertada COMO EXTRA (no reemplazó ningún keyword válido: 0 casos con ES vacío teniendo EN). Se borró el token "otras" de los 544 registros `ia_keywords` **sin re-traducir** (no se perdió información). Backup previo en `db/backups/`.
- **Docs**: README.md (image_analysis "17 géneros" → "keywords libres"; `ia_keywords` sin género), ROADMAP.md ("17 géneros" → "libres"; refinar sin embeddings), notas de código en image_analysis/refinar/traducir.
- **`refinar_keywords.py`** gana `--clave` para procesar `ia_keywords_transcripcion` (keywords de audios/videos salidas de `keywords_transcripciones.py`), y en `SINONIMOS` se dieron grupos propios a `camino` y `gente` (dejaron de colapsar a `ruta`/`personas`) y a `autopista` (unifica `autovía`/`highway`/`freeway`/`motorway`, ya no colapsa a `ruta` — en el dominio es "ruta más ancha, más tráfico", significado distinto). Pasada real sobre `ia_keywords_transcripcion` (140 registros, 109 actualizados) + restauración del único caso que la pasada previa había unificado (`autopista→ruta` en media 780). El diccionario quedó idempotente: re-correr no re-convierte `autopista`.
- **Nube de tags web3 corregida** (`web3/api/tags.php`): ya NO tokeniza las descripciones (`ia_description`) en bruto — eso inyectaba ruido de redacción de la IA (`sugiere` ×1191, `indica` ×675, `entorno`, `general`) y recortaba frases compuestas ("entorno rural" → "entorno") al contar palabras sueltas. Ahora cuenta las **keywords completas** (`ia_keywords`), respetando "entorno rural"/"general mendoza" y filtrando con `KEYWORDS_A_IGNORAR` (mismo criterio que `puente_td.py`/`elecciones.py`). Requiere columna `keywords` en `visualizacion.db` → agregada a `web3/scripts/exportar_visualizacion.py` (lee `ia_keywords`). Snapshot re-exportado (1522 medios, 702 con keywords); verificado con PHP: nube = `bicicleta` (290), `ciclismo` (259), `ruta` (128), sin el ruido.

---

## [Entrega 17] — 2026-08-03

### Cambiado
- **Limpieza de tandas — selección con moondream** (`batch_selector.py`): se creó `MODELO_SELECCION_DEFAULT="moondream:latest"`, usado en `seleccionar_mejor_imagen()`, `seleccionar_mejores_n()` y el CLI `--modelo`. `limpiar_tandas.py` lo importa. La selección es solo curación (no escribe en la DB), así que no necesita el modelo pesado ni el español del FLUJO IA (minicpm) — es ~15x más rápida. El FLUJO IA (image_analysis, improve_db, tag_images) **no se tocó**. Los prompts de selección (`PROMPT_EVALUAR_CALIDAD`, `_seleccionar_por_tema`) se pasaron a **inglés escuetos** (moondream responde mal en español).
- **Limpieza de proxies huérfanos** (`limpiar_tandas.py`): `limpiar_todos_los_proxies` era un import muerto. Ahora `_mover_a_excluir()` llama `limpiar_proxies(ruta)` por cada descartada (evita proxies huérfanos en `.proxies/`), y hay un flag `--limpiar-proxies` para borrar toda la carpeta `.proxies/` de la raíz al final.
- **Timezone — día y hora local (Argentina UTC-3)**:
  - `dia_semana.py`: `parsear_timestamp()` normaliza `Z` y convierte a Argentina antes de `weekday()` (antes el día se calculaba en UTC: 23:30 local lunes → "martes").
  - `loop_db.py` `_extraer_hora()`: convierte a Argentina antes de sacar la hora (el loop quedaba 3h tarde). Guardián `if dt.tzinfo is not None`.
  - `improve_db.py`: fuerza aware UTC (`_as_aware_utc()`) en la interpolación de `run_timestamps`, y normaliza `Z` en `run_keypoints`/`run_gps`.
  - `fetch_weather.py`: normaliza `Z` en las 3 apariciones de `fromisoformat` (181, 255, 403).
- **`--mostrar` → `--no-mostrar`** en `improve_db.py`: la vista en vivo de keywords/descripciones (texto EN generado) se muestra por default; `--no-mostrar` la silencia. Aplica a pasos keywords, descriptions y combinado.
- **Docs**: `AGENTS.md` sincronizado (modelo de selección, limpieza de proxies, timezone, flag invertido). `README.md` actualizado con subcomandos `import-telegram`/`mover`, scripts nuevos y documentos de diseño faltantes.

---

## [Entrega 16] — 2026-08-01

### Añadido
- **Motor de loop** (el "cerebro" de la instalación, agnóstico del renderizador):
  - `scripts/ai_media/loop_engine.py` — **núcleo puro** (sin DB ni render): matemática de arcos horarios (N horas → N−1 segmentos de duración igual), cruce de medianoche (`24 + (H[i+1]−H[i])`), posición de un medio en el loop (`t_loop = t_start + frac·duracion_seg`), descarte de medios fuera del arco, y armado de la spec JSON. Funciones: `calcular_segmentos()`, `hora_en_fraccion()`, `posicionar_hora()/posicionar_medio()`, `armar_spec()`.
  - `scripts/ai_media/loop_db.py` — integración con la DB (solo lectura): filtra `media`+`media_metadata` por municipios/colores/tags/días/clima (AND), ordena por recorrido real (`cumul_distance_m`) o elección, normaliza `timestamp_utc` mixto (`Z`/`+00:00`), genera y **consolida los chiches** por (texto, hora en punto) para no spamear el render, y vuelca la spec a JSON. CLI: `python scripts/ai_media/loop_db.py --horas 7 16 13 18 --salida spec.json`.
  - `scripts/ai_media/test_motor_loop.py` — 47 tests del núcleo (segmentos, cruce nocturno, fracción, posición, descarte, todas las horas). Fix de consola Windows: reconfigura `stdout` a UTF-8 (la flecha `→` rompe cp1252).
- **Documento** `docs/motor_loop.md` — especificación completa del motor (entrada, matemática de segmentos, posicionamiento, chiches, salida JSON, arquitectura y pendientes). Actualiza la referencia de `diseno_instalacion.md` (antes "próximo paso: motor de loop").

### Validado
- Corrida real contra `db/flujos.db` con `--horas 7 16 13 18`: 1328 medios posicionados, 63 chiches **consolidados** (antes 1574), 3 segmentos (7→16, 16→13 nocturno, 13→18).

### Cambiado
- Limpieza de imports duplicados y comentario obsoleto en `audio_tagging.py`; robustez en `batch_selector.py` (nitidez redimensiona a 800px) y `clustering.py` (parseo de keywords + guard de coseno 0).
- `ROADMAP.md`/`VISION.md`/`AGENTS.md`/`README.md` actualizados para reflejar el estado real (pipeline IA EN→ES, audio tagging, motor de loop, GPX, Telegram).

---

## [Entrega 15] — 2026-08-01

### Añadido
- **Keywords desde transcripciones** (`scripts/ai_media/keywords_transcripciones.py`): extrae keywords del **SENTIDO** de las transcripciones (`whisper_segments`) con Ollama texto (`qwen2.5:3b`). Prompt semántico: captura conceptos implícitos (no solo palabras literales), filtra muletillas y ruido, parseo de JSON/texto/numerado. Guarda `ia_keywords_transcripcion` (ES, coma-separado). Umbrales: `MIN_TEXTO_LEN=40`, `MAX_KEYWORDS=8`. Probado: media 227 (entrevista agua hidráulica) → `agua, laguna, bomba, inundación, salinidad, canal, riego, proyección`.
- **Audio tagging** (`scripts/ai_media/audio_tagging.py`): reconocimiento de sonidos ambientales en audio/video con **sherpa-onnx CED-mini** (527 clases AudioSet, int8, 100% local en CPU, sin Ollama). ffmpeg extrae WAV 16 kHz mono en memoria (sin archivos temporales), se divide en ventanas de 10 s, se agregan probs por etiqueta y se queda con top-k. Guarda `ia_keywords_sonido` (ES con glosario EN→ES) e `ia_sonido_raw` (JSON `[{name, prob}]`). Modelo en `models/audio/sherpa-onnx-ced-mini-audio-tagging-2024-04-19/`.
- **Descarga automática del modelo** (`audio_tagging.py`): si no existe `model.int8.onnx` en la ruta por defecto, el script lo **descarga solo** desde GitHub Releases (asset oficial de sherpa-onnx, ~45 MB) y lo extrae a la carpeta canónica, tolerando la estructura anidada del tar. Se puede deshabilitar con `--no-descargar` (útil en entornos sin internet). Verificado end-to-end: descarga → extracción → carga del modelo → dry-run OK.
- **TUI Mejorar DB → Hoja 3 "Audio/video IA"**: nueva hoja paginada con Audio tagging. La Hoja 2 ganó la opción 9 (Keywords desde transcripciones) y `n) Siguiente >>` para ir a la Hoja 3. Coherente con la regla de paginación (las opciones de IA/audio van a la hoja siguiente cuando la temática está llena).

### Cambiado
- **Requisitos nuevos** (`AGENTS.md`): `onnxruntime 1.27.0` + `sherpa-onnx 1.13.4` (`pip install onnxruntime sherpa-onnx`), con instrucciones de descarga/extracción del modelo CED-mini.

### Nota técnica (API sherpa-onnx 1.13)
- **NO** usar `compute(tuple, rate)` (API vieja, da `TypeError`): en 1.13 el flujo es `stream = tagging.create_stream()` → `stream.accept_waveform(rate, samples_float)` → `tagging.compute(stream)` → eventos con `.name`, `.prob`, `.index`.
- **NO** existe `stream.input_finished()` en `OfflineStream` (solo `accept_waveform`, `result`, `get_option`, etc.).
- Resultado: 270 audios/videos procesados en ~78 s (0.29 s/media); 24 sin pista de audio (ffmpeg falla → se loguea como "sin audio").

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
