"""
util_enter.py — Detener procesos de escucha con la tecla Enter.

Helper compartido para los scripts de escucha OSC del proyecto
(`puente_td.py` modo 'fluir' y `osc_probe.py` en modo indefinido).

En Windows Ctrl+C puede no dejar una salida limpia ni alcanzar a los procesos
hijos lanzados desde `flujos.py`, así que estos scripts ofrecen detenerse
presionando Enter (Ctrl+C queda como fallback).
"""

import logging
import threading

log = logging.getLogger(__name__)


def detener_con_enter() -> threading.Event:
    """
    Devuelve un threading.Event que se setea cuando el usuario presiona Enter.

    Lanza un hilo daemon que bloquea en input() y setea el evento al recibir
    Enter. Ante EOF (stdin cerrado) o Ctrl+C el evento también se setea
    (finally) para que el caller termine limpio sin depender del Ctrl+C.
    """
    detener = threading.Event()

    def _esperar_enter() -> None:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            detener.set()

    threading.Thread(target=_esperar_enter, daemon=True).start()
    return detener
