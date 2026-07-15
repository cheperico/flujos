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


def extract_dominant_colors(image_path: str, n_colors: int = 3) -> list:
    """
    Extrae los N colores más representativos de una imagen.
    Usa cuantización de Pillow para reducir la paleta.
    Devuelve lista de strings hex: ["#ff0000", "#00ff00", "#0000ff"]
    """
    try:
        from PIL import Image
        img = Image.open(image_path)

        # Convertir a RGB
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        elif img.mode == "RGBA":
            # Fondo blanco para transparencia
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg

        # Redimensionar para velocidad (max 200px)
        img.thumbnail((200, 200), Image.LANCZOS)

        # Cuantizar: reducir la paleta a n_colores * 4 para tener margen
        # y luego elegir los n_colores más frecuentes con getcolors()
        quantized = img.quantize(colors=n_colors * 4, method=Image.MEDIANCUT)

        # getcolors() devuelve [(frecuencia, indice_paleta), ...] ordenado por freq
        # Si la imagen tiene pocos colores, getcolors() puede devolver None
        color_counts = quantized.getcolors()
        if color_counts:
            # Ordenar de mayor a menor frecuencia
            color_counts.sort(key=lambda x: x[0], reverse=True)
            palette = quantized.getpalette()
            colors = []
            for freq, idx in color_counts[:n_colors]:
                r = palette[idx * 3]
                g = palette[idx * 3 + 1]
                b = palette[idx * 3 + 2]
                colors.append(rgb_to_hex(r, g, b))
        else:
            # Fallback: tomar los primeros N colores de la paleta sin orden
            palette = quantized.getpalette()
            actual = min(n_colors, len(palette) // 3)
            colors = []
            for i in range(actual):
                r = palette[i * 3]
                g = palette[i * 3 + 1]
                b = palette[i * 3 + 2]
                colors.append(rgb_to_hex(r, g, b))

        # Si faltan colores, rellenar con grises
        while len(colors) < n_colors:
            colors.append("#808080")

        return colors

    except Exception as e:
        # Si falla, devolver grises
        return ["#808080"] * n_colors
