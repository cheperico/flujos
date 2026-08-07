# Colección de textos del viaje

<!--
DOCUMENTACIÓN DEL ESQUEMA (esto es un comentario HTML; el parser lo IGNORA,
no se ingesta como texto real. Podés borrarlo o editarlo tan libre como quieras).

CÓMO ESCRIBIR TEXTOS PARA QUE SE INGERAN
========================================

1. FRONTMATTER (obligatorio para la plantilla, pero solo `titulo` es lo único)
   Va al inicio del archivo, delimitado entre dos líneas `---`:

   ---
   titulo: Bitácora del día 12      <- Título de la COLECCIÓN (todo el archivo)
   autor: Juan                       <- Opcional. Autor de los textos
   fecha: 2025-05-03                 <- Opcional. Fecha de escritura (ISO YYYY-MM-DD)
   tags: bitacora, ruta              <- Opcional. Etiquetas separadas por coma
   ubicacion: Santiago del Estero    <- Opcional. Lugar del texto
   ---

   - `titulo`: título general de la colección. Si un texto no tiene subtítulo,
     este valor se usa como su título.
   - `autor`, `fecha`, `tags`, `ubicacion`: opcionales/ comunes a todos los
     textos del archivo.

2. SUBTÍTULOS = TEXTOS INDIVIDUALES
   Cada encabezado de nivel 2 (`##`) abre un texto nuevo. TODO lo que esté bajo
   `## Mi texto` y hasta el siguiente `##` es el CONTENIDO de ese texto.

   ## Primera noche
   Contenido del primer texto...

   ## Llegada a Tafí
   Contenido del segundo texto...

   Cada subtítulo genera UN registro en la tabla `media` con type='text'.

3. SIN SUBTÍTULOS = UN SOLO TEXTO
   Si el archivo NO tiene ningún `##`, todo el cuerpo después del frontmatter
   se toma como UN SOLO texto, cuyo título es el `titulo` del frontmatter
   (o el nombre del archivo si no hay frontmatter).

4. COMENTARIOS HTML (`<!-- ... -->`)
   Se ignoran por completo. Sirven para notas que no querés que sean parte
   del texto visible (como esta documentación).

CASO DE USO:
   - Escribís los archivos .md en la carpeta `textos/`.
   - El usuario es el responsable de armar el texto (no hay conversión automática
     desde docx/pdf).
   - Después corrés el script de ingesta (TUI Ingesta → 5 o `flujos.py ingest-textos`)
     y cada texto subtitulado entra en la base de datos.

------  PLANTILLA VACÍA -------   Desde acá empezás a cargar tus textos reales.
-->

## Titulo del primer texto

Escribí acá el contenido del primer texto. Este bloque, bajo el `##`, es lo
que queda indexado como contenido del texto en la base de datos.

## Titulo del segundo texto

Segundo texto. Al haber VARIOS subtitulos, este archivo genera DOS textos.