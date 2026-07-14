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

2. **La línea es un continuo.** No hay saltos de un día a otro sin que
   exista material para tender el puente. Si entre dos puntos hay un video
   de 3 minutos, ese video ocupa esos 3 minutos en la línea.

3. **El presente es un punto.** La instalación está siempre posicionada en
   algún momento del viaje. Ese momento es el **ahora** de la sala.

4. **El filtro acota, no reemplaza.** El filtro activo (rojo, atardecer,
   entrevista, etc.) acota qué medios del tramo actual se muestran. Pero el
   punto en la línea sigue existiendo aunque ningún medio del tramo coincida
   con el filtro.

## Estructura

```
Buenos Aires ──────┬──────┬──────────┬──────────────┬──────→ Tucumán
                   │      │          │              │
                Luján  Colón  Villa María  Ojo de Agua
                (día 2) (día 5)  (día 8)    (día 11)
```

Cada video 360 es un **segmento** (tiene duración). Cada foto es un
**punto**. Los audios y textos también ocupan su instante.

## Preguntas abiertas

Estas decisiones se postergan hasta la implementación del motor:

- **Sentido**: ¿la línea avanza siempre hacia adelante o puede
  rebobinarse? El candidato natural es que avance, pero no está decidido.
- **Escala**: ¿el movimiento es continuo (segundo a segundo) o a saltos
  (día a día, pueblo a pueblo)?
- **Cluster**: cuando hay muchas fotos en el mismo minuto (ej: 19 fotos
  en un mismo instante), ¿se funden, se elige una al azar, se rotan?
- **Videos como ventanas**: los videos 360 duran minutos. ¿La línea
  avanza con la reproducción del video o el video se reinicia si se
  retrocede en la línea?
- **Vacío**: ¿qué se muestra cuando en el tramo actual no hay medios que
  cumplan el filtro activo?

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

Todo esto ya es posible con el schema actual.
