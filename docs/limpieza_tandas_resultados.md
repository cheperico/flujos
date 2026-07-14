# Pruebas de limpieza de tandas — Resultados

## Contexto

Se compararon 4 estrategias para limpiar tandas de imágenes (agrupar similares
y quedarse con la mejor) sobre 4 subsets de 221 imágenes cada uno
(`fABIAN_A`, `B`, `C`, `D`), copias idénticas de una misma carpeta original.

**Pipeline común a todas:**
1. Agrupar por ventana temporal (5 min)
2. Sub-agrupar por criterio de similitud (según estrategia)
3. De cada sub-grupo, seleccionar la mejor imagen por **calidad visual**
   evaluada por IA (moondream:latest)

## Estrategias comparadas

| ID | Estrategia | Sub-agrupación |
|----|-----------|----------------|
| A | Temporal solo | Ninguna (todo grupo temporal = 1 imagen) |
| B | Temporal + pHash | Hash perceptual (imágenes casi idénticas por píxeles) |
| C | Temporal + Tags | 3 keywords por imagen con moondream, agrupa si comparten ≥1 |
| D | Temporal + Embeddings | Descripción corta con moondream → embedding (nomic-embed-text) → similitud coseno ≥ 0.7 |

## Resultados

| Prueba | Conservadas | Descartadas | % Descarte | Grupos múltiples |
|--------|:-----------:|:-----------:|:----------:|:----------------:|
| **A** | 84 | 137 | **62%** | 57 |
| **B** | 197 | 24 | **11%** | 14 |
| **C** | 144 | 77 | **35%** | 40 |
| **D** | 138 | 83 | **37.5%** | 38 |

## Modelo utilizado

- **Visión (tags, descripciones, evaluación de calidad):** `moondream:latest`
  (1.7 GB) en todas las pruebas.
- **Embeddings (solo D):** `nomic-embed-text` (274 MB).
- No se usaron modelos más grandes por limitaciones de RAM (~80% de uso con
  moondream, base ~40%).

## Tiempos estimados

| Prueba | Tiempo aprox. | Notas |
|--------|:-------------:|-------|
| A | ~3 min | Sin IA en sub-agrupación. Solo evaluar ~57 grupos. |
| B | ~3 min | pHash instantáneo. Solo 14 grupos múltiples que evaluar. |
| C | ~29 min | 40 grupos múltiples → tags + evaluación (~5s/imagen con moondream). |
| D | ~27 min | 38 grupos múltiples → descripción + embedding + evaluación (~5s/imagen). |

## Observaciones cualitativas (usuario)

- **A:** Demasiado agresivo. Descartó imágenes únicas sin razón aparente.
- **B:** Demasiado permisivo. Muchas imágenes casi repetidas quedaron.
- **C:** Mejor balance, pero aún con algunos descartes innecesarios y algunos
  repetidos que podrían haberse ido.
- **D:** El más consistente. Menos descartes innecesarios que C, buena tasa de
  descarte. Aún quedaron algunas imágenes muy similares que podrían haberse
  descartado.

## Decisión

**Estrategia D (embeddings) como favorita**, con posibilidad de ajustar
umbrales más adelante. No se profundiza ahora por priorizar otras funciones
del proyecto.

## Archivos relevantes

- `scripts/limpiar_tandas.py` — Pipeline principal
- `scripts/ai_media/clustering.py` — Sub-agrupación semántica (tags/embeddings)
- `scripts/ai_media/batch_selector.py` — Selección de mejor imagen
- `scripts/ai_media/ollama_client.py` — Cliente Ollama
- `db/reporte_A.json` .. `reporte_D.json` — Reportes detallados
- `D:\Flujos\Testeo\fABIAN_A` .. `fABIAN_D` — Carpetas de prueba
