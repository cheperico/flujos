# Arquitectura del Motor de Instalación

## Contexto

La instalación necesita:

- Reproducir videos 360° en 4 pantallas
- Consultar una base de datos SQLite en tiempo real (filtros por color, keyword, autor, GPS, tiempo)
- Sincronizar una línea de tiempo con velocidad variable
- Detectar picos de ruido (grito) como input para la deriva
- Mostrar keypoints textuales (transcripción) superpuestos o combinados con otros medios
- Navegar por deriva: lógica no determinista que decide qué mostrar según filtros y condiciones externas

Tres tecnologías candidatas evaluadas: TouchDesigner, OpenFrameworks y OpenRndr.

Tras analizar fortalezas y debilidades, surgen **dos enfoques viables**.

---

## Enfoque A: TouchDesigner puro

### Cómo funciona

Todo corre dentro de un solo archivo `.toe`. La red de operadores (TOPs para video,
CHOPs para audio, DATs para datos y lógica) maneja la instalación completa.

```
┌─────────────────────────────────────────────────┐
│                 TouchDesigner                    │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐ │
│  │  Playback │  │  Audio   │  │  Lógica        │ │
│  │  360°     │  │  CHOPs   │  │  (Script DAT)  │ │
│  │  (TOP)    │  │  (grito) │  │  Python +      │ │
│  │           │  │          │  │  SQLite        │ │
│  └──────────┘  └──────────┘  └────────────────┘ │
│                                                   │
│  ┌────────────────────────────────────────────┐  │
│  │  Salida                                   │  │
│  │  NDI/Spout → 4 pantallas 360°             │  │
│  │  + pantalla interacción                   │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Rol de la IA

| Componente | Lo hace la IA |
|------------|--------------|
| Scripts Python dentro de Script DATs | ✅ Sí — consultas SQLite, lógica de deriva, filtros |
| Red de operadores (conexiones visuales) | ❌ No — lo hace el humano en la UI de TD |
| Creación programática de operadores | ✅ Parcial — tedioso pero posible con `op().create()` |
| Ajuste de shaders (GLSL) | ✅ Sí — la IA escribe GLSL |
| Conexión con hardware (proyectores, micrófono) | ❌ No — configuración manual |

### Ventajas

- **Entorno unificado**: todo en un archivo, sin procesos externos
- **Playback 360° listo**: TOPs con VideoIn 360, sin开发的
- **NDI/Spout nativo**: 4 salidas 360° + 1 interacción sin código adicional
- **CHOPs para audio**: detección de pico de ruido en minutos, sin programar FFT
- **OSC/MIDI integrado**: fácil agregar control externo
- **Prototipado visual rápido**: el humano arma el esqueleto visual, la IA rellena la lógica

### Desventajas

- **La IA no dibuja la red**: cada vez que hay que cambiar el flujo visual, lo hace el humano
- **Curva de TD**: requiere aprender el paradigma de operadores para armar el esqueleto
- **Scripting Python limitado**: el Python de TD no tiene todas las librerías del sistema
- **Licencia**: Comercial (aunque la free cubre 1280×1280, que puede servir para pruebas)

### ¿Cuándo elegirlo?

- Cuando el humano quiere **control visual directo** sobre el ruteo de medios
- Cuando se prioriza **velocidad de armado de la parte visual** (playback, multi-pantalla)
- Cuando el esqueleto visual es estable y los cambios son principalmente lógicos
- Cuando el humano tiene experiencia en TD o ganas de aprenderlo

---

## Enfoque B: Híbrido (TD playback + Python lógica)

### Cómo funciona

TouchDesigner se encarga **solo del playback y la captura de audio**.
Toda la lógica de la deriva, consultas a DB y decisión de qué mostrar corre en
**un proceso Python separado** que se comunica con TD mediante OSC (o un pipe TCP/IP).

```
┌────────────────────────┐     OSC      ┌─────────────────────────┐
│     TouchDesigner      │ ◄─────────► │   Proceso Python        │
│                        │             │                         │
│  - Playback video 360° │  "mostrar   │  - Lógica de deriva     │
│  - Captura de audio    │   foto 42   │  - Consultas SQLite     │
│  - CHOP grito          │  durante    │  - Filtros (color,      │
│  - NDI/Spout salidas   │   5s"       │    keyword, autor, GPS) │
│  - Superposición de    │             │  - Línea de tiempo      │
│    texto/transcripción │  "grito     │  - Keypoints            │
│                        │   detectado"│  - Decisión de deriva   │
│                        │             │  - HTTP server para     │
│                        │             │    consultas externas   │
└────────────────────────┘             └─────────────────────────┘
```

TouchDesigner recibe órdenes de alto nivel via OSC: *"reproducí el video X desde el segundo Y"*, *"mostrá la foto Z durante 5 segundos con transición A"*, *"superponé el texto T en la esquina superior derecha"*.

El proceso Python es el **cerebro**; TouchDesigner es el **músculo audiovisual**.

### Rol de la IA

| Componente | Lo hace la IA |
|------------|--------------|
| Proceso Python entero (deriva, DB, filtros, OSC server) | ✅ Sí — 100% del código |
| Red TD reducida (playback + captura de audio + salidas) | ⬜ Parcial — menos operadores, más simple |
| Protocolo OSC entre ambos | ✅ Sí — la IA escribe cliente y servidor |
| Toda la lógica de la instalación | ✅ Sí — en Python, fácil de escribir y depurar |

### Ventajas

- **La IA escribe todo el cerebro**: la parte más compleja (deriva, consultas, decisión) es código Python puro, que la IA domina
- **TD se simplifica**: solo TOPs de playback + CHOP de audio + superposición de texto. No necesita lógica compleja adentro
- **Separación de concerns**: el motor de decisión puede probarse independientemente de TD (sin depender de la UI visual)
- **Iteración rápida**: cambiar la lógica de la deriva es editar Python y reiniciar el proceso, sin tocar el `.toe`
- **Librerías Python completas**: Pillow, numpy, sqlite3, ollama, faster-whisper todo disponible sin limitaciones
- **Debugging fácil**: logs, prints, tests unitarios sobre la lógica de deriva
- **Open source**: el proceso Python es 100% gratuito y portable

### Desventajas

- **Dos procesos que coordinar**: hay que asegurar que la comunicación OSC sea confiable
- **Latencia**: el round-trip OSC agrega ~1-5ms (irrelevante para este tipo de instalación)
- **Complejidad operativa**: dos cosas que pueden fallar en vez de una
- **Setup inicial**: hay que definir bien el protocolo OSC antes de arrancar

### ¿Cuándo elegirlo?

- Cuando se quiere que la IA haga **la mayor cantidad de trabajo posible**
- Cuando la lógica de la deriva va a ser compleja y va a iterarse mucho
- Cuando se valora poder probar la lógica sin TD
- Cuando el humano no quiere aprender TD en profundidad

---

## Comparación lado a lado

| Aspecto | TD Puro | Híbrido |
|---------|---------|---------|
| La IA escribe | Scripts TD, shaders | 100% del cerebro (Python), protocolo OSC |
| El humano arma | Red de operadores visual | Red TD simplificada + definir protocolo OSC |
| Playback 360° | ✅ Nativo | ✅ Nativo (en TD) |
| Multi-pantalla | ✅ NDI/Spout nativo | ✅ NDI/Spout nativo (en TD) |
| Detección de grito | ✅ CHOPs nativo | ✅ CHOPs nativo (en TD) |
| Lógica de deriva | ❌ La IA no la ve en la red | ✅ Código Python puro, testeable |
| Consultas DB | ✅ Script DAT (Python limitado) | ✅ Python completo |
| Librerías externas | ⚠️ Limitado a lo que TD ofrece | ✅ Pillow, numpy, ollama, etc. |
| Debugging | ⚠️ Consola de TD + prints | ✅ Logs, tests, pdb |
| Iteración lógica | ⚠️ Editar script DAT + recargar | ✅ Editar .py + reiniciar proceso |
| Complejidad operativa | Baja (1 proceso) | Media (2 procesos + OSC) |
| Licencia | Comercial | Solo TD es comercial (uso reducido) |
| Rol de la IA en el total | ~40% del trabajo | ~80% del trabajo |

---

## Decisión: a definir

No hay una respuesta correcta única. Depende de:

1. **¿Querés aprender TouchDesigner o que la IA escriba todo lo posible?**
   - Aprender TD → Enfoque A
   - Máximo código de IA → Enfoque B

2. **¿Cuán compleja va a ser la lógica de la deriva?**
   - Simple (2-3 reglas) → Cualquiera funciona
   - Muy compleja (múltiples filtros combinados, pesos, transiciones) → Enfoque B

3. **¿Cuánto vas a iterar sobre la lógica?**
   - Mucho → Enfoque B (editar Python es más rápido que editar la red)
   - Poco → Cualquiera

4. **¿Tenés experiencia previa con TD?**
   - Sí → Enfoque A natural
   - No → Enfoque B (TD se usa al mínimo)

5. **¿Preferís un único archivo .toe o varios componentes?**
   - Único → Enfoque A
   - Modular → Enfoque B

### Posible camino híbrido-progresivo

Arrancar con **Enfoque B** (la IA escribe todo el cerebro en Python, TD mínimo)
y si después se necesita más integración visual, migrar partes de la lógica
a Script DATs dentro de TD. El protocolo OSC permite esta transición gradual:
primero el Python manda órdenes, después algunos módulos se mueven a TD cuando
tenga sentido.

---

## Nota sobre OpenFrameworks

Si en algún momento se decide que TD no es lo adecuado (por licencia, por
curva, por limitaciones técnicas), **OpenFrameworks es el reemplazo natural**
del enfoque híbrido: el proceso Python ya tiene toda la lógica, solo habría
que reemplazar TD por un renderer en C++ que reciba las mismas órdenes via
OSC o TCP. La inversión en el cerebro Python no se pierde.
