# Lecciones: Elecciones en TD 2025.32820 (nubes de metadatos seleccionables)

Documento de debugging de la integración Python ⇄ TouchDesigner para las nubes de
elecciones (metadatos seleccionables: horas, municipios, colores, tags...).

**Fecha**: 2026-08-05 · **TD**: 2025.32820 · **Objetivo**: que un clic en un botón
de la nube envíe `/flujos/seleccion <grupo> <valor> 1|0` por OSC a Python.

> ⚠️ Este documento existe para **no repetir** los pasos que siguen. Todo lo que
> está aquí se verificó empíricamente en esta sesión; no es teoría.

---

## Arquitectura del flujo (diseño)

```
Python (elecciones.py) ──9000──► osc_in1 (OSC In DAT) → osc_callbacks.dat → tablas elec_*
                                                                               │
                                              elecciones_ui.dat lee elec_* ──► botones (Button COMP)
                                                                               │
                          visitante hace clic en un botón                      │
                                                                               ▼
                        osc_out1 (OSC Out DAT) ──9001──► Python  (/flujos/seleccion)
```

## El problema original

Al correr `python scripts/elecciones.py`:
1. El `osc_in` se poblaba (recibía los mensajes crudos) ✅
2. Las tablas `elec_*` **no recibían nada** ❌
3. Y más tarde: la UI se generaba pero **no se veían los botones** en el container ❌

---

## Lección 1 — Un OSC In DAT *solo* muestra mensajes crudos

**Síntoma**: "el osc_in se popula pero las tablas no reciben datos".

**Causa**: un `osc_in` suelto creado a mano muestra los mensajes OSC en su propia
tabla, pero **no enruta a ningún lado**. El enrutamiento a las tablas `elec_*` vive
en `osc_callbacks.dat`, que **debe adjuntarse al DAT interno de callbacks del OSC In**:

1. Doble clic sobre el `osc_in` (OSC In DAT) → se abre y muestra el DAT interno
2. Seleccionar el DAT interno (normalmente `osc_in1_callbacks`)
3. Parámetros: **File** = `td/osc_callbacks.dat`, **Sync to File** = **ON**

**Regla**: los `.dat` del proyecto se adjuntan SIEMPRE al **DAT interno de callbacks**
del operador (Script DAT → su callbacks interno; OSC In → su callbacks interno), igual
que `elecciones_ui.dat` se adjunta a `elecciones_ui_callbacks`.

---

## Lección 2 — `osc_out1` no se llena con los datos de entrada (por diseño)

**Malentendido**: esperar que al correr `elecciones.py` "aparezca algo en el osc_out".

**Realidad**: `osc_out1` es la **salida** de TD hacia Python. Solo se activa cuando
TD **envía** algo (el clic en un botón). Los datos de entrada (elecciones) llegan por
`osc_in1`/9000 y van a las tablas; **nunca pasan por el osc_out**. Cada lado es de
una sola dirección:

```
Python ─9000─► osc_in1 → tablas elec_* → UI
   clic en la UI ──────────────────────────────► osc_out1 ─9001─► Python
```

---

## Lección 3 — En TD 2025.32820 `create()` NO acepta strings de tipo

**Síntoma**: `op('/project2').create("chopexec", ...)` →
`td.tdError: Unknown operator type. Value:'chopexec' Type:<class 'str'>`

**Realidad verificada**: los strings lower-case **no se resuelven** como tipo de
operador en esta build. Los tipos se pasan como **clases globales** inyectadas en el
namespace del **Script/Callback DAT** (NO del Textport).

**Qué funciona** (verificado porque la UI ya se genera):
- `_ROOT.create(containerCOMP, "elecciones_container")` ✅
- `_ROOT.create(panelCHOP, ...)` ✅
- `cont.create(buttonCOMP, ...)` ✅

**Qué NO funciona**:
- `create("chopexec", ...)` / `create("chopexecDAT", ...)` → Unknown operator type
- `create(chopexec, ...)` → `NameError: name 'chopexec' is not defined`

**Conclusión**: usar la clase global directa (`panelexecuteDAT`, `containerCOMP`, ...),
nunca strings.

---

## Lección 4 — En TD 2025.32820 `chopexec` (CHOP Execute DAT) ya no existe

**Síntoma**: el viejo patrón `Panel CHOP → CHOP Execute DAT` (onOffToOn del channel)
fallaba al crear el execute.

**Realidad**: en esta versión **no hay clase global con "exec"** en el namespace
(verificado: `globals()` dentro del Script DAT con filtro exec/panel/chop/opx solo
devuelve las funciones del propio script; `TOTAL clases type: 0` al inspeccionar
`globals()` — aunque `containerCOMP` etc. SÍ funcionan como identificadores, no
aparecen al iterar globals(), porque TD las inyecta por otro mecanismo).

**El patrón correcto y moderno** (confirmado con la doc oficial de Derivative):
**Panel Execute DAT** (`panelexecuteDAT`) para detectar toggles de Button COMPs:

- Parámetro `Panels` → el container (`/project2/elecciones_container`)
- Parámetro `Panel Value` → `state` (estado on/off del botón)
- Toggles: `Off to On` = ON, `On to Off` = ON, `Value Change` = OFF
- Callbacks:
  ```python
  def onOffToOn(panelValue):
      # panelValue.owner = el Button COMP tocado
      btn = panelValue.owner
      grupo = btn.fetch('grupo')
      valor = btn.fetch('valor')
      op('osc_out1').sendOSC('/flujos/seleccion', [grupo, valor, 1])

  def onOnToOff(panelValue):
      ... # igual pero con 0
  ```

**Nota**: el "DAT Execute DAT" que aparece en el menú es otro operador — monitorea
**DATs** (tablas), no paneles. Por eso al intentar conectarle el Panel CHOP abría el
"OP Create Dialog" (quería un conversor en el medio): el tipo de entrada no coincidía.

---

## Lección 5 — El Textport NO tiene las clases de tipos; los Script DATs sí

**Síntoma**: `[n for n in dir() if 'exec' in n.lower()]` → `[]` en el Textport.
`create(chopexec, ...)` → NameError.

**Causa**: el Textport no autocarga las clases de operador; están solo en el contexto
de ejecución de un Script/Callback DAT. Además, `exec(open(...).read())` crea un frame
nuevo donde `globals()` tampoco las ve.

**Cómo verificar tipos reales**: correr dentro de un **Text DAT con Run Script**
(no en el Textport, no con exec()), o directamente probando `_ROOT.create(Clase, ...)`
en el propio script.

---

## Lección 6 — El container no muestra los botones (aún por resolver)

**Síntoma**: `UI generada para 4 grupo(s)` pero el container no se ve / no se ven
los botones.

**Realidad (del docstring del propio `elecciones_ui.dat`)**: los Button COMPs son
Panel COMPs — para VERLOS e interactuar hace falta UNA de estas dos cosas:

1. **`elecciones_render`** (Top Render COMP) apuntando al container, conectado a una
   salida (Null → Out → pantalla); o
2. Abrir el **Node Viewer de tipo "Control Panel"** sobre
   `/project2/elecciones_container` (RMB → View → Control Panel).

Sin eso, los botones existen en la red pero nadie los compone a una textura ni los
interactúa. **Pendiente de resolver en la próxima sesión.**

---

## Lo que sí salió bien (vale la pena repetirlo)

No todo fue fricción — hay patrones que **funcionaron a la primera** y conviene
conservar:

### 1. La generación de la UI por clase global funciona de punta a punta
Aunque `create()` con strings falló (Lección 3), **la UI completa se generó OK**:
`UI generada para 4 grupo(s)` — es decir, `containerCOMP`, `buttonCOMP` y `panelCHOP`
como identificadores globales crean los grupos y botones correctamente. Ese es el
patrón a seguir: **clase global directa, nunca string**.

### 2. El pipeline OSC `Python → TD` ya llegaba
`elecciones.py` (9000) sí recibía el `osc_in` y poblaba la tabla del OSC In DAT.
El enlace que faltaba era solo el **callbacks DAT** (Lección 1). El transporte OSC
base estaba sano.

### 3. La arquitectura de callbacks externos ya estaba probada en el proyecto
El patrón **File + Sync to File = ON** sobre el DAT interno ya se usaba con
`osc_callbacks.dat`. La solución de la Lección 1 reusa ese
mecanismo conocido en vez de inventar otro. (Nota 2026: `nube_generar.dat`,
la nube estática de Text TOPs, se eliminó por obsoleta — quedó solo
`elecciones_ui.dat` como generador de nubes clicables.)

### 4. La verificación de sintaxis con `ast` atrapó errores antes de TD
Correr el `.dat` por `ast.parse()` (Python) después de cada edición detectó
errores de sintaxis sin tener que recargar TD — barato y rápido, sin tocar la DB.

### 5. El probe en `Temp/opencode` permitió diagnosticar sin riesgo
El script de sondeo (`probe_exec_td.py`) se ejecutó desde el directorio temporal
pre-aprobado, no dentro del proyecto — diagnóstico empírico (qué clases existen en
globals) sin ensuciar el repo.

### 6. La doc del proyecto apuntaba en la dirección correcta
El docstring de `elecciones_ui.dat` ya advertía la condición para ver los botones
(render o Control Panel — Lección 6) y el flujo OSC de una sola dirección. Leer la
doc existente primero ahorró tiempo de investigación.

### 7. Decisiones de diseño correctas que no hay que tocar
- **Modelo de datos en tablas `elec_*`** (texto + frecuencia/peso) — la fuente
  de datos que alimenta la UI de botones (`elecciones_ui`, no el `nube_generar`
  eliminado).
- **Separación `osc_in` (entrada) / `osc_out` (salida)** — cada dirección con su
  puerto y su operador; evita acoplarlos (Lección 2).
- **Idioma español + convenciones del proyecto** en el script TD (docstrings,
  nombres de funciones `_snake_case`) — el `.dat` es mantenible y consistente con
  el resto del repo.

---

## Estado actual del código (2026-08-05)

`td/elecciones_ui.dat` ya incluye:
- `_clase_global(fragmentos)` — helper para resolver clases globales por fragmento
- `_asegurar_exec(cont)` — migrado a **Panel Execute DAT** (`panelexecuteDAT`):
  configura `panels`, `panelvalue=state`, `offtoon`/`ontooff`; si no puede crearlo,
  imprime instrucciones para crearlo a mano UNA vez
- `_escribir_callbacks_exec` — firma Panel Execute (`onOffToOn(panelValue)`,
  identifica botón por `panelValue.owner` + filtro `w_`)
- `_asegurar_render` — usa clase global (`["tprender", "toprender"]`) en vez de strings
- `crear_ui()` — llama `_asegurar_exec(cont)` (container, no Panel CHOP)

## ⚠️ Mapa REAL verificado (2026-08-08, export OP Find en `td/opfind1.tsv`)

El toe actual **ya no coincide con el diseño que generaba `elecciones_ui.dat`**
(grupos `ui_<id>` + `w_<grupo>_###` + `elecciones_panelchop`). Hoy la UI de
elecciones está armada con **Replicator COMPs**:

```
/project2/
├── osc_in1 (OSC In DAT 9000) + osc_in1_callbacks  → osc_callbacks.dat
├── osc_out1 (OSC Out DAT → 127.0.0.1:9001)        # TD → Python
├── elec_horas | elec_tags | elec_colores | elec_municipios   (Table DAT, datos)
├── boton_horas_0 / boton_tags_0 / boton_colores_0 / boton_municipios_0  (Button COMP "semilla")
└── elec_horas_container / elec_tags_container3 / elec_colores_container2 / elec_municipios_container1
    └── replicator1 (Replicator COMP) + replicator1_callbacks
        └── boton_<grupo>_N ... (Button COMP, uno por fila de la tabla)
            ├── par1        (Parameter CHOP)
            ├── text        (Text COMP → etiqueta)
            ├── parexec1    (Parameter Execute DAT)
            └── panelexec1  (Panel Execute DAT → envía `/flujos/seleccion/<grupo> <valor>`)
```

**Implicancias**:
- Los botones **existen** (80 Button COMPs, cada uno con sus hijos fijos). La
  Lección 6 (no se veían) quedó resuelta en esta arquitectura: el replicador
  posiciona cada botón en el container y el Panel Execute va **por botón**
  (`panelexec1`), no un exec global del container.
- El **pipeline visual** (movie1 / render / salida) todavía **no está armado** en
  el toe: `osc_callbacks.dat` conserva handlers para `tabla_colores`,
  `color_actual`, `movie1`, `info_imagen` y `seleccion_actual` apuntando a ops a
  recrear — ninguna de esas ops existe por ahora.
- `elecciones_ui.dat` sigue siendo el generador **legacy**: no genera réplicas. Para
  agregar un grupo con la arquitectura actual: Table DAT `elec_<id>` + container
  `elec_<id>_container<N>` + Replicator apuntando a la "semilla" `boton_<id>_0`.

## Checklist de setup en TD (desde cero, versión replicator)

- [ ] `/project1` renombrado a `/project2` (coincide con `_ROOT` en los .dat)
- [ ] `osc_in` (OSC In DAT, puerto 9000) → callbacks interno → File `osc_callbacks.dat`, sync ON
- [ ] `osc_out` (OSC Out DAT, `127.0.0.1:9001`)
- [ ] Tablas `elec_horas`, `elec_municipios`, `elec_colores`, `elec_tags`, ...
- [ ] Por grupo: `elec_<id>_container<N>` + `replicator1` + semilla `boton_<id>_0`
- [ ] `opview1` (OP Viewer) → container del grupo o render COMP para ver/interactuar

## Para la próxima sesión (orden sugerido)

1. **Confirmar la existencia del render**: los botones existen (OP Find), falta
   componerlos (Viewer/Render TOP) para el pipeline de salida
2. **Validar el clic → OSC**: clickear un botón y confirmar que Python recibe
   `/flujos/seleccion` (o que al menos el Textport muestra el send)
3. Si se necesita un generador automático de grupos, **reescribir
   `elecciones_ui.dat`** al patrón replicator (hoy genera `ui_<id>` +
   `elecciones_panelchop`, que no coincide con el toe)
4. Actualizar `AGENTS.md` (docs/scripts TD) y `CHANGELOG.md` cuando cierre

---

## Decisiones de diseño (2026-08-08)

### 1. `elecciones_ui.dat` vs armado manual — diferido

Dos opciones posibles para construir la UI de elecciones:

- **A)** Actualizar `elecciones_ui.dat` para que genere lo mismo que se armó a
  mano (Replicator COMP + `elec_<id>_container<N>` + `boton_<id>_N` + hijos
  `par1`/`text`/`parexec1`/`panelexec1`).
- **B)** Seguir armando los grupos manualmente en TD.

**Decisión actual: B (manual)**. Es más rápido iterar; la opción A queda en
ROADMAP (Etapa 5) como refactor diferido para "algún momento" en que convenga
reproducir el patrón automáticamente.

### 2. Comportamiento de los botones: toggle-OSC → "Fluir" (2026-08-08)

**Estado actual (2026-08-08)**: cada botón manda su propio mensaje OSC al
tocarse (`/flujos/seleccion/<grupo> <valor>` — grupo en la dirección, un solo
valor por mensaje).

**El concepto clave — "Fluir" (decidido 2026-08-08)**: al igual que en la
visualización web (`web3/`, botón `#btn-fluir`), al visitante se le pide que
**seleccione** (acumule) y luego presione el botón **"Fluir"**. Ese disparo
envía **todas las elecciones juntas** — con `osc_probe.py` sobre 9001 se
verificó la ráfaga de una selección completa (8 mensajes: 2 tags, 2 colores,
2 municipios, 2 horas; uno por elección):

```
[OSC] /flujos/seleccion/tags       ('macarona',)
[OSC] /flujos/seleccion/tags       ('obra',)
[OSC] /flujos/seleccion/colores    ('rosa',)
[OSC] /flujos/seleccion/colores    ('verde',)
[OSC] /flujos/seleccion/municipios ('Luján',)
[OSC] /flujos/seleccion/municipios ('Carmen de Areco',)
[OSC] /flujos/seleccion/horas      ('13:00',)
[OSC] /flujos/seleccion/horas      ('06:00',)
```

**Diseño deseado (futuro)**: ese mismo disparo "Fluir" debería acumular en TD
(los toggles NO salen por OSC uno por uno) y enviar **un mensaje grande único**
con todas las elecciones; Python responde con la serie de medios/metadatos
derivados de ese mensaje (alimenta `loop_db.py` → spec JSON).

Implicancias del diseño futuro:
- El `panelexec1` de cada botón dejaría de enviar OSC por toggle y pasaría a
  **marcar un estado local** (ej. fila activa en un Table DAT o flags en un CHOP).
- El botón **"Fluir"** (análogo al de la web) es el disparador de finalización:
  arma el payload acumulado y lo envía por `osc_out1` — ya sea como ráfaga
  actual o como mensaje agregado (formato a definir, p.ej. lista plana o JSON).
- En Python, el receptor del puente deja de esperar toggles individuales y
  procesa **la selección completa** que alimenta el filtrado/loop
  (`loop_db.py` → spec JSON ya soporta horas/municipios/colores/tags).
- No confundir con la entrada: `/flujos/elecciones/<id>` sigue siendo Python→TD
  para poblar las tablas; el cambio es solo en la dirección TD→Python
  (las elecciones acumuladas se envían al "Fluir").

> Pendiente de definir: formato del payload agregado (ráfaga vs un mensaje único)
> y si el disparador es el botón "Fluir" visible en la UI de TD. Ver ROADMAP
> (Etapa 5, "Multiselector OSC" → "Fluir").
