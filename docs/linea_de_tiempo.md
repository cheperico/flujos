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

## Lo que necesita la DB

Para que este diseño funcione, la DB debe responder:

- "dame todos los medios entre `t1` y `t2`"
- "dame los medios del tramo actual filtrados por color/keyword/autor"
- "dame el siguiente medio después de `t`"
- "dame el medio anterior antes de `t`"
- "dame la distribución de medios por hora/día/pueblo"
- "dame los videos/audios que cubren este instante `t`"
- "dame los medios puntuales dentro de este segmento de video"

Con `duration_secs` como columna directa en `media`, estas consultas son
posibles. Para keypoints dentro de un video, se puede usar una tabla
`media_keypoints` con `timestamp_offset_secs`.
