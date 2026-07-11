# Pendientes y mejoras

## 0. Script de consulta (query.py) ✅ Implementado

`scripts/query.py` — explorador de la base de datos desde línea de comandos.

```bash
python scripts\query.py --columns                          # Listar columnas/keys
python scripts\query.py --distinct type --count            # Valores únicos con conteo
python scripts\query.py --distinct author --count          # Autores con conteo
python scripts\query.py --distinct author --count --where "type='image'"
python scripts\query.py --key iptc_keywords --count        # Keywords en metadata
python scripts\query.py --search "tucuman"                 # Búsqueda de texto
```

Queda pendiente implementar para cuando haya datos en la DB.

---

## 1. Keywords IPTC en formato JSON

**Problema:** `IPTC:Keywords` se guarda como `"['viaje', 'bici']"` (representación
Python de lista). No es un formato estándar.

**Solución propuesta:** Normalizar a JSON array al insertar:
```python
import json
meta["iptc_keywords"] = json.dumps(keywords_list)
```
Quedaría: `'["viaje", "bici"]'` — parseable con `json.loads()`.

**Archivo:** `scripts/ingest.py`, función `flatten_exiftool` o en el
procesamiento de imágenes.

---

## 2. Geolocalización por inferencia temporal

**Script:** `scripts/geolocate.py`

**Qué haría:**
1. Tomar medios con GPS conocido (`geolocation_source = 'metadata'`)
2. Ordenarlos por `timestamp_utc`
3. Para cada medio sin GPS, buscar los dos más cercanos en el tiempo que sí tengan GPS
4. Interpolar o asignar la coordenada más cercana
5. Guardar con `geolocation_source = 'inferido_tiempo'`

**Pendiente de:** definición del algoritmo (interpolación lineal, nearest neighbor,
ventana de tiempo máxima).

---

## 3. Merge de metadatos para contenido duplicado

**Script:** `scripts/merge_metadata.py`

**Qué haría:**
Cuando `content_hash` se repite con distinto `file_hash` (misma imagen con
diferentes metadatos EXIF), comparar los metadatos de todos los registros y
producir el registro más completo.

**Pendiente de:** mecanismo de notificación actual (solo loguea), decidir si
merge automático o manual.

---

## 4. Soporte para tracks GPS (GPX)

**Futuro.** Cuando se disponga de un archivo GPX del viaje, cruzar timestamps
con medios para asignar coordenadas más precisas.

**Source value:** `track_gps`

---

## 5. Normalización de nombres de archivo

**Columna existente en schema:** `filename_normalized` (nunca se popula).

**Propósito:** Slug limpio (sin espacios, caracteres especiales) para usar en
pipelines de procesamiento.

---

## 6. Content hash de video

**Flag existente:** `--compute-video-hash`

**Pendiente:** evaluar si vale la pena activarlo por defecto para lotes
chicos, o mejorarlo para que sea más rápido (sampleo de frames en vez de
extraer un frame completo).

---

## 7. Ingest masivo

**Pendiente de:** definir carpeta grande a procesar (actualmente trabajamos
con `D:\Flujos\Ingesta_1` como muestra).
