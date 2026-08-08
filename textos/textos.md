<!--
# Colección de textos del viaje

DOCUMENTACIÓN DEL ESQUEMA (esto es un comentario HTML; el parser lo IGNORA,
no se ingesta como texto real. Podés borrarlo o editarlo tan libre como quieras).

IDEA CENTRAL: EL ARCHIVO .md ES UN CONTENEDOR, NO UN TEXTO
============================================================
El archivo .md (este) es para los medios tipo 'texto' lo que la carpeta es
para los medios tipo imagen: un contenedor/agrupador de origen. La UNIDAD de
medio es cada TEXTO (cada subtítulo `##`), que entra en la base de datos como
un registro propio (su propia id) y es lo que se enriquece con metadata.

  Escritura del archivo .md  vs  Ingesta en la DB
  ------------------------------------------------
  .md (contenedor)    ->   sucede a la carpeta para imágenes
  ## subtitulo (texto) ->   cada foto / cada video / cada TEXTO
  metadata del texto   ->   metadata del medio (autor, fecha, tags, ubicacion)

En el archivo .md no hay metadata de autor/ubicacion a nivel archivo: quien
escribió el texto es el AUTOR DEL TEXTO (por texto), NO de la colección.

CÓMO ESCRIBIR TEXTOS PARA QUE SE INGERAN
========================================

1. FRONTMATTER AMIGO (opcional, solo metadata de la COLECCIÓN)
   Va al inicio del archivo, delimitado entre dos líneas `---`:

   ---
   titulo: Bitácora del día 12    <- Título de la COLECCIÓN (control/origen)
   compilador: Federico            <- Opcional. Quien armó el archivo .md
   tags: bitacora, ruta            <- Opcional. Se heredan a TODOS los textos
   ---

   Solo metadata de la colección (para seguimiento de origen). El .md NO tiene
   autor/ubicacion propios: esos son de cada texto.

2. SUBTÍTULOS = TEXTOS INDIVIDUALES (la UNIDAD DE MEDIO):
   Cada encabezado de nivel 2 (`##`) abre un TEXTO. Bajo el subtítulo van las
   líneas `clave: valor` con la metadata del text (autor, fecha, tags,
   ubicacion) y luego el contenido, hasta el siguiente `##`.

   ## Primera noche
   autor: Juan
   fecha: 2025-05-03
   ubicacion: Santiago del Estero

   Contenido del primer texto ...

   ## Llegada a Tafí
   autor: María
   fecha: 2025-05-05
   tags: valle
   ubicacion: Tafí del Valle

   Contenido del segundo texto ...

   - Claves permitidas por texto: `autor`, `fecha` (ISO YYYY-MM-DD),
     `tags` (separadas por coma, se suman a las de la colección),
     `ubicacion` (lugar del texto). `ubicacion` acepta un nombre de lugar
     (ej: `Moreno`) O una coordenada `lat, lon` (ej: `-34.627328, -58.728783`,
     que se guarda en latitude/longitude del medio).
   - La metadata de cada texto se guarda EN su registro media (author,
     timestamp_utc) o en media_metadata (texto_tags, texto_ubicacion).
   - Cada subtítulo genera UN registro en la tabla `media` con type='text'.

3. SIN SUBTÍTULOS = UN SOLO TEXTO:
   Si el archivo NO tiene ningún `##`, todo el cuerpo después del frontmatter
   se toma como UN SOLO texto, cuyo título es el `titulo` del frontmatter
   (o el nombre del archivo si no hay frontmatter).

4. COMENTARIOS HTML (`<!-- ... -->`):
   Se ignoran por completo. Sirven para notas que no querés que sean parte
   del texto visible (como esta documentación).

CASO DE USO:
   - Escribís los .md en la carpeta `textos/`.
   - El usuario es responsable de armar el texto (por ahora la conversión
     automática desde docx/pdf queda para más adelante).
   - Después corrés el script de ingesta (TUI Ingesta → 5 o `flujos.py ingest-textos`)
     y cada texto subtitulado entra en la base de datos.

Ver un ejemplo concreto en `textos/texto_ejemplo.md`.

------  PLANTILLA VACÍA -------   Desde acá empezás a cargar tus textos reales.
-->