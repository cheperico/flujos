"""
color_utils.py — Utilidades para extracción y naming de colores.

Dependencias: Pillow, webcolors
"""

import webcolors
from webcolors._definitions import _CSS3_HEX_TO_NAMES, _CSS3_NAMES_TO_HEX

# -----------------------------------------------------------------------
# Mapping: nombre CSS inglés → español
# -----------------------------------------------------------------------

CSS_COLORS_ES = {
    # Rojos
    "indianred": "rojo indio",
    "lightcoral": "coral claro",
    "salmon": "salmón",
    "darksalmon": "salmón oscuro",
    "lightsalmon": "salmón claro",
    "crimson": "carmesí",
    "red": "rojo",
    "firebrick": "rojo ladrillo",
    "darkred": "rojo oscuro",
    # Rosas
    "pink": "rosa",
    "lightpink": "rosa claro",
    "hotpink": "rosa intenso",
    "deeppink": "rosa profundo",
    "mediumvioletred": "rojo violeta medio",
    "palevioletred": "rojo violeta pálido",
    # Naranjas
    "coral": "coral",
    "tomato": "tomate",
    "orangered": "rojo anaranjado",
    "darkorange": "naranja oscuro",
    "orange": "naranja",
    # Amarillos
    "gold": "dorado",
    "yellow": "amarillo",
    "lightyellow": "amarillo claro",
    "lemonchiffon": "chiffon limón",
    "lightgoldenrodyellow": "amarillo dorado claro",
    "papayawhip": "papaya",
    "moccasin": "mocasín",
    "peachpuff": "melocotón",
    "palegoldenrod": "vara de oro pálida",
    "khaki": "caqui",
    "darkkhaki": "caqui oscuro",
    # Morados / Violetas
    "lavender": "lavanda",
    "thistle": "cardo",
    "plum": "ciruela",
    "violet": "violeta",
    "orchid": "orquídea",
    "magenta": "magenta",
    "mediumorchid": "orquídea medio",
    "mediumpurple": "púrpura medio",
    "blueviolet": "violeta azulado",
    "darkviolet": "violeta oscuro",
    "darkorchid": "orquídea oscura",
    "darkmagenta": "magenta oscuro",
    "purple": "púrpura",
    "indigo": "añil",
    "slateblue": "azul pizarra",
    "darkslateblue": "azul pizarra oscuro",
    "mediumslateblue": "azul pizarra medio",
    # Verdes
    "greenyellow": "verde amarillento",
    "chartreuse": "chartreuse",
    "lawngreen": "verde césped",
    "lime": "lima",
    "limegreen": "verde lima",
    "palegreen": "verde pálido",
    "lightgreen": "verde claro",
    "mediumspringgreen": "verde primavera medio",
    "springgreen": "verde primavera",
    "mediumseagreen": "verde mar medio",
    "seagreen": "verde mar",
    "forestgreen": "verde bosque",
    "green": "verde",
    "darkgreen": "verde oscuro",
    "yellowgreen": "verde amarillento",
    "olivedrab": "oliva apagado",
    "olive": "oliva",
    "darkolivegreen": "verde oliva oscuro",
    "mediumaquamarine": "aguamarina medio",
    "darkseagreen": "verde mar oscuro",
    "lightseagreen": "verde mar claro",
    "darkcyan": "cian oscuro",
    "teal": "verde azulado",
    # Azules
    "aqua": "aguamarina",
    "cyan": "cian",
    "lightcyan": "cian claro",
    "paleturquoise": "turquesa pálido",
    "aquamarine": "aguamarina",
    "turquoise": "turquesa",
    "mediumturquoise": "turquesa medio",
    "darkturquoise": "turquesa oscuro",
    "cadetblue": "azul cadete",
    "steelblue": "azul acero",
    "lightsteelblue": "azul acero claro",
    "powderblue": "azul polvo",
    "lightblue": "azul claro",
    "skyblue": "azul cielo",
    "lightskyblue": "azul cielo claro",
    "deepskyblue": "azul cielo profundo",
    "dodgerblue": "azul dodger",
    "cornflowerblue": "azul aciano",
    "mediumslateblue": "azul pizarra medio",
    "royalblue": "azul real",
    "blue": "azul",
    "mediumblue": "azul medio",
    "darkblue": "azul oscuro",
    "navy": "azul marino",
    "midnightblue": "azul medianoche",
    # Marrones
    "cornsilk": "seda de maíz",
    "blanchedalmond": "almendra blanqueada",
    "bisque": "bisque",
    "navajowhite": "blanco navajo",
    "wheat": "trigo",
    "burlywood": "madera",
    "tan": "bronceado",
    "rosybrown": "marrón rosáceo",
    "sandybrown": "marrón arena",
    "goldenrod": "vara de oro",
    "darkgoldenrod": "vara de oro oscuro",
    "peru": "perú",
    "chocolate": "chocolate",
    "saddlebrown": "marrón montura",
    "sienna": "siena",
    "brown": "marrón",
    "maroon": "granate",
    # Blancos / Cremas
    "snow": "nieve",
    "honeydew": "rocío de miel",
    "mintcream": "crema de menta",
    "azure": "azur",
    "aliceblue": "azul alicia",
    "ghostwhite": "blanco fantasma",
    "whitesmoke": "humo blanco",
    "seashell": "concha marina",
    "beige": "beige",
    "oldlace": "encaje viejo",
    "floralwhite": "blanco floral",
    "ivory": "marfil",
    "antiquewhite": "blanco antiguo",
    "linen": "lino",
    "lavenderblush": "rubor lavanda",
    "mistyrose": "rosa brumoso",
    # Grises
    "gainsboro": "gainsboro",
    "lightgray": "gris claro",
    "silver": "plata",
    "darkgray": "gris oscuro",
    "gray": "gris",
    "dimgray": "gris tenue",
    "lightslategray": "gris pizarra claro",
    "slategray": "gris pizarra",
    "darkslategray": "gris pizarra oscuro",
    # Blancos
    "white": "blanco",
    # Negros
    "black": "negro",
}

# -----------------------------------------------------------------------
# Mapping: color CSS → color básico (11 categorías)
# -----------------------------------------------------------------------

BASIC_COLORS = {
    "rojo": ["indianred", "lightcoral", "salmon", "darksalmon", "lightsalmon",
             "crimson", "red", "firebrick", "darkred",
             "coral", "tomato", "orangered"],
    "naranja": ["darkorange", "orange"],
    "amarillo": ["gold", "yellow", "lightyellow", "lemonchiffon",
                 "lightgoldenrodyellow", "papayawhip", "moccasin",
                 "peachpuff", "palegoldenrod", "khaki", "darkkhaki",
                 "greenyellow", "chartreuse", "lawngreen",
                 "yellowgreen", "olivedrab", "olive", "darkolivegreen",
                 "cornsilk", "blanchedalmond", "bisque", "navajowhite",
                 "wheat", "burlywood", "tan", "goldenrod", "darkgoldenrod"],
    "verde": ["lime", "limegreen", "palegreen", "lightgreen",
              "mediumspringgreen", "springgreen",
              "mediumseagreen", "seagreen", "forestgreen", "green", "darkgreen",
              "mediumaquamarine", "darkseagreen", "lightseagreen",
              "darkcyan", "teal", "aqua", "cyan", "lightcyan",
              "paleturquoise", "aquamarine", "turquoise", "mediumturquoise",
              "darkturquoise"],
    "azul": ["cadetblue", "steelblue", "lightsteelblue", "powderblue",
             "lightblue", "skyblue", "lightskyblue", "deepskyblue",
             "dodgerblue", "cornflowerblue", "royalblue", "blue",
             "mediumblue", "darkblue", "navy", "midnightblue",
             "azure", "aliceblue", "ghostwhite"],
    "violeta": ["lavender", "thistle", "plum", "violet", "orchid",
                "mediumorchid", "mediumpurple", "blueviolet", "darkviolet",
                "darkorchid", "darkmagenta", "purple", "indigo",
                "slateblue", "darkslateblue", "mediumslateblue",
                "magenta", "lavenderblush"],
    "rosa": ["pink", "lightpink", "hotpink", "deeppink",
             "mediumvioletred", "palevioletred",
             "mistyrose", "rosybrown"],
    "marrón": ["sandybrown", "peru", "chocolate", "saddlebrown",
               "sienna", "brown", "maroon"],
    "blanco": ["snow", "honeydew", "mintcream", "whitesmoke", "seashell",
               "beige", "oldlace", "floralwhite", "ivory", "antiquewhite",
               "linen", "white"],
    "gris": ["gainsboro", "lightgray", "silver", "darkgray", "gray",
             "dimgray", "lightslategray", "slategray", "darkslategray"],
    "negro": ["black"],
}

# Invertir: de nombre CSS a básico
_CSS_TO_BASIC = {}
for basic_name, css_names in BASIC_COLORS.items():
    for css_name in css_names:
        _CSS_TO_BASIC[css_name] = basic_name

# -----------------------------------------------------------------------
# Funciones principales
# -----------------------------------------------------------------------

def hex_to_rgb(hex_color: str) -> tuple:
    """Convierte hex a RGB. Acepta #RRGGBB o RRGGBB."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convierte RGB a hex."""
    return f"#{r:02x}{g:02x}{b:02x}"


def closest_css_color(hex_color: str) -> str:
    """
    Encuentra el nombre CSS más cercano para un color hex dado.
    Usa distancia euclidiana en espacio RGB.
    """
    r, g, b = hex_to_rgb(hex_color)
    min_dist = float("inf")
    closest = None

    for css_name, css_hex in _CSS3_NAMES_TO_HEX.items():
        cr, cg, cb = hex_to_rgb(css_hex)
        # Distancia euclidiana ponderada (percepción humana aproximada)
        dist = ((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            closest = css_name

    return closest or "gray"


def get_color_names(hex_color: str) -> tuple:
    """
    Devuelve (nombre_css_es, nombre_basico) para un color hex.
    """
    # Encontrar el nombre CSS en inglés más cercano
    css_name_en = closest_css_color(hex_color)

    # Traducir a español
    css_name_es = CSS_COLORS_ES.get(css_name_en, css_name_en)

    # Encontrar color básico
    basic_name = _CSS_TO_BASIC.get(css_name_en, "gris")

    return css_name_es, basic_name


def _saturacion_hsv(r: int, g: int, b: int) -> float:
    """Calcula saturación HSV (0-1) a partir de RGB."""
    r_n, g_n, b_n = r / 255.0, g / 255.0, b / 255.0
    mx = max(r_n, g_n, b_n)
    mn = min(r_n, g_n, b_n)
    if mx == 0:
        return 0.0
    return (mx - mn) / mx


def _es_gris_o_negro(r: int, g: int, b: int, umbral_saturacion: float = 0.08) -> bool:
    """
    True si el color es casi gris (muy baja saturación) o casi negro.
    Útil para filtrar colores poco interesantes.
    """
    if max(r, g, b) < 30:  # negro / casi negro
        return True
    if _saturacion_hsv(r, g, b) < umbral_saturacion:
        return True
    return False


def _calcular_grilla(w: int, h: int, celdas_objetivo: int = 16) -> tuple[int, int]:
    """
    Calcula una grilla de celdas adaptativa según el aspect ratio.
    Ej: 4:3 → 4x4, 16:9 → 5x3, etc.
    """
    ratio = w / h
    cols = max(2, int(round((celdas_objetivo * ratio) ** 0.5)))
    rows = max(2, int(round(celdas_objetivo / cols)))
    return cols, rows


def extract_dominant_colors(image_path: str, n_colors: int = 3) -> list:
    """
    Extrae los N colores más representativos de una imagen.

    Estrategia (concentración por grilla):
      1. Divide la imagen en una grilla de ~16 celdas.
      2. En cada celda, cuantiza y obtiene colores con frecuencias.
      3. Para cada color único del conjunto global:
         - Calcula frecuencia TOTAL y cantidad de celdas donde aparece.
         - Score = (frecuencia / celdas) * (0.2 + 0.8 * saturación)
         - Esto penaliza colores dispersos (cielo, niebla) y premia
           colores concentrados en pocas celdas (campera roja, cartel).
      4. Filtra grises/negros extremos.
      5. Devuelve los N mejor puntuados en hex.

    Sin dependencias externas: solo Pillow.
    """
    try:
        from PIL import Image

        # ── 1. Abrir y normalizar ──
        img = Image.open(image_path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        elif img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg

        # Redimensionar a tamaño de trabajo
        w, h = img.size
        img.thumbnail((300, 300), Image.LANCZOS)
        w, h = img.size

        # ── 2. Dividir en grilla ──
        cols, rows = _calcular_grilla(w, h)
        celda_w = max(1, w // cols)
        celda_h = max(1, h // rows)

        # {paleta_idx: {"freq": total, "celdas": set, "r": r, "g": g, "b": b}}
        acum = {}

        for row in range(rows):
            for col in range(cols):
                left = col * celda_w
                upper = row * celda_h
                right = min(left + celda_w, w)
                lower = min(upper + celda_h, h)
                tile = img.crop((left, upper, right, lower))

                # Cuantizar la celda a pocos colores
                q = tile.quantize(colors=12, method=Image.MEDIANCUT)
                counts = q.getcolors()
                if not counts:
                    continue
                pal = q.getpalette()

                for freq, idx in counts:
                    r_c = pal[idx * 3]
                    g_c = pal[idx * 3 + 1]
                    b_c = pal[idx * 3 + 2]
                    # Usar hex como clave única
                    hex_c = rgb_to_hex(r_c, g_c, b_c)
                    if hex_c not in acum:
                        acum[hex_c] = {"freq": 0, "celdas": set(), "r": r_c, "g": g_c, "b": b_c}
                    acum[hex_c]["freq"] += freq
                    acum[hex_c]["celdas"].add((row, col))

        if not acum:
            return ["#808080"] * n_colors

        # ── 3. Puntuar cada color ──
        # Score = (freq / n_celdas) * (0.2 + 0.8 * sat)
        # freq / n_celdas: penaliza colores que aparecen en muchas celdas (dispersos)
        total_celdas = rows * cols
        scored = []
        for hex_c, data in acum.items():
            r, g, b = data["r"], data["g"], data["b"]
            n_celdas = len(data["celdas"])
            sat = _saturacion_hsv(r, g, b)
            # Concentración: entre más celdas ocupa, menor el score
            concentracion = total_celdas / max(1, n_celdas)
            score = data["freq"] * concentracion * (0.2 + 0.8 * sat)
            scored.append((score, r, g, b))

        scored.sort(key=lambda x: x[0], reverse=True)

        # ── 4. Seleccionar, filtrando grises/negros ──
        colors = []
        for score, r, g, b in scored:
            if len(colors) >= n_colors:
                break
            if _es_gris_o_negro(r, g, b) and len(colors) > 0:
                if any(not _es_gris_o_negro(*hex_to_rgb(c)) for c in colors):
                    continue
            colors.append(rgb_to_hex(r, g, b))

        # Rellenar si faltan
        if len(colors) < n_colors:
            for score, r, g, b in scored:
                if len(colors) >= n_colors:
                    break
                hex_c = rgb_to_hex(r, g, b)
                if hex_c not in colors:
                    colors.append(hex_c)

        while len(colors) < n_colors:
            colors.append("#808080")

        return colors

    except Exception as e:
        return ["#808080"] * n_colors
