#!/usr/bin/env python3
"""
geocode.py — Geocodificación inversa de coordenadas GPS usando Georef API batch.

Convierte coordenadas (lat, lon) en Argentina a provincia, departamento,
municipio y localidad usando la API pública del Estado argentino.

Endpoint batch: POST https://apis.datos.gob.ar/georef/api/ubicacion
(acepta hasta 100 coordenadas por request, sin API key)

Uso:
    python scripts/geocode.py                          # Geocodifica toda la BD (solo pendientes)
    python scripts/geocode.py --coords lat,lon lat,lon ...  # Coordenadas específicas
    python scripts/geocode.py --db ruta.db              # BD alternativa
    python scripts/geocode.py --limit 500               # Solo N registros
    python scripts/geocode.py --dry-run                 # Previsualizar sin ejecutar

Fases del proyecto (ver docs/geocodificacion_reversa.md):
    Fase 1 - Georef API batch  (este script)
    Fase 2 - Fallback offline  (futuro)
"""

import argparse
import json
import logging
import math
import os
import sqlite3
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

# Permitir ejecución standalone: agregar raíz del proyecto al path
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.util import abrir, resolver_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("geocode")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

GEOREF_URL = "https://apis.datos.gob.ar/georef/api/ubicacion"
BATCH_SIZE = 100
REQUEST_TIMEOUT = 30  # segundos
MAX_RETRIES = 1       # reintentos por batch fallido

# ---------------------------------------------------------------------------
# Migración de esquema
# ---------------------------------------------------------------------------

GEOCODE_COLUMNS = [
    ("provincia", "TEXT"),
    ("departamento", "TEXT"),
    ("municipio", "TEXT"),
    ("localidad", "TEXT"),
    ("geocode_source", "TEXT"),
    ("geocode_date", "TEXT"),
]


def migrar_db(conn: sqlite3.Connection):
    """Agrega columnas de geocodificación si no existen."""
    for col_name, col_type in GEOCODE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE media ADD COLUMN {col_name} {col_type}")
            log.info("Columna '%s' agregada a media.", col_name)
        except sqlite3.OperationalError:
            pass  # ya existe


# ---------------------------------------------------------------------------
# API Georef
# ---------------------------------------------------------------------------

def _batch_georef(ubicaciones: list[dict]) -> list[dict]:
    """
    Envía un lote de coordenadas a la API Georef y devuelve las respuestas.

    Args:
        ubicaciones: lista de {"lat": lat, "lon": lon}

    Returns:
        Lista de respuestas con la misma estructura que la API.
        Cada elemento tiene 'provincia', 'departamento', etc.
    """
    payload = json.dumps({"ubicaciones": ubicaciones}).encode("utf-8")
    req = Request(
        GEOREF_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        raise RuntimeError(f"Error de conexión con Georef API: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Respuesta inválida de Georef API: {e}") from e

    return data.get("resultados", [])


def _extraer_resultado(resp: dict) -> dict:
    """
    Extrae provincia, departamento, municipio y localidad de una respuesta
    individual de la API Georef.

    La respuesta tiene esta estructura:
    {
        "parametros": {"lat": ..., "lon": ...},
        "ubicacion": {
            "lat": -34.6037,
            "lon": -58.3816,
            "provincia": {"id": "02", "nombre": "Ciudad Autónoma de Buenos Aires"},
            "departamento": {"id": "02001", "nombre": "Comuna 1"},
            "municipio": {"id": "02001001", "nombre": "Ciudad Autónoma de Buenos Aires"},
            "localidad": {"id": "02001001000", "nombre": "Buenos Aires"}
        }
    }

    Algunos campos pueden ser None si la coordenada cae fuera de Argentina
    o en una zona no categorizada.
    """
    def _nombre(obj):
        if obj and isinstance(obj, dict):
            return obj.get("nombre")
        return None

    ubicacion = resp.get("ubicacion") or {}
    return {
        "provincia": _nombre(ubicacion.get("provincia")),
        "departamento": _nombre(ubicacion.get("departamento")),
        "municipio": _nombre(ubicacion.get("municipio")),
        "localidad": _nombre(ubicacion.get("localidad")),
    }


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def reverse_geocode(coords: list[tuple], batch_size: int = BATCH_SIZE) -> dict:
    """
    Convierte una lista de coordenadas (lat, lon) a provincia/departamento/
    municipio/localidad usando la API batch de Georef.

    Args:
        coords: lista de tuplas (lat, lon) en WGS84 decimal
        batch_size: máximo de coordenadas por request (default 100)

    Returns:
        dict: {(lat, lon): {"provincia": ..., "departamento": ...,
                            "municipio": ..., "localidad": ...}}
    """
    total = len(coords)
    if total == 0:
        return {}

    resultados = {}
    batches = math.ceil(total / batch_size)
    t0 = time.time()

    for batch_idx in range(batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch_coords = coords[start:end]

        ubicaciones = [{"lat": lat, "lon": lon} for lat, lon in batch_coords]

        # Reintentar si falla
        respuesta = None
        for intento in range(1 + MAX_RETRIES):
            try:
                respuesta = _batch_georef(ubicaciones)
                break
            except (RuntimeError, URLError) as e:
                log.warning("Batch %d/%d — intento %d/%d falló: %s",
                            batch_idx + 1, batches, intento + 1, 1 + MAX_RETRIES, e)
                if intento < MAX_RETRIES:
                    time.sleep(1)
                else:
                    log.error("Batch %d/%d — descartado tras %d reintentos.",
                              batch_idx + 1, batches, 1 + MAX_RETRIES)

        if respuesta is None:
            # Marcar como fallidas
            for lat, lon in batch_coords:
                resultados[(lat, lon)] = {
                    "provincia": None,
                    "departamento": None,
                    "municipio": None,
                    "localidad": None,
                }
            continue

        # Procesar respuestas
        for i, resp in enumerate(respuesta):
            lat, lon = batch_coords[i]
            resultados[(lat, lon)] = _extraer_resultado(resp)

        # Progreso
        elapsed = time.time() - t0
        procesadas = min(end, total)
        log.info("Batch %d/%d — %d/%d coords procesadas (%.1fs)",
                 batch_idx + 1, batches, procesadas, total, elapsed)

    return resultados


# ---------------------------------------------------------------------------
# Operaciones con la base de datos
# ---------------------------------------------------------------------------


def contar_pendientes(conn: sqlite3.Connection) -> int:
    """Cuenta registros con GPS pero sin geocodificar."""
    return conn.execute(
        "SELECT COUNT(*) FROM media WHERE latitude IS NOT NULL AND provincia IS NULL"
    ).fetchone()[0]


def obtener_pendientes(conn: sqlite3.Connection, limit: int = None) -> list[tuple]:
    """
    Obtiene los registros pendientes de geocodificación.

    Returns:
        Lista de (id, lat, lon)
    """
    query = "SELECT id, latitude, longitude FROM media WHERE latitude IS NOT NULL AND provincia IS NULL"
    if limit:
        query += f" LIMIT {limit}"
    return conn.execute(query).fetchall()


def _obtener_todos(conn: sqlite3.Connection, limit: int = None) -> list[tuple]:
    """
    Obtiene TODOS los registros con GPS (para update/replace).

    Returns:
        Lista de (id, lat, lon)
    """
    query = "SELECT id, latitude, longitude FROM media WHERE latitude IS NOT NULL"
    if limit:
        query += f" LIMIT {limit}"
    return conn.execute(query).fetchall()


def geocode_media(db_path: str, limit: int = None, dry_run: bool = False,
                   mode: str = "skip") -> int:
    """
    Geocodifica registros de la BD que tienen GPS.

    Args:
        db_path: ruta a la base de datos SQLite
        limit: máximo de registros a procesar (None = todos)
        dry_run: si True, solo muestra cuántos se procesarían
        mode: skip → solo pendientes (provincia IS NULL)
              update/replace → todos los que tienen GPS

    Returns:
        Cantidad de registros actualizados
    """
    conn = abrir(db_path)
    migrar_db(conn)

    try:
        if mode in ("update", "replace"):
            # Todos los que tienen GPS (actualizar sobreescribe)
            query = "SELECT COUNT(*) FROM media WHERE latitude IS NOT NULL"
            pendientes = conn.execute(query).fetchone()[0]
            label = "geolocalizados"
            obtener_fn = _obtener_todos
        else:
            pendientes = contar_pendientes(conn)
            label = "pendientes"
            obtener_fn = obtener_pendientes

        if pendientes == 0:
            log.info("No hay registros %s de geocodificación.", label)
            return 0

        if dry_run:
            log.info("Dry-run: %d registro(s) %s de geocodificar.", pendientes, label)
            if limit and limit < pendientes:
                log.info("  (limit=%d, se procesarían %d de %d)", limit, limit, pendientes)
            return 0

        if mode == "replace":
            log.info("Modo replace: limpiando geodatos existentes...")
            conn.execute("""
                UPDATE media SET provincia = NULL, departamento = NULL,
                    municipio = NULL, localidad = NULL, geocode_source = NULL,
                    geocode_date = NULL
                WHERE latitude IS NOT NULL
            """)
            conn.commit()

        registros = obtener_fn(conn, limit)
        if not registros:
            return 0

        cantidad = len(registros)
        log.info("Geocodificando %d registro(s)...", cantidad)

        # Preparar coordenadas
        coords = [(lat, lon) for _, lat, lon in registros]

        # Geocodificar por lotes
        resultados = reverse_geocode(coords)

        # Guardar en BD en transacciones de a BATCH_SIZE
        actualizados = 0
        t0 = time.time()

        for batch_start in range(0, cantidad, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, cantidad)
            batch_registros = registros[batch_start:batch_end]

            conn.execute("BEGIN TRANSACTION")
            for media_id, lat, lon in batch_registros:
                res = resultados.get((lat, lon), {})
                conn.execute("""
                    UPDATE media
                    SET provincia = ?,
                        departamento = ?,
                        municipio = ?,
                        localidad = ?,
                        geocode_source = ?,
                        geocode_date = datetime('now')
                    WHERE id = ?
                """, (
                    res.get("provincia"),
                    res.get("departamento"),
                    res.get("municipio"),
                    res.get("localidad"),
                    "georef_api",
                    media_id,
                ))
            conn.commit()

            actualizados += len(batch_registros)
            elapsed = time.time() - t0
            log.info("DB batch %d/%d — %d/%d registros actualizados (%.1fs)",
                     batch_start // BATCH_SIZE + 1,
                     (cantidad + BATCH_SIZE - 1) // BATCH_SIZE,
                     actualizados, cantidad, elapsed)

        log.info("Geocodificación completada: %d registros actualizados.", actualizados)
        return actualizados

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] = None):
    parser = argparse.ArgumentParser(
        description="Geocodificación inversa de coordenadas GPS usando Georef API batch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/geocode.py
  python scripts/geocode.py --coords "-34.6037,-58.3816 -31.4135,-64.1810 -41.1335,-71.3103"
  python scripts/geocode.py --db db/flujos.db --limit 500
  python scripts/geocode.py --dry-run
        """,
    )

    parser.add_argument(
        "--coords", type=str, default=None,
        help=(
            "Coordenadas a geocodificar. "
            "Usar una string separada por espacios: \"lat,lon lat,lon ...\" "
            "Ej: --coords \"-34.6037,-58.3816 -31.4135,-64.1810\""
        )
    )
    parser.add_argument(
        "--db", default=None,
        help="Ruta a la base de datos SQLite (default: db/flujos.db en la raíz del proyecto)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Máximo de registros a procesar"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo mostrar cuántos registros se procesarían sin ejecutar"
    )
    parser.add_argument(
        "--mode", default="skip", choices=["skip", "update", "replace"],
        help="Modo de ejecución: skip (solo pendientes), update (todos), replace (limpiar y regenerar)"
    )

    args = parser.parse_args(argv)

    if args.coords:
        # Modo coordenadas directas
        coords_list = []
        for token in args.coords.strip().split():
            token = token.strip()
            if not token:
                continue
            try:
                lat_str, lon_str = token.split(",")
                lat, lon = float(lat_str), float(lon_str)
                coords_list.append((lat, lon))
            except (ValueError, TypeError):
                log.error("Formato invalido: '%s'. Use lat,lon (ej: -34.6037,-58.3816)", token)
                sys.exit(1)

        if not coords_list:
            log.error("No se proporcionaron coordenadas válidas.")
            sys.exit(1)

        log.info("Geocodificando %d coordenada(s)...", len(coords_list))
        resultados = reverse_geocode(coords_list)

        print()
        print("  Resultados:")
        print("  " + "-" * 70)
        for (lat, lon), datos in resultados.items():
            prov = datos.get("provincia") or "-"
            dept = datos.get("departamento") or "-"
            muni = datos.get("municipio") or "-"
            loc = datos.get("localidad") or "-"
            print(f"  [GPS] ({lat:.4f}, {lon:.4f})")
            print(f"     Provincia:    {prov}")
            print(f"     Departamento: {dept}")
            print(f"     Municipio:    {muni}")
            print(f"     Localidad:    {loc}")
            print("  " + "-" * 70)
        return

    # Modo BD
    db_path = resolver_db(args.db)

    if not os.path.isfile(db_path):
        log.error("Base de datos no encontrada: %s", db_path)
        log.error("Usá --db para especificar una ruta alternativa.")
        sys.exit(1)

    geocode_media(db_path, limit=args.limit, dry_run=args.dry_run, mode=args.mode)


if __name__ == "__main__":
    main()
