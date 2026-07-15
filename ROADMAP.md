# Roadmap — Flujos

Pipeline completo: `Curar → Ingestar → Inferir → Consultar`

---

## 1. CURACIÓN (pre-ingesta)

| Item | Prioridad | Estado |
|---|---|---|
| Redimensionar fotos a tamaño manejable | Media | ❌ |
| Eliminar duplicados pre-ingesta (por hash de contenido) | Media | ❌ |
| Eliminar malas fotos (borrosas, subexpuestas) | Baja | ❌ Parcial (solo selección por calidad con IA) |
| Etiquetado con IA (descripciones + keywords IPTC) | Baja | ❌ |
| Curar videos (transcodificar, samplear) | Baja | ❌ |

**Scripts existentes relacionados:** `limpiar_tandas.py`, `mover_descartadas.py`

---

## 2. INGESTA

| Item | Prioridad | Estado |
|---|---|---|
| Escaneo + fingerprint rápido | Alta | ✅ |
| Extracción EXIF (GPS, timestamps, cámara, autor) | Alta | ✅ |
| Extracción de colores dominantes | Alta | ⚠️ Bug webcolors — colores en NULL |
| Deduplicación por contenido | Alta | ✅ |
| Guardar raíz de ingesta en config | Alta | ✅ |
| Ingesta incremental (skip por file_hash) | Alta | ✅ |
| Flag `--verbose`, `--dry-run`, `--full-hash`, `--compute-video-hash` | Media | ✅ |
| Keywords IPTC en JSON (hoy están como string Python) | Media | ❌ |
| **`ingest_batch_id`** para identificar y deshacer ingestas | Alta | ✅ |
| Content hash de video optimizado | Baja | ❌ |
| `filename_normalized` (slug limpio) | Baja | ❌ |

---

## 3. INFERENCIA (post-ingesta)

| Item | Prioridad | Estado |
|---|---|---|
| **Inferir GPS** desde medios cercanos en el tiempo | Alta | ❌ |
| Inferir timestamps faltantes | Media | ❌ |
| Inferir autor desde medios cercanos | Baja | ❌ |
| Merge de metadatos para contenido duplicado | Baja | ❌ |
| Soporte para tracks GPS (GPX) | Baja | ❌ |

---

## 4. GESTIÓN DE DB

| Item | Prioridad | Estado |
|---|---|---|
| `relocate.py` — cambiar raíz de medios | Alta | ✅ |
| **`reset-db`** — borrar datos y reiniciar | Media | ❌ |
| **`undo-ingest`** — deshacer una ingesta por batch_id | Alta | ✅ |
| `duration_secs` como columna en media | Alta | ✅ |
| `ingest_batch_id` como columna en media | Alta | ✅ |

---

## 5. CONSULTAS Y HERRAMIENTAS

| Item | Prioridad | Estado |
|---|---|---|
| `query.py` — consultas por columna, valores únicos, búsqueda | Alta | ✅ |
| `flujos.py` — entry point unificado con subcomandos y TUI | Alta | ✅ |
| Inferencia de ubicaciones desde la DB (GIS) | Media | ❌ |

---

## 6. INSTALACIÓN (TouchDesigner)

| Item | Prioridad | Estado |
|---|---|---|
| Motor de deriva (lógica de navegación no determinista) | Alta | ❌ Concepto definido en VISION.md |
| Línea de tiempo como eje ordenador | Alta | ❌ Diseño en docs/linea_de_tiempo.md |
| Salida a 5 pantallas (1 interacción + 4 360°) | Alta | ❌ |
| Detección de pico de ruido como input | Media | ❌ |
| Caché de consultas frecuentes / recorridos predefinidos | Baja | ❌ Nota en docs/flujo_de_medios.md |

---

## Historial

- **2026-07-13:** Pipeline completo documentado en docs/flujo_de_medios.md.
  Bug de ExifTool fixeado. Entry point unificado creado (flujos.py).
  relocate.py creado. Tabla config agregada al schema.

- **2026-07-13 (2da ronda):** duration_secs e ingest_batch_id como columnas
  en media. undo-ingest implementado en flujos.py. docs/linea_de_tiempo.md
  actualizado con concepto de segmentos (videos/audios ocupan intervalo,
  no punto) y velocidad variable.
