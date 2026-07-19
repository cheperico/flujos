#!/usr/bin/env python3
"""
mapa_ruta.py — Genera un mapa HTML interactivo con Folium desde los GPS de la BD.

Lee los registros geolocalizados de la base de datos, dibuja la ruta en un mapa
interactivo con marcadores informativos, y opcionalmente colorea los segmentos
por pendiente y agrega una capa de calor.

Uso:
    python scripts/mapa_ruta.py                            # Genera mapa_ruta.html
    python scripts/mapa_ruta.py --output ruta.html          # Nombre de salida
    python scripts/mapa_ruta.py --no-markers                # Solo línea, sin marcadores
    python scripts/mapa_ruta.py --heatmap                   # Incluir heatmap
    python scripts/mapa_ruta.py --road-colors               # Colorear segmentos por gradiente
    python scripts/mapa_ruta.py --db ruta.db                # BD alternativa
    python scripts/mapa_ruta.py --verbose                   # Mostrar progreso
"""

import argparse
import logging
import math
import os
import sqlite3
import sys

# ---------------------------------------------------------------------------
# Importar folium con mensaje de error claro si no está instalado
# ---------------------------------------------------------------------------

try:
    import folium
    from folium.plugins import HeatMap
except ImportError:
    print("=" * 60)
    print("  ERROR: Folium no está instalado.")
    print("  Ejecutá:  pip install folium")
    print("=" * 60)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mapa_ruta")

# ---------------------------------------------------------------------------
# Constantes de visualización
# ---------------------------------------------------------------------------

# Colores para road-colors (gradiente)
#   < -3%  → azul intenso (bajada fuerte)
#   -1 a -3 → verde azulado (bajada suave)
#   -1 a +1 → gris/amarillo (llano)
#   +1 a +3 → naranja (subida suave)
#   > +3%   → rojo (subida fuerte)
GRADIENT_COLORS = [
    (-float("inf"), -3.0, "#1a3a8a"),   # bajada fuerte
    (-3.0, -1.0, "#3a8acc"),            # bajada suave
    (-1.0, 1.0, "#888888"),             # llano
    (1.0, 3.0, "#cc8a3a"),             # subida suave
    (3.0, float("inf"), "#cc3333"),     # subida fuerte
]

# Color default para la línea de ruta sin road-colors
RUTA_COLOR = "#3388ff"
RUTA_OPACITY = 0.8
RUTA_WEIGHT = 4

# Tile por defecto (CartoDB positron — estilo claro, elegante)
TILE_CARTO = "CartoDB positron"
TILE_OSM = "OpenStreetMap"
TILE_DEFAULT = TILE_CARTO

ATTR_CARTO = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors &copy; <a href="https://carto.com/">CARTO</a>'
)

# ---------------------------------------------------------------------------
# Función auxiliar: color de segmento según gradiente
# ---------------------------------------------------------------------------

def color_segun_gradiente(gradient_pct: float | None) -> str:
    """Devuelve un color hex según el porcentaje de pendiente."""
    if gradient_pct is None:
        return RUTA_COLOR
    for inicio, fin, color in GRADIENT_COLORS:
        if inicio <= gradient_pct < fin:
            return color
    return RUTA_COLOR


def formatear_pendiente(grad: float | None) -> str:
    """Formatea el gradiente como string legible."""
    if grad is None:
        return "—"
    if abs(grad) < 0.01:
        return "0 %"
    return f"{grad:+.2f} %"


def formatear_distancia(m: float | None) -> str:
    """Formatea distancia en metros o kilómetros."""
    if m is None:
        return "—"
    if m >= 1000:
        return f"{m / 1000:.2f} km"
    return f"{m:.0f} m"


# ---------------------------------------------------------------------------
# Lectura de datos desde la BD
# ---------------------------------------------------------------------------

def leer_puntos_gps(conn: sqlite3.Connection) -> list[dict]:
    """
    Lee todos los registros con GPS ordenados por timestamp_utc.

    Returns:
        Lista de dicts con: id, filename_original, lat, lon, timestamp_utc,
        provincia, departamento, municipio, distancia, gradiente,
        cumul_distancia, altitud.
    """
    rows = conn.execute("""
        SELECT
            id,
            filename_original,
            latitude,
            longitude,
            timestamp_utc,
            provincia,
            departamento,
            municipio,
            distance_from_prev_m,
            gradient_pct,
            cumul_distance_m,
            altitude
        FROM media
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY timestamp_utc ASC
    """).fetchall()

    puntos = []
    for row in rows:
        puntos.append({
            "id": row[0],
            "filename": row[1],
            "lat": row[2],
            "lon": row[3],
            "timestamp": row[4] or "",
            "provincia": row[5] or "",
            "departamento": row[6] or "",
            "municipio": row[7] or "",
            "distancia_m": row[8],       # distance_from_prev_m
            "gradiente": row[9],         # gradient_pct
            "cumul_dist_m": row[10],     # cumul_distance_m
            "altitud": row[11],          # altitude
        })
    return puntos


# ---------------------------------------------------------------------------
# Generación del mapa
# ---------------------------------------------------------------------------

def generar_mapa(
    db_path: str,
    output: str = "mapa_ruta.html",
    markers: bool = True,
    heatmap: bool = False,
    road_colors: bool = False,
    verbose: bool = False,
) -> str:
    """
    Genera un mapa HTML interactivo con Folium desde la base de datos.

    Args:
        db_path: Ruta a la base de datos SQLite.
        output: Ruta del archivo HTML de salida.
        markers: Si True, agrega marcadores con popups en cada punto GPS.
        heatmap: Si True, agrega capa de mapa de calor.
        road_colors: Si True, colorea los segmentos de ruta según el gradiente.
        verbose: Si True, muestra información detallada durante el proceso.

    Returns:
        Ruta absoluta del archivo HTML generado, o None si no hay datos.

    Raises:
        ImportError: Si no se encuentra el módulo folium.
    """
    # Validar DB
    if not os.path.isfile(db_path):
        log.error("Base de datos no encontrada: %s", db_path)
        return None

    # Conectar y leer datos
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        # Verificar que la tabla media existe
        try:
            conn.execute("SELECT COUNT(*) FROM media").fetchone()
        except sqlite3.OperationalError as e:
            log.error("La tabla 'media' no existe en la DB: %s", e)
            return None

        puntos = leer_puntos_gps(conn)

    finally:
        conn.close()

    if not puntos:
        log.warning("No hay registros con GPS en la base de datos.")
        return None

    total = len(puntos)
    log.info("Leídos %d puntos GPS desde la BD.", total)
    if verbose:
        log.info("  Rango: %s → %s", puntos[0]["timestamp"], puntos[-1]["timestamp"])

    # ---- Calcular centro y bounds ----
    lats = [p["lat"] for p in puntos]
    lons = [p["lon"] for p in puntos]
    centro_lat = sum(lats) / len(lats)
    centro_lon = sum(lons) / len(lons)
    bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]

    # ---- Crear mapa base ----
    m = folium.Map(
        location=[centro_lat, centro_lon],
        zoom_start=10,
        tiles=TILE_DEFAULT,
        attr=ATTR_CARTO,
        control_scale=True,
    )

    # Ajustar zoom para que cubra toda la ruta
    m.fit_bounds(bounds)

    # ---- Agregar línea de ruta ----
    if road_colors and total >= 2:
        # Segmentos individuales con color según gradiente
        for i in range(1, total):
            p_prev = puntos[i - 1]
            p_curr = puntos[i]
            color = color_segun_gradiente(p_curr["gradiente"])
            grad_str = formatear_pendiente(p_curr["gradiente"])

            seg = folium.PolyLine(
                locations=[(p_prev["lat"], p_prev["lon"]),
                           (p_curr["lat"], p_curr["lon"])],
                color=color,
                weight=RUTA_WEIGHT,
                opacity=RUTA_OPACITY,
                tooltip=f"{grad_str} | {p_curr['filename']}",
                popup=folium.Popup(
                    f"<b>Pendiente:</b> {grad_str}<br>"
                    f"<b>Distancia:</b> {formatear_distancia(p_curr['distancia_m'])}",
                    max_width=250,
                ),
            )
            seg.add_to(m)

        # Agregar leyenda de colores de gradiente
        _agregar_leyenda_gradiente(m)

    else:
        # Línea única de color fijo
        coords = [(p["lat"], p["lon"]) for p in puntos]
        ruta = folium.PolyLine(
            locations=coords,
            color=RUTA_COLOR,
            weight=RUTA_WEIGHT,
            opacity=RUTA_OPACITY,
            tooltip=f"Ruta — {total} puntos | {formatear_distancia(puntos[-1].get('cumul_dist_m'))}",
        )
        ruta.add_to(m)

    # ---- Agregar marcadores ----
    if markers:
        _agregar_marcadores(m, puntos, verbose)

    # ---- Agregar heatmap ----
    if heatmap:
        _agregar_heatmap(m, puntos, verbose)

    # ---- Guardar ----
    output_abs = os.path.abspath(output)
    m.save(output_abs)
    log.info("Mapa guardado: %s", output_abs)

    if verbose:
        n_con_grad = sum(1 for p in puntos if p["gradiente"] is not None)
        n_con_dist = sum(1 for p in puntos if p["distancia_m"] is not None)
        log.info("  Puntos con gradiente: %d/%d", n_con_grad, total)
        log.info("  Puntos con distancia: %d/%d", n_con_dist, total)
        if puntos[-1].get("cumul_dist_m"):
            log.info("  Distancia total ruta: %s",
                     formatear_distancia(puntos[-1]["cumul_dist_m"]))

    return output_abs


# ---------------------------------------------------------------------------
# Marcadores con popups
# ---------------------------------------------------------------------------

def _agregar_marcadores(mapa, puntos: list[dict], verbose: bool):
    """Agrega marcadores a cada punto GPS con popup informativo."""
    # Agregar marcador de inicio (verde) con icono especial
    if puntos:
        p = puntos[0]
        popup_html = _crear_popup(p, es_inicio=True)
        folium.Marker(
            location=[p["lat"], p["lon"]],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"🏁 Inicio: {p.get('filename', '')}",
            icon=folium.Icon(color="green", icon="play", prefix="fa"),
        ).add_to(mapa)

    # Agregar marcador de fin (rojo) con icono especial
    if len(puntos) > 1:
        p = puntos[-1]
        popup_html = _crear_popup(p, es_fin=True)
        folium.Marker(
            location=[p["lat"], p["lon"]],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"🏁 Fin: {p.get('filename', '')}",
            icon=folium.Icon(color="red", icon="stop", prefix="fa"),
        ).add_to(mapa)

    # Marcadores intermedios (azules, más pequeños)
    for i in range(1, len(puntos) - 1):
        p = puntos[i]
        popup_html = _crear_popup(p)
        folium.Marker(
            location=[p["lat"], p["lon"]],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=p.get("filename", f"Punto {i}"),
            icon=folium.Icon(color="blue", icon="info-sign", prefix="glyphicon"),
        ).add_to(mapa)

    log.info("Agregados %d marcadores (inicio: verde, fin: rojo, intermedios: azul).",
             len(puntos))


def _crear_popup(punto: dict, es_inicio: bool = False, es_fin: bool = False) -> str:
    """Crea el HTML del popup para un punto GPS."""
    lat = punto["lat"]
    lon = punto["lon"]
    ts = punto["timestamp"]
    filename = punto["filename"]

    # Ubicación
    prov = punto["provincia"] or "—"
    depto = punto["departamento"] or "—"
    muni = punto["municipio"] or "—"

    ubicacion = f"{prov}"
    if muni and muni != prov:
        ubicacion += f", {muni}"
    if depto and depto != muni and depto != prov:
        ubicacion += f" ({depto})"

    # Datos de ruta
    dist = formatear_distancia(punto["distancia_m"])
    cumul = formatear_distancia(punto["cumul_dist_m"])
    grad = formatear_pendiente(punto["gradiente"])
    alt = f"{punto['altitud']:.0f} m" if punto["altitud"] is not None else "—"

    # Título
    titulo = "🏁 INICIO" if es_inicio else ("🏁 FIN" if es_fin else f"Punto #{punto['id']}")

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; min-width: 260px;">
        <div style="font-weight: bold; font-size: 15px; margin-bottom: 6px;
                    border-bottom: 2px solid #3388ff; padding-bottom: 4px;">
            {titulo}
        </div>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Archivo</td>
                <td style="padding: 2px 0;"><code>{filename}</code></td></tr>
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Timestamp</td>
                <td style="padding: 2px 0;">{ts}</td></tr>
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Coordenadas</td>
                <td style="padding: 2px 0;">{lat:.6f}, {lon:.6f}</td></tr>
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Ubicación</td>
                <td style="padding: 2px 0;">{ubicacion}</td></tr>
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Dist. desde anterior</td>
                <td style="padding: 2px 0;">{dist}</td></tr>
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Dist. acumulada</td>
                <td style="padding: 2px 0;">{cumul}</td></tr>
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Pendiente</td>
                <td style="padding: 2px 0;">{grad}</td></tr>
            <tr><td style="padding: 2px 6px 2px 0; color: #555;">Altitud</td>
                <td style="padding: 2px 0;">{alt}</td></tr>
        </table>
    </div>
    """
    return html


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

def _agregar_heatmap(mapa, puntos: list[dict], verbose: bool):
    """Agrega una capa de mapa de calor basada en la densidad de puntos."""

    # Preparar datos: [lat, lon, peso]
    # Peso = intensidad relativa (1 por defecto, o basado en frecuencia)
    heat_data = [[p["lat"], p["lon"], 1] for p in puntos]

    HeatMap(
        data=heat_data,
        radius=15,
        blur=10,
        max_zoom=13,
        min_opacity=0.3,
        gradient={
            0.3: "blue",
            0.5: "lime",
            0.7: "yellow",
            0.9: "orange",
            1.0: "red",
        },
    ).add_to(mapa)

    log.info("Capa HeatMap agregada (%d puntos).", len(puntos))


# ---------------------------------------------------------------------------
# Leyenda de colores de gradiente (road-colors)
# ---------------------------------------------------------------------------

def _agregar_leyenda_gradiente(mapa):
    """Agrega una leyenda HTML explicativa de los colores de segmento."""
    from branca.element import Template, MacroElement

    template = """
    {% macro html(this, kwargs) %}
    <div style="
        position: fixed;
        bottom: 30px;
        right: 30px;
        z-index: 9999;
        background: white;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.2);
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
        line-height: 1.6;
        min-width: 140px;
    ">
        <div style="font-weight: bold; margin-bottom: 6px; border-bottom: 1px solid #ddd; padding-bottom: 4px;">
            Pendiente
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 18px; height: 4px; background: #1a3a8a;"></span>
            <span>&lt; -3 % (bajada fuerte)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 18px; height: 4px; background: #3a8acc;"></span>
            <span>-3 a -1 % (bajada)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 18px; height: 4px; background: #888888;"></span>
            <span>-1 a +1 % (llano)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 18px; height: 4px; background: #cc8a3a;"></span>
            <span>+1 a +3 % (subida)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 18px; height: 4px; background: #cc3333;"></span>
            <span>&gt; +3 % (subida fuerte)</span>
        </div>
    </div>
    {% endmacro %}
    """

    macro = MacroElement()
    macro._template = Template(template)
    mapa.get_root().add_child(macro)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] = None):
    parser = argparse.ArgumentParser(
        description="Genera un mapa HTML interactivo con Folium desde los GPS de la BD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/mapa_ruta.py                                    # Mapa con marcadores
  python scripts/mapa_ruta.py --output docs/mapa_viaje.html      # Ruta de salida personalizada
  python scripts/mapa_ruta.py --no-markers                        # Solo línea, sin marcadores
  python scripts/mapa_ruta.py --heatmap                           # Con capa de calor
  python scripts/mapa_ruta.py --road-colors                       # Segmentos coloreados por pendiente
  python scripts/mapa_ruta.py --road-colors --heatmap             # Todo incluido
  python scripts/mapa_ruta.py --db db/flujos.db --verbose         # BD explícita con detalle
        """,
    )

    parser.add_argument(
        "--output", "-o",
        default="mapa_ruta.html",
        help="Archivo HTML de salida (default: mapa_ruta.html)",
    )
    parser.add_argument(
        "--db", default=None,
        help="Ruta a la base de datos SQLite (default: db/flujos.db en la raíz del proyecto)",
    )
    parser.add_argument(
        "--no-markers",
        action="store_true",
        help="No agregar marcadores en los puntos GPS",
    )
    parser.add_argument(
        "--heatmap",
        action="store_true",
        help="Agregar capa de mapa de calor (HeatMap)",
    )
    parser.add_argument(
        "--road-colors",
        action="store_true",
        help="Colorear segmentos de ruta según pendiente: verde=bajada, rojo=subida",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar información detallada durante el proceso",
    )

    args = parser.parse_args(argv)

    # Resolver ruta de DB
    if args.db:
        db_path = os.path.abspath(args.db)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        db_path = os.path.join(project_root, "db", "flujos.db")

    if not os.path.isfile(db_path):
        log.error("Base de datos no encontrada: %s", db_path)
        log.error("Usá --db para especificar una ruta alternativa.")
        sys.exit(1)

    log.info("Base de datos: %s", db_path)

    # Generar mapa
    resultado = generar_mapa(
        db_path=db_path,
        output=args.output,
        markers=not args.no_markers,
        heatmap=args.heatmap,
        road_colors=args.road_colors,
        verbose=args.verbose,
    )

    if resultado:
        log.info("")
        log.info("Mapa generado exitosamente:")
        log.info("  Archivo: %s", resultado)
        log.info("  Abrílo en tu navegador para explorar la ruta.")
        log.info("")
        log.info("Opciones disponibles:")
        log.info("  --no-markers    Sin marcadores")
        log.info("  --heatmap       Con capa de calor")
        log.info("  --road-colors   Segmentos coloreados por pendiente")
        log.info("  --output PATH   Ruta de salida personalizada")
        log.info("  --verbose       Más detalles en consola")
    else:
        log.error("No se pudo generar el mapa.")
        sys.exit(1)


if __name__ == "__main__":
    main()
