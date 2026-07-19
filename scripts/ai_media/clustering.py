"""
Módulo de clustering semántico para agrupar imágenes dentro de una tanda temporal.

Estrategias:
  - tags: agrupa por palabras clave extraídas por IA
  - embeddings: agrupa por similitud semántica de descripciones (nomic-embed-text)
"""

import logging
from typing import Optional

from scripts.ai_media.image_analysis import MODELO_VISION_DEFAULT

logger = logging.getLogger(__name__)


def agrupar_por_tags(
    grupo: list[str],
    modelo_vision: str = MODELO_VISION_DEFAULT,
    compartir_min: int = 1,
) -> list[list[str]]:
    """
    Agrupa imágenes dentro de un grupo temporal compartiendo al menos N tags.

    1. Para cada imagen, pide al modelo de visión 3 palabras clave.
    2. Agrupa greedy: la primera imagen define el grupo, se agregan las que
       compartan al menos `compartir_min` tags.

    Args:
        grupo: Lista de rutas de imágenes (mismo grupo temporal).
        modelo_vision: Modelo de visión para extraer tags.
        compartir_min: Mínimo de tags compartidos para estar en el mismo grupo.

    Returns:
        Lista de sub-grupos.
    """
    from scripts.ai_media.ollama_client import OllamaVision

    if len(grupo) <= 1:
        return [grupo]

    cliente = OllamaVision(modelo=modelo_vision)

    prompt_tags = (
        "Respondé ÚNICAMENTE 3 palabras clave separadas por coma "
        "que describan el contenido principal de esta imagen. "
        "Ejemplo: 'atardecer, plaza, bicicletas'"
    )

    tags_por_ruta = {}
    for ruta in grupo:
        try:
            respuesta = cliente.analizar_imagen(ruta, prompt=prompt_tags, temperatura=0.1)
            tags = [t.strip().lower().rstrip(".") for t in respuesta.split(",")][:3]
            tags_por_ruta[ruta] = set(tags)
            logger.debug("Tags de %s: %s", ruta, tags)
        except Exception as e:
            logger.warning("Error extrayendo tags de %s: %s", ruta, e)
            tags_por_ruta[ruta] = set()

    # Agrupamiento greedy: la primera imagen del grupo define el cluster
    sub_grupos = []
    asignadas = set()

    for ruta in grupo:
        if ruta in asignadas:
            continue

        grupo_sim = [ruta]
        asignadas.add(ruta)
        tags_ref = tags_por_ruta.get(ruta, set())

        for otra in grupo:
            if otra in asignadas:
                continue
            tags_otra = tags_por_ruta.get(otra, set())
            if tags_ref and tags_otra and len(tags_ref & tags_otra) >= compartir_min:
                grupo_sim.append(otra)
                asignadas.add(otra)

        sub_grupos.append(grupo_sim)

    # Estadísticas
    multi = sum(1 for g in sub_grupos if len(g) > 1)
    logger.info(
        "  Tags: %d grupos (%d multi-imagen) en grupo temporal de %d imágenes",
        len(sub_grupos), multi, len(grupo)
    )

    return sub_grupos


def agrupar_por_embeddings(
    grupo: list[str],
    modelo_vision: str = MODELO_VISION_DEFAULT,
    modelo_embed: str = "nomic-embed-text",
    umbral_similitud: float = 0.7,
) -> list[list[str]]:
    """
    Agrupa imágenes por similitud semántica usando embeddings de descripciones.

    1. Para cada imagen, obtiene una breve descripción con el modelo de visión.
    2. Convierte cada descripción a embedding (nomic-embed-text).
    3. Agrupa por cosine similarity (umbral configurable).

    Args:
        grupo: Lista de rutas de imágenes.
        modelo_vision: Modelo de visión para describir.
        modelo_embed: Modelo de embeddings (nomic-embed-text recomendado).
        umbral_similitud: Umbral de cosine similarity (0-1) para considerar mismo grupo.

    Returns:
        Lista de sub-grupos.
    """
    from scripts.ai_media.ollama_client import OllamaVision
    from ollama import embeddings
    import numpy as np

    if len(grupo) <= 1:
        return [grupo]

    cliente = OllamaVision(modelo=modelo_vision)

    prompt_desc = (
        "Describí brevemente lo que se ve en esta imagen en una oración "
        "de máximo 15 palabras. Evitá valoraciones, solo describí el contenido."
    )

    # 1. Obtener descripciones
    desc_por_ruta = {}
    for ruta in grupo:
        try:
            desc = cliente.analizar_imagen(ruta, prompt=prompt_desc, temperatura=0.1)
            desc_por_ruta[ruta] = desc.strip()
            logger.debug("Descripción de %s: %s", ruta, desc[:50])
        except Exception as e:
            logger.warning("Error describiendo %s: %s", ruta, e)
            desc_por_ruta[ruta] = ""

    # 2. Generar embeddings
    emb_por_ruta = {}
    for ruta, desc in desc_por_ruta.items():
        if desc:
            try:
                resp = embeddings(model=modelo_embed, prompt=desc)
                emb_por_ruta[ruta] = np.array(resp["embedding"], dtype=np.float32)
            except Exception as e:
                logger.warning("Error generando embedding para %s: %s", ruta, e)

    if not emb_por_ruta:
        logger.warning("  No se pudieron generar embeddings, se conserva el grupo original")
        return [grupo]

    # 3. Agrupar por cosine similarity
    sub_grupos = []
    asignadas = set()

    for ruta in grupo:
        if ruta in asignadas:
            continue

        grupo_sim = [ruta]
        asignadas.add(ruta)

        if ruta not in emb_por_ruta:
            sub_grupos.append(grupo_sim)
            continue

        emb_ref = emb_por_ruta[ruta]

        for otra in grupo:
            if otra in asignadas or otra not in emb_por_ruta:
                continue
            emb_otra = emb_por_ruta[otra]
            sim = float(np.dot(emb_ref, emb_otra) / (
                np.linalg.norm(emb_ref) * np.linalg.norm(emb_otra)
            ))
            if sim >= umbral_similitud:
                grupo_sim.append(otra)
                asignadas.add(otra)

        sub_grupos.append(grupo_sim)

    # Estadísticas
    multi = sum(1 for g in sub_grupos if len(g) > 1)
    logger.info(
        "  Embeddings: %d grupos (%d multi-imagen) en grupo temporal de %d imágenes",
        len(sub_grupos), multi, len(grupo)
    )

    return sub_grupos
