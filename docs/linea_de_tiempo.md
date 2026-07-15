# Línea de tiempo — Diseño conceptual

## Qué es

La línea de tiempo es el **eje vertebral invisible** de la instalación.
Organiza todos los medios según su posición cronológica en el viaje, desde
la salida de Buenos Aires hasta la llegada a Tucumán.

No se ve en la sala. Pero gobierna qué se muestra, en qué orden y con qué
contexto.

## Principios

1. **Todo medio tiene un momento.** Cada foto, video, audio o texto fue
   registrado en un instante del viaje. Ese instante (`timestamp_utc`) es su
   coordenada primaria en la línea.

2. **La línea no es uniforme.** Los medios no están espaciados de manera
   pareja. Hay momentos con muchas fotos seguidas y otros con horas de
   silencio. La línea respeta esos intervalos reales: no comprime ni
   estira el tiempo.

3. **El presente es un punto.** La instalación está siempre posicionada en
   algún momento del viaje. Ese momento es el **ahora** de la sala.

4. **El filtro acota, no reemplaza.** El filtro activo (rojo, atardecer,
   entrevista, etc.) acota qué medios del tramo actual se muestran. Pero el
   punto en la línea sigue existiendo aunque ningún medio del tramo coincida
   con el filtro.

## Estructura de la línea

```
tiempo real del viaje ──────────────────────────────────────────────→
                        |          |               |
                     foto 1    video 3 min      foto 2
                     (punto)   (segmento)      (punto)
```

Los medios se dividen en dos tipos según cómo ocupan la línea:

| Tipo | Ocupa | Ejemplos |
|---|---|---|
| **Punto** | Un instante (`timestamp_utc`) | Fotos, textos |
| **Segmento** | Un intervalo (`timestamp_utc` a `timestamp_utc + duration_secs`) | Videos, audios |

Un video de una hora puede solaparse temporalmente con fotos que se
sacaron durante esa hora. La línea no oculta eso: el video y las fotos
comparten el mismo tramo.

### Velocidad variable

El tiempo en la línea fluye a la **velocidad real del viaje**. Esto implica
que el "ritmo" de la instalación cambia según el contenido:

- Durante un video de 5 minutos, el tiempo pasa 1:1 (el video se reproduce).
- Entre el último medio de un día y el primero del siguiente, puede haber
  horas o días de diferencia — una **elipsis**.
- En momentos con muchas fotos seguidas (ej: 20 fotos en 2 minutos), la
  línea avanza rápido y se genera un **sumario** visual.

La instalación no se salta esos huecos ni acelera las zonas densas. Los
recorre al ritmo que el viaje realmente tuvo.

## Preguntas abiertas

Estas decisiones se postergan hasta la implementación del motor:

- **Sentido**: ¿la línea avanza siempre hacia adelante o puede
  rebobinarse? El candidato natural es que avance, pero no está decidido.
- **Cluster**: cuando hay muchas fotos en el mismo minuto (ej: 19 fotos
  en un mismo instante), ¿se funden, se elige una al azar, se rotan?
- **Solapamiento**: si un video de una hora coincide con fotos de ese
  mismo tramo, ¿se muestran las fotos superpuestas al video?
- **Vacío**: ¿qué se muestra cuando en el tramo actual no hay medios que
  cumplan el filtro activo?
- **Keypoints en video**: si un video tiene marcadores internos
  (transcripción, detección de escenas), esos puntos pueden funcionar
  como sub-paradas dentro del segmento.

## Relación con la deriva

La línea no es determinista. Es el **soporte**. La deriva elige **qué**
mostrar de lo que hay en el tramo actual, y el grito puede cambiar el
filtro o desplazar el punto en la línea. Pero la línea provee la
**continuidad narrativa** del viaje.

## `end_time` — Columna para consultas por rango

Para responder rápido a "¿qué medios están activos en este instante?", la DB
tiene la columna `end_time` en la tabla `media`:

```
end_time = timestamp_utc                   → para puntos (fotos, textos)
end_time = timestamp_utc + duration_secs   → para segmentos (videos, audios)
```

Con esta columna, un momento `t` se resuelve con un rango simple:

```sql
SELECT * FROM media
WHERE timestamp_utc <= '2025-09-03T10:40:00'
  AND end_time     >= '2025-09-03T10:40:00'
```

Hay índices en `timestamp_utc` y `end_time`, así que la consulta es eficiente
aunque la DB tenga millones de registros.

### Escenario concreto

```
10:30 ─────── 10:35 ─────── 10:40 ─────── 10:50 ─────── 11:00
  │              │              │              │
 foto         INICIO          foto           foto
              entrevista
              (20 min)

A las 10:40 → coinciden la foto de las 10:40 Y la entrevista (10:35→10:55)
```

La consulta a las 10:40 devuelve ambos medios. La instalación decide qué
hacer: mostrar ambos, priorizar uno, superponerlos, etc.

### Datos relacionales

| medio | tipo | timestamp_utc | duration_secs | end_time |
|-------|------|---------------|---------------|----------|
| foto 10:30 | punto | 2025-09-03T10:30:00 | NULL | 2025-09-03T10:30:00 |
| entrevista | segmento | 2025-09-03T10:35:00 | 1200 | 2025-09-03T10:55:00 |
| foto 10:40 | punto | 2025-09-03T10:40:00 | NULL | 2025-09-03T10:40:00 |
| foto 10:50 | punto | 2025-09-03T10:50:00 | NULL | 2025-09-03T10:50:00 |

### Consultas que responde la DB

| Consulta | SQL |
|----------|-----|
| "medios activos en t" | `WHERE timestamp_utc <= t AND end_time >= t` |
| "medios entre t1 y t2" | `WHERE timestamp_utc <= t2 AND end_time >= t1` |
| "siguiente medio después de t" | `WHERE timestamp_utc > t ORDER BY timestamp_utc LIMIT 1` |
| "medio anterior antes de t" | `WHERE end_time < t ORDER BY end_time DESC LIMIT 1` |
| "videos/audios que cubren t" | `WHERE type IN ('video','audio') AND timestamp_utc <= t AND end_time >= t` |
| "distribución por día" | `SELECT DATE(timestamp_utc), COUNT(*) FROM media GROUP BY 1` |
| "medios puntuales dentro de segmento" | `WHERE timestamp_utc >= :seg_start AND timestamp_utc <= :seg_end AND type = 'image'` |

### Keypoints dentro de un video

La tabla `media_keypoints` almacena puntos de interés dentro de un medio
continuo (video/audio). Cada keypoint tiene:

- `timestamp_offset_secs`: offset desde el inicio del medio (segundos)
- `timestamp_absolute`: timestamp absoluto en la línea de tiempo
  (= `timestamp_utc` del medio + offset). Esto permite consultas por rango
  sin cálculos por fila.
- `key`: tipo de keypoint (`transcription`, `scene_change`, etc.)
- `value`: contenido (texto de transcripción, etc.)

```sql
CREATE TABLE media_keypoints (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id              INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    timestamp_offset_secs REAL NOT NULL,           -- offset desde inicio
    timestamp_absolute    TEXT NOT NULL,            -- timestamp_utc + offset
    key                   TEXT NOT NULL DEFAULT 'transcription',
    value                 TEXT,
    source                TEXT DEFAULT 'whisper'    -- 'whisper', 'ollama', etc.
);
```

#### Ejemplo: consultar qué se dijo justo cuando se tomó una foto

```sql
SELECT kp.value AS dialogo, kp.timestamp_offset_secs
FROM media_keypoints kp
JOIN media foto ON foto.id = ?
WHERE kp.timestamp_absolute <= foto.timestamp_utc
  AND kp.media_id = ?
ORDER BY kp.timestamp_absolute DESC
LIMIT 1;
```

Esto devuelve la línea de diálogo que se estaba diciendo en el video justo
en el momento exacto en que se tomó la foto.

#### Independencia de capas

En un mismo instante `t` la instalación puede consultar cada capa por
separado:

| Capa | Consulta |
|------|----------|
| 🖼 Visual | `SELECT * FROM media WHERE timestamp_utc <= t AND end_time >= t AND type = 'image'` |
| 🔊 Auditiva | `SELECT * FROM media WHERE timestamp_utc <= t AND end_time >= t AND type IN ('video','audio')` |
| 📝 Textual | `SELECT value FROM media_keypoints WHERE timestamp_absolute = t AND key = 'transcription'` |
| 🎨 Metadata | `SELECT author, color_1_hex, latitude FROM media WHERE ...` |

Cada capa se resuelve independientemente. La instalación decide qué
combinación mostrar (ej: foto + texto de transcripción, sin video ni audio).
