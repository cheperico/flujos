"""
Puente BD → TouchDesigner vía OSC.

Modos:
  enviar     → envía lista de colores a TD y espera selección
  colores    → solo envía los colores disponibles
  enviar_imgs → envía N imágenes de un color específico

Uso básico:
  python scripts/puente_td.py enviar           # loop completo: colores → espera → imágenes
  python scripts/puente_td.py colores           # solo lista de colores
  python scripts/puente_td.py enviar_imgs rojo  # 10 imágenes rojas
"""

import argparse
import logging
import sqlite3
import time
import random
from pathlib import Path
from typing import Optional

from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher

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
    conn = sqlite3.connect(db_path)
    colores = conn.execute("""
        SELECT DISTINCT color_1_name_basic FROM media
        WHERE color_1_name_basic IS NOT NULL
        ORDER BY color_1_name_basic
    """).fetchall()
    conn.close()
    return [c[0] for c in colores]


def obtener_imagenes_por_color(db_path: str, color: str, limit: int = 10) -> list[dict]:
    """Devuelve imágenes al azar de un color dado."""
    conn = sqlite3.connect(db_path)
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
        """,
    )

    parser.add_argument("modo",
                        nargs="?",
                        choices=["enviar", "colores", "enviar_imgs"],
                        default="enviar",
                        help="Modo de operación")
    parser.add_argument("color", nargs="?",
                        help="Color para enviar_imgs (ej: rojo, azul, verde)")
    parser.add_argument("--db", default="db/flujos.db",
                        help="Ruta a la DB (default: db/flujos.db)")
    parser.add_argument("--cant", type=int, default=10,
                        help="Cantidad de imágenes (default: 10)")
    parser.add_argument("--host", default=OSC_HOST,
                        help=f"Host TD (default: {OSC_HOST})")
    parser.add_argument("--port", type=int, default=OSC_PUERTO_TD,
                        help=f"Puerto OSC TD (default: {OSC_PUERTO_TD})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Modo detallado")

    args = parser.parse_args(argv)

    nivel = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=nivel, format="%(message)s")

    if not Path(args.db).exists():
        log.error(f"Base de datos no encontrada: {args.db}")
        return 1

    if args.modo == "colores":
        modo_colores(args.db)
    elif args.modo == "enviar_imgs":
        if not args.color:
            log.error("Especificá un color: python puente_td.py enviar_imgs rojo")
            return 1
        modo_enviar_imgs(args.db, args.color, args.cant)
    else:  # enviar (default)
        modo_enviar(args.db)

    return 0


if __name__ == "__main__":
    exit(main())
