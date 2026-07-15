# Roadmap — Flujos

## Pipeline

```
Etapa 1: PREPARAR MEDIOS     →  Limpieza de tandas, redimensionar, etc.
Etapa 2: INGESTA              →  Ingesta en DB + metadatos
Etapa 3: MEJORA DE DB         →  Etiquetado, inferencia, transcripción, color
Etapa 4: POST-PROCESO (yapa)  →  Escribir metadatos de DB a los archivos
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
| Extracción de colores dominantes | Alta | ⚠️ Bug webcolors — colores en NULL |
| Deduplicación por contenido | Alta | ✅ |
| Ingesta incremental (skip por file_hash) | Alta | ✅ |
| `ingest_batch_id` + `duration_secs` como columnas | Alta | ✅ |
| Guardar raíz de ingesta en config | Alta | ✅ |
| Undo-ingest por batch_id | Alta | ✅ `flujos.py undo-ingest` |
| `end_time` para consultas por rango temporal | Alta | ✅ Agregado a schema, ingest, flujos.py |
| Keywords IPTC en JSON (hoy string Python) | Media | ❌ |
| Content hash de video optimizado | Baja | ❌ |

---

## Etapa 3: Mejora de DB

| Item | Prioridad | Estado | Script |
|---|---|---|---|
| Etiquetado por keywords con IA | Alta | ✅ | `scripts/ai_media/tag_images.py` |
| Transcripción de audios/videos con timestamp | Alta | ✅ | `scripts/ai_media/transcribe.py` |
| Descripción de imágenes con IA | Alta | ✅ | `scripts/ai_media/image_analysis.py` |
| **Inferencia de GPS** desde medios cercanos en el tiempo | **Alta** | ❌ | — |
| Lectura de color de imágenes (fix webcolors) | Alta | ❌ | `color_utils.py` (bug) |
| Inferencia de timestamps faltantes | **Alta** | ❌ | — |
| Inferencia de autor desde medios cercanos | Baja | ❌ | — |
| Merge de metadatos para contenido duplicado | Baja | ❌ | — |
| Soporte para tracks GPS (GPX) | Baja | ❌ | — |

---

## Etapa 4: Post-proceso (yapa)

| Item | Prioridad | Estado |
|---|---|---|
| Escribir metadatos de DB a archivos (EXIF/IPTC o XML sidecar) | Baja | ❌ |

---

## Gestión de DB

| Item | Prioridad | Estado |
|---|---|---|
| `flujos.py` entry point unificado + TUI | Alta | ✅ |
| `relocate.py` — cambiar raíz de medios | Alta | ✅ |
| `reset-db` — borrar datos y reiniciar | Media | ❌ |
| `backfill-end-time` — poblar end_time en registros existentes | Alta | ✅ flujos.py |

---

## Instalación (TouchDesigner)

| Item | Prioridad | Estado |
|---|---|---|
| Motor de deriva (lógica de navegación no determinista) | Alta | ❌ Concepto en VISION.md |
| Línea de tiempo como eje ordenador | Alta | ❌ Diseño en docs/linea_de_tiempo.md |
| Salida a 5 pantallas (1 interacción + 4 360°) | Alta | ❌ |
| Detección de pico de ruido como input | Media | ❌ |
| Caché de consultas frecuentes / recorridos predefinidos | Baja | ❌ |

---

## Historial

- **2026-07-13:** Pipeline completo documentado. Bug ExifTool fixeado.
  `flujos.py` creado. `relocate.py` creado. Tabla `config` agregada.
- **2026-07-13 (2da ronda):** `duration_secs` e `ingest_batch_id` en schema.
  `undo-ingest` implementado. README y ROADMAP actualizados.
- **2026-07-15:** `end_time` agregado a schema, ingest y flujos.py.
  `backfill-end-time` subcomando. Timestamps faltantes a prioridad alta.
  Documentación actualizada.
