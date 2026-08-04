# Diseño: armado y limpieza de tandas por subcarpetas

> Estado: diseño propuesto (Ago 2026).
> Motivación: el pipeline actual (`limpiar_tandas.py`) limpia una carpeta
> completa de golpe con descarte automático por phash/IA. Las pruebas sobre
> `C:\Users\Federico\Desktop\Flujos\test tandas` (5 tandas, 39 imágenes)
> demostraron que el descarte automático pierde fotos valiosas por detalles
> que el modelo no ve (pájaro presente/ausente, encuadre, ángulo de luz,
> bicho canasto como "urn"). Nueva estrategia: **separar tandas en
> subcarpetas y limpiar por tanda**, con un **espectro de estrategias** que va
> de lo conservador (solo descarta lo obvio, el usuario decide lo fino) a lo
> agresivo (delegación total a un modelo potente y lento, con el usuario
> sabiendo a qué atenerse).

---

## Problema actual (evidencia empírica)

Sobre las 5 tandas de test (39 imágenes, elecciones humanas = 14 valiosas):

| Umbral phash | Descarta | Valiosas perdidas |
|:---:|:---:|:---:|
| ≤ 2 / ≤ 3 | 4 | 2 |
| ≤ 4 / ≤ 5 (actual) | 12 | 6 |
| ≤ 8 | 14 | 6 |
| ≤ 10 | 15 | 6 |

- El phash mide similitud de **píxeles**, no de contenido: junta fotos
  casi-idénticas en píxeles que el humano quiere comparar (185313/185314,
  encuadre) y descarta una.
- moondream con el prompt genérico (EN, escueto) describe el nido de hornero
  como `urn with a red light...` y el bicho canasto como `urn with a white
  object...`. No ve los sujetos pequeños por su tamaño relativo. Tampoco
  diferencia "con pájaro" de "sin pájaro".
- `PROMPT_CLUSTER_TAGS` (criterio `tags`) devuelve **vacío siempre** con
  moondream → criterio roto en la práctica.
- Por eso: **ningún criterio automático actual es seguro para descartar
  definitivamente en tandas de detalle**.

---

## Nueva arquitectura: tres componentes

### Etapa 1 — Armar y separar tandas (`armar_tandas.py`, NUEVO)

**Objetivo**: organizar una carpeta con muchas imágenes en subcarpetas de
tandas manejables, para que el usuario limpie por tanda en vez de enfrentar
una carpeta monstruosa.

**Reglas**:
1. Escanea la carpeta raíz (sin tocar `excluir/`, `.proxies/`, ni la carpeta `tandas/`).
2. **Agrupación primaria holgada**: temporal, ventana configurable
   (`--ventana-minutos`, default 5 min). Este es el "modelo básico".
3. **Solo se mueven tandas de MÁS de 3 imágenes** (`--min-imagenes 4`):
   - tandas de 1 imagen → quedan en la raíz
   - tandas de 2-3 imágenes → quedan en la raíz (no se fragmenta el trabajo)
   - tandas de 4+ imágenes → se mueven a `tandas/`
4. **Naming de carpeta**: `Tanda_<YYYYMMDD_HHMMSS del primer archivo>__<N>img`
   (ej: `Tanda_20250814_130604__13img`).
5. Mueve sidecars (`.AAE`, `.json`, `.xml`, `.XMP`) junto con cada imagen.
6. **Nunca toca la DB**: corre siempre pre-ingesta (antes de `ingest.py`).
   Si los archivos ya están ingeridos, usar `relocate.py` o `mover_media.py`.

**Estructura resultante**:
```
origen/
├── 20250811_185311.jpg          ← tanda unitaria: NO se mueve
├── 20250906_155817.jpg          ← tanda unitaria: NO se mueve
├── tandas/
│   ├── Tanda_20250814_130604__13img/
│   │   ├── IMG_20250814_130604.jpg
│   │   ├── ...
│   │   └── excluir/              ← (se crea en la etapa 2)
│   ├── Tanda_20250906_212423__5img/
│   └── ...
```

**Args CLI (propuestos)**:
- `carpeta` (posicional, obligatorio)
- `--ventana-minutos` (default 5)
- `--min-imagenes` (default 4, tandas de más de 3 imágenes)
- `--dry-run`, `--json`
- `--carpeta-tandas` (default `tandas`)

### Etapa 2 — Limpiar por tanda: la familia de estrategias

**Objetivo**: operar sobre UNA subcarpeta de tanda (o todas en modo batch),
aplicando una estrategia del espectro. En vez de un solo criterio, se ofrece
una **familia de scripts/estrategias ordenadas por agresividad**, para que el
usuario elija cuánto quiere delegar o atacar carpetas específicas con
estrategias específicas.

**Cambios sobre el script actual**:
1. Acepta una **subcarpeta de tanda** como entrada (además de la carpeta raíz).
2. Por default, si se le pasa una tanda, limpia SOLO esa tanda (no toda la raíz).
3. **Descarte directo** (decisión del usuario): la estrategia elige y mueve a
   `excluir/`. El usuario puede recuperar manualmente si la tanda tiene algo
   relevante.
4. **`excluir/` dentro de cada subcarpeta de tanda** (`Tanda_X/excluir/`),
   no global.
5. El pre-filtro phash **NO descarta definitivamente** en las estrategias
   conservadoras: solo agrupa candidatas (los sub-grupos phash se convierten
   en grupos de selección; se conserva la mejor de cada grupo). El phash
   como descarte agresivo queda solo en las estrategias altas.

#### Espectro de estrategias (de conservador a agresivo)

| Nivel | Estrategia | Descarta | Resto | Indicado para |
|:---:|-----------|----------|-------|---------------|
| **1** | `obvio` | duplicados exactos (phash bajo) + desenfoque evidente (nitidez) | el resto queda para el humano | default. Tandas normales. No pierde casi nada. |
| **2** | `nitidez-por-subgrupo` | dentro de cada sub-grupo phash, descarta las menos nítidas | el mejor de cada sub-wvu | Tandas de ráfaga del mismo motivo. |
| **3** | `embeddings` | separa sub-motivos semánticos y conserva el mejor de cada uno | 1 por sub-motivo | Tandas que mezclan motivos (ej: caminata con 3 fotos de cosas distintas). |
| **4** | `modelo-potente` | **(delegación total)** un modelo grande de visión ve TODAS las imágenes de la tanda y decide cuáles se van | el usuario sabe que delegó | Quienes prefieren delegar el trabajo y solo repasar resultado. |

> **Sobre `calidad`/`tags`**: el criterio `calidad` con moondream quedó
> **desestimado** (fragilidad, respuestas vacías o `5.0`/`8.0` fijos, no
> discrimina). El criterio `tags` con moondream está **roto** (vacío siempre).
> Solo tienen sentido en el nivel 4 (`modelo-potente`) con qwen2.5vl/llama3.2
> u otro modelo capaz.

**Menú propuesto (modo interactivo por tanda)**:
```
Limpieza de Tanda_20250814_130604__13img (13 imágenes)
  1. Obvio (nitidez + phash objetivo)      [CPU, instantáneo — recomendado]
  2. Nitidez por sub-grupo                 [CPU]
  3. Embeddings (por sub-motivo)           [IA niómica]
  4. Modelo potente (delegación total)     [IA visión grande, LENTA]
  5. Sin limpieza automática (revisar mano)
  0. Volver / comprobar resultados
```

### Etapa 3 — Delegación total (`limpiar_modelo_potente.py`, OPCIONAL)

**Regreso (mejorado) a la estrategia original de "un modelo ve todas las
imágenes y decide"**, pero ahora con dos condiciones que resuelven las
crittếcِs identificadas:

- **Modelo potente y lento**: `qwen2.5vl:7b` / `llama3.2-vision:latest` (o el
  que se elija), NO moondream. Usa proxys de 800px (rápido) para clasificar y
  el modelo grande para decidir. Costo: ~seg a más por imagen; aceptable como
  corrida nocturna o pasada puntual.
- **El usuario sabe a qué atenerse**: como la decisión es automática y
  agresiva, se debe correr de forma **explícita** (no default) y el usuario
  acepta que es una delegación. El script pide confirmación al inicio,
  muestra el resumen global al final, y **nunca toca imágenes fuera de la
  tanda/apuesto** elegida.

Interfaz mínima:
```
limpiar_modelo_potente.py Tanda_* --modelo qwen2.5vl:7b [--solo-candidatas]
```
- Sin `--solo-candidatas` → descarga directo a `Tanda_X/excluir/`.
- Con `--solo-candidatas` → mueve a `Tanda_X/candidatos/` para repaso humano
  antes de confirmar (alternativa prudente dentro del modo delegado).

Prompts: en inglés, sin pedirle "qué hay" (evitar sesgo); pide puntuación de
conservación (1-10) con justificación breve, similar a `PROMPT_EVALUAR_CALIDAD`
pero robustecido (se corrigió el formato que moondream rompía).

> ⚠️ Este nivel se desaconseja para tandas de detalle biológico (pájaro/
> insecto pequeño), donde ni el modelo grande suele acertar sin ayuda. Está
> pensado para tandas de "mucho volumen repetido" donde delegar traba y
> liberar al usuario.

---

## Decisiones tomadas (validación del usuario)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | Mínimo de imágenes para mover a `tandas/` | **más de 3** (≥ 4) |
| 2 | Dónde va `excluir/` | **dentro de cada subcarpeta de tanda** |
| 3 | Descarte automático | **directo** (el usuario recupera manualmente si ve algo relevante) |
| 4 | Momento del armado | **siempre pre-ingesta** (no toca la DB) |
| 5 | Espectro de limpieza | **familia de estrategias** por agresividad (obvio → delegación) |
| 6 | Modelo potente | **opcional y explícito** (delegación total; el usuario sabe a qué atenerse) |

---

## Integración con el pipeline

```
[Medios crudos en carpeta]
       │
       ▼
1. armar_tandas.py  (NUEVO)
   ├── agrupa por tiempo (holgado)
   ├── mueve tandas de ≥4 imágenes a tandas/Tanda_*__Nimg/
   └── las de 1-3 quedan en la raíz
       │
       ▼
2. limpieza por tanda (familia de estrategias)
   ├── estrategia 1: obvio (CPU, default)        → Tanda_X/excluir/
   ├── estrategia 2: nitidez-por-subgrupo (CPU)
   ├── estrategia 3: embeddings (IA nómica)
   ├── estrategia 4: modelo-potente (IA grande, explícita)
   │                    → Tanda_X/excluir/ (o Tanda_X/candidatos/)
   └── o el usuario limpia a mano la subcarpeta
       │
       ▼
3. ingest.py  (sin cambios)
   └── escanea raíz + tandas/*, ignora todas las carpetas excluir/
```

**Nota sobre `ingest.py`**: ya excluye carpetas `excluir/` en cualquier nivel
según su docstring ("Carpetas `excluir/` y ocultas siempre se excluyen").
Verificar que la exclusión sea por nombre de carpeta en cualquier nivel, no
solo en la raíz.

---

## Mejoras pendientes detectadas en el proceso

1. **`PROMPT_CLUSTER_TAGS` roto**: moondream devuelve vacío con el formato
   "Reply with ONLY 3 comma-separated keywords". Revisar el prompt (probable
   fix: formato más simple tipo `3 words:`) o documentar el criterio `tags`
   como no funcional.
2. **`ingest.py` — exclusión de `excluir/` a cualquier nivel**: confirmar que
   el scan recursivo ignora `excluir/` en subcarpetas (las nuevas
   `Tanda_X/excluir/`).
3. **`relocate.py` / `mover_media.py`**: si el armado se corre sobre medios ya
   ingeridos, actualizar rutas en la DB (fuera de alcance del armado
   pre-ingesta, pero documentar).
4. **Limpiar proxies**: al mover tandas a subcarpetas, los `.proxies/`
   quedan en la carpeta original. Reusar `limpiar_proxies()` / `--limpiar-proxies`
   del `limpiar_tandas.py` actual en el nuevo `armar_tandas.py`.
5. **Prompt de modelo potente robusto**: el `PROMPT_EVALUAR_CALIDAD` actual
   (formato `'8. razón'`) fue el que moondream rompía; al usarlo con
   qwen2.5vl/llama3.2-vision revisar que el formato de respuesta sea estable
   y parseable (`_extraer_puntaje`), o simplificarlo para el modelo grande.
6. **Interfaz del espectro en TUI**: el menú Mejorar DB → Preparar medios
   debe crecer para incluir `armar_tandas.py` (1. Limpieza de tandas →
   sub-opciones) y la familia de estrategias por tanda.

---

## Archivos involucrados

- `scripts/armar_tandas.py` — NUEVO (etapa 1: separar tandas en subcarpetas)
- `scripts/limpiar_tandas.py` — REDISEÑADO (etapa 2: estrategias 1-3, por subcarpeta)
- `scripts/limpiar_modelo_potente.py` — NUEVO (etapa 3: delegación total, opcional)
- `scripts/ingest.py` — verificar exclusión de `excluir/` en cualquier nivel
- `scripts/ai_media/clustering.py` — revisar `PROMPT_CLUSTER_TAGS`; base de la estrategia embeddings
- `scripts/ai_media/batch_selector.py` — base de selección por nitidez/calidad
- `scripts/ai_media/ollama_client.py` — selector de modelo potente (qwen2.5vl:7b/llama3.2-vision)
- `db/` — sin cambios (armado pre-ingesta)

## Pruebas de validación

- Repetir sobre `C:\Users\Federico\Desktop\Flujos\test tandas`:
  - `armar_tandas.py` → debe crear `tandas/Tanda_*__*img/` para las tandas
    de ≥4 (G1=8, G2=4, G3=13, G4=9, G5=5) y dejar en la raíz las unitarias.
  - `limpiar_tandas.py Tanda_*` con criterio `nitidez` → descarta a
    `Tanda_*/excluir/`, sin perder las 14 valiosas (el humano recupera).
- Comparar conservadas/descartadas contra las elecciones humanas del
  benchmark (`temp/benchmark_criterios.py`).
