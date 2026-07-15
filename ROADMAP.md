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

| Item | Prioridad | Estado | Ejecuta vía |
|---|---|---|---|
| Etiquetado por keywords con IA | Alta | ✅ | `improve-db --steps keywords` |
| Transcripción de audios/videos con timestamp | Alta | ✅ | `improve-db --steps transcribe` |
| Descripción de imágenes con IA | Alta | ✅ | `improve-db --steps descriptions` |
| Lectura de color de imágenes (fix webcolors) | Alta | ✅ | `improve-db --steps colors` |
| **Inferencia de GPS** desde medios cercanos | **Alta** | ✅ | `improve-db --steps gps` |
| **Inferencia de timestamps faltantes** | **Alta** | ✅ | `improve-db --steps timestamps` |
| Tabla `media_keypoints` + poblar desde transcripciones | Alta | ✅ | `improve-db --steps keypoints` |
| Inferencia de autor desde medios cercanos | Baja | ❌ | — |
| Detección/corrección de offset de reloj en cámaras | Media | ❌ Nota: si una cámara tiene la hora mal configurada, todos sus medios tienen timestamp desplazado. Se podría detectar comparando timestamps EXIF vs GPS track o vs medios de otros dispositivos en el mismo momento. |
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
| `improve-db` — comando unificado de mejora (7 pasos, modos skip/update/replace) | Alta | ✅ `scripts/improve_db.py` + flujos.py |

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
- **2026-07-15 (2da ronda):** Tabla `media_keypoints` en schema.
  `scripts/improve_db.py` creado con 7 pasos (colors, keywords,
  descriptions, transcribe, keypoints, timestamps, gps) y 3 modos
  (skip/update/replace). Subcomando `improve-db` en flujos.py (CLI + TUI).
  Dependencias entre pasos resueltas automáticamente.
- **2026-07-15 (3ra ronda):** Fixes varios:
  - Fallback timestamp prioriza FileCreateDate de ExifTool antes de getmtime
  - relocate.py ahora maneja sidecar_xml como ruta relativa correctamente
  - improve_db.py: serialización numpy fixeada (language_probability)
  - check_db.py y check_gps.py refactorizados con argparse + main()
  - flujos.py: TUI acepta --db en ingesta; CLI acepta --db en check-db,
    check-gps, undo-ingest, backfill-end-time, reset-db
  - undo_ingest: query de current_ingest_batch movida fuera del loop
  - ROADMAP: anotado "detectar offset de reloj en cámaras" como media
