"""
Puente BD → TouchDesigner vía OSC.

Modos:
  enviar       → envía lista de colores a TD y espera selección
  colores      → solo envía los colores disponibles
  enviar_imgs  → envía N imágenes de un color específico
  nube         → genera nube de etiquetas con keywords de la DB

Uso básico:
  python scripts/puente_td.py enviar              # loop completo
  python scripts/puente_td.py colores              # solo lista de colores
  python scripts/puente_td.py enviar_imgs rojo     # 10 imágenes rojas
  python scripts/puente_td.py nube                 # nube de tags
"""

import argparse
import logging
import sqlite3
import time
import random
from pathlib import Path
from collections import Counter
from typing import Optional

# Permitir ejecución standalone: agregar raíz del proyecto al path
if __name__ == "__main__" and __package__ is None:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher

from db.util import abrir, resolver_db

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración OSC
# ---------------------------------------------------------------------------
OSC_HOST = "127.0.0.1"
OSC_PUERTO_TD = 9000   # Python → TD
OSC_PUERTO_PY = 9001    # TD → Python


def enviar(cliente: udp_client.SimpleUDPClient, address: str, *args):
    """Envía un mensaje OSC."""
    log.debug(f"OSC → {address} {args}")
    cliente.send_message(address, list(args))


# ---------------------------------------------------------------------------
# Consultas DB
# ---------------------------------------------------------------------------

def obtener_colores(db_path: str) -> list[str]:
    """Devuelve lista de colores básicos distintos en la DB."""
    conn = abrir(db_path)
    colores = conn.execute("""
        SELECT DISTINCT color_1_name_basic FROM media
        WHERE color_1_name_basic IS NOT NULL
        ORDER BY color_1_name_basic
    """).fetchall()
    conn.close()
    return [c[0] for c in colores]


def obtener_imagenes_por_color(db_path: str, color: str, limit: int = 10) -> list[dict]:
    """Devuelve imágenes al azar de un color dado."""
    conn = abrir(db_path)
    conn.row_factory = sqlite3.Row
    filas = conn.execute("""
        SELECT id, filename_original, filepath_absoluto,
               color_1_hex, color_1_name_basic,
               timestamp_utc, provincia
        FROM media
        WHERE (color_1_name_basic = ? OR color_2_name_basic = ? OR color_3_name_basic = ?)
          AND filepath_absoluto IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    """, (color, color, color, limit)).fetchall()
    conn.close()
    resultados = []
    for f in filas:
        ruta = f["filepath_absoluto"].replace("\\", "/")
        resultados.append({
            "id": f["id"],
            "ruta": ruta,
            "archivo": f["filename_original"],
            "color": f["color_1_name_basic"],
            "color_hex": f["color_1_hex"],
        })
    return resultados


# ---------------------------------------------------------------------------
# Modo interactivo completo
# ---------------------------------------------------------------------------

color_seleccionado = None


def al_recibir_seleccion(unused_addr, *args):
    """Callback cuando TD envía el color seleccionado."""
    global color_seleccionado
    if args:
        color_seleccionado = str(args[0])
        log.info(f"📥 Recibido color de TD: {color_seleccionado}")


def modo_enviar(db_path: str):
    """Envía colores a TD, espera selección, envía imágenes."""
    global color_seleccionado

    # 1. Obtener colores de la DB
    colores = obtener_colores(db_path)
    log.info(f"🎨 Colores disponibles ({len(colores)}): {', '.join(colores)}")

    # 2. Cliente OSC → TD
    cli = udp_client.SimpleUDPClient(OSC_HOST, OSC_PUERTO_TD)

    # Enviar lista de colores
    enviar(cli, "/flujos/colores", *colores)
    # También envío uno por uno por si el OSC In DAT no soporta múltiples args
    for c in colores:
        enviar(cli, "/colores", c)
    log.info(f"✅ Enviados {len(colores)} colores a TD (puerto {OSC_PUERTO_TD})")

    # 3. Servidor OSC para recibir selección de TD
    disp = dispatcher.Dispatcher()
    disp.map("/flujos/seleccion", al_recibir_seleccion)
    disp.map("/seleccion", al_recibir_seleccion)

    server = osc_server.ThreadingOSCUDPServer(
        (OSC_HOST, OSC_PUERTO_PY), disp
    )
    log.info(f"👂 Escuchando selección de TD en puerto {OSC_PUERTO_PY}...")

    # 4. Esperar hasta que TD envíe un color (timeout 120s)
    tiempo_espera = 120
    inicio = time.time()
    while color_seleccionado is None:
        server.handle_request()
        if color_seleccionado is not None:
            break
        time.sleep(0.1)
        if time.time() - inicio > tiempo_espera:
            log.warning("⏰ Timeout esperando selección de TD")
            return

    # 5. Consultar imágenes de ese color
    color = color_seleccionado
    log.info(f"🎯 Color seleccionado: {color}")
    imagenes = obtener_imagenes_por_color(db_path, color, limit=10)
    log.info(f"🖼 Enviando {len(imagenes)} imágenes de color {color} a TD...")

    # 6. Enviar cada imagen
    for img in imagenes:
        enviar(cli, "/flujos/slideshow/imagen", img["ruta"], img["id"], color)
        enviar(cli, "/slideshow/imagen", img["ruta"], img["id"], color)
        time.sleep(0.5)

    log.info(f"✅ {len(imagenes)} imágenes enviadas. ¡Listo!")


# ---------------------------------------------------------------------------
# Modo: solo colores
# ---------------------------------------------------------------------------

def modo_colores(db_path: str):
    """Solo envía la lista de colores a TD."""
    colores = obtener_colores(db_path)
    log.info(f"🎨 Colores: {', '.join(colores)}")
    cli = udp_client.SimpleUDPClient(OSC_HOST, OSC_PUERTO_TD)
    enviar(cli, "/flujos/colores", *colores)
    for c in colores:
        enviar(cli, "/colores", c)
    log.info(f"✅ {len(colores)} colores enviados a TD")


# ---------------------------------------------------------------------------
# Modo: enviar imágenes de un color
# ---------------------------------------------------------------------------

def modo_enviar_imgs(db_path: str, color: str, cantidad: int = 10):
    """Envía N imágenes al azar de un color."""
    imagenes = obtener_imagenes_por_color(db_path, color, limit=cantidad)
    if not imagenes:
        log.warning(f"⚠️  No hay imágenes de color '{color}'")
        return
    log.info(f"🖼 {len(imagenes)} imágenes de color '{color}':")
    cli = udp_client.SimpleUDPClient(OSC_HOST, OSC_PUERTO_TD)
    for img in imagenes:
        log.info(f"   ID {img['id']:4d} | {img['archivo']}")
        enviar(cli, "/flujos/slideshow/imagen", img["ruta"], img["id"], color)
        enviar(cli, "/slideshow/imagen", img["ruta"], img["id"], color)
        time.sleep(1.0)
    log.info("✅ Listo")


# ---------------------------------------------------------------------------
# Nube de etiquetas
# ---------------------------------------------------------------------------

KEYWORDS_A_IGNORAR = [
    'elige una', 'genero', 'fotografico', 'es un(a)', 'la imagen',
    'una de las siguientes', 'deben describir', 'ejemplo:', 'separas con comas',
    'el aguacate', "esponja ribiosa", "sa_20001", "roberto", "federico",
    "el aguaje", "elante", "ella", "documento", "objetivo", "objeto",
    "otras)", "otras."
]


def contar_keywords(db_path: str) -> Counter:
    """Cuenta frecuencia de keywords en la DB (columna ia_keywords)."""
    conn = abrir(db_path)
    rows = conn.execute(
        "SELECT value FROM media_metadata WHERE key='ia_keywords'"
    ).fetchall()
    conn.close()

    contador = Counter()
    for r in rows:
        texto = str(r[0])
        partes = [p.strip().lower().strip("'\"") for p in texto.split(",")]
        for p in partes:
            p = p.strip()
            if len(p) <= 2:
                continue
            if any(ign in p for ign in KEYWORDS_A_IGNORAR):
                continue
            contador[p] += 1
    return contador


def modo_nube(db_path: str, max_tags: int = 40):
    """Cuenta keywords y envía pares keyword:frecuencia a TD."""
    log.info("Contando keywords en la DB...")
    contador = contar_keywords(db_path)
    if not contador:
        log.warning("No se encontraron keywords.")
        return

    log.info(f"   {len(contador)} keywords únicas, {sum(contador.values())} apariciones totales")
    for kw, n in contador.most_common(10):
        log.info(f"   {kw:25s} {n}")

    # Tomar top N
    items = contador.most_common(max_tags)
    max_freq = items[0][1]

    # Armar lista plana: [kw1, freq1, kw2, freq2, ...]
    # Normalizar frecuencias a 0-1 para que TD calcule tamaños
    args_list = []
    for palabra, freq in items:
        proporcion = freq / max_freq if max_freq > 0 else 0
        args_list.append(palabra)
        args_list.append(freq)          # frecuencia absoluta
        args_list.append(round(proporcion, 3))  # peso normalizado 0-1

    cli = udp_client.SimpleUDPClient(OSC_HOST, OSC_PUERTO_TD)
    enviar(cli, "/flujos/nube/datos", *args_list)
    log.info(f"✅ Enviados {len(items)} pares keyword:freq a TD")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Puente BD → TouchDesigner vía OSC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/puente_td.py enviar              # loop completo
  python scripts/puente_td.py colores              # solo lista de colores
  python scripts/puente_td.py enviar_imgs rojo     # 10 rojas
  python scripts/puente_td.py enviar_imgs azul --cant 5
  python scripts/puente_td.py nube                 # nube de tags
  python scripts/puente_td.py nube --max-tags 60   # mas palabras en la nube
        """,
    )

    parser.add_argument("modo",
                        nargs="?",
                        choices=["enviar", "colores", "enviar_imgs", "nube"],
                        default="enviar",
                        help="Modo de operación")
    parser.add_argument("color", nargs="?",
                        help="Color para enviar_imgs (ej: rojo, azul, verde)")
    parser.add_argument("--db", default=None,
                        help="Ruta a la DB (default: db/flujos.db)")
    parser.add_argument("--cant", type=int, default=10,
                        help="Cantidad de imágenes (default: 10)")
    parser.add_argument("--max-tags", type=int, default=40,
                        help="Cantidad máxima de palabras en la nube (default: 40)")
    parser.add_argument("--host", default=OSC_HOST,
                        help=f"Host TD (default: {OSC_HOST})")
    parser.add_argument("--port", type=int, default=OSC_PUERTO_TD,
                        help=f"Puerto OSC TD (default: {OSC_PUERTO_TD})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Modo detallado")

    args = parser.parse_args(argv)

    nivel = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=nivel, format="%(message)s")

    db_path = resolver_db(args.db)

    if not Path(db_path).exists():
        log.error(f"Base de datos no encontrada: {db_path}")
        return 1

    if args.modo == "colores":
        modo_colores(db_path)
    elif args.modo == "enviar_imgs":
        if not args.color:
            log.error("Especificá un color: python puente_td.py enviar_imgs rojo")
            return 1
        modo_enviar_imgs(db_path, args.color, args.cant)
    elif args.modo == "nube":
        modo_nube(db_path, args.max_tags)
    else:  # enviar (default)
        modo_enviar(db_path)

    return 0


if __name__ == "__main__":
    exit(main())
