# Rediseño de embeddings — nota de dirección

Fecha: 2026-08-15. Contexto: los embeddings fueron desactivados (2026-08-11)
porque modelo/prompt/fuentes/usos aún no eran útiles (retirados del TUI,
`generate_embeddings.py` standalone). Esta nota fija el objetivo al que apuntar
cuando se rediseñe.

## El problema que resuelven los embeddings

La capa léxica (`SINONIMOS` de `refinar_keywords.py`) unifica la **misma entidad
escrita distinto** (monte buey / monte bué / monte bley). Pero hay pares de
**ideas distintas y cercanas** que el léxico NO debe (ni puede) unificar — y que
sin embargo la instalación debería poder agrupar:

- **"identidad nacional" y "monumento"**: dos ideas distintas (decisión
  2026-08-15: se mantienen separadas como tags) pero semánticamente muy cercanas
  (un monumento suele expresar identidad nacional).
- **Los textos de "viajeros" importados** (crónicas históricas tipo Tschiffely)
  son situaciones históricas que hacen a la identidad nacional — comparten tema
  con fotos de monumentos, placas conmemorativas y fechas (1916-2016,
  fundada 1670, mundial 1934...).

Los embeddings son la herramienta para esa agrupación **semántica**: agrupar por
significado, no por forma ortográfica.

## Hacia dónde apuntar en el rediseño

1. **Uso principal**: agrupar/clusterear conceptos cercanos **entre tipos de
   medio** (imagen ↔ texto ↔ audio) — p. ej. fotos de monumentos con textos
   históricos de viajeros.
2. **Fuentes del vector por medio**: combinar las señales de texto ya en la DB —
   `ia_keywords` (visión), `ia_description`, `ia_keywords_texto` (textos
   viajeros), `texto_completo`, `ia_keywords_transcripcion`.
3. **NO duplicar el léxico**: `SINONIMOS` sigue siendo el lugar para variantes
   ortográficas de la misma entidad. Los embeddings no deben usarse para "falsos
   sinónimos" — lección ya aprendida: la capa semántica de `refinar_keywords`
   producía ciclismo→deporte, nublado→soleado y se eliminó por completo.
4. **Criterio de éxito futuro**: dado "identidad nacional", el sistema debería
   encontrar fotos de monumentos, placas conmemorativas y textos históricos
   relacionados, aunque no compartan palabras.

## Notas abiertas

- ¿Qué modelo de embeddings? (nomic-embed-text era el default; reevaluar
  modelo/prompt).
- ¿Cómo exponer la agrupación en la instalación? (p. ej. cluster como
  elección/filtro en `elecciones.py`, o como señal para el motor de loop).
