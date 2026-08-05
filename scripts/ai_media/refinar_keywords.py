#!/usr/bin/env python3
"""
refinar_keywords.py — Refina y unifica las keywords generadas por IA.

Toma los valores de `media_metadata.ia_keywords` ya generados y los limpia
en 2 capas:

  1. LÉXICA (siempre, sin IA)
     - minúsculas, limpieza de caracteres raros
     - plural → singular (bicicletas → bicicleta)
     - quitar artículos / ruido ("la", "el", "un", "una")
     - descartar keywords inválidas (len < 3, valores tipo prompt, etc.)

  2. DICCIONARIO (siempre, determinístico)
     - Sinónimos explícitos del dominio (bici → bicicleta, moto → motocicleta)
     - El canónico es el término más "estándar" del grupo

(Nota: la capa SEMÁNTICA con embeddings fue ELIMINADA en Ago 2026. Los
embeddings de paraphrase-multilingual generaban falsos sinónimos que
degradaban términos específicos del dominio, por ejemplo ciclismo→deporte,
nublado→soleado, parche→parque. La traducción con translategemma ya produce
keywords limpias y consistentes, así que la unificación por embeddings no
aportaba y podía meter errores.)

Después de refinar, reescribe `media_metadata.ia_keywords` con los valores
canónicos, deduplicando y manteniendo el género fotográfico en primer lugar.

Uso:
    python scripts/ai_media/refinar_keywords.py                 # léxico + diccionario
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
import os
import re
import sqlite3
import sys
from collections import Counter

log = logging.getLogger(__name__)

# Permitir ejecución standalone: agregar raíz del proyecto al path
# (el TUI lo ejecuta como script suelto, donde 'scripts' no es un paquete
# importable; sin esto `from scripts.ai_media.checkpoint import ...` falla con
# ModuleNotFoundError). Mismo patrón que los demás scripts de ai_media/.
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )

# ── Diccionario de sinónimos del dominio (bici, viaje, Argentina) ───────────
# Clave = canónico, valor = lista de variantes que se unifican al canónico.
# Incluye variantes EN del pipeline IA (los modelos de visión responden en
# inglés; la traducción a ES puede dejar alguna palabra sin traducir, y este
# diccionario la recupera en el refinamiento).
SINONIMOS: dict[str, list[str]] = {
    "bicicleta": ["bici", "bicicletas", "bike", "bicycle", "bicycles", "bici de montaña", "mtb", "mountain bike", "cycling"],
    "motocicleta": ["moto", "motocicletas", "moto de enduro", "motomel", "motorcycle"],
    "automóvil": ["auto", "autos", "coche", "coches", "camioneta", "camionetas", "vehículo", "vehiculo", "car", "vehicle"],
    "ruta": ["carretera", "caminos", "camino", "autopista", "autovía", "ruta nacional", "ruta 9", "road", "highway"],
    "montaña": ["montañas", "cerro", "cerros", "sierra", "sierras", "cordillera", "cordilleras", "mountain", "mountains"],
    "atardecer": ["puesta de sol", "ocaso", "anochecer", "atardeceres", "sunset"],
    "amanecer": ["salida del sol", "alba", "aurora", "amaneceres", "sunrise"],
    "ciudad": ["ciudades", "pueblo", "pueblos", "zona urbana", "city", "town"],
    "naturaleza": ["campo", "paisaje natural", "nature", "outdoor"],
    "bosque": ["bosques", "selva", "arboleda", "forest"],
    "árbol": ["arboles", "arbol", "árboles", "plantas", "tree", "branch", "rama", "ramas", "branches"],
    "animales": ["animal", "vaca", "vacas", "caballo", "caballos", "perro", "perros",
                 "gato", "gatos", "oveja", "ovejas", "burro", "burros", "ganado", "animals"],
    "comida": ["gastronomía", "comidas", "plato", "platos", "almuerzo", "cena", "desayuno", "asado", "food"],
    "personas": ["persona", "gente", "hombres", "mujeres",
                 "caminante", "caminantes", "viajero", "viajeros", "baqueano", "people"],
    "deporte": ["deportes", "competición", "carrera", "sport"],
    "ciclismo": ["ciclista", "ciclistas", "cycling", "cyclist", "cyclists", "pedaleando"],
    "viaje": ["trayecto", "recorrido", "ruta viajera", "trip", "adventure", "aventura", "road trip", "viaje en ruta"],
    "fotografía": ["foto", "fotos", "imagen", "imágenes", "retrato fotográfico", "photography"],
    "urbanismo": ["edificios", "edificio", "rascacielos", "construcción", "buildings"],
    "arquitectura": ["edificaciones", "fachada", "fachadas", "architecture"],
    "noche": ["nocturna", "nocturno", "noche estrellada", "night"],
    "cielo": ["cielos", "nubes", "cielo azul", "horizonte", "sky", "clouds", "cloud"],
    "lluvia": ["lluvioso", "tormenta", "tormentas", "llovizna", "rain"],
    "frío": ["frio", "helada", "escarcha", "cold"],
    "calor": ["sol intenso", "sequía", "caluroso", "heat"],
    "música": ["musica", "banda", "recital", "show", "concierto", "tocar", "music"],
    "arte": ["pintura", "mural", "murales", "graffiti", "art"],
    "abuela": ["abuelita", "anciana", "abuelo", "anciano"],
    "niño": ["niños", "nene", "nenes", "chico", "chicos", "pequeño", "kids"],
    "amigo": ["amigos", "compañero", "compañeros", "compañera", "friends"],
    "felicidad": ["alegría", "sonrisa", "sonrisas", "risa", "risas", "smile"],
    "cansancio": ["fatiga", "agotamiento", "tired"],
    "mochila": ["mochilas", "equipaje", "alforjas", "alforja", "bolso", "bolsos", "backpack", "pannier", "alforja"],
    "carpas": ["carpa", "campamento", "acampar", "campaña", "camping", "camp"],
    "comida_argentina": ["empanadas", "asado", "milanesa", "locro", "mate", "dulce de leche"],
    "mate": ["yerba", "termo"],
    "casco": ["helmet", "cascos"],
    "reparación": ["repair", "reparar", "fix", "mantenimiento"],
    "tela": ["cloth", "fabric", "telas", "tela roja"],
    "equipamiento": ["gear", "equipamento"],
    "viento": ["wind"],
    "camino_de_tierra": ["gravel", "ripio", "grava"],
    "banquina": ["roadside"],
    "senderismo": ["trail", "sendero", "hiking"],
    "esfuerzo": ["effort", "esfuerzos"],
    "paisaje": ["landscape", "scenery", "vista"],
}

# Palabras tan genéricas que no aportan (se descartan si no son género)
STOPWORDS = {
    "la", "el", "los", "las", "un", "una", "unos", "unas", "de", "del", "y",
    "en", "con", "por", "para", "que", "es", "se", "su", "al", "lo", "a",
    "the", "and", "of", "to", "in", "imagen", "foto", "fotografía", "fotografía",
    "este", "esta", "eso", "esa", "una escena", "escena", "otro", "otra",
    "image", "photo", "scene", "outdoor", "object", "objects", "color", "colors",
    "person", "people", "colours",
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


def _es_frase_basura(palabra: str) -> bool:
    """
    Detecta frases de 3+ palabras que no son sinónimos conocidos del dominio.

    El modelo a veces regurgita frases completas como keyword
    (ej: "pájaro de ánus morrison", "del tiempo no de de la").
    Se excluyen las variantes multi-palabra de SINONIMOS
    (ej: "bici de montaña" es válida y se mapea a "bicicleta").
    """
    if palabra.count(" ") < 2:  # 2 palabras o menos: no aplica
        return False
    p = palabra.lower()
    for variantes in SINONIMOS.values():
        if p in [v.lower() for v in variantes]:
            return False
    return True


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
    if _es_frase_basura(p):
        return True
    return False


def singularizar(palabra: str) -> str:
    """Plural → singular simple (montañas → montaña, perros → perro, autos → auto).

    CONSERVADOR: NO toca palabras terminadas en "-es" (árboles, flores, viajes,
    atardeceres) porque la regla no es segura sin morfología — los casos comunes
    del dominio ya están cubiertos por SINONIMOS (se aplica antes).
    """
    if not palabra or len(palabra) < 4:
        return palabra
    # -s tras vocal simple, salvo "-es" (no confiable): montañas→montaña, perros→perro
    if (palabra.endswith("s") and len(palabra) > 3
            and palabra[-2] in "aeiouáéíóú"
            and not palabra.endswith("es")):
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
            # El género puede estar en cualquier posición (qwen a veces pone el sujeto primero).
            # IMPORTANTE: conservar TODAS las keywords (incluida la posición 0,
            # que no es género pero sí puede ser una keyword válida).
            resto = list(norm)
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
        description="Refina y unifica keywords de IA (léxico + diccionario)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None, help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="skip: solo los que tienen keywords (default) | update: todos | replace: igual que update")
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

    # Envolver el trabajo real con manejo de interrupción: al cortar con
    # Ctrl+C se commitean los pendientes y se sale con mensaje claro
    # (manejar_interrupcion), sin traceback.
    from scripts.ai_media.checkpoint import manejar_interrupcion
    with manejar_interrupcion(conn=conn, etiqueta="refinar_keywords"):
        _ejecutar(conn, args)


def _ejecutar(conn, args) -> None:
    """
    Ejecuta el refinamiento completo: léxico + diccionario + escritura.

    Separado de main() para poder envolverlo en manejar_interrupcion sin
    re-indentar el cuerpo (mismo nivel de indentación de función).
    """
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

    # --- Paso 3: comparar y mostrar cambios ---
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

    # --- Paso 4: escribir en DB ---
    if not args.dry_run and cambios:
        # Checkpoint por lote: commit cada 20 registros en vez de uno solo
        # al final (si se corta con Ctrl+C, el progreso queda guardado y se
        # retoma con --mode update).
        from scripts.ai_media.checkpoint import Checkpoint
        cp = Checkpoint(conn, cada=20, etiqueta="refinar_keywords")
        try:
            for mid, nueva in refinadas.items():
                valor_nuevo = ", ".join(nueva)
                conn.execute(
                    "UPDATE media_metadata SET value = ? WHERE media_id = ? AND key = 'ia_keywords'",
                    (valor_nuevo, mid),
                )
                cp.contar()
            cp.finalizar()
        except Exception as e:
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
