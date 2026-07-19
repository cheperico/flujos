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

# ──────────────────────────────────────────────
#  LISTA CONTROLADA DE GÉNEROS FOTOGRÁFICOS
# ──────────────────────────────────────────────
# El modelo SOLO puede elegir de acá. Si devuelve algo fuera,
# se reemplaza por "otras" en post-procesamiento.
GENEROS_FOTOGRAFICOS = [
    "retrato",
    "retrato grupal",
    "paisaje",
    "nocturna",
    "macro",
    "arquitectura",
    "documento",
    "callejera",
    "naturaleza",
    "abstracto",
    "deporte",
    "comida",
    "objeto",
    "urbano",
    "evento",
    "animales",
    "otras",
]

_GENEROS_STR = (
    "retrato, retrato grupal (varias personas), paisaje, nocturna, macro, "
    "arquitectura (edificios), documento (fotografía documental), "
    "callejera (street photography), naturaleza (flora/fauna), abstracto, "
    "deporte, comida, objeto (bodegón/producto), urbano (entorno ciudad), "
    "evento (fiestas/conciertos), animales, otras"
)

# ──────────────────────────────────────────────
#  MODELO POR DEFECTO
# ──────────────────────────────────────────────
# Se puede cambiar según la máquina:
#   - moondream:latest  → rápido, liviano (1.7 GB), ideal para PCs modestas
#   - qwen2.5vl:latest  → más calidad, más lento (6 GB)
#   - qwen2.5vl:3b      → balance (3.2 GB)
MODELO_VISION_DEFAULT = "moondream:latest"

# ──────────────────────────────────────────────
#  PROMPTS
# ──────────────────────────────────────────────

PROMPT_KEYWORDS = (
    "Analizá esta imagen y devolvé únicamente una lista de 5 a 7 palabras clave "
    "en español que describan su contenido. "
    "La PRIMERA palabra clave debe ser el género fotográfico de la imagen. "
    "Elegí UNICAMENTE de esta lista, NO inventes: "
    + _GENEROS_STR + ". "
    "Si ningún género encaja bien, elegí 'otras'. "
    "Las siguientes (2 a 6) deben describir elementos, colores, escena. "
    "Separalas con comas. No incluyas explicación ni ningún otro texto. "
    "Ejemplo: 'paisaje, montaña, lago, atardecer, bosque, cielo, reflejo'"
)

PROMPT_DESCRIBIR = (
    "Describí esta imagen en UNA oración en español, empezando por el sujeto principal. "
    "No uses frases como 'la imagen muestra', 'la foto presenta', 'en esta imagen se ve' "
    "ni ningún otro encabezado. Arrancá directo: 'Un perro...', 'Dos personas...', "
    "'Un paisaje...', etc. Incluí elementos principales, colores y acción si la hay."
)

PROMPT_COMBINADO = (
    "Analizá esta imagen y devolvé únicamente un JSON con dos campos:\n"
    '1. "keywords": una lista de 5 a 7 palabras clave en español.\n'
    "   La PRIMERA debe ser el género fotográfico. "
    "Elegí UNICAMENTE de esta lista, NO inventes: "
    + _GENEROS_STR + ".\n"
    "   Si ningún género encaja bien, elegí 'otras'.\n"
    '   Las siguientes describen elementos, colores, escena.\n'
    '2. "description": UNA oración en español, arrancando por el sujeto principal. '
    "No uses frases como 'la imagen muestra' ni similares. "
    "Incluí elementos principales, colores y acción.\n\n"
    'Formato exacto: {"keywords": ["paisaje", "montaña", "lago"], "description": "Un lago rodeado de montañas bajo un cielo despejado."}\n'
    "No incluyas nada más que el JSON."
)

PROMPT_CLASIFICAR = (
    "Clasificá esta imagen en una de estas categorías: "
    "naturaleza, urbano, retrato, abstracto, documento, evento, paisaje, arquitectura, "
    "objeto, arte, comida, tecnología, deporte, noche, macro, otras. "
    "Respondé solo con el nombre de la categoría."
)


# ──────────────────────────────────────────────
#  VALIDACIÓN DE GÉNERO
# ──────────────────────────────────────────────

def _validar_genero(keywords: list[str]) -> list[str]:
    """
    Verifica que la primera keyword (el género fotográfico) esté dentro
    de GENEROS_FOTOGRAFICOS. Si no, intenta mapearla o la reemplaza por "otras".

    También limpia cualquier texto entre paréntesis que el modelo pudiera
    repetir del prompt (ej: "retrato grupal (varias personas)" → "retrato grupal").

    Args:
        keywords: Lista de keywords extraídas por el modelo.

    Returns:
        Lista de keywords con el género validado.
    """
    if not keywords:
        return keywords

    genero_raw = keywords[0].strip().lower()

    # Limpiar texto entre paréntesis (el modelo a veces repite la descripción)
    if "(" in genero_raw:
        genero_raw = genero_raw[:genero_raw.index("(")].strip()
        keywords[0] = genero_raw

    # Búsqueda exacta (case-insensitive)
    for valido in GENEROS_FOTOGRAFICOS:
        if genero_raw == valido.lower():
            keywords[0] = valido
            return keywords

    # Búsqueda aproximada: contener o ser contenido
    for valido in GENEROS_FOTOGRAFICOS:
        v = valido.lower()
        if genero_raw in v or v in genero_raw:
            keywords[0] = valido
            logger.info("  -> Género mapeado: '%s' → '%s'", genero_raw, valido)
            return keywords

    # No se encontró match → reemplazar por "otras"
    logger.warning(
        "  -> Género '%s' no reconocido, reemplazado por 'otras'",
        genero_raw
    )
    keywords[0] = "otras"
    return keywords


def extraer_keywords(
    ruta_imagen: str,
    modelo: str = MODELO_VISION_DEFAULT,
    temperatura: float = 0.2,
    usar_proxy: bool = True,
) -> list[str]:
    """
    Analiza una imagen y devuelve 5-7 palabras clave en español.

    Args:
        ruta_imagen: Ruta al archivo de imagen.
        modelo: Modelo de visión a usar. Por defecto MODELO_VISION_DEFAULT.
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

    # Validar que el género esté en la lista controlada
    keywords = _validar_genero(keywords)

    logger.info("Keywords extraídas de %s: %s", Path(ruta_imagen).name, keywords)
    return keywords


def extraer_keywords_batch(
    rutas_imagenes: list[str],
    modelo: str = MODELO_VISION_DEFAULT,
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
            keywords = _validar_genero(keywords)
            resultados.append({
                "ruta": ruta_orig,
                "keywords": keywords,
                "error": None,
            })

    return resultados


def describir_imagen(
    ruta_imagen: str,
    modelo: str = MODELO_VISION_DEFAULT,
    temperatura: float = 0.3,
    usar_proxy: bool = True,
) -> str:
    """
    Genera una descripción en lenguaje natural de una imagen.

    Args:
        ruta_imagen: Ruta al archivo de imagen.
        modelo: Modelo de visión (por defecto moondream).
        temperatura: Control de creatividad.
        usar_proxy: Si True, usa proxy redimensionado.

    Returns:
        Descripción textual de la imagen.
    """
    ruta_proxy = obtener_proxy(ruta_imagen, usar_proxy=usar_proxy)
    cliente = OllamaVision(modelo=modelo)
    return cliente.analizar_imagen(ruta_proxy, PROMPT_DESCRIBIR, temperatura)


def analizar_imagen_completo(
    ruta_imagen: str,
    modelo: str = MODELO_VISION_DEFAULT,
    temperatura: float = 0.2,
    usar_proxy: bool = True,
) -> dict:
    """
    Analiza una imagen con UNA sola llamada a la IA y devuelve
    tanto keywords como descripción.

    Usa PROMPT_COMBINADO que pide un JSON con ambos campos.

    Args:
        ruta_imagen: Ruta al archivo de imagen.
        modelo: Modelo de visión (por defecto moondream).
        temperatura: Control de creatividad.
        usar_proxy: Si True, usa proxy redimensionado.

    Returns:
        Dict con:
          { "keywords": [str, ...], "description": str }

    Raises:
        FileNotFoundError: Si la imagen no existe.
        ValueError: Si no se pudo parsear el JSON de respuesta.
    """
    ruta_proxy = obtener_proxy(ruta_imagen, usar_proxy=usar_proxy)
    cliente = OllamaVision(modelo=modelo)

    respuesta = cliente.analizar_imagen(
        ruta_proxy,
        prompt=PROMPT_COMBINADO,
        temperatura=temperatura,
    )

    resultado = _parsear_combinado(respuesta)

    if resultado is None:
        logger.warning(
            "No se pudo parsear respuesta combinada de: %s. Respuesta: %s",
            ruta_imagen, respuesta
        )
        # Fallback: tratar de parsear keywords y descripción por separado
        keywords = _parsear_keywords(respuesta)
        keywords = _validar_genero(keywords)
        return {
            "keywords": keywords,
            "description": respuesta.strip(),
        }

    # Validar género en keywords
    resultado["keywords"] = _validar_genero(resultado.get("keywords", []))

    logger.info(
        "Análisis completo de %s: %d keywords, %d chars descripción",
        Path(ruta_imagen).name,
        len(resultado.get("keywords", [])),
        len(resultado.get("description", ""))
    )
    return resultado


def analizar_imagen_completo_batch(
    rutas_imagenes: list[str],
    modelo: str = MODELO_VISION_DEFAULT,
    temperatura: float = 0.2,
    usar_proxy: bool = True,
) -> list[dict]:
    """
    Analiza múltiples imágenes con UNA sola llamada a la IA cada una
    y devuelve keywords y descripción.

    Args:
        rutas_imagenes: Lista de rutas a imágenes.
        modelo: Modelo de visión.
        temperatura: Control de creatividad.
        usar_proxy: Si True, usa proxies redimensionados.

    Returns:
        Lista de dicts con {"ruta", "keywords", "description", "error"}.
    """
    if usar_proxy:
        rutas_proxy = [(r, obtener_proxy(r)) for r in rutas_imagenes]
    else:
        rutas_proxy = [(r, r) for r in rutas_imagenes]

    rutas_proxy_solo = [p for _, p in rutas_proxy]

    cliente = OllamaVision(modelo=modelo)
    resultados_vision = cliente.analizar_imagenes(
        rutas_proxy_solo,
        prompt=PROMPT_COMBINADO,
        temperatura=temperatura,
    )

    resultados = []
    for (ruta_orig, _), item in zip(rutas_proxy, resultados_vision):
        if item["error"]:
            resultados.append({
                "ruta": ruta_orig,
                "keywords": [],
                "description": "",
                "error": item["error"],
            })
        else:
            parsed = _parsear_combinado(item["respuesta"])
            if parsed is None:
                keywords = _parsear_keywords(item["respuesta"])
                keywords = _validar_genero(keywords)
                resultados.append({
                    "ruta": ruta_orig,
                    "keywords": keywords,
                    "description": item["respuesta"].strip(),
                    "error": None,
                })
            else:
                keywords = _validar_genero(parsed.get("keywords", []))
                resultados.append({
                    "ruta": ruta_orig,
                    "keywords": keywords,
                    "description": parsed.get("description", ""),
                    "error": None,
                })

    return resultados


def _parsear_combinado(respuesta: str) -> Optional[dict]:
    """
    Parsea la respuesta JSON del prompt combinado.

    Espera: {"keywords": [...], "description": "..."}
    Puede venir dentro de bloques ```json ... ```.

    Returns:
        Dict con "keywords" y "description", o None si falla.
    """
    texto = respuesta.strip()

    # Limpiar bloques de código Markdown
    texto = re.sub(r"^```(?:json)?\s*\n?", "", texto)
    texto = re.sub(r"\n?```\s*$", "", texto)
    texto = texto.strip()

    # Intentar parsear como JSON
    # A veces el modelo usa comillas simples
    for attempt in [texto, texto.replace("'", '"')]:
        try:
            datos = json.loads(attempt)
            if isinstance(datos, dict):
                keywords = datos.get("keywords", [])
                description = datos.get("description", "")
                # Asegurar tipos
                if isinstance(keywords, str):
                    # Vino como string "paisaje, montaña" en vez de lista
                    keywords = _parsear_keywords(keywords)
                elif not isinstance(keywords, list):
                    keywords = [str(keywords)]
                if not isinstance(description, str):
                    description = str(description)
                return {"keywords": keywords, "description": description}
        except (json.JSONDecodeError, TypeError):
            continue

    # Si no se pudo parsear, buscar keywords con _parsear_keywords y descripción en el resto
    lines = texto.split("\n")
    keywords_line = None
    for line in lines:
        low = line.strip().lower()
        if "keywords" in low or "palabras" in low or "keyword" in low:
            keywords_line = line
            break

    if keywords_line:
        # Intentar extraer lista
        kw = _parsear_keywords(keywords_line)
        if kw:
            desc = texto.strip()
            return {"keywords": kw, "description": desc}

    return None


def clasificar_imagen(
    ruta_imagen: str,
    modelo: str = MODELO_VISION_DEFAULT,
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
      - "```json\\n[...]\\n```" (Markdown code block)
    """
    # Limpiar
    texto = respuesta.strip().strip("'\"")

    # Limpiar bloques de código Markdown (```json ... ```, ``` ... ```)
    texto = re.sub(r"^```(?:json|python)?\s*\n?", "", texto)
    texto = re.sub(r"\n?```\s*$", "", texto)
    texto = texto.strip()

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
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Analizar imágenes con modelos de visión Ollama"
    )
    parser.add_argument("imagenes", nargs="+", help="Rutas a las imágenes")
    # Opciones generales
    parser.add_argument("--modelo", default=MODELO_VISION_DEFAULT,
                        help=f"Modelo de visión Ollama. (default: {MODELO_VISION_DEFAULT})")
    parser.add_argument("--list-models", action="store_true",
                        help="Mostrar modelos Ollama instalados y salir")
    parser.add_argument("--action", default="keywords",
                        choices=["keywords", "describir", "clasificar", "combinado"],
                        help="Acción a realizar. 'combinado' hace keywords + descripción en una sola llamada")
    parser.add_argument("--json", help="Exportar resultados a JSON")

    args = parser.parse_args()

    if args.list_models:
        try:
            import ollama
            response = ollama.list()
            if hasattr(response, "models"):
                modelos = response.models
            elif isinstance(response, dict):
                modelos = response.get("models", [])
            else:
                modelos = list(response)
            print("=== Modelos instalados en Ollama ===\n")
            for m in modelos:
                nombre = m.model if hasattr(m, "model") else str(m)
                print(f"  {nombre}")
            print()
        except Exception as e:
            print(f"Error al conectar con Ollama: {e}")
        sys.exit(0)

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

            elif args.action == "combinado":
                resultado = analizar_imagen_completo(ruta, modelo=args.modelo)
                print(f"\n{ruta}")
                print(f"  Keywords: {', '.join(resultado['keywords'])}")
                print(f"  Descripción: {resultado['description']}")

        except Exception as e:
            print(f"ERROR en {ruta}: {e}")
