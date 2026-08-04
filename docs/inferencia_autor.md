# Inferencia y asignación de Autor de los Medios

## Contexto / Problema

La instalación agrupa y filtra medios por autor (carpetas "fotos de fabián",
"videos de juan", etc.). Para que eso funcione, cada registro de `media` debe
tener un `author` **confiable**. La columna viene acompañada de `author_source`,
que documenta de dónde salió el valor.

**Problema detectado** (auditoría Ago 2026, `db/flujos.db`, 1328 registros):

| source | cantidad | calidad |
|--------|---------:|---------|
| `exif` | 1 | ✅ cámara Sony |
| `carpeta` | 507 | 🟡 mixto (algunos reales, muchos basura) |
| `(null)` | 820 | 🟢 Telegram (`mensaje.from`, nombre real del chat) |

De los 507 con `source='carpeta'`, **206 son "Parte 1"** — el fallback actual
`author = carpeta` (carpeta cruda) metió el nombre de la carpeta como si fuera
una persona. **Eso es exactamente lo que hay que eliminar.**

Los 820 con `source=NULL` en realidad son **correctos**: vienen de Telegram y su
`author = mensaje["from"]` (el remitente real en el chat). Solo les falta el
flag `author_source`.

---

## Objetivo

Una **jerarquía de fuentes confiables** (de más a menos confiable) que nunca
invente un nombre falso. Si no hay forma de saber el autor, se deja **vacío**
(`NULL`) — es preferible no saberlo a saber una mentira.

---

## Jerarquía de fuentes propuesta

```text
1. Diccionario de personas (manual + derivado de Telegram) → source='diccionario'
2. EXIF Artist / Creator / IPTC By-line (imágenes)          → source='exif'
3. Marca/modelo de cámara o de celular                       → source='dispositivo'
4. Remitente del mensaje de Telegram (si hay link)           → source='telegram'
5. Ingreso manual (campo explícito del usuario)              → source='manual'
6. VACÍO (NULL)                                              → source=(null)
```

> ⚠️ **Se elimina** el fallback "usa el nombre crudo de la carpeta como autor".

---

## Fuentes en detalle

### 1. Diccionario de personas

Primera fuente y la más confiable. Combina dos orígenes:

**a) Diccionario derivado de Telegram** (nuevo)
- Se construye **automáticamente** a partir de los mensajes ya importados:
  `SELECT DISTINCT from_name FROM telegram_messages WHERE from_name IS NOT NULL`.
- Cada persona conocida del viaje queda en el diccionario con los nombres que usó
  en el chat (a veces el mismo contacta está con variantes: `Fabian`,
  `Fabian Wagmister`, `Fabi`, …).

> ⚠️ **El chat contiene mucho ruido** (auditado Ago 2026): bots (`Chatbro`),
> variantes cortas (`Lu`, `Lux`, `Ama`, `Mati`), nombres descriptivos
> (`Luis ...`), emojis (`TATU LENCERIA 🎀`) y gente que no es del viaje
> (`Conde Orlok`, `Diego Luna`). Por eso **el diccionario derivado de Telegram
> NO se usa crudo**: debe limpiarse y fusionarse por alias, y puede corregirse
> manualmente en `CARPETA_AUTHOR_MAP` (fuente autoritativa final). El orden de
> uso del diccionario es: `CARPETA_AUTHOR_MAP` gana sobre el derivado de
> Telegram cuando hay conflicto en el mapeo carpeta→persona.

> ⚠️ **Salvedad sobre las fuentes de inferencia**: los usuarios del diccionario
> derivado de Telegram **no necesariamente aparecen** en las demás vías de
> inferencia (carpetas, EXIF, dispositivo). Un nombre del chat como `Negra` o
> `Leo Spinetto` está en Telegram, pero su foto local puede estar en una carpeta
> sin su nombre (`Parte 1`, `fABIAN_C`) o con otra ortografía. Esto significa que
> el diccionario de Telegram NO se "combina" con la inferencia por carpeta para
> deducir autor de forma automática — solo aporta el **catálogo de personas
> posibles** y, cuando hay vínculo (mismo archivo en Telegram o coincidencia de
> carpeta), el nombre. La construcción del diccionario final (a quién mapear, con
> qué alias) se hace de forma **semi-manual** en `CARPETA_AUTHOR_MAP`, no se
> deriva a ciegas del chat. **Pendiente de resolver** en detalle al implementar.

**b) Mapping de carperetas → persona** (manual, en un diccionario del proyecto)
- Consolida el actual `CARPETA_AUTHOR_MAP` de `ingest.py`, extendido con las
  personas del grupo.
- Ejemplo:
  ```python
  CARPETA_AUTHOR_MAP = {
      "fABIAN":   "Fabian Wagmister",
      "fabian 2": "Fabian Wagmister",
      "FOTOS JPM": "Juan Pablo Margenat",
      "Lucas":      "Lucas Gaspari",
      ...
  }
  ```
- La comparación es por **substring en ambos sentidos** (carpeta ↔ nombre clave):
  si la carpeta (o una subcarpeta de la ruta) contiene el nombre de una persona
  del diccionario → se asigna esa persona.

**c) Resolución entre Telegram y el nombre crudo de carpeta**
- Si una carpeta/subcarpeta coincide con un nombre del diccionario (derivado de
  Telegram o de `CARPETA_AUTHOR_MAP`), se usa **ese** nombre, incluso si la
  carpeta está en mayúsculas / con sufijos (`fABIAN_C`, `fabian 2`).

### 2. EXIF / metadata del archivo

Para imágenes y videos ya soportado en `infer_author()`:
- `EXIF:Artist`, `XMP:Creator`, `IPTC:By-line`, `EXIF:Owner`.
- Cambio menor: priorizar el diccionario por encima de esto (hoy es al revés),
  porque una persona es más específica que el device.

### 3. Marca/modelo de cámara o celular

- Para videos con sidecar XML Sony: `xml_devicemanufacturer` + `xml_devicemodelname`.
- Para imágenes: EXIF `Make`/`Model`.
- Se guarda como `author = "Sony ILCE-7SM2"` (device), `source='dispositivo'`.
- **Default si el resto no dijo nada, nunca inventa persona.**

### 4. Telegram (re-consulta por vínculo temporal)

- Para los 820 que ya vinieron con autor real del chat, se marca `author_source='telegram'`.
- Para **medios ingeridos por archivo** (carpeta local) que NO tienen autor:
  si su timestamp cae dentro de la ventana temporal de un mensaje de Telegram de
  una persona del grupo, y el medio no tiene otra fuente → usar el remitente.
  Requiere la tabla `telegram_messages` (ya existe) y cruz por `date_unixtime`.

### 5. Ingreso manual explícito

- Un comando/opción TUI para fijar autor a una selección de medios (por id,
  carpeta, rango temporal o tipo).
- **Siempre sobrescribe** cualquier fuente automática (ver `--mode replace`).
- `source='manual'`.

### 6. Vacío

- Si ninguna fuente resuelve: `author=NULL`, `author_source=NULL`.
- **Nunca** fabricar `author = carpeta` ni `author = "Desconocido"`.

---

## Cambios a `db`/colas

- `author_source` ya existe. Se completará con los nuevos valores:
  `diccionario`, `exif`, `dispositivo`, `telegram`, `manual`, `(null)`.
- No hay migración de schema necesaria (solo re-llenar `author`/`author_source` con
  una pasada `--mode replace`).

---

## Cambios de código propuestos

1. `ingest.py::infer_author()`:
   - Reordenar prioridad: diccionario → EXIF → dispositivo → (vacío).
   - **Eliminar** el último recurso `author = carpeta`.
   - Aceptar `personas` (diccionario derivado + mapa) como parámetro.
2. Nuevo helper (dónde ?): `build_personas(conn) -> dict` que construye el
   diccionario desde `telegram_messages.from_name` + `CARPETA_AUTHOR_MAP`.
3. `import_telegram.py`: al insertar media set `author_source='telegram'` cuando
   el autor venga del mensaje.
4. Nuevo script `scripts/inferir_autor.py` (o step de `improve_db.py`):
   - Backfill de `author`/`author_source` sobre toda la DB con la jerarquía.
   - Soporta `--mode skip|update|replace` y `--dry-run`.
5. Opción TUI (sugerida): Menú Mantenimiento DB → "Inferir / reasignar autor".

---

## Prioridades de implementación (sugerencia)

1. **Desactivar fallback carpeta** (eliminar `author = carpeta`) + reordenar
   prioridad → inmediato, corrige los 206 de `Parte 1` y los futuros.
2. **Marcar `author_source='telegram'`** en los 820 ya correctos.
3. **Diccionario de personas** derivado + mapping extendido → pasa los medios por
   archivo con autor real (evita `"Parte 1"`).
4. **Vínculo temporal con Telegram** para reconocer medios en carpetas sin nombre.
5. **Campo manual** en el TUI.

---

## Criterios de éxito

- Cero medias con `author` = nombre de carpeta crudo (stop words: `Parte`,
  `photos`, `voice_messages`, números, …).
- Todos los medios con autor tienen un `author_source` consistente.
- Al re-correr con `--mode replace`, los autores confiables no cambian.