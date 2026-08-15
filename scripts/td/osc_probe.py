#!/usr/bin/env python3
"""
osc_probe.py — Eco OSC: escucha lo que llega a un puerto y lo imprime.

Útil para verificar el flujo TD → Python (OSC Out de TouchDesigner, puerto 9001)
sin arrancar el puente completo: correr este script, tocar un botón de la
nube de elecciones en TD y ver en la consola:

    [OSC] /flujos/seleccion ('horas', '14:00', 1)

Uso:
    python scripts/td/osc_probe.py              # escucha en 9001 (Enter para salir)
    python scripts/td/osc_probe.py 9001 60      # puerto + segundos de ventana
"""

import argparse
import sys
import threading
import time

from pythonosc import dispatcher, osc_server

from util_enter import detener_con_enter

HOST = "127.0.0.1"
PUERTO_DEFAULT = 9001

RECIBIDOS: list[tuple[str, tuple]] = []


def on_message(address: str, *args) -> None:
    """Imprime todo mensaje OSC recibido y lo acumula en RECIBIDOS."""
    print(f"[OSC] {address} {args!r}", flush=True)
    RECIBIDOS.append((address, args))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Eco OSC: escucha mensajes en un puerto y los imprime.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos:
  python scripts/td/osc_probe.py            # escucha en 9001 (TD -> Python), Enter para salir
  python scripts/td/osc_probe.py 9001 60    # 60 segundos de ventana
        """,
    )
    parser.add_argument("puerto", type=int, nargs="?", default=PUERTO_DEFAULT,
                        help=f"Puerto a escuchar (default: {PUERTO_DEFAULT}).")
    parser.add_argument("segundos", type=float, nargs="?", default=0,
                        help="Ventana de escucha en segundos (0 = hasta Enter).")
    parser.add_argument("--host", default=HOST, help=f"Host (default: {HOST}).")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    disp = dispatcher.Dispatcher()
    disp.set_default_handler(on_message)

    server = osc_server.ThreadingOSCUDPServer((args.host, args.puerto), disp)
    print(f"Escuchando OSC en {args.host}:{args.puerto} ... "
          f"(Enter para salir)", flush=True)

    ventana = args.segundos
    if ventana:
        print(f"Ventana de {ventana}s. Toca un botón en TouchDesigner.", flush=True)
        fin = threading.Event()

        def _parar():
            fin.wait(ventana)
            server.shutdown()

        threading.Thread(target=_parar, daemon=True).start()
        server.serve_forever()
        server.server_close()
        print(f"Ventana terminada: {len(RECIBIDOS)} mensaje(s) recibido(s).")
        return 0 if RECIBIDOS else 1

    detener = detener_con_enter()
    try:
        hilo = threading.Thread(target=server.serve_forever, daemon=True)
        hilo.start()
        while not detener.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()
    finally:
        server.shutdown()
        server.server_close()
    if detener.is_set():
        print("Detenido por el usuario (Enter).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
