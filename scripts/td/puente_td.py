"""
Puente BD → TouchDesigner vía OSC.

Modos:
  elecciones   → envía las nubes de metadatos seleccionables (horas,
                 municipios, colores, tags, días, clima) al motor de TD
  fluir        → escucha la ráfaga de selección del botón "Fluir" (9001),
                 acumula por grupo, detecta el fin, genera el spec del loop
                 con loop_db.generar_loop y lo envía por 9002

Uso básico:
  python scripts/td/puente_td.py elecciones           # nubes de elecciones
  python scripts/td/puente_td.py elecciones --grupo horas,tags
  python scripts/td/puente_td.py fluir                # escucha continua (Enter para detener)
"""

import argparse
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

# Permitir ejecución standalone: agregar raíz del proyecto al path
if __name__ == "__main__" and __package__ is None:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher

from db.util import resolver_db
# util_enter.py vive en scripts/td/ (misma carpeta que este script)
if __package__ is None:
    import sys, os as _os
    _scripts_dir = _os.path.dirname(_os.path.abspath(__file__))
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
from elecciones import enviar_grupos as enviar_elecciones
from util_enter import detener_con_enter

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración OSC
# ---------------------------------------------------------------------------
OSC_HOST = "127.0.0.1"
OSC_PUERTO_TD = 9000            # Python → TD (nubes de elecciones)
OSC_PUERTO_PY = 9001            # TD → Python (ráfaga del "Fluir")
OSC_PUERTO_TD_RESULTADO = 9002  # Python → TD (resultado del loop, canal separado)

# Direcciones OSC del flujo "Fluir".
OSC_ADDR_SELECCION = "/flujos/seleccion"   # prefijo TD → Python (por grupo)
OSC_ADDR_FLUIR = "/flujos/fluir"            # prefijo Python → TD por 9002


def enviar(cliente: udp_client.SimpleUDPClient, address: str, *args):
    """Envía un mensaje OSC."""
    log.debug(f"OSC → {address} {args}")
    cliente.send_message(address, list(args))


# ---------------------------------------------------------------------------
# Modo: elecciones (nubes de metadatos seleccionables)
# ---------------------------------------------------------------------------

def modo_elecciones(db_path: str, grupos: Optional[str] = None):
    """Envía las nubes de elecciones (horas, municipios, colores, tags...) a TD."""
    ids = [s.strip() for s in grupos.split(",") if s.strip()] if grupos else []
    log.info("Enviando nubes de elecciones a TD...")
    enviar_elecciones(db_path, ids)
    log.info("✅ Nubes de elecciones enviadas")


# ---------------------------------------------------------------------------
# Modo: fluir (botón "Fluir" de TouchDesigner)
# ---------------------------------------------------------------------------

# Grupo OSC (sufijo tras /flujos/seleccion/) → clave de filtro en loop_db.
GRUPOS_OSC_A_FILTRO = {
    "tags": "tags",
    "colores": "colores",
    "municipios": "municipios",
    "dias": "dias",
    "clima": "clima",
}

# Separador que utiliza el CLI de loop_db por grupo (tags por ';', el resto por
# coma). Se respeta para no romper el formato que espera _filtrar_media.
SEPARADOR_GRUPO = {
    "tags": ";",
    "colores": ",",
    "municipios": ",",
    "dias": ",",
    "clima": ",",
}


def _importar_loop_db() -> Any:
    """
    Importa loop_db desde scripts/ai_media agregando su carpeta al sys.path.

    loop_db.py convive con loop_engine en scripts/ai_media/ y hace
    `import loop_engine`; por eso necesita su propio directorio en sys.path
    (mismo patrón que ya usa el script para scripts/ y la raíz del proyecto).
    """
    if __package__ is None:
        import sys as _sys
        import os as _os
        _raiz_proyecto = _os.path.dirname(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        _ai_media_dir = _os.path.join(_raiz_proyecto, "scripts", "ai_media")
        if _ai_media_dir not in _sys.path:
            _sys.path.insert(0, _ai_media_dir)
    import loop_db  # noqa: E402
    return loop_db


def _parsear_hora_osc(valor: Any) -> Optional[int]:
    """
    Convierte un valor hora de la ráfaga ('13:00', '06:00') a hora entera (13, 6).

    El ':minutos' es opcional; si el texto no es un entero 0..23 se
    devuelve None para que el caller lo descarte con advertencia.
    """
    texto = str(valor).strip()
    parte = texto.split(":")[0]
    try:
        hora = int(parte)
    except (TypeError, ValueError):
        return None
    if not 0 <= hora <= 23:
        return None
    return hora


def _filtros_desde_seleccion(
    selecciones: dict[str, list[str]],
) -> tuple[list[int], dict[str, list[str]]]:
    """
    Traduce la ráfaga acumulada {grupo: [valores...]} a (horas, filtros).

    La estructura de filtros es exactamente la misma que arma el CLI de
    loop_db (municipios/colores/días/clima como listas; tags como lista que
    _filtrar_media usa con LIKE '%tag%'). Cada mensaje de la ráfaga puede
    traer un valor simple, pero también se soporta que venga más de uno
    (separados por el separador del grupo).
    """
    horas: list[int] = []
    for valor in selecciones.get("horas", []):
        hora = _parsear_hora_osc(valor)
        if hora is None:
            log.warning("  Hora no parseable de la ráfaga, descartada: %r", valor)
        elif hora not in horas:
            horas.append(hora)

    filtros: dict[str, list[str]] = {}
    for grupo_osc, nombre_filtro in GRUPOS_OSC_A_FILTRO.items():
        valores = selecciones.get(grupo_osc) or []
        sep = SEPARADOR_GRUPO.get(grupo_osc, ",")
        items: list[str] = []
        for valor in valores:
            for parte in str(valor).split(sep):
                parte = parte.strip()
                if parte and parte not in items:
                    items.append(parte)
        if items:
            filtros[nombre_filtro] = items

    return horas, filtros


def _enviar_filtro(cli, clave: str, valor) -> None:
    """Envía un filtro del usuario como mensaje clave-valor por 9002.

    El callbacks escribe `/flujos/fluir/filtro <clave> <valor>` como una fila
    [clave, valor] en `fluir_estado` (la misma tabla donde van los totales).
    Si `valor` es una lista, se une con ", " para que quede un único texto.
    """
    if isinstance(valor, (list, tuple)):
        valor = ", ".join(str(v) for v in valor if str(v).strip())
    enviar(cli, f"{OSC_ADDR_FLUIR}/filtro", clave, "" if valor is None else str(valor))


def _procesar_rafaga(
    db_path: str,
    selecciones: dict[str, list[str]],
    loop_secs: float,
    spec_salida: str,
    host: str = OSC_HOST,
    enviar_medios: bool = True,
) -> Optional[str]:
    """
    Genera el spec del loop con loop_db.generar_loop, lo escribe a archivo y
    lo envía por OSC al puerto 9002 (canal separado para el resultado).

Contrato de salida por 9002 (rediseño: el spec trae `por_tipo` y `resumen`):
      1. `/flujos/fluir/resumen <total> <loop_secs> <image> <video> <audio> <text>`
         — resumen con conteos por tipo (de `spec['resumen']`).
      2. `/flujos/fluir/filtro <clave> <valor>` — uno por filtro puesto por el
         usuario (hora_inicio, hora_fin, horas_elegidas, municipios, colores,
         tags, dias, clima). El callbacks los escribe como filas [clave, valor]
         en `fluir_estado`.
      3. Por tipo, en orden estable (image, video, audio, text):
         `/flujos/fluir/tabla <tipo> <cantidad>` — anuncio del comienzo de una
         tabla para un tipo (TD arma fluir_fotos/fluir_videos/fluir_audios/fluir_textos).
         `/flujos/fluir/medio <media_id> <ruta> <keypoint> <hora> <tipo>` — uno
         por medio (keypoint + hora posicionan temporalmente sin leer el archivo).
      4. `/flujos/fluir/chiche <hora> <texto>` — uno por chiche ambiental.
      5. `/flujos/fluir/fin <total>` — marca de finalización.
      6. La spec completa se escribe a `spec_salida` (TD puede leerla).

    Con `enviar_medios` False solo se envían resumen + fin (sin tabla/medio/chiche).

    Args:
        db_path: ruta a la base de datos.
        selecciones: ráfaga acumulada {grupo: [valores...]}.
        loop_secs: duración del loop en segundos.
        spec_salida: ruta del archivo JSON donde se vuelca el spec.
        host: host de TD para el cliente OSC de salida.
        enviar_medios: si se envían los mensajes tabla/medio/chiche (default True).

    Returns:
        Ruta del spec escrita, o None si no se pudo generar.
    """
    loop_db = _importar_loop_db()

    horas, filtros = _filtros_desde_seleccion(selecciones)
    log.info("  Horas: %s | filtros: %s",
             ", ".join(str(h) for h in horas) or "sin horas (0..23)",
             filtros or "ninguno")

    ruta_spec = Path(spec_salida)
    if not ruta_spec.is_absolute():
        ruta_spec = Path(__file__).resolve().parents[2] / ruta_spec
    ruta_spec.parent.mkdir(parents=True, exist_ok=True)
    ruta_spec = str(ruta_spec)

    spec = loop_db.generar_loop(
        db_path=db_path,
        horas=horas,
        loop_secs=loop_secs,
        modalidad_ubicaciones="geo",
        filtros=filtros,
        salida=ruta_spec,
    )

    resumen = spec.get("resumen") or {}
    n_total = resumen.get("total", len(spec.get("medios", [])))
    n_chiches = len(spec.get("chiches", []))
    log.info("   Loop generado: %d medios, %d chiches.", n_total, n_chiches)
    if n_total == 0:
        log.warning("  El loop no dejó medios dentro del arco "
                    "(filtros + horas demasiado estrictos).")

    cli = udp_client.SimpleUDPClient(host, OSC_PUERTO_TD_RESULTADO)
    enviar(cli, f"{OSC_ADDR_FLUIR}/resumen",
           n_total,
           spec.get("loop_secs", loop_secs),
           resumen.get("image", 0),
           resumen.get("video", 0),
           resumen.get("audio", 0),
           resumen.get("text", 0))

    # Filtros puestos por el usuario: se reflejan en fluir_estado para que el
    # estado del loop muestre qué eligió el visitante (hora inicio/fin y
    # municipios/colores/tags/dias/clima si vienen). Mensaje genérico por
    # clave-valor; el callbacks los escribe como filas [clave, valor].
    rango = resumen.get("rango_horas") or [0, 23]
    _enviar_filtro(cli, "hora_inicio", rango[0])
    _enviar_filtro(cli, "hora_fin", rango[1])
    _enviar_filtro(cli, "horas_elegidas", horas if horas else [])
    for clave_filtro, etiqueta in (
        ("municipios", "municipios"),
        ("colores", "colores"),
        ("tags", "tags"),
        ("dias", "dias"),
        ("clima", "clima"),
    ):
        valores = filtros.get(clave_filtro) or []
        if valores:
            _enviar_filtro(cli, etiqueta, valores)
    log.info("  Filtros enviados por 9002: hora_inicio=%s hora_fin=%s "
             "municipios=%s colores=%s tags=%s",
             rango[0], rango[1],
             filtros.get("municipios") or [],
             filtros.get("colores") or [],
             filtros.get("tags") or [])

    por_tipo = spec.get("por_tipo") or {}
    if enviar_medios:
        # `por_tipo` se itera en el orden estable de loop_db (image, video,
        # audio, text). Si un tipo no tiene medios no se emite nada: el
        # resumen ya lo reporta en 0.
        for tipo in loop_db.TIPOS_POR_DEFECTO:
            items = por_tipo.get(tipo, [])
            if not items:
                continue
            enviar(cli, f"{OSC_ADDR_FLUIR}/tabla", tipo, len(items))
            for medio in items:
                media_id = medio.get("media_id")
                ruta = str(medio.get("ruta") or "").replace("\\", "/")
                keypoint = medio.get("keypoint")
                if keypoint is None:
                    keypoint = medio.get("t_loop", 0.0)
                hora = medio.get("hora", 0.0)
                if not ruta:
                    log.warning("  ruta vacía para media_id %s; se envía igual",
                                media_id)
                enviar(cli, f"{OSC_ADDR_FLUIR}/medio",
                       media_id, ruta, keypoint, hora, tipo)

        for chich in spec.get("chiches", []):
            hora_chiche = chich.get("hora")
            if hora_chiche is None:
                hora_chiche = chich.get("t", 0.0)
            enviar(cli, f"{OSC_ADDR_FLUIR}/chiche",
                   hora_chiche, chich.get("texto", ""))

    enviar(cli, f"{OSC_ADDR_FLUIR}/fin", n_total)
    detalle = f"{n_total} medios"
    if enviar_medios:
        detalle += f" + {n_chiches} chiches"
    else:
        detalle += " (modo resumen+fin, sin tabla/medio/chiche)"
    log.info("  Enviado por 9002: %s.", detalle)
    return ruta_spec


def modo_fluir(
    db_path: str,
    debounce: float = 0.7,
    loop_secs: float = 300.0,
    spec_salida: str = "td/spec_fluir.json",
    una_vez: bool = False,
    host: str = OSC_HOST,
    enviar_medios: bool = True,
) -> None:
    """
    Modo "Fluir": escucha la ráfaga de selección de TD, la acumula por grupo,
    detecta el fin con debounce y genera/envia el loop por 9002.

    TD envía un mensaje OSC por cada elección acumulada en el único click del
    "Fluir", con el formato `/flujos/seleccion/<grupo> <valor>`. No existe una
    marca de "fin": se considera la ráfaga completa cuando pasan `debounce`
    segundos sin recibir otro mensaje. Tras procesarla el proceso queda
    escuchando la próxima ráfaga (a menos que `una_vez` sea True).

    Args:
        db_path: ruta a la base de datos.
        debounce: segundos sin mensajes para considerar la ráfaga terminada.
        loop_secs: duración del loop en segundos.
        spec_salida: ruta del archivo JSON del spec.
        una_vez: procesar una única ráfaga y salir.
        host: host de TD.
        enviar_medios: si se envían los mensajes tabla/medio/chiche por 9002
            (False → solo resumen + fin).
    """
    selecciones: dict[str, list[str]] = {}
    ultimo_mensaje = time.monotonic()

    def al_recibir_seleccion(addr: str, *args: Any) -> None:
        """Acumula cada mensaje de la ráfaga en su grupo."""
        nonlocal ultimo_mensaje
        if not addr.startswith(OSC_ADDR_SELECCION + "/"):
            return
        grupo = addr.rsplit("/", 1)[-1]
        if grupo == "seleccion":
            return
        valores = [str(a) for a in args if a is not None]
        if not valores:
            return
        if grupo != "horas" and grupo not in GRUPOS_OSC_A_FILTRO:
            log.warning("  Grupo OSC desconocido, se ignora: %r", grupo)
            return
        ultimo_mensaje = time.monotonic()
        selecciones.setdefault(grupo, []).extend(valores)
        log.info("  Ráfaga %s → %s", grupo, ", ".join(valores))

    disp = dispatcher.Dispatcher()
    disp.set_default_handler(al_recibir_seleccion)
    server = osc_server.ThreadingOSCUDPServer((host, OSC_PUERTO_PY), disp)
    hilo = threading.Thread(target=server.serve_forever, daemon=True)
    hilo.start()
    log.info("👂 Escuchando 'Fluir' en %s:%d (debounce %.1fs)... (Enter para detener)",
             host, OSC_PUERTO_PY, debounce)

    detener = detener_con_enter()
    try:
        while not detener.is_set():
            if selecciones and time.monotonic() - ultimo_mensaje >= debounce:
                log.info("  Ráfaga completa (%d selecciones). Generando loop...",
                         sum(len(v) for v in selecciones.values()))
                _procesar_rafaga(
                    db_path,
                    selecciones,
                    loop_secs,
                    spec_salida,
                    host,
                    enviar_medios=enviar_medios,
                )
                selecciones.clear()
                if una_vez:
                    log.info("  --una-vez: saliendo tras la primera ráfaga.")
                    break
            time.sleep(0.1)
    except KeyboardInterrupt:
        log.warning("⏹  Ctrl+C: escucha del 'Fluir' detenida.")
    finally:
        server.shutdown()
        server.server_close()
    if detener.is_set():
        log.info("  Detenido por el usuario (Enter).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Puente BD → TouchDesigner vía OSC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/td/puente_td.py elecciones           # nubes de elecciones
  python scripts/td/puente_td.py elecciones --grupo horas,tags
  python scripts/td/puente_td.py fluir                # escucha continua (Enter para detener)
  python scripts/td/puente_td.py fluir --una-vez --debounce 1.0  # 1 ráfaga y sale
  python scripts/td/puente_td.py fluir --no-enviar-medios        # solo resumen + fin

Probar "fluir" sin TouchDesigner (3 terminales):

  T1 (escucha 1 ráfaga y sale):
    python scripts/td/puente_td.py fluir --una-vez --debounce 1.0
  T2 (ráfaga falsa — 2 horas = rango):
    python -c "from pythonosc import udp_client as c; cl=c.SimpleUDPClient('127.0.0.1',9001); msgs=[('/flujos/seleccion/horas','06:00'),('/flujos/seleccion/horas','13:00')]; [cl.send_message(a,v) for a,v in msgs]"
  T3 (ver retorno por 9002):
    python scripts/td/osc_probe.py 9002 15
        """,
    )

    parser.add_argument("modo",
                        nargs="?",
                        choices=["elecciones", "fluir"],
                        default="elecciones",
                        help="Modo de operación")
    parser.add_argument("--grupo", default=None,
                        help="Grupos de elecciones separados por coma (ej: horas,tags)")
    parser.add_argument("--db", default=None,
                        help="Ruta a la DB (default: db/flujos.db)")
    parser.add_argument("--debounce", type=float, default=0.7,
                        help="Segundos sin nuevos mensajes OSC para considerar "
                             "terminada la ráfaga del 'Fluir' (default: 0.7)")
    parser.add_argument("--loop-secs", type=float, default=300.0,
                        help="Duración del loop en segundos (default: 300)")
    parser.add_argument("--spec-salida", default="td/spec_fluir.json",
                        help="Ruta del archivo JSON donde se escribe el spec "
                             "(default: td/spec_fluir.json)")
    parser.add_argument("--una-vez", action="store_true",
                        help="Procesar una única ráfaga y salir "
                             "(default: escucha continua)")
    parser.add_argument("--enviar-medios", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Enviar por 9002 los mensajes tabla/medio/chiche "
                             "(default: True). Con --no-enviar-medios solo van "
                             "resumen + fin.")
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

    if args.modo == "elecciones":
        modo_elecciones(db_path, args.grupo)
    elif args.modo == "fluir":
        modo_fluir(
            db_path,
            debounce=args.debounce,
            loop_secs=args.loop_secs,
            spec_salida=args.spec_salida,
            una_vez=args.una_vez,
            host=args.host,
            enviar_medios=args.enviar_medios,
        )

    return 0


if __name__ == "__main__":
    exit(main())
