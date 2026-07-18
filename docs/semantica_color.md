# Semántica del Color

> Diseño conceptual — pendiente de implementación.
> Idea original: ir más allá del color como dato físico y agregar una capa
> semántica/cultural/emocional.

---

## Problema

Hoy la DB sabe que un medio tiene `color_1_name_basic = 'rojo'`, pero no sabe
qué *significa* ese rojo en contexto. El rojo de una ambulancia no es lo mismo
que el rojo de una rosa, aunque ambos sean `#c1272d`.

---

## Propuesta

### 1. Tabla de referencia `color_meanings`

Mapping universal de categoría básica de color → significados culturales,
emocionales, simbólicos y naturales.

```sql
CREATE TABLE color_meanings (
    color_basic TEXT NOT NULL,       -- rojo, azul, verde, etc.
    meaning TEXT NOT NULL,           -- pasion, peligro, amor, tristeza...
    peso REAL DEFAULT 1.0,           -- peso base de la asociacion
    categoria TEXT,                  -- emocion, simbolo, natural, cultural
    UNIQUE(color_basic, meaning)
);
```

Ejemplos de carga:

| color_basic | meaning | peso | categoria |
|-------------|---------|------|-----------|
| rojo | peligro | 0.8 | simbolo |
| rojo | pasion | 0.7 | emocion |
| rojo | amor | 0.6 | emocion |
| rojo | urgencia | 0.5 | simbolo |
| azul | tristeza | 0.8 | emocion |
| azul | calma | 0.7 | emocion |
| azul | frio | 0.6 | natural |
| verde | naturaleza | 0.9 | natural |
| verde | esperanza | 0.7 | emocion |
| amarillo | alegria | 0.8 | emocion |
| amarillo | advertencia | 0.7 | simbolo |
| ... | ... | ... | ... |

### 2. Resolución en query-time (JOIN)

Sin duplicar datos. Cada medio hereda los significados de sus colores
dominantes mediante JOIN:

```sql
-- Todos los medios "peligrosos" (por color)
SELECT DISTINCT m.* FROM media m
JOIN color_meanings cm ON cm.color_basic IN (
    m.color_1_name_basic,
    m.color_2_name_basic,
    m.color_3_name_basic
)
WHERE cm.meaning = 'peligro'
ORDER BY
    CASE WHEN cm.color_basic = m.color_1_name_basic THEN 1
         WHEN cm.color_basic = m.color_2_name_basic THEN 2
         ELSE 3 END;
```

El `ORDER BY` prioriza el color dominante sobre los secundarios.

### 3. Ponderación contextual

El `peso` base de `color_meanings` se puede modular por:
- **Jerarquía del color**: `color_1` pesa más que `color_3`
- **Concentración**: qué % de la imagen cubre ese color (hoy no lo tenemos)

Fórmula tentativa:

```
peso_efectivo = significado.peso * (3 - posicion_color) / 3
```

### 4. IA contextual (enriquecimiento por medio, opcional)

Para ir más fino, preguntar a Ollama sobre cada imagen:

> *"Además del contenido de la imagen, ¿qué emociones o símbolos evoca el
> color dominante ({nombre_color}) en este contexto específico?"*

Guardar resultado en `media_metadata`:

| media_id | key | value |
|----------|-----|-------|
| 42 | `color_meaning_contextual` | `["peligro", "urgencia", "alerta"]` |

Así, en una ambulancia el rojo → peligro/urgencia, mientras que en una rosa
el rojo → amor/pasión, aunque ambos sean `color_basic = rojo`.

### 5. Kuleshov effect en la instalación

En TouchDesigner, el color de fondo o de un overlay modula cómo se percibe
el contenido:

- **Fondo rojo + video de camión** → peligro, velocidad
- **Fondo rojo + primer plano de un beso** → amor, pasión
- **Fondo azul + misma escena** → tristeza, distancia

Esto es lógica de presentación, no de DB, pero la DB debe poder responder:

```sql
-- Medios cuyo SIGNIFICADO coincida con el color de fondo actual
SELECT m.* FROM media m
JOIN color_meanings cm ON cm.color_basic = m.color_1_name_basic
WHERE cm.meaning = 'peligro'
  AND m.timestamp_utc BETWEEN ? AND ?;
```

### 6. Cross-modal retrieval

Buscar por emoción/símbolo encuentra medios por su color aunque la palabra
no esté en los keywords:

- Buscar `"tristeza"` → medios azules/violetas (sin necesidad de tag explícito)
- Buscar `"frio"` → medios azules/blancos
- Buscar `"calor"` → medios rojos/naranjas

Esto abre consultas del tipo:

```sql
-- Unir significado de color + keywords de IA + transcripción
SELECT m.*, cm.meaning
FROM media m
JOIN color_meanings cm ON cm.color_basic IN (m.color_1_name_basic, m.color_2_name_basic, m.color_3_name_basic)
LEFT JOIN media_metadata kw ON kw.media_id = m.id AND kw.key = 'ia_keywords'
LEFT JOIN media_metadata tr ON tr.media_id = m.id AND tr.key = 'transcript'
WHERE cm.meaning = 'peligro'
   OR kw.value LIKE '%peligro%'
   OR tr.value LIKE '%peligro%';
```

---

## Integración con el pipeline actual

```
improve-db --step colors  (ya existe)
       │
       ▼
[Etapa nueva: Semantica de color]
  ├── Opcion A: Solo tabla color_meanings + JOIN (sin cambios en DB de medios)
  └── Opcion B: IA contextual → media_metadata (opcional, post-ingesta)
```

No requiere migración de schema existente. Solo crear `color_meanings` y
poblarla. El JOIN se arma del lado de la consulta.

---

## Próximos pasos (cuando corresponda)

1. Definir lista de significados por color básico (curación colectiva)
2. Crear `color_meanings` en schema.sql
3. Agregar script de población (diccionario fijo)
4. Opcional: agregar paso a improve-db para IA contextual
5. Actualizar query.py para búsqueda por significado
6. Integrar en TouchDesigner para Kuleshov effect
