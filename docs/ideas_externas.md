# Ideas externas recopiladas

Documento de referencia para conversaciones futuras. Cada idea tiene un título
corto y una descripción breve para poder referenciarla sin re-leer el texto
original completo.

---

## Motor de Deriva (TD)

### Eco del Grito
El pico de ruido no hace un hard cut sino que dispara una distorsión visual
temporal (aberración cromática, estática, barrido) que simboliza la irrupción
física en el espacio digital.

### Filtros en Pila (LIFO)
Pila de filtros: si hay un grito sobre una foto de tierra, el filtro pasa a
tierra y el anterior (atardecer) queda en espera. Sin interrupciones, el
filtro latente vuelve gradualmente.

### Deriva Abstracta (Vacío)
Cuando no hay resultados para el filtro actual en el tramo de tiempo, en vez
de pantalla negra mostrar mapas vectoriales del viaje con sonidos ambientales,
o acelerar la línea de tiempo hasta el próximo hito que coincida.

---

## Experiencia Sensorial

### Manubrio / Pedal (Control Háptico)
Un manubrio real de bicicleta con sensores: pedalear para avanzar/retroceder
en la línea de tiempo, girar el manubrio para cambiar filtro cromático o
desplazar el foco entre pantallas.

### Audio 3D Geolocalizado
El audio de entrevistas y sonidos de naturaleza se espacializa en la sala
según qué pantalla muestra el medio asociado. Si la foto está en la pantalla
trasera derecha, el audio emerge de ese altavoz.

---

## Composición Visual con Metadatos

### Postales en 360°
Fotos tomadas en el mismo tramo temporal que un video 360° aparecen flotando
como postales suspendidas en el espacio envolvente, ubicadas por coordenadas
GPS o dispersas alrededor del espectador.

### Tipografía Cinética (Keypoints)
Las transcripciones (media_keypoints) se proyectan como subtítulos cinéticos
grandes en las paredes. Tamaño, velocidad y color reaccionan al volumen y
tono del audio original (FFT en TD).

### Iluminación Sala por Color (DMX)
Los colores dominantes del medio actual (color_1_hex) controlan tiras LED o
proyectores DMX/ArtNet en la sala física. Atardecer naranja → sala teñida de
naranja.

---

## Arquitectura de Integración

### Enfoque Híbrido (Recomendación)
Validación externa del Enfoque B: cerebro Python (deriva + DB) separado del
músculo TD (render + audio). Permite tests unitarios y migración futura a
otro motor (OF, Unreal) sin re-escribir la lógica.

### Pre-carga (Preload OSC)
El cerebro Python mantiene una cola de 2-3 medios probables y envía
/preload/media_id antes de /play. TD carga el video en un Movie File In
secundario y conmuta con crossfade, evitando dropped frames.

### Simulador de Sala 3D
Pequeño simulador dentro del .toe que representa las 5 pantallas en un
espacio virtual 3D en un monitor secundario, para calibrar la deriva fuera
de la galería.

---

## Relaciones Cromáticas

### Temperatura y Luminosidad
Calcular temperatura (cálido/frío/neutro) y luminosidad (0.0-1.0) desde RGB.
La deriva puede alternar entre "tramos cálidos" (Santiago del Estero) y
"tramos fríos" (amaneceres húmedos de Santa Fe).

### Vecindad Cromática Mínima
Transición entre medios por distancia euclidiana en espacio HSL/Lab en vez
de salto aleatorio. Las pantallas cambian como un degradado en el tiempo.

---

## Sincronicidad Espacio-Temporal

### Burbujas de Sincronicidad
Detección automática de momentos donde múltiples dispositivos registraron el
mismo evento (radio 100m, ventana 5min). Al entrar a una burbuja, la pantalla
360° muestra la cámara principal y las secundarias destellan fotos de los
otros dispositivos.

---

## Embeddings Semánticos

### media_embeddings (Vectores)
Tabla que almacena embeddings vectoriales (nomic-embed-text) de descripciones
y transcripciones. Permite asociación libre: si una foto muestra "árbol seco
en la banquina", puede transicionar a un audio donde alguien dice "necesito
descansar a la sombra".

### Deriva por Similitud Coseno
Al ocurrir un grito, se calcula el embedding del medio actual y se buscan
los medios con mayor similitud coseno en toda la DB, habilitando relaciones
abstractas no deterministas.

---

## Esfuerzo Físico y Altitud

### Pendiente como Metadata Narrativa
A partir de altitud y coordenadas consecutivas, calcular pendiente promedio.
Subida → baja velocidad de transición, sonidos de esfuerzo. Bajada → acelera
transiciones, audios con energía.

---

## Clima Histórico

### Enriquecimiento Climático
Poblar datos climáticos históricos (temperatura, lluvia, viento) desde
timestamp_utc + lat/lon con APIs externas. La deriva puede filtrar por
"calor extremo >38°C" o "viento en contra".

---

## Hilos de Entrevistas

### Hilos de Diálogo
Relacionar fragmentos de transcripción (media_keypoints) por interlocutor o
tema, incluso si fueron grabados días después en otra provincia. La deriva
puede saltar entre fragmentos de la misma persona sosteniendo el hilo
narrativo por sobre el espacio físico.
