# Retorno del "Fluir" en TouchDesigner — Guía de armado (canal 9002)

> Documento de armado **manual** del lado TouchDesigner para recibir el resultado
> del gesto "Fluir" que devuelve Python por el puerto **9002**.
> No edita archivos TD: el `.toe` se arma a mano siguiendo esta guía.
>
> **Fecha**: 2026-08-09 · **TD**: 2025.32820 (ver `docs/lecciones_elecciones_td.md`)
> · **Pipeline**: `scripts/puente_td.py` modo `fluir` (ya implementado) ·
> **Spec**: `docs/motor_loop.md` + `td/spec_fluir.json` (ejemplo real en disco) ·
> **Callbacks**: `td/fluir_callbacks.dat` (contrato NUEVO por tipos).

---

## 0. Resumen ejecutivo de la arquitectura propuesta

El retorno del "Fluir" llega por un **canal OSC nuevo y aislado** (9002) que
recrea el mismo patrón probado en `osc_in1` en la sesión de elecciones: un
**OSC In DAT** con su **callbacks interno adjuntado a un `.dat` externo**
(File + Sync to File).

**Rediseño clave**: el contrato OSC pasó de "una lista plana de medios"
(`/resultado`, `/medio`, `/fin`) a un **contrato por tipos** — Python agrupa
los medios por tipo (`image`, `video`, `audio`, `text`), anuncia cada tabla con
`/tabla`, y envía cada medio con su **keypoint** (= `t_loop`, posición dentro
del loop) y su **hora**. TD ya no depende del JSON para saber "cuándo" sale cada
medio: lo trae el wire.

```
Python: puente_td.py modo fluir
   │
   │  1. escribe td/spec_fluir.json   (spec completo: loop_secs, resumen, por_tipo, chiches)
   │  2. envía por OSC 9002, en orden:
   │     /flujos/fluir/resumen <total> <loop_secs> <image> <video> <audio> <text>
   │     Por tipo (image, video, audio, text; solo si tiene medios):
   │       /flujos/fluir/tabla  <tipo> <cantidad>
   │       /flujos/fluir/medio  <media_id> <ruta> <keypoint> <hora> <tipo>  (×cantidad)
   │     /flujos/fluir/chiche <hora> <texto>   (0..N)
   │     /flujos/fluir/fin   <total>
   ▼
/project2/
   ├── osc_in2           (OSC In DAT, puerto 9002)   ← NUEVO, independiente
   │   └── osc_in2_callbacks  ◄── File: td/fluir_callbacks.dat (Sync to File ON)
   │           ├─ /resumen → fluir_estado     (total, loop_secs, image, video, audio, text)
   │           ├─ /tabla+/medio → fluir_fotos / fluir_videos / fluir_sonidos / fluir_textos
   │           ├─ /chiche → fluir_chiches
   │           └─ /fin      → fluir_estado.fin=1 + cotejo con td/spec_fluir.json
   ▼
   (consumo, opcional según etapa visual)
   ├── fluir_estado      (Table DAT clave-valor: total, loop_secs, por tipo, fin, recibidos/esperados)
   ├── fluir_fotos / fluir_videos / fluir_sonidos / fluir_textos  (Tablas por tipo, misma estructura)
   ├── fluir_chiches     (Table DAT: hora, texto)
   ├── fluir_loop        (Timeline o Count CHOP en loop 0..loop_secs)
   └── fluir_movie       (Movie File In TOP) → reproducción del loop
```

**Regla de oro**: `osc_in2` **no se conecta ni comparte nada** con `osc_in1`
(puerto 9000, nubes `elec_*`) ni con `osc_out1` (9001, selección). Cada canal
mantiene su operador y sus tablas `elec_*` vs `fluir_*`. Eso ya estaba decidido
en `docs/lecciones_elecciones_td.md` §"Decisión clave" (canal 9002 separado) y
esta guía lo respeta al pie.

---

## 1. Contrato del canal 9002 (lo que llega exactamente)

Antes de armar ningún operador hay que fijar el wire — esto lo escribe
`scripts/puente_td.py` (`_procesar_rafaga`, ya implementado) y viene de
`spec["resumen"]` / `spec["por_tipo"]` / `spec["chiches"]`:

| Orden | Address | Args | Significado |
|---|---|---|---|
| 1 | `/flujos/fluir/resumen` | `i:int total`, `f:float loop_secs`, `i:image`, `i:video`, `i:audio`, `i:text` | Resumen del lote: totales por tipo (de `spec["resumen"]`) |
| 2 (por filtro activo; 0..N) | `/flujos/fluir/filtro` | `s:clave`, `s:valor` | Un filtro puesto por el usuario → fila `[clave, valor]` en `fluir_estado`. Claves: `hora_inicio`, `hora_fin`, `horas_elegidas` (siempre); `municipios`, `colores`, `tags`, `dias`, `clima` (solo si vienen) |
| 3 (por tipo, orden estable image → video → audio → text; **solo si tiene medios**) | `/flujos/fluir/tabla` | `s:tipo`, `i:cantidad` | Comienza una tabla para un tipo |
| 4 | `/flujos/fluir/medio` (×cantidad) | `i:media_id`, `s:ruta`, `f:keypoint`, `f:hora`, `s:tipo` | Un medio por mensaje; el tipo es el del bloque |
| — (se repite tabla+medio para cada tipo con medios) | | | |
| 5 | `/flujos/fluir/chiche` (0..N) | `f:hora`, `s:texto` | Un chiche climático/astronómico |
| 6 | `/flujos/fluir/fin` | `i:int total` | Marca de finalización del lote |

Puntos que conviene notar antes de programar:

- **La address real es `/flujos/fluir/...`** (constante `OSC_ADDR_FLUIR` en
  `puente_td.py`). En documentación previa figuraron variantes con typo
  (`/flojos/fluir`, `/fljujos/fluir`); **la real es `/flujos/fluir`** — se
  verifica empíricamente con `osc_probe.py 9002`. El callbacks compara el
  address absoluto contra `"/flujos/fluir/..."`.
- **`keypoint` = `t_loop`**: posición temporal del medio **dentro del loop**
  (segundos sobre `[0, loop_secs)`). QUEDA **DEFINIDO** con ese significado; ya
  no es una decisión abierta. `hora` es la hora decimal de los metadatos (0..24).
  Ambos valores viajan en el wire: el motor puede posicionar cada medio sin leer
  el JSON.
- **Tipos sin medios no se anuncian**: si `image` tiene 0 medios, el resumen
  reporta `image=0` y NO se envía `/tabla image` ni ningún `/medio` image.
- **`/flujos/fluir/filtro` refleja la elección del usuario**: el estado del
  loop (tabla `fluir_estado`) no solo tiene totales sino también qué eligió el
  visitante (`hora_inicio`, `hora_fin`, `horas_elegidas` siempre; más
  `municipios`, `colores`, `tags`, `dias`, `clima` si vienen). El puente lo
  genera desde `spec["resumen"]["filtros"]` / `spec["resumen"]["rango_horas"]`.
- **El archivo `td/spec_fluir.json` se escribe ANTES del primer mensaje OSC** y
  ahora **no es la fuente única**: se lee solo para **cotejar** (debug de
  pérdida UDP) en `fin`.
- Los mensajes son **best-effort** (UDP). El `fin` trae la cantidad esperada
  para detectar paquetes perdidos comparando contra las tablas recibidas.

---

## 2. Paso 1 — Crear el receptor `osc_in2` (OSC In DAT, puerto 9002)

**Objetivo**: disponer de un punto de entrada dedicado para el retorno del
"Fluir", físicamente separado del canal de nubes (9000).

**Instrucción**:

1. En `/project2`, `Add Operator` → **OSC In DAT** (categoría `DAT`). TD lo
   nombra automáticamente **`osc_in2`** (porque `osc_in1` ya existe) y su DAT
   interno de callbacks queda **`osc_in2_callbacks`** — mantener esos nombres,
   NO renombrar.
2. En los parámetros del OSC In DAT (página de red / `OSC In`): **Port = 9002**.
   Dejar `Active` = ON.
3. Verificar con un probe externo en otra terminal:
   `python scripts/osc_probe.py 9002 5` → los mensajes `/flujos/fluir/...`
   deben aparecer en la tabla del `osc_in2`.
4. (Opcional, layout) Ubicar `osc_in2` a la derecha de `osc_out1`.

**Por qué**:

- Un OSC In DAT solo **muestra** los mensajes crudos en su propia tabla; el
  enrutado a las tablas vive en su callbacks interno (Lección 1 de
  `docs/lecciones_elecciones_td.md`).
- El nombre `osc_in2` es el que TD autogenera al crear el segundo OSC In DAT
  (con `osc_in1` ya existente) y su callbacks interno `osc_in2_callbacks`; es el
  nombre real del toe. Mantenerlo (sin renombrar) evita romper la referencia
  del callbacks y mantiene la convención `osc_i<N>` del proyecto.
- Puerto distinto (9002) + operador distinto (`osc_in2`) ⇒ **cero interferencia**
  con `osc_in1/9000`: aunque un mensaje erróneo llegara al socket viejo, no
  tocaría las nubes porque viven en otro operador y otro puerto.

---

## 3. Paso 2 — Crear `td/fluir_callbacks.dat` y adjuntarlo al callbacks de `osc_in2`

**Objetivo**: implementar el cerebro de recepción: distribuir los mensajes del
contrato **por tipo** en tablas separadas (`fluir_fotos`, `fluir_videos`,
`fluir_sonidos`, `fluir_textos`), mantener `fluir_estado` y `fluir_chiches`, y
en `fin` cotejar recibido vs esperado (+ el spec JSON).

**Instrucción**:

1. Crear el archivo `td/fluir_callbacks.dat` con el contenido de la §3.2.
2. Doble clic sobre **`osc_in2`** → se abre el DAT interno `osc_in2_callbacks`.
3. En ese DAT: **`File` = `fluir_callbacks.dat`**, **`Sync to File` = ON**.
4. Guardar el `.dat` y pulsar `Load` para forzar el sync; verificar en el
   Textport que no hay errores (o correr por
   `python -c "import ast; ast.parse(open('td/fluir_callbacks.dat', encoding='utf-8').read()); print('OK')"`).

**Por qué**: el patrón **File + Sync to File = ON** es el que ya usa el
proyecto (`osc1_callbacks` → `osc_callbacks.dat`, `elecciones_ui_callbacks` →
`elecciones_ui.dat`) y permite editar el código fuera de TD y que se refleje en
el `.toe`.

### 3.1 Convenciones a respetar dentro del `.dat`

- **Prefijo de log**: `[fluir_callbacks] ...`.
- **Idioma**: español (docstrings, variables `_snake_case`).
- **`_ROOT`**: al inicio `_ROOT = op("/project2")`.
- **Constantes**: `OSC_ADDR_FLUIR = "/flujos/fluir"` (la real del sender) y el
  mapeo `TABLAS_POR_TIPO` image/video/audio/text → fotos/videos/sonidos/textos.
- **Helper central**: `_tabla_para_tipo(tipo)` devuelve el nombre de tabla
  correcto (las 4 tablas de medios tienen **la misma estructura**).
- **Router**: `_enrutar(address, args)` por **address absoluto** — los 5
  addresses son fijos.
- **Guardas**: si falta una tabla destino, advertencia clara y `return`.

### 3.2 Esqueleto de `fluir_callbacks.dat` (listo para copiar/pegar)

El contenido real vive en `td/fluir_callbacks.dat`; este bloque es un espejo del
mismo (docstring + handlers). Ver §4 y §8 para crear las tablas que consume.

```python
"""
fluir_callbacks.dat — Callbacks del receptor de retorno del "Fluir" (OSC 9002).

El cerebro Python (scripts/puente_td.py modo 'fluir') envía por el puerto
9002 un contrato POR TIPO, en este orden exacto:

    /flujos/fluir/resumen <total> <loop_secs> <image> <video> <audio> <text>
    /flujos/fluir/filtro <clave> <valor>  (0..N, filtros del usuario → fluir_estado)
    Por tipo (image, video, audio, text; SOLO si tiene medios):
        /flujos/fluir/tabla  <tipo> <cantidad>
        /flujos/fluir/medio  <media_id> <ruta> <keypoint> <hora> <tipo>  (x cantidad)
    /flujos/fluir/chiche <hora> <texto>   (0..N)
    /flujos/fluir/fin   <total>

keypoint = t_loop: posición del medio dentro del loop (segundos en [0, loop_secs)).
El OSC ya trae todo; el spec JSON solo se lee para cotejar (debug de pérdida UDP).
"""

_ROOT = op("/project2")
PREFIJO_LOG = "[fluir_callbacks]"
OSC_ADDR_FLUIR = "/flujos/fluir"

# Nombre de tabla destino por tipo de medio.
TABLAS_POR_TIPO = {
    "image": "fluir_fotos",
    "video": "fluir_videos",
    "audio": "fluir_sonidos",
    "text": "fluir_textos",
}
HEADER_MEDIO = ["media_id", "ruta", "keypoint", "hora", "tipo"]

_tipo_actual = None
_total_esperado = 0

def onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer):
    """Entry point del callbacks interno del OSC In DAT (firma fija de TD)."""
    try:
        _enrutar(address, list(args))
    except Exception as e:
        print(f"{PREFIJO_LOG} Error en {address}: {e}")

def _enrutar(address, args):
    """Despacha por address absoluto. Los seis mensajes del 'Fluir' son fijos."""
    if address == OSC_ADDR_FLUIR + "/resumen":
        _recibir_resumen(args)
    elif address == OSC_ADDR_FLUIR + "/filtro":
        _recibir_filtro(args)
    elif address == OSC_ADDR_FLUIR + "/tabla":
        _recibir_tabla(args)
    elif address == OSC_ADDR_FLUIR + "/medio":
        _recibir_medio(args)
    elif address == OSC_ADDR_FLUIR + "/chiche":
        _recibir_chiche(args)
    elif address == OSC_ADDR_FLUIR + "/fin":
        _recibir_fin(args)
    else:
        print(f"{PREFIJO_LOG} Dirección desconocida: {address} {args}")

def _tabla(nombre):
    """Devuelve una tabla del proyecto o imprime advertencia si no existe."""
    t = _ROOT.op(nombre)
    if t is None:
        print(f"{PREFIJO_LOG} Falta la tabla '{nombre}' (ver checklist)")
    return t

def _tabla_para_tipo(tipo):
    """Devuelve el nombre de tabla para un tipo (image->fluir_fotos, ...)."""
    nombre = TABLAS_POR_TIPO.get(tipo)
    if nombre is None:
        print(f"{PREFIJO_LOG} Tipo desconocido: '{tipo}'")
    return nombre

def _filas_datos(tabla):
    """Cantidad de filas de datos (descuenta la fila 0 header)."""
    return max(0, tabla.numRows - 1)

def _limpiar(tabla, header):
    """Vacía una tabla y escribe su fila 0 (header)."""
    tabla.clear()
    tabla.appendRow(list(header))

def _recibir_resumen(args):
    """Resumen: total, loop_secs y conteos por tipo; reinicia tablas."""
    global _total_esperado, _tipo_actual
    tabla = _tabla("fluir_estado")
    if tabla is None:
        return
    total = int(args[0]) if len(args) > 0 and args[0] is not None else 0
    loop_secs = float(args[1]) if len(args) > 1 and args[1] is not None else 300.0
    n_image = int(args[2]) if len(args) > 2 and args[2] is not None else 0
    n_video = int(args[3]) if len(args) > 3 and args[3] is not None else 0
    n_audio = int(args[4]) if len(args) > 4 and args[4] is not None else 0
    n_text = int(args[5]) if len(args) > 5 and args[5] is not None else 0
    _total_esperado = total
    _tipo_actual = None
    _limpiar(tabla, ["clave", "valor"])
    tabla.appendRow(["total", total])
    tabla.appendRow(["loop_secs", loop_secs])
    tabla.appendRow(["image", n_image])
    tabla.appendRow(["video", n_video])
    tabla.appendRow(["audio", n_audio])
    tabla.appendRow(["text", n_text])
    tabla.appendRow(["fin", 0])
    for nombre in TABLAS_POR_TIPO.values():
        t = _tabla(nombre)
        if t is not None:
            _limpiar(t, HEADER_MEDIO)
    t_chiches = _tabla("fluir_chiches")
    if t_chiches is not None:
        _limpiar(t_chiches, ["hora", "texto"])
    print(f"{PREFIJO_LOG} Resumen: {total} medios (image={n_image}, "
          f"video={n_video}, audio={n_audio}, text={n_text}), "
          f"loop de {loop_secs}s")

def _recibir_filtro(args):
    """Filtro del usuario → fila [clave, valor] en fluir_estado."""
    if len(args) < 2:
        print(f"{PREFIJO_LOG} Mensaje 'filtro' incompleto: {args}")
        return
    clave = str(args[0] or "").strip()
    valor = str(args[1] or "")
    if not clave:
        print(f"{PREFIJO_LOG} 'filtro' sin clave, ignorado: {args}")
        return
    tabla = _tabla("fluir_estado")
    if tabla is None:
        return
    _escribir_estado(tabla, clave, valor)
    print(f"{PREFIJO_LOG} Filtro: {clave} = {valor}")

def _recibir_tabla(args):
    """Anuncio del comienzo de una tabla por tipo."""
    global _tipo_actual
    tipo = str(args[0]) if len(args) > 0 and args[0] is not None else ""
    cantidad = int(args[1]) if len(args) > 1 and args[1] is not None else 0
    _tipo_actual = tipo
    nombre = _tabla_para_tipo(tipo)
    if nombre is not None:
        t = _tabla(nombre)
        if t is not None:
            _limpiar(t, HEADER_MEDIO)
    print(f"{PREFIJO_LOG} Tabla {tipo}: {cantidad} medios esperados")

def _recibir_medio(args):
    """Acumula un medio en la tabla de su tipo (una fila por medio)."""
    if len(args) < 5:
        print(f"{PREFIJO_LOG} Mensaje 'medio' incompleto: {args}")
        return
    media_id = int(str(args[0])) if args[0] is not None else 0
    ruta = str(args[1] or "").replace("\\", "/")  # normaliza separadores para TD
    keypoint = float(args[2]) if args[2] is not None else 0.0
    hora = float(args[3]) if args[3] is not None else 0.0
    tipo = str(args[4]) if args[4] is not None else _tipo_actual
    nombre = _tabla_para_tipo(tipo)
    if nombre is None:
        return
    tabla = _tabla(nombre)
    if tabla is None:
        return
    if tabla.numRows == 0:
        tabla.appendRow(list(HEADER_MEDIO))
    tabla.appendRow([media_id, ruta, keypoint, hora, tipo])

def _recibir_chiche(args):
    """Acumula un chiche ambiental (clima/astronomía) en fluir_chiches."""
    if len(args) < 2:
        print(f"{PREFIJO_LOG} Mensaje 'chiche' incompleto: {args}")
        return
    hora = float(args[0]) if args[0] is not None else 0.0
    texto = str(args[1] or "")
    tabla = _tabla("fluir_chiches")
    if tabla is None:
        return
    if tabla.numRows == 0:
        tabla.appendRow(["hora", "texto"])
    tabla.appendRow([hora, texto])

def _recibir_fin(args):
    """Finaliza el lote: marca fin=1 y valida recibidos vs esperados."""
    global _tipo_actual
    tabla_estado = _tabla("fluir_estado")
    if tabla_estado is None:
        return
    esperado = int(args[0]) if args else _total_esperado
    recibido = 0
    for nombre in TABLAS_POR_TIPO.values():
        t = _tabla(nombre)
        if t is not None:
            recibido += _filas_datos(t)
    if esperado >= 0 and esperado != recibido:
        print(f"{PREFIJO_LOG} ¡Ojo! fin dice {esperado} medios, recibí {recibido} "
              "(posible pérdida de paquetes OSC)")
    _escribir_estado(tabla_estado, "fin", 1)
    _escribir_estado(tabla_estado, "recibidos", recibido)
    _escribir_estado(tabla_estado, "esperados", esperado)
    _tipo_actual = None
    print(f"{PREFIJO_LOG} Fin de lote: {recibido} medios cargados "
          f"(esperados {esperado}).")
    _cotejar_spec(recibido)

def _escribir_estado(tabla, clave, valor):
    """Agrega o actualiza una fila [clave, valor] en fluir_estado."""
    for r in range(1, tabla.numRows):
        fila = tabla.row(r)
        if fila and str(fila[0]).lower() == clave:
            tabla.setCell(r, 1, valor)
            return
    tabla.appendRow([clave, valor])

def _cotejar_spec(recibido):
    """Lee td/spec_fluir.json y coteja totales por tipo (solo debug)."""
    import json as _json
    try:
        ruta = "{}/spec_fluir.json".format(project.folder)
        with open(ruta, "r", encoding="utf-8") as f:
            spec = _json.load(f)
    except Exception as e:
        print(f"{PREFIJO_LOG} Error al leer el spec JSON: {e}")
        return None
    resumen = spec.get("resumen") or {}
    total_spec = resumen.get("total", len(spec.get("medios", [])))
    if total_spec != recibido:
        print(f"{PREFIJO_LOG} Cotejo: spec dice {total_spec} medios, recibí {recibido}")
    por_tipo = spec.get("por_tipo") or {}
    for tipo, nombre in TABLAS_POR_TIPO.items():
        esperados_tipo = len(por_tipo.get(tipo, []))
        t = _tabla(nombre)
        recibidos_tipo = _filas_datos(t) if t is not None else 0
        if esperados_tipo != recibidos_tipo:
            print(f"{PREFIJO_LOG} Cotejo {tipo}: spec dice {esperados_tipo}, "
                  f"recibí {recibidos_tipo}")
    print(f"{PREFIJO_LOG} Spec leído: {total_spec} medios, "
          f"{len(spec.get('chiches', []))} chiches")
    return spec
```

> **Nota**: este bloque es un espejo del archivo `td/fluir_callbacks.dat` del
> repo (fuente de verdad). El `.dat` en disco es el que se adjunta con
> File+Sync (tarea A); la guía lo replica para que el armado manual tenga el
> código a mano sin abrir el repo.

---

## 4. Paso 3 — Crear las tablas de datos de consumo

**Objetivo**: disponer de estructuras planas que el motor visual lea sin
parsear código dentro de los operadores de renderizado.

**Instrucción** (Table DAT, en la raíz de `/project2`):

| Op | Tipo | Columnas / uso |
|---|---|---|
| `fluir_estado` | Table DAT | pares clave-valor → filas `total`, `loop_secs`, `image`, `video`, `audio`, `text`, `fin` (0/1), `recibidos`, `esperados` + **filtros del usuario** (`hora_inicio`, `hora_fin`, `horas_elegidas`, `municipios`, `colores`, `tags`, `dias`, `clima` si vienen) |
| `fluir_fotos` | Table DAT | `media_id`, `ruta`, `keypoint`, `hora`, `tipo` — medios `image` desde OSC |
| `fluir_videos` | Table DAT | `media_id`, `ruta`, `keypoint`, `hora`, `tipo` — medios `video` desde OSC |
| `fluir_sonidos` | Table DAT | `media_id`, `ruta`, `keypoint`, `hora`, `tipo` — medios `audio` desde OSC |
| `fluir_textos` | Table DAT | `media_id`, `ruta`, `keypoint`, `hora`, `tipo` — medios `text` desde OSC |
| `fluir_chiches` | Table DAT | `hora`, `texto` — eventos ambientales desde OSC |

**Por qué**: las 4 tablas por tipo comparten estructura y el callbacks las
llena con un único helper `_tabla_para_tipo()`. Separar por tipo deja que el
motor lea solo la clase que le toca reproducir (fotos → TOP + Text, videos →
Movie, sonidos → Audio/Text, textos → Text), sin recorrer una lista mixta.

---

## 5. Alternativa (rápida): consumir solo el OSC, sin esperar el JSON

**Objetivo**: primera iteración funcional: con el wire solo (sin parsear
`spec_fluir.json`) ya se puede posicionar todo.

**Instrucción**: usar `fluir_fotos` / `fluir_videos` / `fluir_sonidos` /
`fluir_textos` llena por `/medio` (cada fila trae `keypoint` y `hora`) +
`fin` de `fluir_estado`.

- **Ventaja**: no necesita el archivo; funciona aunque el JSON tarde en salir;
  es lo más rápido de armar y ya respeta el "cuándo" de cada medio (`keypoint`).
- **Limitación**: para reproducir un `image` sin romper el instante hace falta
  decidir una duración efectiva (ver Decisiones abiertas nº 3).

**Por qué**: con el contrato por tipos, el wire es autosuficiente para
posicionar; el JSON queda como fuente de enriquecimiento (color, tags, desc)
para etapas visuales posteriores.

---

## 6. Opciones de reproducción coherentes con el motor de loop existente

Según `docs/motor_loop.md` (§3 y §6), el spec define un reloj de **loop de
`loop_secs`** con cada medio ubicado en un `keypoint` (= `t_loop`) dentro de
`[0, loop_secs)`. La reproducción usa:

### a) Reloj de loop

- **Op que se necesita**: `fluir_loop` — un **Timeline CHOP** (o `Clock CHOP`)
  en loop de `0..loop_secs`. Tomar `loop_secs` de `fluir_estado` (fila
  `loop_secs`), nunca asumir 300 fijo.
- **Por qué**: el motor Python ya calculó dónde cae cada medio; si TD ignora el
  `keypoint` y reproduce linealmente, la instalación pierde la idea de
  "recorrer Buenos Aires → Tucumán en el tiempo de los metadatos".

### b) Cursor de medio activo

- Opción: `fluir_engine` — un **Script DAT / Execute DAT** que cada frame
  calcula `t = fluir_loop[0] % loop_secs` y, con **las tablas por tipo**
  (`fluir_fotos`, `fluir_videos`, `fluir_sonidos`, `fluir_textos`), decide qué
  medio está activo:
  - tipo `image`: mostrar si `t ∈ [keypoint, keypoint + duracion_efectiva]`
    (la spec da `duracion = 0` en imágenes → **decisión de diseño**: duración
    mínima de tarjeta, p. ej. `max(3s, porción del segmento)` — ver Decisiones
    abiertas nº 3).
  - tipo `video`: reproducir con su duración real (si entra en la porción del
    segmento) o recortar un fragmento (§3.3 del motor).
- Conexión concreta: `fluir_movie` (Movie File In TOP) recibe el archivo desde
  el Script (`movie.par.file = ruta; movie.par.play = 1`).

**Por qué**: `keypoint` ya está **definido** (= `t_loop`): no hace falta
parsear el spec para posicionar; la tabla del tipo correcto da la ruta y el
instante.

### c) Chiches (eventos ambientales)

- Con `fluir_chiches` (`hora` → `texto`), el `fluir_engine` detecta el cruce y
  dispara un pulso (p. ej. un `LumaBlur`/`Level` destello o un Text overlay).
  Coincide con la definición de "eventos ambientales" del motor (§5).

### d) No pisar nombres legacy

- Nada de esto ocupa los nombres `movie1`, `tabla_colores`, `color_actual`,
  `info_imagen`, `seleccion_actual` (ver §7). El reproductor del Fluir debe
  llamarse **`fluir_movie`**, NO `movie1`.

Esta sección es de alto nivel adrede: fija el contrato de datos (dónde vive
cada dato que el motor necesita); el armado fino del render queda para la etapa
de pipeline visual, pero los nombres y tablas quedan disponibles.

---

## 7. Integración sin romper (reglas duras)

1. **`osc_in2` es 100% independiente de `osc_in1`/9000**:
   - No comparte callbacks DAT (`osc_in2_callbacks` vs `osc_in1_callbacks` están
     separados), ni tablas (`fluir_*` vs `elec_*`), ni sockets.
   - No se mueve ni se renombra nada de `osc_in1`/`osc_out1`/`elec_*`/`boton_*`.
2. **No recrear el pipeline legacy bajo nombres existentes**: no crear
   `movie1`, `tabla_colores`, `color_actual`, `info_imagen`, `seleccion_actual`
   para este canal. El reproductor del Fluir se llama `fluir_movie`.
3. **El `panelexec1` de los botones de elección no se toca** (sigue mandando la
   ráfaga del "Fluir" por 9001). El retorno 9002 es una adición, no un cambio.

---

## 8. Checklist de armado (ops a crear a mano, con nombres concretos)

- [ ] **`osc_in2`** — OSC In DAT en `/project2`, página `Network` → `Port = 9002`.
- [ ] **`osc_in2_callbacks`** — DAT interno de `osc_in2`; **File** =
      `td/fluir_callbacks.dat`, **Sync to File = ON**.
- [ ] **`fluir_callbacks.dat`** — archivo en `td/`, con el contenido de §3.2 (nuevo por tipos).
- [ ] **`fluir_estado`** — Table DAT (clave-valor: total, loop_secs, image, video,
      audio, text, fin, recibidos, esperados + filtros del usuario: hora_inicio,
      hora_fin, horas_elegidas, municipios, colores, tags, dias, clima si vienen).
- [ ] **`fluir_fotos`** — Table DAT (media_id, ruta, keypoint, hora, tipo).
- [ ] **`fluir_videos`** — Table DAT (media_id, ruta, keypoint, hora, tipo).
- [ ] **`fluir_sonidos`** — Table DAT (media_id, ruta, keypoint, hora, tipo).
- [ ] **`fluir_textos`** — Table DAT (media_id, ruta, keypoint, hora, tipo).
- [ ] **`fluir_chiches`** — Table DAT (hora, texto).
- [ ] (Opcional, etapa visual) **`fluir_loop`** Timeline CHOP; **`fluir_movie`**
      Movie File In TOP; **`fluir_engine`** Script DAT con el planificador (scheduler).
- [ ] Verificación de punta a punta (3 terminales):
      `python scripts/puente_td.py fluir --una-vez`, un terminal con
      `python scripts/osc_probe.py 9002 5`, y en TD chequear que
      `fluir_fotos/fluir_videos/fluir_sonidos/fluir_textos` se llenan y
      `fluir_estado.fin = 1` al terminar (y `recibidos` == `esperados`).

---

## 9. Decisiones (algunas cerradas con el rediseño por tipos)

| # | Decisión | Estado | Motivo |
|---|---|---|---|
| 1 | Nombre del receptor del retorno | **Resuelta** — `osc_in2` + `osc_in2_callbacks` | Convención real `osc_i<N>`; no renombrar. |
| 2 | Typo del address (`/flojos`, `/fljujos`) | **Resuelta** | la real es `/flujos/fluir` (ver `osc_probe.py 9002`, `puente_td.py::OSC_ADDR_FLUIR`) |
| 3 | Duración efectiva de imágenes (`duracion=0`) | **Abierta** (recomendación: `max(3s, porción del segmento)`) | `keypoint` ya define el INICIO, pero no la permanencia en imagen |
| 4 | ¿`fin` dispara el render o solo coteja? | **Resuelta** | `fin` marca `fin=1`, guarda `recibidos/esperados` y coteja el JSON (ya no es fuente única) |
| 5 | Debug de pérdida UDP | **Resuelta** | `fluir_estado` guarda `recibidos/esperados` |
| 6 | `loop_secs` configurable | **Resuelta** | leer de `fluir_estado`, nunca fijo 300 |
| 7 | Tabla de audio: `fluir_sonidos` vs `fluir_audios` | **Resuelta** → `fluir_sonidos` | consistente con español del proyecto (un docstring de `puente_td.py` dice `audios`, pero la decisión es `sonidos`) |
| 8 | Significado de `keypoint` | **Resuelta** | `keypoint` = `t_loop`: posición en segundos dentro del loop (0..loop_secs) — se usa tal cual del wire |
| 9 | El estado refleja el filtro del usuario | **Resuelta** | `spec["resumen"]["filtros"]` + mensaje `/flujos/fluir/filtro <clave> <valor>` → filas en `fluir_estado` (hora_inicio, hora_fin, horas_elegidas, municipios, colores, tags, dias, clima). Así TD muestra qué eligió el visitante, no solo totales |

---

## 10. Referencias cruzadas

- `docs/lecciones_elecciones_td.md` — Lección 1 (File+Sync), Lección 3/4/5
  (clases globales, Panel Execute, Textport vs Script DAT).
- `docs/motor_loop.md` — §3 (segmentos/posicionamiento), §5 (chiches),
  §6 (salida JSON del spec).
- `docs/arquitectura_motor.md` — Enfoque B (híbrido: TD = músculo audiovisual).
- `scripts/puente_td.py` — `_procesar_rafaga`: orden por tipo + `OSC_ADDR_FLUIR`.
- `td/osc_callbacks.dat` — modelo de routing (`_ROOT`, `onReceiveOSC`,
  `_enrutar`, prefijo de logs).
- `td/opfind1.tsv` — mapa real de ops del toe: no existen (aún) `osc_in2` ni
  tablas `fluir_*`; se crean con esta guía.