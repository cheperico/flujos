"""
Puente BD → TouchDesigner vía OSC.

Modos:
  enviar       → envía lista de colores a TD y espera selección
  fluir        → escucha la ráfaga de selección del botón "Fluir" (9001),
                 acumula por grupo, detecta el fin, genera el spec del loop
                 con loop_db.generar_loop y lo envía por 9002
  colores      → solo envía los colores disponibles
  enviar_imgs  → envía N imágenes de un color específico
  nube         → genera nube de etiquetas con keywords de la DB
  elecciones   → envía las nubes de metadatos seleccionables (horas,
                 municipios, colores, tags, días, clima) al motor de TD

Uso básico:
  python scripts/puente_td.py enviar              # loop completo
  python scripts/puente_td.py colores              # solo lista de colores
  python scripts/puente_td.py enviar_imgs rojo     # 10 imágenes rojas
  python scripts/puente_td.py nube                 # nube de tags
  python scripts/puente_td.py elecciones           # nubes de elecciones
  python scripts/puente_td.py elecciones --grupo horas,tags
  python scripts/puente_td.py fluir                # escucha continua del "Fluir"
"""

import argparse
import json
import logging
import sqlite3
import threading
import time
import random
from pathlib import Path
from collections import Counter
from typing import Any, Optional

# Permitir ejecución standalone: agregar raíz del proyecto al path
if __name__ == "__main__" and __package__ is None:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pythonosc import udp_client
from pythonosc import osc_server
from pythonosc import dispatcher

from db.util import abrir, resolver_db
# elecciones.py vive en scripts/ (misma carpeta que este script)
if __package__ is None:
    import sys, os as _os
    _scripts_dir = _os.path.dirname(_os.path.abspath(__file__))
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
from elecciones import enviar_grupos as enviar_elecciones

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
# Modo: elecciones (nubes de metadatos seleccionables)
# ---------------------------------------------------------------------------

def modo_elecciones(db_path: str, grupos: Optional[str] = None):
    """Envía las nubes de elecciones (horas, municipios, colores, tags...) a TD."""
    ids = [s.strip() for s in grupos.split(",") if s.strip()] if grupos else []
    log.info("Enviando nubes de elecciones a TD...")
    enviar_elecciones(db_path, ids)
    log.info("✅ Nubes de elecciones enviadas")


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


def _partes_keywords(texto: str) -> list[str]:
    """
    Divide el valor de ia_keywords en partes (keywords individuales).
    Soporta los dos formatos que históricamente se guardaron en la DB:
      - Texto plano separado por comas:  "paisaje, montaña"
      - JSON array:                       '["paisaje", "montaña"]'
    Devuelve partes en minúsculas y sin quotes.
    """
    texto = texto.strip()
    if not texto:
        return []
    if texto.startswith("["):
        try:
            datos = json.loads(texto)
            if isinstance(datos, list):
                return [str(p).strip().lower().strip("'\"") for p in datos]
        except (json.JSONDecodeError, TypeError):
            pass
    return [p.strip().lower().strip("'\"") for p in texto.split(",") if p.strip()]


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
        partes = _partes_keywords(texto)
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
        _ai_media_dir = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)), "ai_media")
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
        ruta_spec = Path(__file__).resolve().parents[1] / ruta_spec
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
    log.info("👂 Escuchando 'Fluir' en %s:%d (debounce %.1fs)...",
             host, OSC_PUERTO_PY, debounce)

    try:
        while True:
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
  python scripts/puente_td.py fluir                # escucha continua del "Fluir"
  python scripts/puente_td.py fluir --una-vez --debounce 1.0  # 1 ráfaga y sale
  python scripts/puente_td.py fluir --no-enviar-medios        # solo resumen + fin

Probar "fluir" sin TouchDesigner (3 terminales):

  T1 (escucha 1 ráfaga y sale):
    python scripts/puente_td.py fluir --una-vez --debounce 1.0
  T2 (ráfaga falsa — 2 horas = rango):
    python -c "from pythonosc import udp_client as c; cl=c.SimpleUDPClient('127.0.0.1',9001); msgs=[('/flujos/seleccion/horas','06:00'),('/flujos/seleccion/horas','13:00')]; [cl.send_message(a,v) for a,v in msgs]"
  T3 (ver retorno por 9002):
    python scripts/osc_probe.py 9002 15
        """,
    )

    parser.add_argument("modo",
                        nargs="?",
                        choices=["enviar", "colores", "enviar_imgs", "nube", "elecciones", "fluir"],
                        default="enviar",
                        help="Modo de operación")
    parser.add_argument("color", nargs="?",
                        help="Color para enviar_imgs (ej: rojo, azul, verde)")
    parser.add_argument("--grupo", default=None,
                        help="Grupos de elecciones separados por coma (ej: horas,tags)")
    parser.add_argument("--db", default=None,
                        help="Ruta a la DB (default: db/flujos.db)")
    parser.add_argument("--cant", type=int, default=10,
                        help="Cantidad de imágenes (default: 10)")
    parser.add_argument("--max-tags", type=int, default=40,
                        help="Cantidad máxima de palabras en la nube (default: 40)")
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

    if args.modo == "colores":
        modo_colores(db_path)
    elif args.modo == "enviar_imgs":
        if not args.color:
            log.error("Especificá un color: python puente_td.py enviar_imgs rojo")
            return 1
        modo_enviar_imgs(db_path, args.color, args.cant)
    elif args.modo == "nube":
        modo_nube(db_path, args.max_tags)
    elif args.modo == "elecciones":
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
    else:  # enviar (default)
        modo_enviar(db_path)

    return 0


if __name__ == "__main__":
    exit(main())
