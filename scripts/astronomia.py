#!/usr/bin/env python3
"""
astronomia.py — Cálculo de posición del sol (algoritmo NOAA) y clasificación twilight.

Calcula elevación, azimut y distancia del sol para cada registro geolocalizado
con timestamp_utc válido. También clasifica el momento del día (día, golden hour,
blue hour, crepúsculos, noche).

Algoritmo: NOAA Solar Calculator (2017)
Referencia: https://gml.noaa.gov/grad/solcalc/

Columnas que actualiza en la tabla media:
  - sun_elevation      Altura del sol sobre el horizonte (grados, -90 a +90)
  - sun_azimuth        Dirección del sol (grados, 0°=N, 90°=E)
  - sun_distance_au    Distancia al sol en unidades astronómicas (~1.0)
  - twilight_period    Clasificación del momento del día
  - astronomy_source   Fuente del cálculo ('noaa_calculator')

Uso:
    python scripts/astronomia.py                            # Procesa toda la BD
    python scripts/astronomia.py --db ruta.db               # BD alternativa
    python scripts/astronomia.py --dry-run                  # Previsualizar sin escribir
    python scripts/astronomia.py --verbose                  # Mostrar cada punto
"""

import argparse
import logging
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone

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
log = logging.getLogger("astronomia")

# ---------------------------------------------------------------------------
# Columnas que este script gestiona
# ---------------------------------------------------------------------------

ASTRONOMY_COLUMNS = [
    "sun_elevation",
    "sun_azimuth",
    "sun_distance_au",
    "twilight_period",
    "secs_since_sunrise",
    "secs_to_sunset",
    "secs_since_noon",
]

ASTRONOMY_COLUMNS_TEXT = [
    "astronomy_source",
    "sunrise_ts",
    "sunset_ts",
    "solar_noon_ts",
]

# ---------------------------------------------------------------------------
# Algoritmo NOAA Solar Calculator
# ---------------------------------------------------------------------------

def _dia_juliano(dt_utc: datetime) -> float:
    """Calcula el día juliano para una fecha UTC."""
    y = dt_utc.year
    m = dt_utc.month
    d = dt_utc.day + dt_utc.hour / 24.0 + dt_utc.minute / 1440.0 + dt_utc.second / 86400.0

    if m <= 2:
        y -= 1
        m += 12

    A = int(y / 100)
    B = 2 - A + int(A / 4)

    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5


def _posicion_sol(lat: float, lon: float, dt_utc: datetime) -> tuple[float, float, float]:
    """
    Calcula la posición del sol usando el algoritmo NOAA.

    Args:
        lat: Latitud en grados decimales (negativo = sur)
        lon: Longitud en grados decimales (negativo = oeste)
        dt_utc: Fecha/hora en UTC

    Returns:
        (elevacion, azimut, distancia_au) en grados y UA
    """
    jd = _dia_juliano(dt_utc)

    # Medio siglo juliano
    T = (jd - 2451545.0) / 36525.0

    # Coordenadas eclípticas del sol
    L0 = (280.46646 + T * (36000.76983 + 0.0003032 * T)) % 360
    M = (357.52911 + T * (35999.05029 - 0.0001537 * T)) % 360

    # Ecuación del centro
    C = (
        (1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(math.radians(M))
        + (0.019993 - 0.000101 * T) * math.sin(2 * math.radians(M))
        + 0.000289 * math.sin(3 * math.radians(M))
    )

    # Longitud eclíptica del sol
    sun_lon = (L0 + C) % 360

    # Anomalía verdadera
    sun_anom = (M + C) % 360

    # Distancia al sol en UA
    v = sun_anom + 0  # anomalía verdadera
    R = (1.000001018 * (1 - 0.016708634 * math.cos(math.radians(sun_anom)))) ** (-1)
    # R en AU (aproximación simple)

    # Oblicuidad de la eclíptica
    obliquity = 23.439291 - 0.0130042 * T

    # Ascensión recta y declinación
    ra = math.atan2(
        math.cos(math.radians(obliquity)) * math.sin(math.radians(sun_lon)),
        math.cos(math.radians(sun_lon))
    )
    dec = math.asin(
        math.sin(math.radians(obliquity)) * math.sin(math.radians(sun_lon))
    )

    # Ángulo horario local
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360
    ha = (gmst + lon - math.degrees(ra)) % 360
    if ha > 180:
        ha -= 360

    # Elevación y azimut
    lat_rad = math.radians(lat)
    ha_rad = math.radians(ha)

    elev_rad = math.asin(
        math.sin(lat_rad) * math.sin(dec)
        + math.cos(lat_rad) * math.cos(dec) * math.cos(ha_rad)
    )

    azim = math.atan2(
        -math.cos(dec) * math.sin(ha_rad),
        math.sin(dec) * math.cos(lat_rad)
        - math.cos(dec) * math.sin(lat_rad) * math.cos(ha_rad)
    )

    elevacion = math.degrees(elev_rad)
    azimut = (math.degrees(azim) + 360) % 360  # normalizar a 0-360

    return elevacion, azimut, R


# ---------------------------------------------------------------------------
# Eventos solares: amanecer, atardecer, cenit (algoritmo NOAA)
# ---------------------------------------------------------------------------

# Constante: elevación del sol en el horizonte para amanecer/atardecer
# Incluye refracción atmosférica estándar (0.5667°) + radio solar (0.2667°)
HORIZONTE_SOLAR = -0.833


def _geometria_solar_para_fecha(jd_0h: float) -> dict:
    """
    Calcula la geometría solar básica para un día juliano a las 0h UTC.

    Args:
        jd_0h: Día juliano a las 0h UTC

    Returns:
        dict con T, M, C, sun_lon, obliquity, ra_deg, dec_deg, R
    """
    # Medio siglo juliano
    T = (jd_0h - 2451545.0) / 36525.0

    # Coordenadas eclípticas del sol
    L0 = (280.46646 + T * (36000.76983 + 0.0003032 * T)) % 360
    M = (357.52911 + T * (35999.05029 - 0.0001537 * T)) % 360

    # Ecuación del centro
    C = (
        (1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(math.radians(M))
        + (0.019993 - 0.000101 * T) * math.sin(2 * math.radians(M))
        + 0.000289 * math.sin(3 * math.radians(M))
    )

    # Longitud eclíptica del sol
    sun_lon = (L0 + C) % 360

    # Anomalía verdadera
    sun_anom = (M + C) % 360

    # Distancia al sol en UA
    R = (1.000001018 * (1 - 0.016708634 * math.cos(math.radians(sun_anom)))) ** (-1)

    # Oblicuidad de la eclíptica
    obliquity = 23.439291 - 0.0130042 * T

    # Ascensión recta y declinación
    ra = math.atan2(
        math.cos(math.radians(obliquity)) * math.sin(math.radians(sun_lon)),
        math.cos(math.radians(sun_lon))
    )
    dec = math.asin(
        math.sin(math.radians(obliquity)) * math.sin(math.radians(sun_lon))
    )

    return {
        "T": T,
        "M": M,
        "C": C,
        "sun_lon": sun_lon,
        "obliquity": obliquity,
        "ra_deg": math.degrees(ra),
        "dec_deg": math.degrees(dec),
        "R": R,
    }


def _calcular_eventos_solares(
    lat: float, lon: float, dt_utc: datetime
) -> dict:
    """
    Calcula los eventos solares del día (amanecer, atardecer, cenit)
    para una ubicación y fecha específicas.

    Algoritmo NOAA: https://gml.noaa.gov/grad/solcalc/

    Args:
        lat: Latitud en grados decimales (negativo = sur)
        lon: Longitud en grados decimales (negativo = oeste)
        dt_utc: Fecha/hora en UTC (se usa solo la fecha)

    Returns:
        dict con:
            - sunrise: datetime UTC del amanecer (o None si no hay)
            - sunset: datetime UTC del atardecer (o None si no hay)
            - solar_noon: datetime UTC del cenit solar (o None si no hay)
            - dia_sin_ocaso: True si es sol de medianoche
            - dia_sin_amanecer: True si es noche polar
    """
    # Día juliano a las 0h UTC de la fecha
    fecha_0h = dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    jd_0h = _dia_juliano(fecha_0h)

    # Geometría solar del día
    geo = _geometria_solar_para_fecha(jd_0h)

    ra_deg = geo["ra_deg"]
    dec_deg = geo["dec_deg"]

    # GMST a las 0h UTC
    gmst0 = (280.46061837 + 360.98564736629 * (jd_0h - 2451545.0)) % 360

    # ---- Cenit solar (solar noon) ----
    # Ocurre cuando el ángulo horario H = 0:
    # GMST(t) + lon = ra  →  gmst0 + 360.98564736629 * t/24 + lon = ra
    # t = (ra - lon - gmst0) / (360.98564736629/24)
    # 360.98564736629/24 = 15.041068639 grados/hora
    t_noon = (ra_deg - lon - gmst0) / 15.041068639
    # Normalizar a [0, 24)
    t_noon %= 24.0

    # Recalcular geometría para el mediodía para mejor precisión
    noon_dt = fecha_0h.replace(hour=int(t_noon), minute=int((t_noon % 1) * 60))
    jd_noon = _dia_juliano(noon_dt)

    # Una iteración de refinamiento
    T_noon = (jd_noon - 2451545.0) / 36525.0
    M_noon = (357.52911 + T_noon * (35999.05029 - 0.0001537 * T_noon)) % 360
    C_noon = (
        (1.914602 - 0.004817 * T_noon - 0.000014 * T_noon * T_noon) * math.sin(math.radians(M_noon))
        + (0.019993 - 0.000101 * T_noon) * math.sin(2 * math.radians(M_noon))
        + 0.000289 * math.sin(3 * math.radians(M_noon))
    )
    sun_lon_noon = ((280.46646 + T_noon * (36000.76983 + 0.0003032 * T_noon)) % 360 + C_noon) % 360
    obliquity_noon = 23.439291 - 0.0130042 * T_noon
    ra_noon = math.atan2(
        math.cos(math.radians(obliquity_noon)) * math.sin(math.radians(sun_lon_noon)),
        math.cos(math.radians(sun_lon_noon))
    )
    ra_noon_deg = math.degrees(ra_noon)

    # Actualizar t_noon con ra refinado
    gmst0_noon = (280.46061837 + 360.98564736629 * (jd_0h - 2451545.0)) % 360
    t_noon = (ra_noon_deg - lon - gmst0_noon) / 15.041068639
    t_noon %= 24.0

    # Crear datetime del cenit
    horas = int(t_noon)
    minutos = int((t_noon - horas) * 60)
    segundos = int(((t_noon - horas) * 60 - minutos) * 60)
    try:
        solar_noon_dt = fecha_0h.replace(
            hour=horas, minute=minutos, second=segundos, tzinfo=timezone.utc
        )
    except ValueError:
        solar_noon_dt = None

    # ---- Amanecer y atardecer ----
    # cos_H = (sin(elev_horizonte) - sin(lat) * sin(dec)) / (cos(lat) * cos(dec))
    lat_rad = math.radians(lat)
    dec_rad = math.radians(dec_deg)

    cos_H = (
        math.sin(math.radians(HORIZONTE_SOLAR))
        - math.sin(lat_rad) * math.sin(dec_rad)
    ) / (math.cos(lat_rad) * math.cos(dec_rad))

    sunrise_dt = None
    sunset_dt = None
    dia_sin_ocaso = False
    dia_sin_amanecer = False

    if cos_H > 1.0:
        # Sol de medianoche: el sol nunca se pone
        dia_sin_ocaso = True
    elif cos_H < -1.0:
        # Noche polar: el sol nunca sale
        dia_sin_amanecer = True
    else:
        # Mitad del día en grados
        H = math.degrees(math.acos(cos_H))

        # Amanecer = cenit - H/15 horas
        t_sunrise = t_noon - H / 15.0
        t_sunset = t_noon + H / 15.0

        # Crear datetimes
        def _hora_a_dt(hora_frac: float) -> datetime:
            h = int(hora_frac) % 24
            m = int(((hora_frac % 1)) * 60)
            s = int((((hora_frac % 1) * 60) - m) * 60)
            return fecha_0h.replace(hour=h, minute=m, second=s, tzinfo=timezone.utc)

        sunrise_dt = _hora_a_dt(t_sunrise)
        sunset_dt = _hora_a_dt(t_sunset)

    return {
        "sunrise": sunrise_dt,
        "sunset": sunset_dt,
        "solar_noon": solar_noon_dt,
        "dia_sin_ocaso": dia_sin_ocaso,
        "dia_sin_amanecer": dia_sin_amanecer,
    }


def _formatear_hora(dt: datetime | None) -> str:
    """Formatea un datetime como HH:MM:SS o '—' si es None."""
    if dt is None:
        return "—"
    return dt.strftime("%H:%M:%S")


def _formatear_intervalo(segundos: float | None) -> str:
    """
    Formatea un intervalo en segundos a texto human-readable.

    Args:
        segundos: Cantidad de segundos (positivo o negativo)

    Returns:
        Cadena como "2h 15m", "45m", "8s", o "—" si es None
    """
    if segundos is None:
        return "—"
    abs_s = abs(segundos)
    if abs_s >= 3600:
        return f"{int(abs_s // 3600)}h {int((abs_s % 3600) // 60)}m"
    elif abs_s >= 60:
        return f"{int(abs_s // 60)}m"
    else:
        return f"{int(abs_s)}s"


def _texto_solar(dt_utc: datetime, eventos: dict) -> str:
    """
    Genera un texto human-readable con la situación solar.

    Args:
        dt_utc: Timestamp del medio
        eventos: dict de _calcular_eventos_solares()

    Returns:
        Texto como "sol salió hace 2h 15m, se pone en 4h 30m"
    """
    sunrise = eventos["sunrise"]
    sunset = eventos["sunset"]
    noon = eventos["solar_noon"]

    partes = []

    # Tiempo desde/hasta el amanecer
    if sunrise:
        diff = (dt_utc - sunrise).total_seconds()
        if diff > 0:
            partes.append(f"sol sali\u00f3 hace {_formatear_intervalo(diff)}")
        elif diff < 0:
            partes.append(f"sol sale en {_formatear_intervalo(-diff)}")
        else:
            partes.append("sol saliendo ahora")

    # Tiempo desde/hasta el atardecer
    if sunset:
        diff = (sunset - dt_utc).total_seconds()
        if diff > 300:  # más de 5 min para el atardecer
            partes.append(f"se pone en {_formatear_intervalo(diff)}")
        elif diff > 0:
            partes.append("atardeciendo ahora")
        elif diff > -300:
            partes.append("atardecer reci\u00e9n")
        else:
            partes.append(f"se puso hace {_formatear_intervalo(-diff)}")

    return " | ".join(partes) if partes else "sin datos solares"


# ---------------------------------------------------------------------------
# Clasificación del momento del día
# ---------------------------------------------------------------------------

def clasificar_twilight(elevacion: float) -> str:
    """
    Clasifica el momento del día según la elevación del sol.

    Args:
        elevacion: Altura del sol sobre el horizonte (grados)

    Returns:
        Cadena con la clasificación
    """
    if elevacion >= 12.0:
        return "dia"
    elif elevacion >= 6.0:
        return "golden_hour"
    elif elevacion >= 0.0:
        return "blue_hour"
    elif elevacion >= -6.0:
        return "crepuculo_civil"
    elif elevacion >= -12.0:
        return "crepuculo_nautico"
    elif elevacion >= -18.0:
        return "crepuculo_astronomico"
    else:
        return "noche"


# ---------------------------------------------------------------------------
# Migración de schema
# ---------------------------------------------------------------------------

def _asegurar_columnas(conn: sqlite3.Connection) -> None:
    """Agrega columnas de astronomía si no existen."""
    cursor = conn.execute("PRAGMA table_info(media)")
    columnas_existentes = {row[1] for row in cursor.fetchall()}

    for col in ASTRONOMY_COLUMNS:
        if col not in columnas_existentes:
            conn.execute(f"ALTER TABLE media ADD COLUMN {col} REAL")
            log.info("  Columna agregada: %s", col)

    for col in ASTRONOMY_COLUMNS_TEXT:
        if col not in columnas_existentes:
            conn.execute(f"ALTER TABLE media ADD COLUMN {col} TEXT")
            log.info("  Columna agregada: %s", col)

    conn.commit()


# ---------------------------------------------------------------------------
# Procesamiento principal
# ---------------------------------------------------------------------------

def calcular_astronomia(
    db_path: str,
    mode: str = "skip",
    dry_run: bool = False,
) -> dict:
    """
    Calcula posición del sol y clasifica twilight para todos los registros GPS.

    Args:
        db_path: Ruta a la base de datos
        mode: 'skip' (solo pendientes), 'update' (todos), 'replace' (limpiar y regenerar)
        dry_run: Si True, no escribe en la BD

    Returns:
        Diccionario con estadísticas del procesamiento
    """
    conn = abrir(db_path)

    # Verificar si las columnas existen
    cursor = conn.execute("PRAGMA table_info(media)")
    columnas_existentes = {row[1] for row in cursor.fetchall()}
    todas_las_columnas = ASTRONOMY_COLUMNS + ASTRONOMY_COLUMNS_TEXT
    columnas_nuevas = [col for col in todas_las_columnas if col not in columnas_existentes]

    if columnas_nuevas and not dry_run:
        _asegurar_columnas(conn)
        log.info("Columnas nuevas agregadas: %s", ", ".join(columnas_nuevas))
    elif columnas_nuevas and dry_run:
        log.info("Columnas nuevas (no se crearán en dry-run): %s", ", ".join(columnas_nuevas))

    # Limpiar si es replace
    if mode == "replace" and not dry_run:
        for col in ASTRONOMY_COLUMNS:
            conn.execute(f"UPDATE media SET {col} = NULL")
        for col in ASTRONOMY_COLUMNS_TEXT:
            conn.execute(f"UPDATE media SET {col} = NULL")
        conn.commit()
        log.info("Columnas de astronomía limpiadas (modo replace).")

    # Construir query según modo
    where = "WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND timestamp_utc IS NOT NULL"
    if mode == "skip" and "sun_elevation" in columnas_existentes:
        where += " AND sun_elevation IS NULL"

    query = f"""
        SELECT id, latitude, longitude, timestamp_utc
        FROM media
        {where}
        ORDER BY timestamp_utc
    """

    cursor = conn.execute(query)
    registros = cursor.fetchall()
    total = len(registros)

    if total == 0:
        log.info("No hay registros pendientes de procesar.")
        conn.close()
        return {"total": 0, "procesados": 0, "errores": 0,
                "con_amanecer": 0, "con_atardecer": 0, "con_cenit": 0,
                "dia_sin_ocaso": 0, "dia_sin_amanecer": 0}

    log.info("Registros a procesar: %d", total)

    procesados = 0
    errores = 0
    eventos_estadisticas = {
        "con_amanecer": 0,
        "con_atardecer": 0,
        "con_cenit": 0,
        "dia_sin_ocaso": 0,
        "dia_sin_amanecer": 0,
    }

    for media_id, lat, lon, ts_utc in registros:
        try:
            # Parsear timestamp UTC
            if "T" in ts_utc:
                dt_utc = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
            else:
                dt_utc = datetime.strptime(ts_utc, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )

            # Calcular posición del sol
            elevacion, azimut, distancia = _posicion_sol(lat, lon, dt_utc)

            # Clasificar twilight
            twilight = clasificar_twilight(elevacion)

            # Calcular eventos solares del día
            eventos = _calcular_eventos_solares(lat, lon, dt_utc)

            # Calcular tiempos relativos (segundos)
            def _diff_seg(dt_evento: datetime | None) -> float | None:
                if dt_evento is None:
                    return None
                return (dt_utc - dt_evento).total_seconds()

            secs_since_sunrise = _diff_seg(eventos["sunrise"])
            secs_to_sunset = (
                (eventos["sunset"] - dt_utc).total_seconds()
                if eventos["sunset"] else None
            )
            secs_since_noon = _diff_seg(eventos["solar_noon"])

            # Texto human-readable
            texto_solar = _texto_solar(dt_utc, eventos)

            # Preparar valores para DB
            sunrise_str = (
                eventos["sunrise"].isoformat() if eventos["sunrise"] else None
            )
            sunset_str = (
                eventos["sunset"].isoformat() if eventos["sunset"] else None
            )
            noon_str = (
                eventos["solar_noon"].isoformat() if eventos["solar_noon"] else None
            )

            if dry_run:
                log.info(
                    "  [DRY] ID=%d | %s | elev=%.1f deg | %s",
                    media_id, _formatear_hora(dt_utc), elevacion, texto_solar,
                )
            else:
                conn.execute(
                    """UPDATE media SET
                        sun_elevation = ?,
                        sun_azimuth = ?,
                        sun_distance_au = ?,
                        twilight_period = ?,
                        sunrise_ts = ?,
                        sunset_ts = ?,
                        solar_noon_ts = ?,
                        secs_since_sunrise = ?,
                        secs_to_sunset = ?,
                        secs_since_noon = ?,
                        astronomy_source = 'noaa_calculator',
                        updated_at = datetime('now')
                    WHERE id = ?""",
                    (
                        elevacion, azimut, distancia, twilight,
                        sunrise_str, sunset_str, noon_str,
                        secs_since_sunrise, secs_to_sunset, secs_since_noon,
                        media_id,
                    ),
                )

            procesados += 1

            if eventos["sunrise"]:
                eventos_estadisticas["con_amanecer"] += 1
            if eventos["sunset"]:
                eventos_estadisticas["con_atardecer"] += 1
            if eventos["solar_noon"]:
                eventos_estadisticas["con_cenit"] += 1
            if eventos["dia_sin_ocaso"]:
                eventos_estadisticas["dia_sin_ocaso"] += 1
            if eventos["dia_sin_amanecer"]:
                eventos_estadisticas["dia_sin_amanecer"] += 1

            if procesados % 50 == 0:
                log.info("  Procesados: %d/%d", procesados, total)

        except Exception as e:
            log.warning("  Error en media_id=%d: %s", media_id, e)
            errores += 1

    if not dry_run:
        conn.commit()

    conn.close()

    resultado = {
        "total": total,
        "procesados": procesados,
        "errores": errores,
    }
    resultado.update(eventos_estadisticas)
    return resultado


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Calcula posición del sol y clasifica twilight (algoritmo NOAA).",
        epilog="""
Ejemplos:
  python scripts/astronomia.py                    # Procesa toda la BD
  python scripts/astronomia.py --dry-run          # Solo previsualizar
  python scripts/astronomia.py --mode replace     # Recalcular todo
  python scripts/astronomia.py --verbose          # Ver cada punto
        """,
    )
    parser.add_argument(
        "--db", default=None,
        help="Ruta a la base de datos SQLite (default: db/flujos.db en la raíz del proyecto)",
    )
    parser.add_argument(
        "--mode", choices=["skip", "update", "replace"], default="skip",
        help="Modo de procesamiento: skip=solo pendientes, update= todos, replace=limpiar y regenerar (default: skip)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Previsualizar sin escribir en la BD",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Mostrar información detallada durante el proceso",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        log.setLevel(logging.DEBUG)

    # Resolver ruta de DB
    db_path = resolver_db(args.db)

    log.info("Base de datos: %s", db_path)
    log.info("Modo: %s", args.mode)
    if args.dry_run:
        log.info("Modo DRY RUN — no se escribirá en la BD")

    # Ejecutar
    resultado = calcular_astronomia(db_path, mode=args.mode, dry_run=args.dry_run)

    # Resumen
    log.info("")
    log.info("=== Resumen ===")
    log.info("  Total registros: %d", resultado["total"])
    log.info("  Procesados: %d", resultado["procesados"])
    log.info("  Errores: %d", resultado["errores"])
    log.info("")
    log.info("  Amaneceres calculados:  %d", resultado["con_amanecer"])
    log.info("  Atardeceres calculados: %d", resultado["con_atardecer"])
    log.info("  Cenits calculados:      %d", resultado["con_cenit"])
    if resultado["dia_sin_ocaso"]:
        log.info("  Días sin ocaso (sol de medianoche): %d", resultado["dia_sin_ocaso"])
    if resultado["dia_sin_amanecer"]:
        log.info("  Días sin amanecer (noche polar):   %d", resultado["dia_sin_amanecer"])

    if not args.dry_run and resultado["procesados"] > 0:
        # Mostrar distribución de twilight
        conn = abrir(db_path)
        cursor = conn.execute(
            "SELECT twilight_period, COUNT(*) FROM media WHERE twilight_period IS NOT NULL GROUP BY twilight_period ORDER BY COUNT(*) DESC"
        )
        log.info("")
        log.info("Distribución de twilight:")
        for periodo, count in cursor.fetchall():
            log.info("  %-25s %d", periodo, count)
        conn.close()


if __name__ == "__main__":
    main()
