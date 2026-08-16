# Videos 360° equirectangulares en la web — opciones

> Documento de opciones (2026-08-15). Pendiente de decisión e implementación.
> Item de roadmap: "Visualización web (deploy)" en `ROADMAP.md`.

## Problema

Los videos 360° equirectangulares (2:1) de la colección no se pueden ver como
tales en el navegador: el `<video>` nativo los muestra aplanados. Un visor 360°
proyecta el video sobre la cara interna de una esfera con la cámara adentro y
permite mirar alrededor (drag / giroscopio / zoom).

## Estado actual del proyecto (relevante para implementar)

| Pieza | Estado |
|---|---|
| Reproducción de video en la web (`deploy/`) | ❌ No existe: el bloque "Videos" del lienzo es solo una lista de descripciones (`renderMediosLista` → rama "otros"). Solo reproducen imágenes (slideshow) y audio (plan `SONIDO`) |
| Flag 360° en el snapshot (`visualizacion.db`) | ❌ No existe. `exportar_visualizacion.py` *detecta* 360° (ffprobe + marcador `xmp_spherical` de `media_metadata`) solo para decidir el transcode, pero **no lo persiste** en la tabla `medios` |
| Servir videos (`deploy/api/servir_medio.php`) | ⚠️ Usa `readfile()` **sin soporte HTTP Range**. Sin Range el `<video>` del navegador no puede streamear ni buscar (seek) — rompería cualquier reproducción, 360 o no |
| Videos 360 en la DB principal | 139 videos; **0** marcados `xmp_spherical`. El detector quedaría a la heurística ffprobe: aspecto exactamente 2:1 con ancho ≥ 3840, o metadata esférica del stream (`side_data`/tags) |
| Transcode | Opt-in: `exportar_visualizacion.py --transcode` con `--transcode-360-largo 1920` genera MP4/H.264 1920px web-friendly para 360° |

## Cómo funciona un visor 360° en el navegador

Patrón estándar (vigente 2026):

1. Crear un `<video>` con la fuente (`api/servir_medio.php?id=N`).
2. Usar el video como textura (`THREE.VideoTexture` en Three.js, o
   `texImage2D` por frame en WebGL puro).
3. Proyectarlo sobre una esfera **vista desde adentro** (`side: BackSide`).
4. Mover la cámara con drag (mouse/touch), giroscopio (`DeviceOrientation`,
   con `requestPermission()` en iOS 13+), y opcionalmente vista VR/Cardboard
   (split screen).

## Opciones

### A. Three.js — recomendada

- `VideoTexture` + `SphereGeometry` con `BackSide` + `OrbitControls` (drag) /
  `DeviceOrientationControls` (giroscopio).
- Es la solución dominante (Cloudimage 360, Panolens, Photo Sphere Viewer,
  etc. la usan de base). Madura, documentada, con ejemplos oficiales
  (threejs.org/examples: video/kinect, panorama/equirectangular).
- Servible como `three.min.js` local (~600 KB) o por CDN; **sin build step** —
  encaja con el deploy actual (SPA plana + Apache/PHP).
- Incluye zoom, fullscreen y vista Cardboard/VR de regalo.

### B. WebGL custom sin dependencias

- Fragment shader con el **mapeo inverso equirect**: dado yaw/pitch de la
  cámara, muestrear la textura del video en el quad fullscreen.
- Cero librerías, muy liviano y acorde al estilo minimalista del proyecto.
- Contra: hay que escribir a mano la carga del video como textura
  (`texImage2D` por frame), controles de cámara (drag + giroscopio), zoom,
  resize y la integración con el lienzo.

### C. A-Frame

- `<a-videosphere>` + `look-controls` → prototipo en minutos, drag y
  giroscopio declarativos.
- Contra: agrega ~250 KB+ y un paradigma de escena distinto al lienzo
  (componentes HTML vs DOM plano).

### D. Librerías nicho

- **Panolens**, **@cloudimage/360-video**, **Photo Sphere Viewer** (JS, no
  WordPress): menos código propio, pero dependencia externa, menos control de
  integración con el lienzo y peso variable.

## Requisitos de pipeline (independientes de la opción elegida)

1. **`scripts/exportar_visualizacion.py`**: persistir `es_360` en el snapshot
   (columna nueva en `medios`) desde `xmp_spherical` + heurística ffprobe,
   para que la web sepa qué videos abrir en modo 360.
2. **`deploy/api/servir_medio.php`**: soporte **HTTP Range** (imprescindible
   para reproducir cualquier video, 360 o no).
3. **Transcode**: correr el exportador con `--transcode` y
   `--transcode-360-largo 1920` para que los 360 queden en MP4/H.264 1920px.
4. **`deploy/js/app.js` + `css/estilos.css`**: renderer 360 en el bloque
   Videos (drag + giroscopio), con fallback a la lista actual para videos
   normales.

## Recomendación

**Three.js local** (no CDN, para no depender de red en la instalación): lo más
robusto, rápido de implementar, con drag/giroscopio/VR integrados. El shader
WebGL custom queda como alternativa si se quiere cero dependencias absolutas.

## Pasos futuros antes de decidir

- Detectar cuántos videos son realmente 360 (correr ffprobe sobre los 139
  videos: aspecto 2:1/ancho ≥ 3840 o metadata esférica) y, si corresponde,
  marcar `xmp_spherical` en la DB para que el pipeline los trate como 360
  (hoy 0 marcados).
- Elegir enfoque (A/B/C/D) según la prioridad de la instalación.
