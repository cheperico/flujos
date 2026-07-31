#!/usr/bin/env python3
"""
refinar_keywords.py — Refina y unifica las keywords generadas por IA.

Toma los valores de `media_metadata.ia_keywords` ya generados y los limpia
en 3 capas:

  1. LÉXICA (siempre, sin IA)
     - minúsculas, limpieza de caracteres raros
     - plural → singular (bicicletas → bicicleta)
     - quitar artículos / ruido ("la", "el", "un", "una")
     - descartar keywords inválidas (len < 3, valores tipo prompt, etc.)

  2. DICCIONARIO (siempre, determinístico)
     - Sinónimos explícitos del dominio (bici → bicicleta, moto → motocicleta)
     - El canónico es el término más "estándar" del grupo

  3. SEMÁNTICA (--usar-embeddings, opcional)
     - Embeddings con paraphrase-multilingual:latest (entrenado para sinónimos)
     - Agrupa keywords con similitud coseno ≥ umbral (default 0.82)
     - El canónico de cada grupo = el término más frecuente en la DB

Después de refinar, reescribe `media_metadata.ia_keywords` con los valores
canónicos, deduplicando y manteniendo el género fotográfico en primer lugar.

Uso:
    python scripts/ai_media/refinar_keywords.py                 # solo léxico + diccionario
    python scripts/ai_media/refinar_keywords.py --usar-embeddings   # + capa semántica
    python scripts/ai_media/refinar_keywords.py --dry-run       # previsualizar sin escribir
    python scripts/ai_media/refinar_keywords.py --mode update   # reprocesa todos

Modos (igual que el resto del pipeline):
    skip    → solo registros con ia_keywords ya presentes (default)
    update  → reprocesa todos los registros con ia_keywords
    replace → limpia y regenera (equivalente a update para este script)
"""

import argparse
import json
import logging
import math
import os
import re
import sqlite3
import sys
from collections import Counter

log = logging.getLogger(__name__)

# ── Modelo de embeddings para sinónimos ─────────────────────────────────────
# paraphrase-multilingual:latest está entrenado específicamente para detectar
# si dos textos significan lo mismo (paráfrasis). Multilingüe (español OK).
MODELO_EMBEDDINGS = "paraphrase-multilingual:latest"

# ── Diccionario de sinónimos del dominio (bici, viaje, Argentina) ───────────
# Clave = canónico, valor = lista de variantes que se unifican al canónico.
SINONIMOS: dict[str, list[str]] = {
    "bicicleta": ["bici", "bicicletas", "bike", "bici de montaña", "mtb", "mountain bike"],
    "motocicleta": ["moto", "motocicletas", "moto de enduro", "motomel"],
    "automóvil": ["auto", "autos", "coche", "coches", "camioneta", "camionetas", "vehículo", "vehiculo"],
    "ruta": ["carretera", "caminos", "camino", "autopista", "autovía", "ruta nacional", "ruta 9"],
    "montaña": ["montañas", "cerro", "cerros", "sierra", "sierras", "cordillera", "cordilleras"],
    "atardecer": ["puesta de sol", "ocaso", "anochecer", "atardeceres"],
    "amanecer": ["salida del sol", "alba", "aurora", "amaneceres"],
    "ciudad": ["ciudades", "pueblo", "pueblos", "zona urbana"],
    "naturaleza": ["campo", "paisaje natural"],
    "bosque": ["bosques", "selva", "arboleda"],
    "árbol": ["arboles", "arbol", "árboles", "plantas"],
    "animales": ["animal", "vaca", "vacas", "caballo", "caballos", "perro", "perros",
                 "gato", "gatos", "oveja", "ovejas", "burro", "burros", "ganado"],
    "comida": ["gastronomía", "comidas", "plato", "platos", "almuerzo", "cena", "desayuno", "asado"],
    "personas": ["persona", "gente", "hombres", "mujeres", "ciclista", "ciclistas",
                 "caminante", "caminantes", "viajero", "viajeros", "baqueano"],
    "deporte": ["deportes", "ciclismo", "competición", "carrera"],
    "viaje": ["trayecto", "recorrido", "ruta viajera"],
    "fotografía": ["foto", "fotos", "imagen", "imágenes", "retrato fotográfico"],
    "urbanismo": ["edificios", "edificio", "rascacielos", "construcción"],
    "arquitectura": ["edificaciones", "fachada", "fachadas"],
    "noche": ["nocturna", "nocturno", "noche estrellada"],
    "cielo": ["cielos", "nubes", "cielo azul", "horizonte"],
    "lluvia": ["lluvioso", "tormenta", "tormentas", "llovizna"],
    "frío": ["frio", "helada", "escarcha"],
    "calor": ["sol intenso", "sequía", "caluroso"],
    "música": ["musica", "banda", "recital", "show", "concierto", "tocar"],
    "arte": ["pintura", "mural", "murales", "graffiti"],
    "abuela": ["abuelita", "anciana", "abuelo", "anciano"],
    "niño": ["niños", "nene", "nenes", "chico", "chicos", "pequeño"],
    "amigo": ["amigos", "compañero", "compañeros", "compañera"],
    "felicidad": ["alegría", "sonrisa", "sonrisas", "risa", "risas"],
    "cansancio": ["fatiga", "agotamiento"],
    "mochila": ["mochilas", "equipaje", "alforjas", "alforja", "bolso", "bolsos"],
    "carpas": ["carpa", "campamento", "acampar", "campaña"],
    "comida_argentina": ["empanadas", "asado", "milanesa", "locro", "mate", "dulce de leche"],
    "mate": ["yerba", "termo"],
}

# Palabras tan genéricas que no aportan (se descartan si no son género)
STOPWORDS = {
    "la", "el", "los", "las", "un", "una", "unos", "unas", "de", "del", "y",
    "en", "con", "por", "para", "que", "es", "se", "su", "al", "lo", "a",
    "the", "and", "of", "to", "in", "imagen", "foto", "fotografía", "fotografía",
    "este", "esta", "eso", "esa", "una escena", "escena", "otro", "otra",
}

# Patrones de ruido del modelo (cuando regurgitó el prompt en vez de keywords)
PATRONES_BASURA = [
    r"g[eé]nero fotogr[aá]fico",
    r"elige una",
    r"deben describir",
    r"no incluyas",
    r"ejemplo",
    r"ning[uú]n otro texto",
    r"separa",
    r"palabra clave",
    r"this is",
    r"spanish",
    r"primera palabra",
    r"^\.\.\.$",
    r"no inventes",
    r"separ[aá]las",
    r"no incluesas",
    r"^sa_\d+$",           # nombres de archivo Sony (sa_20001)
    r"^dsc\d+",            # nombres de archivo DSC
    r"^\d+x\d+$",          # resoluciones
    r"^\d+\s*[a-z]",
]

# Mezcla de géneros en una sola keyword (ej: "retrato grupal paisaje") — es ruido
def _tiene_mezcla_generos(palabra: str) -> bool:
    """Detecta si una keyword contiene 2+ géneros distintos (ruido del modelo).

    Ej: "retrato grupal paisaje" → sí (retrato grupal + paisaje).
        "retrato grupal" → no (solo 1 género; "retrato" es subcadena de "retrato grupal").
    """
    p = palabra.lower()
    encontrados = set()
    for g in sorted(GENEROS_FOTOGRAFICOS, key=len, reverse=True):
        if g.lower() in p:
            encontrados.add(g)
    # Quitar géneros que son subcadena de otro ya encontrado (ej: "retrato" ⊂ "retrato grupal")
    a_quitar = set()
    for g1 in encontrados:
        for g2 in encontrados:
            if g1 != g2 and g1.lower() in g2.lower():
                a_quitar.add(g1)
    encontrados -= a_quitar
    return len(encontrados) >= 2

# Géneros fotográficos válidos (mismo set que image_analysis.py)
GENEROS_FOTOGRAFICOS = [
    "retrato", "retrato grupal", "paisaje", "nocturna", "macro",
    "arquitectura", "documento", "callejera", "naturaleza", "abstracto",
    "deporte", "comida", "objeto", "urbano", "evento", "animales", "otras",
]

# Mapeo de variantes de género → género canónico
VARIANTES_GENERO = {
    "nocturno": "nocturna",
    "nocturnas": "nocturna",
    "arquitectónico": "arquitectura",
    "street": "callejera",
    "street photography": "callejera",
    "documental": "documento",
    "fotografía documental": "documento",
    "bodegón": "objeto",
    "producto": "objeto",
    "paisajes": "paisaje",
    "macros": "macro",
    "retratos": "retrato",
    "urbanas": "urbano",
    "urbanos": "urbano",
    "animal": "animales",
    "fiesta": "evento",
    "concierto": "evento",
    "comidas": "comida",
    "gastronomía": "comida",
    "deportes": "deporte",
    "ciclismo": "deporte",
}


def normalizar_palabra(palabra: str) -> str:
    """Capa léxica: limpia una keyword individual."""
    p = palabra.strip().lower().strip("'\",.;:!?¿¡()[]").strip()
    # Quitar cualquier resto de prompt entre paréntesis
    if "(" in p:
        p = p[:p.index("(")].strip()
    if "..." in p:
        p = p.split("...")[0].strip()
    # Quitar artículos iniciales ("la montaña" → "montaña")
    p = re.sub(r"^(la|el|los|las|un|una|unos|unas)\s+", "", p)
    # Quitar comillas restantes
    p = p.strip("'\",.;:")
    return p


def es_basura(palabra: str) -> bool:
    """Detecta si una keyword es ruido (regurgitación del prompt, etc.)."""
    p = palabra.lower()
    for pat in PATRONES_BASURA:
        if re.search(pat, p):
            return True
    if len(p) < 3:
        return True
    if p in STOPWORDS:
        return True
    if _tiene_mezcla_generos(p):
        return True
    return False


def singularizar(palabra: str) -> str:
    """Plural → singular simple (bicicletas → bicicleta, árboles → árbol)."""
    if not palabra or len(palabra) < 4:
        return palabra
    # -es: árboles → árbol, peces → pez (pero no "res", "nes", "les" que son parte de raíz)
    if palabra.endswith("es") and len(palabra) > 5 and not palabra.endswith(("res", "nes", "les")):
        return palabra[:-2]
    # -s tras vocal: montañas → montaña, perros → perro, autos → auto
    if palabra.endswith("s") and len(palabra) > 3 and palabra[-2] in "aeiouáéíóú":
        return palabra[:-1]
    return palabra


def aplicar_sinonimos(palabra: str) -> str:
    """Capa diccionario: devuelve el canónico si la palabra es una variante."""
    p = palabra.lower()
    for canonico, variantes in SINONIMOS.items():
        if canonico and p == canonico.lower():
            return canonico
        if p in [v.lower() for v in variantes if v]:
            return canonico
    return palabra


def similitud_coseno(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def es_genero(palabra: str) -> str | None:
    """
    Devuelve el género fotográfico canónico si la palabra es un género válido
    (o variante conocida). None si no es género.
    """
    p = palabra.strip().lower()
    # Exacto
    for g in GENEROS_FOTOGRAFICOS:
        if p == g.lower():
            return g
    # Variante conocida
    if p in VARIANTES_GENERO:
        return VARIANTES_GENERO[p]
    # Contenido aproximado (evita falsos positivos con palabras cortas)
    for g in GENEROS_FOTOGRAFICOS:
        if len(p) >= 4 and (p in g or g in p):
            return g
    return None


def refinar_lista_keywords(keywords: list[str]) -> list[str]:
    """
    Aplica capas léxica + diccionario a una lista de keywords.
    Conserva el género (primer elemento) si es válido, y garantiza que
    el resultado SIEMPRE tenga un género al inicio (default 'otras').

    Args:
        keywords: Lista de keywords extraídas por el modelo.

    Returns:
        Lista de keywords refinadas con género validado al inicio.
    """
    if not keywords:
        return ["otras"]

    # Normalizar todas
    norm = [normalizar_palabra(k) for k in keywords]
    # Filtrar basura
    norm = [n for n in norm if n and not es_basura(n)]

    # Buscar género: primero en posición 0, luego en cualquier posición
    genero: str | None = None
    resto: list[str] = []
    # 1er intento: la primera keyword normalizada
    if norm:
        g = es_genero(norm[0])
        if g:
            genero = g
            resto = norm[1:]
        else:
            resto = norm[1:]
            # Buscar género dentro del resto (qwen a veces pone el sujeto primero)
            for i, kw in enumerate(resto):
                g = es_genero(kw)
                if g:
                    genero = g
                    resto.pop(i)
                    break

    # Si no hay género → "otras"
    if genero is None:
        genero = "otras"

    # Singularizar y aplicar sinónimos al resto
    # (los géneros duplicados del resto se descartan — el género principal ya se eligió)
    resto = [r for r in resto if es_genero(r) is None]
    resto = [singularizar(r) for r in resto]
    resto = [aplicar_sinonimos(r) for r in resto]
    resto = [r for r in resto if r and not es_basura(r)]

    # Quitar duplicados preservando orden
    vistos = set()
    resto_uniq = []
    for r in resto:
        if r not in vistos and r != genero:
            vistos.add(r)
            resto_uniq.append(r)

    # Reconstruir: género primero, luego el resto (máx 6 = total 7)
    return [genero] + resto_uniq[:6]


def refinar_con_embeddings(keywords_unicas: list[str], umbral: float = 0.82,
                           frecuencias: Counter | None = None) -> dict[str, str]:
    """
    Capa semántica: agrupa keywords por similitud de embeddings y devuelve
    un mapeo {palabra_original → palabra_canónica}.

    Args:
        keywords_unicas: Lista de keywords únicas normalizadas.
        umbral: Similitud coseno mínima para considerar sinónimos.
        frecuencias: Contador de frecuencias para elegir el canónico
                     (el más frecuente gana).

    Returns:
        Dict palabra → canónico.
    """
    try:
        import ollama
    except ImportError:
        log.warning("  No se pudo importar ollama. Capa semántica desactivada.")
        return {}

    log.info("  Generando embeddings para %d keywords con %s...",
             len(keywords_unicas), MODELO_EMBEDDINGS)
    try:
        resp = ollama.embed(model=MODELO_EMBEDDINGS, input=keywords_unicas)
        embs = resp.get("embeddings", [])
    except Exception as e:
        log.warning("  Error generando embeddings: %s. Capa semántica desactivada.", e)
        return {}

    if not embs or len(embs) != len(keywords_unicas):
        log.warning("  Embeddings devueltos no coinciden (%d != %d). Capa semántica desactivada.",
                    len(embs), len(keywords_unicas))
        return {}

    # Agrupar por similitud: algoritmo de unión simple (greedy)
    grupos: list[list[str]] = []
    for i, kw in enumerate(keywords_unicas):
        emb = embs[i]
        encontrado = False
        for grupo in grupos:
            # Comparar contra el primer elemento del grupo (centroide aproximado)
            idx = keywords_unicas.index(grupo[0])
            if similitud_coseno(emb, embs[idx]) >= umbral:
                grupo.append(kw)
                encontrado = True
                break
        if not encontrado:
            grupos.append([kw])

    # Elegir canónico de cada grupo: el más frecuente, luego el más corto
    mapeo: dict[str, str] = {}
    for grupo in grupos:
        if len(grupo) == 1:
            mapeo[grupo[0]] = grupo[0]
            continue
        mejor = None
        mejor_score: tuple[int, int] | None = None
        for kw in grupo:
            freq = frecuencias.get(kw, 0) if frecuencias else 0
            score = (freq, -len(kw))  # más frecuente, y si empata, más corto
            if mejor_score is None or score > mejor_score:
                mejor_score = score
                mejor = kw
        for kw in grupo:
            mapeo[kw] = mejor

    # Log de grupos formados (para debug)
    for grupo in grupos:
        if len(grupo) > 1:
            log.info("    Grupo sinónimos: %s → %s", ", ".join(grupo), mapeo[grupo[0]])

    return mapeo


def obtener_keywords_db(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Lee todos los ia_keywords de la DB. Devuelve {media_id: [keywords]}."""
    filas = conn.execute(
        "SELECT media_id, value FROM media_metadata WHERE key = 'ia_keywords'"
    ).fetchall()
    resultado: dict[int, list[str]] = {}
    for mid, valor in filas:
        if not valor:
            continue
        # El valor puede ser string separado por comas o JSON array
        try:
            lista = json.loads(valor)
            if isinstance(lista, list):
                resultado[mid] = [str(x) for x in lista]
                continue
        except (json.JSONDecodeError, TypeError):
            pass
        # Formato string: "a, b, c"
        partes = [p.strip().strip("'\"").rstrip(".,;") for p in valor.split(",") if p.strip()]
        resultado[mid] = partes
    return resultado


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Refina y unifica keywords de IA (léxico + diccionario + embeddings)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None, help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="skip: solo los que tienen keywords (default) | update: todos | replace: igual que update")
    parser.add_argument("--usar-embeddings", action="store_true",
                        help="Activa la capa semántica con paraphrase-multilingual")
    parser.add_argument("--umbral", type=float, default=0.82,
                        help="Similitud mínima para agrupar sinónimos (default: 0.82)")
    parser.add_argument("--dry-run", action="store_true", help="Previsualizar cambios sin escribir")
    parser.add_argument("--verbose", action="store_true", help="Log detallado")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolver DB
    db_path = args.db
    if db_path is None:
        default_db = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "db", "flujos.db",
        )
        if os.path.isfile(default_db):
            db_path = default_db
        else:
            print("  No se encontró db/flujos.db. Especificá --db.")
            sys.exit(1)

    if not os.path.isfile(db_path):
        print(f"  ERROR: No existe la DB: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Leer keywords
    datos = obtener_keywords_db(conn)
    if not datos:
        print("  No hay ia_keywords en la DB. Nada que refinar.")
        conn.close()
        return

    log.info("  Registros con ia_keywords: %d", len(datos))

    # --- Paso 1: extraer todas las keywords únicas y sus frecuencias ---
    todas = []
    for lista in datos.values():
        todas.extend(lista)
    counter = Counter(t.lower() for t in todas)
    log.info("  Keywords totales (con duplicados): %d | únicas: %d",
             len(todas), len(counter))

    # --- Paso 2: aplicar capa léxica + diccionario a nivel de cada registro ---
    refinadas: dict[int, list[str]] = {}
    for mid, lista in datos.items():
        refinadas[mid] = refinar_lista_keywords(lista)

    # --- Paso 3 (opcional): capa semántica sobre keywords únicas ---
    mapeo_semantico: dict[str, str] = {}
    if args.usar_embeddings:
        # Keywords únicas después de la capa léxica/diccionario (para no embeddear ruido)
        unicas_post = set()
        for lista in refinadas.values():
            unicas_post.update(lista)
        unicas_post = sorted(unicas_post)
        if unicas_post:
            # Frecuencias post-refinamiento (para elegir canónico)
            freq_post: Counter = Counter()
            for lista in refinadas.values():
                freq_post.update(lista)
            mapeo_semantico = refinar_con_embeddings(
                unicas_post, umbral=args.umbral, frecuencias=freq_post)
            # Aplicar mapeo
            for mid in refinadas:
                refinadas[mid] = [mapeo_semantico.get(k, k) for k in refinadas[mid]]
                # Dedupe final preservando orden
                vistos = set()
                refinadas[mid] = [k for k in refinadas[mid]
                                  if not (k in vistos or vistos.add(k))]

    # --- Paso 4: comparar y mostrar cambios ---
    cambios = 0
    sin_cambios = 0
    for mid in list(refinadas.keys()):
        if refinadas[mid] == datos.get(mid, []):
            sin_cambios += 1
        else:
            cambios += 1

    log.info("  Registros con cambios: %d | sin cambios: %d", cambios, sin_cambios)

    if args.dry_run:
        print("\n  [DRY-RUN] Cambios propuestos (máx 10):")
        mostrados = 0
        for mid, nueva in refinadas.items():
            if nueva != datos.get(mid, []):
                print(f"\n  media {mid}:")
                print(f"    ANTES: {datos.get(mid, [])}")
                print(f"    DESPUÉS: {nueva}")
                mostrados += 1
                if mostrados >= 10:
                    break
        print(f"\n  Total con cambios: {cambios}")
        conn.close()
        return

    # --- Paso 5: escribir en DB ---
    if not args.dry_run and cambios:
        # Guardar backup previo en memoria (no en DB, por si acaso)
        # Actualizar registros
        conn.execute("BEGIN")
        try:
            for mid, nueva in refinadas.items():
                valor_nuevo = ", ".join(nueva)
                conn.execute(
                    "UPDATE media_metadata SET value = ? WHERE media_id = ? AND key = 'ia_keywords'",
                    (valor_nuevo, mid),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.error("  Error escribiendo en DB: %s", e)
            conn.close()
            sys.exit(1)

        log.info("  ✅ Keywords refinadas: %d registros actualizados", cambios)

        # Mostrar ejemplo de un registro con cambios
        for mid, nueva in refinadas.items():
            if nueva != datos.get(mid, []):
                print(f"\n  Ejemplo media {mid}:")
                print(f"    ANTES: {datos.get(mid, [])}")
                print(f"    DESPUÉS: {nueva}")
                break

    elif not cambios:
        print("  Nada que cambiar (ya estaban refinadas).")

    conn.close()


if __name__ == "__main__":
    main()
