#!/usr/bin/env python3
"""
inferir_hora_textos.py — Infiere timestamp de textos (type='text') con posición
GPS interpolando contra el track GPX (posición → tiempo).

Contexto: los textos ingresados con `ingest_textos.py` pueden no tener fecha en
su metadata (`fecha:` vacía en la sección o en el frontmatter del .md). Decisión
de diseño (2026-08-16): un texto sin fecha solo obtiene su fecha/hora
interpolando SU PUNTO (lat/lon) contra el track GPX del viaje: se buscan los
2 puntos del track más cercanos por distancia Haversine y se interpola el
instante entre ambos con ponderación por distancia inversa (el punto más
cercano pesa más).

Umbral:
  --umbral (default 2000 m) es el corte sobre la distancia del punto MÁS
  cercano del track. Si el texto está a más de `--umbral` metros del track se
  SKIPEA (no se escribe nada): la posición no está sobre la ruta y cualquier
  hora inferida sería especulativa (se cuenta como `fuera_umbral`).

Marcador:
  Los textos inferidos quedan marcados con
  `media.geolocation_source = 'track_interpolado'` (mismo source que usa
  keypoints_contexto.py para las posiciones interpoladas de video/audio).

Diseño pendiente (documentado en ROADMAP 2026-08-16):
  Algunos textos narran una trayectoria MÁS ALLÁ de su punto (ej: "De Saladillo
  a Bell Ville"). Hoy la hora se infiere en el punto único; a futuro los textos
  deberían soportar MÚLTIPLES ubicaciones (inicio/fin del segmento narrado)
  para que la interpolación (y la futura línea de tiempo/visualización) abarque
  toda la trayectoria narrada.

Modos:
  skip    (default) solo textos con timestamp_utc NULL o no parseable
  update  procesa TODOS los textos con lat/lon (sobrescribe el timestamp)

Uso:
    python scripts/inferir_hora_textos.py
    python scripts/inferir_hora_textos.py --mode update
    python scripts/inferir_hora_textos.py --dry-run --verbose
    python scripts/inferir_hora_textos.py --umbral 5000
"""

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# La consola de Windows por defecto usa cp1252, que no puede codificar los
# caracteres acentuados que imprimen los títulos de los textos. Reconfiguramos
# stdout a UTF-8 con fallback 'replace' (mismo fix que en loop_db.py).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass  # Python < 3.7 o stdout sin reconfigure

# Permitir importar db.util y scripts hermanos desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.util import abrir, resolver_db  # noqa: E402
from scripts.gradiente import haversine  # noqa: E402
from scripts.ingest_gpx import parsear_gpx  # noqa: E402

log = logging.getLogger(__name__)

# Zona horaria del viaje (Argentina, UTC-3): la hora local reportada por texto.
_ZONA_ARGENTINA = timezone(timedelta(hours=-3))

# Marcador de geolocation_source para textos con hora inferida del track
# (mismo source que keypoints_contexto.py para posiciones interpoladas).
SOURCE_TRACK_INTERPOLADO = "track_interpolado"

UMBRAL_DEFAULT_M = 2000.0


# ---------------------------------------------------------------------------
# Helpers de tiempo
# ---------------------------------------------------------------------------

def _parsear_timestamp(valor: str | None) -> datetime | None:
    """
    Parsea un timestamp a datetime aware (UTC).

    Copia el patrón de `scripts/ai_media/loop_db.py` (`_parsear_timestamp`):
    los timestamps vienen en formato mixto ('Z' / '+00:00') y se reemplaza 'Z'
    por '+00:00' antes de parsear. Devuelve None si el valor es vacío o no se
    puede parsear (ej: la cadena literal 'None' que producía el bug de
    ingest_textos.py).
    """
    texto = (valor or "").strip()
    if not texto:
        return None
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Track GPX
# ---------------------------------------------------------------------------

def _puntos_track_con_tiempo(gpx: dict) -> list[tuple[datetime, float, float]]:
    """
    Puntos del track GPX con `time` válido: [(dt_utc, lat, lon)] ordenados.

    Devuelve solo los puntos que sirven para inferir tiempo (tienen timestamp
    parseable y coordenadas). Se ordenan por tiempo para estabilidad aunque la
    búsqueda de vecinos es espacial (Haversine).
    """
    puntos: list[tuple[datetime, float, float]] = []
    for tp in gpx.get("track_points") or []:
        dt = _parsear_timestamp(tp.get("time"))
        if dt is None or tp.get("latitude") is None or tp.get("longitude") is None:
            continue
        puntos.append((dt, tp["latitude"], tp["longitude"]))
    puntos.sort(key=lambda p: p[0])
    return puntos


def _cargar_tracks(conn: sqlite3.Connection) -> list[dict]:
    """
    Relee los .gpx de TODOS los tracks registrados en `tracks` (los track
    points NO se persisten en DB; decisión del plan — ver keypoints_contexto).

    Returns:
        Lista de dicts {"name", "ruta", "puntos"}. Los tracks sin archivo o sin
        puntos con tiempo se descartan con log warning.
    """
    conn.row_factory = sqlite3.Row  # idempotente; robusto a llamadas directas
    filas = conn.execute(
        "SELECT id, name, filepath_absoluto FROM tracks ORDER BY id"
    ).fetchall()
    tracks: list[dict] = []
    for fila in filas:
        ruta = fila["filepath_absoluto"]
        if not ruta or not Path(ruta).exists():
            log.warning("Archivo GPX no existe o sin ruta (track %s): %s",
                        fila["name"], ruta)
            continue
        try:
            gpx = parsear_gpx(ruta)
        except Exception as e:
            log.warning("No se pudo parsear GPX %s: %s", ruta, e)
            continue
        puntos = _puntos_track_con_tiempo(gpx)
        if len(puntos) < 2:
            log.warning("Track sin suficientes puntos con tiempo: %s", ruta)
            continue
        tracks.append({"name": fila["name"], "ruta": ruta, "puntos": puntos})
        log.info("Track: %s (%s) — %d puntos con tiempo.",
                 fila["name"], ruta, len(puntos))
    return tracks


# ---------------------------------------------------------------------------
# Interpolación posición → tiempo
# ---------------------------------------------------------------------------

# Si los 2 vecinos espaciales están en pasadas distintas (gap temporal grande),
# la interpolación entre ellos produce un instante intermedio sin sentido.
# El gap normal entre vecinos de una misma pasada es de segundos a ~minutos;
# 2 h separa con seguridad pasadas distintas (caso real: Melincué, 21 h).
UMBRAL_PASADA_H = 2.0


def _dos_vecinos(
    puntos: list[tuple[datetime, float, float]],
    lat: float,
    lon: float,
) -> tuple[tuple[datetime, float, float], tuple[datetime, float, float], float, float] | None:
    """
    Los 2 puntos del track para interpolar: los 2 más cercanos por Haversine.

    Regla del plan: los 2 vecinos espaciales más cercanos con ponderación por
    distancia inversa. Si esos 2 vecinos caen en pasadas DISTINTAS de la ruta
    (gap temporal > UMBRAL_PASADA_H, ej: el track pasa dos veces cerca de
    Melincué con ~21 h de diferencia), el segundo vecino se reemplaza por el
    vecino temporal de p1 en la ruta (anterior o posterior, el más cercano en
    espacio) para que la interpolación sea a lo largo de la misma pasada.

    Returns:
        (p1, p2, d1, d2) con d1 <= d2 (distancias en metros), o None si no hay
        suficientes puntos (len < 2).
    """
    if len(puntos) < 2:
        return None
    distancias = sorted(
        ((haversine(lat, lon, p[1], p[2]), p) for p in puntos),
        key=lambda x: x[0],
    )
    p1, d1 = distancias[0][1], distancias[0][0]
    p2, d2 = distancias[1][1], distancias[1][0]

    # Pasadas distintas: reemplazar p2 por el vecino temporal de p1 en la ruta
    gap_h = abs((p2[0] - p1[0]).total_seconds()) / 3600.0
    if gap_h > UMBRAL_PASADA_H:
        idx = puntos.index(p1)
        candidatos: list[tuple[datetime, float, float]] = []
        if idx > 0:
            candidatos.append(puntos[idx - 1])
        if idx < len(puntos) - 1:
            candidatos.append(puntos[idx + 1])
        p2 = min(candidatos, key=lambda p: haversine(lat, lon, p[1], p[2]))
        d2 = haversine(lat, lon, p2[1], p2[2])

    if d1 > d2:
        p1, p2, d1, d2 = p2, p1, d2, d1
    return p1, p2, d1, d2


def _interpolar_instante(
    p1: tuple[datetime, float, float],
    p2: tuple[datetime, float, float],
    d1: float,
    d2: float,
) -> datetime:
    """
    Interpola el instante entre los 2 vecinos con ponderación por distancia
    inversa: t = (t1*d2 + t2*d1) / (d1 + d2) — el punto MÁS CERCANO pesa más.

    Si d1 + d2 == 0 (ambos coinciden con el texto) se usa el tiempo de p1.
    """
    t1, _, _ = p1
    t2, _, _ = p2
    if d1 + d2 == 0:
        return t1
    t1_sec = t1.timestamp()
    t2_sec = t2.timestamp()
    t_sec = (t1_sec * d2 + t2_sec * d1) / (d1 + d2)
    return datetime.fromtimestamp(t_sec, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _textos_candidatos(conn: sqlite3.Connection, mode: str) -> list[sqlite3.Row]:
    """Textos con lat/lon según el modo (skip: timestamp inválido o NULL)."""
    conn.row_factory = sqlite3.Row
    filas = conn.execute(
        "SELECT id, filename_original, latitude, longitude, timestamp_utc "
        "FROM media WHERE type='text' AND latitude IS NOT NULL AND longitude IS NOT NULL "
        "ORDER BY id"
    ).fetchall()
    if mode == "skip":
        return [f for f in filas if _parsear_timestamp(f["timestamp_utc"]) is None]
    return filas


def procesar_conexion(
    conn: sqlite3.Connection,
    mode: str = "skip",
    umbral_m: float = UMBRAL_DEFAULT_M,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Pipeline de inferencia posición → tiempo sobre una conexión abierta.

    Returns:
        dict con estadísticas: candidatos, inferidos, fuera_umbral,
        sin_posicion, ya_tienen.
    """
    stats = {
        "candidatos": 0,
        "inferidos": 0,
        "fuera_umbral": 0,
        "sin_posicion": 0,
        "ya_tienen": 0,
    }

    tracks = _cargar_tracks(conn)
    if not tracks:
        log.warning("Sin track GPX: no se puede interpolar posición.")
        return stats

    # Unir todos los puntos con tiempo de todos los tracks (el viaje es 1 track
    # hoy; si hubiera varios, la búsqueda espacial sobre el total es válida).
    puntos_todos: list[tuple[datetime, float, float]] = []
    for t in tracks:
        puntos_todos.extend(t["puntos"])
    log.info("Puntos track con tiempo disponibles: %d", len(puntos_todos))

    # Sin posición: textos sin lat/lon (no inferibles por este método)
    sin_pos = conn.execute(
        "SELECT COUNT(*) FROM media WHERE type='text' "
        "AND (latitude IS NULL OR longitude IS NULL)"
    ).fetchone()[0]
    stats["sin_posicion"] = sin_pos
    if sin_pos:
        log.info("Textos sin posición (no inferibles): %d", sin_pos)

    candidatos = _textos_candidatos(conn, mode)
    stats["candidatos"] = len(candidatos)
    log.info("Textos candidatos (%s): %d", mode, len(candidatos))

    for fila in candidatos:
        mid = fila["id"]
        titulo = fila["filename_original"] or f"#{mid}"
        lat = fila["latitude"]
        lon = fila["longitude"]

        vecinos = _dos_vecinos(puntos_todos, lat, lon)
        if vecinos is None:
            stats["fuera_umbral"] += 1
            log.info("  [%s] %-52s — track sin puntos suficientes (skip)", mid, titulo)
            continue

        p1, p2, d1, d2 = vecinos
        if d1 > umbral_m:
            stats["fuera_umbral"] += 1
            log.info("  [%s] %-52s — fuera de umbral (%.0f m > %.0f m)",
                     mid, titulo, d1, umbral_m)
            continue

        instante = _interpolar_instante(p1, p2, d1, d2)
        ts_iso = instante.isoformat()
        hora_local = instante.astimezone(_ZONA_ARGENTINA)
        local_str = hora_local.strftime("%H:%M")

        if dry_run:
            log.info("  [dry-run] [%s] %-52s — dist %.0f m | hora inferida %s local (%s)",
                     mid, titulo, d1, local_str, ts_iso)
            stats["inferidos"] += 1
            continue

        conn.execute(
            "UPDATE media SET timestamp_original = ?, timestamp_utc = ?, "
            "geolocation_source = ? WHERE id = ?",
            (ts_iso, ts_iso, SOURCE_TRACK_INTERPOLADO, mid),
        )
        stats["inferidos"] += 1
        log.info("  [%s] %-52s — dist %.0f m | hora inferida %s local (%s)",
                 mid, titulo, d1, local_str, ts_iso)

    if not dry_run:
        conn.commit()

    # En skip: textos que YA tienen timestamp válido (no candidatos)
    if mode == "skip":
        ya = conn.execute(
            "SELECT COUNT(*) FROM media WHERE type='text' "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL "
            "AND timestamp_utc IS NOT NULL"
        ).fetchone()[0]
        stats["ya_tienen"] = ya - stats["inferidos"] if not dry_run else ya
        if dry_run:
            stats["ya_tienen"] = ya
    return stats


def procesar(db_path: str, **kwargs) -> dict:
    """Abre la DB real y ejecuta el pipeline."""
    conn = abrir(resolver_db(db_path))
    try:
        return procesar_conexion(conn, **kwargs)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def crear_parser() -> argparse.ArgumentParser:
    """Parser de argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description=(
            "Infiera timestamp_utc/timestamp_original de textos (type='text') "
            "con posición GPS interpolando contra el track GPX (posición → tiempo)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/inferir_hora_textos.py
  python scripts/inferir_hora_textos.py --mode update
  python scripts/inferir_hora_textos.py --dry-run --verbose
  python scripts/inferir_hora_textos.py --umbral 5000
        """,
    )
    parser.add_argument("--db", default=None, help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument(
        "--mode", choices=["skip", "update"], default="skip",
        help="skip: solo timestamp NULL/no parseable (default) | update: procesa todos y sobrescribe",
    )
    parser.add_argument(
        "--umbral", type=float, default=UMBRAL_DEFAULT_M,
        help=f"Distancia máxima al punto más cercano del track en metros (default: {UMBRAL_DEFAULT_M:g})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Previsualizar sin escribir en la DB")
    parser.add_argument("--verbose", "-v", action="store_true", help="Logging detallado")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point del script (ejecutable standalone o desde flujos.py)."""
    args = crear_parser().parse_args(argv)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    log.info("=== INFERENCIA DE HORA DE TEXTOS (posición → track GPX) ===")
    log.info("Modo: %s | umbral: %.0f m | dry_run=%s", args.mode, args.umbral, args.dry_run)
    if args.dry_run:
        log.info("=== DRY RUN — no se escribirá en la DB ===")

    stats = procesar(
        args.db,
        mode=args.mode,
        umbral_m=args.umbral,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    log.info("")
    log.info("Resumen: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
