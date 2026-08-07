# Roadmap — Flujos

## Pipeline

```
Etapa 1: PREPARAR MEDIOS     →  Limpieza de tandas, redimensionar, etc.
Etapa 2: INGESTA              →  Ingesta en DB + metadatos base + colores
Etapa 3: MEJORA DB            →  Etiquetado IA, transcripción, colores, timestamps, GPS
Etapa 4: ENRIQUECIMIENTO      →  Geocodificación, clima, día, gradientes
Etapa 5: INSTALACIÓN          →  TouchDesigner + motor de deriva
```

---

## Etapa 1: Preparar medios

| Item | Prioridad | Estado |
|---|---|---|
| Limpieza de tandas (seleccionar mejores imágenes por tanda) | Alta | ✅ `limpiar_tandas.py`, `mover_descartadas.py` |
| Redimensionar fotos | Media | ❌ Se hace con IrfanView |

---

## Etapa 2: Ingesta

| Item | Prioridad | Estado |
|---|---|---|
| Escaneo + fingerprint rápido | Alta | ✅ |
| Extracción EXIF (GPS, timestamps, cámara, autor) | Alta | ✅ |
| Extracción de colores dominantes | Alta | ✅ `color_utils.py` (Redmean, anti-gray bias, centrality) |
| Deduplicación por contenido | Alta | ✅ |
| Ingesta incremental (skip por file_hash) | Alta | ✅ |
| `ingest_batch_id` + `duration_secs` como columnas | Alta | ✅ |
| Guardar raíz de ingesta en config | Alta | ✅ |
| Undo-ingest por batch_id | Alta | ✅ |
| `end_time` para consultas por rango temporal | Alta | ✅ |
| GPS sign bug (lat/lon positivo en Argentina) | **Corregido** | ✅ Fixeado en ingest.py (`_es_sur_oeste()`, `_parse_gps_position()`) y verificado en los registros con GPS (signo negativo correcto) |
| Keywords IPTC en JSON (hoy string Python) | Media | ❌ |
| Content hash de video optimizado | Baja | ❌ |

---

## Etapa 3: Mejora DB

| Item | Prioridad | Estado | Ejecuta vía |
|---|---|---|---|
| Colores dominantes (reprocesar) | Alta | ✅ | `improve-db --steps colors --mode` |
| Etiquetado por keywords con IA (keywords libres) | Alta | ✅ | `improve-db --steps keywords --mode` |
| Descripción de imágenes con IA | Alta | ✅ | `improve-db --steps descriptions --mode` |
| Transcripción de audios/videos con timestamp | Alta | ✅ | `improve-db --steps transcribe --mode` |
| Keypoints (segmentos de transcripción) | Alta | ✅ | `improve-db --steps keypoints --mode` |
| **Inferencia de GPS** desde medios cercanos | Alta | ✅ | `improve-db --steps gps --mode` |
| **Inferencia de timestamps faltantes** | Alta | ✅ | `improve-db --steps timestamps --mode` |
| Pipeline unificado (10 pasos) con skip/update/replace | Alta | ✅ | `improve_db.py` + flujos.py TUI |
| Etiquetado combinado (keywords + descripción en 1 llamada de visión) | Media | ✅ | `improve-db --steps combinado --mode` |
| Pipeline IA EN → ES (visión genera EN, traducción ES con qwen2.5:3b) | Alta | ✅ | `improve_db.py` + `traducir_metadata.py` |
| Refinar/unificar keywords (sinónimos) | Media | ✅ | `refinar_keywords.py` |
| Audio tagging (sonidos ambientales, sherpa-onnx local) | Media | ✅ | `audio_tagging.py` |
| Verificación de Ollama antes de pasos IA | Alta | ✅ | `_verificar_ollama()` en flujos.py |
| Threading en llamadas Ollama (2 workers) | Media | ✅ | `ThreadPoolExecutor` en improve_db.py |
| Inferencia de autor desde medios cercanos | Baja | ❌ | — |
| Detección/corrección de offset de reloj en cámaras | Media | ❌ | — |
| Merge de metadatos para contenido duplicado | Baja | ❌ | — |

---

## Etapa 4: Enriquecimiento

| Item | Prioridad | Estado | Ejecuta vía |
|---|---|---|---|
| **Geocodificación inversa** (provincia, municipio, localidad) | Alta | ✅ | `geocode.py --mode` (Georef API Argentina) |
| **Clima histórico** (temperatura, humedad, lluvia, nubes) | Alta | ✅ | `fetch_weather.py --mode` (Open-Meteo ERA5-Land) |
| **Día de la semana** en español | Alta | ✅ | `dia_semana.py --mode` |
| **Gradientes de ruta** (distancia Haversine, elevación, pendiente) | Alta | ✅ | `gradiente.py --mode` (Python puro, sin numpy) |
| **Posición del sol / twilight** (NOAA) | Alta | ✅ | `astronomia.py --mode` (sin dependencias externas) |
| Keywords del sentido de transcripciones | Media | ✅ | `keywords_transcripciones.py` |
| Embeddings vectoriales (búsqueda semántica) | Media | ⏳ | `generate_embeddings.py` + `clustering.py` |

---

## Etapa 5: Instalación (TouchDesigner)

| Item | Prioridad | Estado |
|---|---|---|
| Motor de deriva (lógica de navegación no determinista) | Alta | ❌ Concepto en VISION.md |
| Línea de tiempo como eje ordenador | Alta | ❌ Diseño en docs/linea_de_tiempo.md |
| Salida a 5 pantallas (1 interacción + 4 360°) | Alta | ❌ |
| Detección de pico de ruido como input | Media | ❌ |
| Caché de consultas frecuentes / recorridos predefinidos | Baja | ❌ |

---

## Gestión de DB

| Item | Prioridad | Estado |
|---|---|---|
| `flujos.py` entry point unificado + TUI | Alta | ✅ |
| `relocate.py` — cambiar raíz de medios | Alta | ✅ |
| `reset-db` — backup + borrar datos y reiniciar | Media | ✅ |
| `backup-db` / `restore-db` — copias de seguridad | Media | ✅ |
| `backfill-end-time` — poblar end_time en registros existentes | Alta | ✅ |
| `improve-db` — comando unificado de mejora (9 pasos, 3 modos) | Alta | ✅ |
| Todos los scripts con `--mode skip/update/replace` unificado | Alta | ✅ |
| `_preguntar_modo()` en TUI para todas las operaciones DB | Alta | ✅ |
| `_verificar_ollama()` antes de pasos IA en TUI | Alta | ✅ |
| **Mapa de datos centralizado** (qué escribe cada script y dónde) | Media | ✅ Documentado en AGENTS.md |
| Soporte para tracks GPS (GPX) | Baja | ✅ `ingest_gpx.py` + tablas `tracks`/`waypoints` |
| Desktop Telegram (chats, mensajes, multimedia) | Media | ✅ `import_telegram.py` |

---

## Documentación

| Item | Prioridad | Estado |
|---|---|---|
| `AGENTS.md` documentación exhaustiva (schema, mapa de datos, scripts, TUI, convenciones, pitfalls) | Alta | ✅ |
| `README.md` actualizado con todos los scripts, comandos, TUI, schema, enriquecimiento | Alta | ✅ |
| `ROADMAP.md` actualizado con todas las etapas | Alta | ✅ |
| `docs/geocodificacion_reversa.md` — estrategias de geocodificación | Media | ✅ |
| `docs/limpieza_tandas_resultados.md` — comparativa de estrategias | Media | ✅ |
| `docs/arquitectura_motor.md` — TD puro vs híbrido | Baja | ✅ |
| `docs/flujo_de_medios.md` — flujo en el motor | Baja | ✅ |
| `docs/linea_de_tiempo.md` — diseño de timeline | Baja | ✅ |

---

## Mejoras de robustez

| Item | Prioridad | Estado |
|------|-----------|--------|
| Timeout en ThreadPoolExecutor (keywords/descriptions) para evitar colgado por suspensión | Media | ❌ Pendiente |
| Verificar timeouts en ollama_client.py (requests.post) | Media | ❌ Pendiente |

---

## Historial

- **2026-07-13:** Pipeline completo documentado. Bug ExifTool fixeado.
  `flujos.py` creado. `relocate.py` creado. Tabla `config` agregada.
- **2026-07-13 (2da ronda):** `duration_secs` e `ingest_batch_id` en schema.
  `undo-ingest` implementado. README y ROADMAP actualizados.
- **2026-07-15:** `end_time` agregado a schema, ingest y flujos.py.
  `backfill-end-time` subcomando. Timestamps faltantes a prioridad alta.
- **2026-07-15 (2da ronda):** Tabla `media_keypoints` en schema.
  `scripts/improve_db.py` creado con 7 pasos y 3 modos.
- **2026-07-15 (3ra ronda):** Fixes: timestamp fallback, relocate sidecars,
  numpy serialization, check_db/check_gps refactor, --db en varios comandos.
- **2026-07-16:** **Mejoras mayores:**
  - `color_utils.py`: Redmean distance, anti-gray bias (1.5×), centrality boost,
    relative saturation, grey variants, olive→verde, fuchsia→violeta
  - `geocode.py`, `gradiente.py`, `fetch_weather.py`, `dia_semana.py`:
    todos con `--mode skip/update/replace` unificado
  - TUI: `_preguntar_modo()` en todas las operaciones DB
  - TUI: `_verificar_ollama()` verifica Ollama antes de pasos IA
  - TUI: nuevo submenú "Mantenimiento DB" (relocate, gradient, backfill, backup, restore, reset)
  - TUI: backup-db / restore-db implementados
  - TUI: resumen DB simplificado (6 líneas)
  - GPS sign bug fixeado en `ingest.py` (South/West text completo)
  - `AGENTS.md`: reescritura completa como documentación exhaustiva
  - `README.md`: actualización completa con todos los scripts, comandos, TUI, schema, enriquecimiento
  - `ROADMAP.md`: actualización con todas las etapas y nuevo historial
  - **Mapa de datos centralizado** agregado a AGENTS.md
