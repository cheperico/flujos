# Flujo de medios — Pipeline completo

## Visión general

El pipeline tiene tres etapas principales, en orden:

```
Medios crudos → CURACIÓN → INGESTA → RELACIONES → DB lista para la instalación
```

Cada etapa puede volver a correrse total o parcialmente sin romper las
anteriores.

---

## 1. CURACIÓN (pre-ingesta)

Antes de indexar cualquier medio en la DB, hay que prepararlo. La curación
opera sobre los **archivos físicos**, no sobre la DB.

### Tareas

| Tarea | Qué hace |
|---|---|
| **Redimensionar** | Fotos muy grandes → tamaño manejable (ej: 1920px lado mayor) |
| **Eliminar duplicados** | Por hash de contenido, no por nombre |
| **Eliminar malas fotos** | Borrosas, subexpuestas, completamente oscuras, etc. |
| **Etiquetado con IA** | Poner descripciones y keywords en IPTC usando modelos locales (Ollama) |

### Notas

- La curación podría ser un script que recorra una carpeta, procese cada
  archivo y deje los resultados in-place o en una carpeta de salida.
- El etiquetado con IA es opcional y puede hacerse por lote.
- Videos y audios tienen su propia curación (más adelante).

### Scripts existentes relacionados

- `limpiar_tandas.py`: selección inteligente de mejor imagen por tanda
  (usa moondream para evaluar calidad). No es exactamente curación pero se
  acerca.
- `mover_descartadas.py`: mueve las descartadas a una carpeta separada.

---

## 2. INGESTA (indexación)

Ya existe (`ingest.py`). Escanea los medios curados, extrae metadatos
(EXIF, GPS, timestamps, colores, autor) y los inserta en la DB.

### Particularidades

- La ingesta es **incremental**: si un archivo ya está en la DB por su
  `file_hash`, se saltea.
- Guarda la raíz de ingesta en la tabla `config` para poder relocalizar
  después.
- Cada ingesta corre sobre una carpeta y procesa todo lo que encuentra.

### Lo que falta

- Poder identificar y deshacer una ingesta específica. Hoy no hay una
  marca de "lote de ingesta" — todos los registros son indistinguibles.
  Se podría agregar un `ingest_batch_id` en la tabla `media` que se
  asigne al inicio de cada corrida.

---

## 3. POST-INGESTA: inferencia

Una vez que los medios están en la DB, hay datos que se pueden **completar**
infiriendo a partir de la información que ya existe. La columna ordenadora
es el **tiempo**: si dos medios comparten timestamp, es muy probable que
compartan ubicación.

### Qué se puede inferir

| Inferencia | Qué hace | Ejemplo |
|---|---|---|
| **Espacial** | Completar latitud/longitud donde falte usando medios cercanos en el tiempo que sí tengan GPS | Foto de Fabian sin GPS pero misma hora que una de Negra con GPS → se asigna la misma coordenada |
| **Temporal** | Completar timestamps faltantes | Video sin fecha pero rodeado de fotos con fecha → se infiere el rango |
| **De autor** | Asignar autor a medios donde no se pudo determinar | Foto sin EXIF ni carpeta identificable pero misma hora que las de Fabian → se asigna a Fabian |

### Scripts necesarios

- `inferir_gps.py` — completar coordenadas faltantes.
- `inferir_timestamp.py` — completar timestamps faltantes.

## 4. VINCULACIÓN (en runtime, no en pipeline)

La vinculación entre medios no es una etapa del pipeline. **No se procesa
post-ingesta.** Los vínculos ya existen implícitamente en los metadatos que
comparten.

Cada medio tiene muchas columnas de metadatos (color, GPS, autor, keywords,
timestamps). La columna ordenadora es el **tiempo**. La instalación, en
tiempo real, consulta la DB y obtiene medios vinculados por:

| Eje de vinculación | Se consulta con |
|---|---|
| **Temporal** | `timestamp_utc` — medios cercanos en el tiempo |
| **Cromático** | `color_1/2/3_name_basic` — mismo color predominante |
| **Espacial** | `latitude/longitude` — misma zona geográfica |
| **Autoral** | `author` — mismo autor |
| **Temático** | keywords en `media_metadata` — mismas palabras clave |

No hace falta una tabla `media_relations` ni un script que las genere. Las
relaciones se resuelven en cada consulta que haga la instalación a la DB.

### Nota de arquitectura (para cuando se implemente la instalación)

Puede convenir tener **recorridos predefinidos** (rutas curadas que
atraviesan el viaje con un criterio narrativo) o una **capa de caché** que
pre-calcule consultas frecuentes (ej: "medios rojos ordenados por tiempo").
Eso no cambia el diseño de la DB ni el pipeline — es una optimización del
motor de consulta que se construye en TouchDesigner (o el motor que se use).

---

## Gestión de la DB

### Reset completo

Un script que borre todo y deje la DB lista para arrancar de cero:

```powershell
python flujos.py reset-db           # Borra datos, mantiene schema
python flujos.py reset-db --hard    # Borra la DB entera y la recrea
```

### Deshacer ingesta

Se necesita un `ingest_batch_id` en la tabla `media`. Cada corrida de
ingesta genera un ID único. Después se puede:

```powershell
python flujos.py undo-ingest --batch 2    # Borra todos los medios de la ingesta 2
python flujos.py ingest --list-batches    # Lista las ingestas realizadas
```

### Deshacer relaciones

Cada pasada de relaciones debería registrar qué hizo (timestamp, tipo,
parámetros). Algo como la tabla `config` pero con historial:

```sql
CREATE TABLE IF NOT EXISTS relation_passes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo       TEXT NOT NULL,       -- 'inferir_gps', 'agrupar_color', etc.
    parametros TEXT,                -- JSON con los parámetros usados
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Cada registro que se modifica guarda el `relation_pass_id` que lo tocó.
Así se puede deshacer una pasada específica.

---

## Estado actual (Julio 2026)

| Etapa | Script | Estado |
|---|---|---|
| Curación | `limpiar_tandas.py`, `mover_descartadas.py` | Parcial (solo selección por calidad) |
| Ingesta | `ingest.py` | ✅ Completo (con bugs recién fixeados) |
| Inferencia (GPS, timestamp) | — | ❌ No existe |
| Vinculación (runtime) | Se resuelve consultando la DB | ✅ No hace falta script |
| Reset DB | — | ❌ No existe |
| Undo ingesta | — | ❌ No existe |
