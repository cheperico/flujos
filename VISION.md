# Flujos — Visión del proyecto

## El origen

Un grupo de personas viajó de Buenos Aires a Tucumán en bicicleta. Durante el
trayecto registraron el viaje con múltiples dispositivos y formatos:

- **Videos** (algunos 360°)
- **Fotos**
- **Entrevistas**
- **Sonidos ambientales**
- **Textos**

Ese registro es la materia prima de la instalación.

## La instalación

Una sala con **5 pantallas**:

- **1 pantalla de interacción**: una persona elige un filtro inicial (color,
  palabra clave, ubicación, etc.)
- **4 pantallas envolventes**: composición de videos 360° con superposición
  de imágenes, sonidos y textos relacionados con el filtro elegido

## La deriva como método curatorial

El recorrido no es asociativo ni determinista. No hay reglas fijas del tipo
"si rojo → entonces naranja". El filtro elegido se **mantiene**, pero la
navegación entre los medios que cumplen ese filtro es imprevisible.

**El sistema no decide. El sistema ofrece.**

La deriva se produce por cambios de foco que irrumpen desde fuera:

1. Alguien en la sala hace un **ruido fuerte** (un grito, un golpe)
2. El ruido captura lo que se está viendo en ese momento (un atardecer, una
   entrevista, una ruta de tierra)
3. Ese contenido se convierte en el nuevo filtro activo
4. El filtro anterior **queda latente**, disponible para emerger en la
   próxima interrupción

El sistema no reconoce voz ni usa modelos de lenguaje. Un **umbral de audio**
(en TouchDesigner) es suficiente para detectar el pico de ruido y activar el
cambio.

## La base de datos como mapa

No es el motor de la experiencia. Es el **mapa** del viaje — todos los
medios indexados para poder responder preguntas como:

- "dame imágenes donde predomine el rojo"
- "dame atardeceres"
- "dame videos grabados cerca de este punto"
- "dame medios de este tramo del viaje"
- "dame sonidos de la misma hora del día"
- "dame textos donde aparezca esta palabra"

El mapa se construye con:

| Eje de indexación | Columna en DB |
|---|---|
| Cromático | `color_1/2/3_name_basic`, `color_1/2/3_name_css` |
| Temporal | `timestamp_utc` |
| Espacial | `latitude`, `longitude`, `geolocation_source` |
| De autor | `author`, `author_source` |
| Temático | keywords en `media_metadata` |
| De tipo | `type`, `subtype` (360, entrevista, etc.) |

## La línea de tiempo como recorrido

Cada medio tiene un `timestamp_utc` que lo ubica en la cronología del viaje.
Los videos tienen además `duration_secs`, lo que permite tratarlos como
fragmentos dentro de esa temporalidad.

La línea de tiempo permite reconstruir el viaje: desde la salida en Buenos
Aires hasta la llegada a Tucumán, pasando por Luján, Carmen de Areco, Colón,
Melincué, Bell Ville, Villa María, Ojo de Agua, Loreto y todos los puntos
intermedios.

## El stack

| Componente | Rol |
|---|---|
| **Python** | Scripts de ingestión y post-procesamiento |
| **SQLite** | Base de datos embebida (el mapa) |
| **ffmpeg** | Análisis y transcodificación de medios |
| **ExifTool** | Extracción de metadatos EXIF/IPTC |
| **TouchDesigner** | Motor de la instalación (composición, audio, video) |

## Estado del proyecto

El pipeline de ingestión, enriquecimiento y consulta está **completo y operativo**
(ver `README.md` y `AGENTS.md` para el detalle actual: schema, scripts, comandos).
Queda como trabajo futuro el **motor de la instalación** (la lógica de deriva) en
TouchDesigner, cuyo diseño conceptual se documenta en `docs/diseno_instalacion.md`.
