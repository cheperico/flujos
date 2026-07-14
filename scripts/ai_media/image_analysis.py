"""
Análisis de imágenes con modelos de visión de Ollama.

Funcionalidades:
  - Extraer palabras clave (keywords) de una imagen (5-7 palabras)
  - Describir una imagen en texto
  - Clasificar imágenes por contenido
  - Procesamiento por lote

Uso básico:
    from scripts.ai_media.image_analysis import extraer_keywords, describir_imagen

    keywords = extraer_keywords("foto.jpg")
    print(keywords)  # ["playa", "atardecer", "palmeras", "arena", "mar", "cielo", "nubes"]

    descripcion = describir_imagen("foto.jpg")
    print(descripcion)

Línea de comandos:
    python -m scripts.ai_media.image_analysis foto.jpg
    python -m scripts.ai_media.image_analysis foto1.jpg foto2.jpg --modelo moondream:latest
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from scripts.ai_media.ollama_client import OllamaVision
from scripts.ai_media.proxy import obtener_proxy

logger = logging.getLogger(__name__)

# Prompt para extraer palabras clave de imágenes
PROMPT_KEYWORDS = (
    "Analizá esta imagen y devolvé únicamente una lista de 5 a 7 palabras clave "
    "en español que describan su contenido. "
    "Separalas con comas. No incluyas explicación ni ningún otro texto. "
    "Ejemplo: 'playa, atardecer, palmeras, arena, mar, cielo, nubes'"
)

PROMPT_DESCRIBIR = (
    "Describí esta imagen en una o dos oraciones en español. "
    "Mencioná los elementos principales, colores, composición y atmósfera."
)

PROMPT_CLASIFICAR = (
    "Clasificá esta imagen en una de estas categorías: "
    "naturaleza, urbano, retrato, abstracto, documento, evento, paisaje, arquitectura, "
    "objeto, arte, comida, tecnología, deporte, noche, macro, otras. "
    "Respondé solo con el nombre de la categoría."
)


def extraer_keywords(
    ruta_imagen: str,
    modelo: str = "moondream:latest",
    temperatura: float = 0.2,
    usar_proxy: bool = True,
) -> list[str]:
    """
    Analiza una imagen y devuelve 5-7 palabras clave en español.

    Args:
        ruta_imagen: Ruta al archivo de imagen.
        modelo: Modelo de visión a usar. Por defecto moondream (rápido y liviano).
        temperatura: Control de creatividad. Bajo para keywords predecibles.
        usar_proxy: Si True, usa proxy redimensionado a 2MP para acelerar.

    Returns:
        Lista de palabras clave (strings).

    Raises:
        FileNotFoundError: Si la imagen no existe.
        ValueError: Si no se pudieron extraer keywords.
    """
    ruta_proxy = obtener_proxy(ruta_imagen, usar_proxy=usar_proxy)
    cliente = OllamaVision(modelo=modelo)

    respuesta = cliente.analizar_imagen(
        ruta_proxy,
        prompt=PROMPT_KEYWORDS,
        temperatura=temperatura,
    )

    # Parsear la respuesta: puede venir como "cosa1, cosa2, ..." o "1. cosa1 2. cosa2..."
    keywords = _parsear_keywords(respuesta)

    if not keywords:
        logger.warning(
            "No se pudieron extraer keywords de: %s. Respuesta: %s",
            ruta_imagen, respuesta
        )
        # Fallback: devolver la respuesta completa como única keyword
        return [respuesta.strip()]

    logger.info("Keywords extraídas de %s: %s", Path(ruta_imagen).name, keywords)
    return keywords


def extraer_keywords_batch(
    rutas_imagenes: list[str],
    modelo: str = "moondream:latest",
    temperatura: float = 0.2,
    usar_proxy: bool = True,
) -> list[dict]:
    """
    Analiza múltiples imágenes y extrae keywords de cada una.

    Args:
        rutas_imagenes: Lista de rutas a imágenes.
        modelo: Modelo de visión.
        temperatura: Control de creatividad.
        usar_proxy: Si True, usa proxies redimensionados.

    Returns:
        Lista de dicts con {"ruta", "keywords", "error"}.
    """
    # Aplicar proxies y mantener mapeo ruta_original -> ruta_proxy
    if usar_proxy:
        rutas_proxy = [(r, obtener_proxy(r)) for r in rutas_imagenes]
    else:
        rutas_proxy = [(r, r) for r in rutas_imagenes]

    rutas_proxy_solo = [p for _, p in rutas_proxy]

    cliente = OllamaVision(modelo=modelo)
    resultados_vision = cliente.analizar_imagenes(
        rutas_proxy_solo,
        prompt=PROMPT_KEYWORDS,
        temperatura=temperatura,
    )

    resultados = []
    for (ruta_orig, _), item in zip(rutas_proxy, resultados_vision):
        if item["error"]:
            resultados.append({
                "ruta": ruta_orig,
                "keywords": [],
                "error": item["error"],
            })
        else:
            keywords = _parsear_keywords(item["respuesta"])
            resultados.append({
                "ruta": ruta_orig,
                "keywords": keywords,
                "error": None,
            })

    return resultados


def describir_imagen(
    ruta_imagen: str,
    modelo: str = "qwen2.5vl:latest",
    temperatura: float = 0.3,
    usar_proxy: bool = True,
) -> str:
    """
    Genera una descripción en lenguaje natural de una imagen.

    Args:
        ruta_imagen: Ruta al archivo de imagen.
        modelo: Modelo de visión (por defecto qwen2.5vl para mejor calidad).
        temperatura: Control de creatividad.
        usar_proxy: Si True, usa proxy redimensionado.

    Returns:
        Descripción textual de la imagen.
    """
    ruta_proxy = obtener_proxy(ruta_imagen, usar_proxy=usar_proxy)
    cliente = OllamaVision(modelo=modelo)
    return cliente.analizar_imagen(ruta_proxy, PROMPT_DESCRIBIR, temperatura)


def clasificar_imagen(
    ruta_imagen: str,
    modelo: str = "moondream:latest",
    usar_proxy: bool = True,
) -> str:
    """
    Clasifica una imagen en una categoría predefinida.

    Args:
        ruta_imagen: Ruta al archivo de imagen.
        modelo: Modelo de visión.
        usar_proxy: Si True, usa proxy redimensionado.

    Returns:
        Nombre de la categoría.
    """
    ruta_proxy = obtener_proxy(ruta_imagen, usar_proxy=usar_proxy)
    cliente = OllamaVision(modelo=modelo)
    return cliente.analizar_imagen(ruta_proxy, PROMPT_CLASIFICAR, temperatura=0.1)


def _parsear_keywords(respuesta: str) -> list[str]:
    """
    Parsea la respuesta del modelo y extrae keywords como lista.

    Maneja formatos:
      - "playa, atardecer, palmeras"
      - "'playa', 'atardecer', 'palmeras'" (con/quotes individuales)
      - "1. playa 2. atardecer 3. palmeras"
      - "- playa\\n- atardecer\\n- palmeras"
      - "['playa', 'atardecer', 'palmeras']"
    """
    # Limpiar
    texto = respuesta.strip().strip("'\"")

    # Detectar si viene como lista JSON (con comillas dobles o simples)
    if texto.startswith("[") and texto.endswith("]"):
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            # Intentar con comillas dobles (a veces viene con simples)
            try:
                texto_json = texto.replace("'", '"')
                return json.loads(texto_json)
            except json.JSONDecodeError:
                pass

    # Detectar formato numerado: "1. cosa 2. cosa"
    if re.match(r"^\d+[\.\)]", texto):
        items = re.findall(r"\d+[\.\)]\s*([^\d,;]+)", texto)
        if items:
            return [_limpiar_kw(i) for i in items if i.strip()]

    # Detectar formato viñetas: "- cosa" o "* cosa"
    if re.match(r"^[\-\*]", texto):
        items = re.findall(r"[\-\*]\s*([^\n]+)", texto)
        if items:
            return [_limpiar_kw(i) for i in items if i.strip()]

    # Separar por " - " (a veces el modelo usa guiones medios como separador)
    if " - " in texto:
        items = [_limpiar_kw(i) for i in texto.split(" - ") if i.strip()]
        items = [i for i in items if len(i) < 80 and len(i) > 1]
        if len(items) > 1:
            return items

    # Separar por comas (puede venir con quotes individuales: 'cosa', 'otra')
    if "," in texto:
        items = [i.strip().strip("'\"").rstrip(".,;") for i in texto.split(",") if i.strip()]
        items = [_limpiar_kw(i) for i in items if i.strip()]
        items = [i for i in items if len(i) < 80]
        if items:
            return items

    # Separar por saltos de línea
    items = [_limpiar_kw(i) for i in texto.split("\n") if i.strip()]
    items = [i for i in items if len(i) < 80]
    if len(items) > 1:
        return items

    # Si solo queda un item largo, no es keyword - devolver vacío o el texto
    if len(items) == 1 and len(items[0]) > 60:
        return []
    if items:
        return items

    # Si todo falla, tratar como texto único
    return [_limpiar_kw(texto)]


def _limpiar_kw(palabra: str) -> str:
    """Limpia una keyword individual de caracteres no deseados."""
    return palabra.strip().strip("'\"").rstrip(".,;!?¿¡").strip()


# ---- CLI ----
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Analizar imágenes con modelos de visión Ollama"
    )
    parser.add_argument("imagenes", nargs="+", help="Rutas a las imágenes")
    parser.add_argument("--modelo", default="moondream:latest",
                        choices=["moondream:latest", "qwen2.5vl:latest",
                                 "qwen2.5vl:3b", "llama3.2-vision:latest",
                                 "gemma4:e4b"],
                        help="Modelo de visión")
    parser.add_argument("--action", default="keywords",
                        choices=["keywords", "describir", "clasificar"],
                        help="Acción a realizar")
    parser.add_argument("--json", help="Exportar resultados a JSON")

    args = parser.parse_args()

    for ruta in args.imagenes:
        if not Path(ruta).exists():
            print(f"ERROR: No existe: {ruta}")
            continue

        try:
            if args.action == "keywords":
                keywords = extraer_keywords(ruta, modelo=args.modelo)
                print(f"\n{ruta}")
                print(f"  Keywords: {', '.join(keywords)}")

            elif args.action == "describir":
                desc = describir_imagen(ruta, modelo=args.modelo)
                print(f"\n{ruta}")
                print(f"  Descripción: {desc}")

            elif args.action == "clasificar":
                cat = clasificar_imagen(ruta, modelo=args.modelo)
                print(f"\n{ruta}")
                print(f"  Categoría: {cat}")

        except Exception as e:
            print(f"ERROR en {ruta}: {e}")
