#!/usr/bin/env python3
"""Diagnostica cámaras Insta360 en una carpeta de videos 360°.

Para cada .mp4 encontrado recursivamente, extrae el QuickTime:CreateDate
embebido (UTC), bitrate, fps y el timestamp del filename. Clasifica la
cámara (A / B / B reconfigurada / desconocida) y calcula la hora real
local Argentina (CreateDate − 3 h).

No escribe en la DB — es una utilidad de solo lectura.

Uso:
    python scripts/diagnosticar_camaras_360.py --root <carpeta>
    python scripts/diagnosticar_camaras_360.py --root <carpeta> --solo-resumen
    python scripts/diagnosticar_camaras_360.py --root <carpeta> --json
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────────

UTC = timezone.utc
OFFSET_ARGENTINA = timedelta(hours=3)  # Argentina = UTC−3

# Perfiles de cámara (bitrate en bps)
BITRATE_A_MBPS = 55  # ≥55 Mbps → cámara A
BITRATE_B_MIN_MBPS = 25  # >25 y <55 → cámara B
BITRATE_B_MAX_MBPS = 55
FPS_2997 = 29.97
FPS_24 = 24.0

# Offsets normales filename→embebido (horas)
OFFSET_A_NORMAL = 7.0  # A: filename +7h = embebido UTC
OFFSET_B_NORMAL = -1.0  # B: filename −1h = embebido UTC

# Regex para extraer timestamp del filename
RE_FILENAME = re.compile(r"VID_(\d{8})_(\d{6})")


# ── Helpers externos ────────────────────────────────────────────────────────

def _buscar_exiftool() -> str | None:
    """Busca exiftool en ubicaciones conocidas y en PATH."""
    candidatos = [
        r"C:\Program Files\digiKam\exiftool.exe",
        r"C:\Program Files\exiftool.exe",
        "exiftool",
    ]
    for ruta in candidatos:
        if ruta == "exiftool":
            hallado = shutil.which(ruta)
            if hallado:
                return hallado
        elif os.path.isfile(ruta):
            return ruta
    return None


def _buscar_ffprobe() -> str | None:
    """Busca ffprobe en PATH."""
    hallado = shutil.which("ffprobe")
    return hallado


# ── Extracción de metadatos ─────────────────────────────────────────────────

def _extraer_create_date(exiftool: str, ruta: str) -> str | None:
    """Extrae QuickTime:CreateDate con exiftool -json -n. Devuelve str ISO o None."""
    cmd = [exiftool, "-json", "-n", "-QuickTime:CreateDate", ruta]
    try:
        resultado = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if resultado.returncode != 0:
            log.debug("  exiftool error %s: %s", Path(ruta).name, resultado.stderr.strip()[:200])
            return None
        datos = json.loads(resultado.stdout)
        if not datos:
            return None
        fecha = datos[0].get("CreateDate")
        return str(fecha) if fecha else None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        log.debug("  exiftool excepción %s: %s", Path(ruta).name, exc)
        return None


def _extraer_video_info(ffprobe: str, ruta: str) -> tuple[float | None, int | None]:
    """Extrae r_frame_rate y bitrate con ffprobe. Devuelve (fps, bitrate_bps)."""
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,bit_rate",
        "-of", "json",
        ruta,
    ]
    try:
        resultado = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if resultado.returncode != 0:
            log.debug("  ffprobe error %s: %s", Path(ruta).name, resultado.stderr.strip()[:200])
            return None, None
        datos = json.loads(resultado.stdout)
        streams = datos.get("streams", [])
        if not streams:
            return None, None
        stream = streams[0]

        # Parsear fps desde "num/den"
        fps = None
        r_frame_rate = stream.get("r_frame_rate")
        if r_frame_rate and "/" in str(r_frame_rate):
            partes = str(r_frame_rate).split("/")
            try:
                num, den = int(partes[0]), int(partes[1])
                fps = round(num / den, 2) if den else None
            except (ValueError, ZeroDivisionError):
                fps = None
        elif r_frame_rate:
            try:
                fps = round(float(r_frame_rate), 2)
            except ValueError:
                fps = None

        # Bitrate puede ser "N/A" o estar en stream en vez de format
        bitrate = None
        br = stream.get("bit_rate")
        if br and br != "N/A":
            try:
                bitrate = int(br)
            except ValueError:
                pass

        return fps, bitrate
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        log.debug("  ffprobe excepción %s: %s", Path(ruta).name, exc)
        return None, None


# ── Parseo y clasificación ─────────────────────────────────────────────────

def _parsear_timestamp_filename(nombre: str) -> datetime | None:
    """Extrae datetime del pattern VID_YYYYMMDD_HHMMSS del filename."""
    m = RE_FILENAME.search(nombre)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _parsear_create_date(fecha_str: str) -> datetime | None:
    """Parsea un string de CreateDate (ISO-like) a datetime aware UTC."""
    if not fecha_str:
        return None
    # ExifTool puede devolver: "2025:08:24 20:52:18" o "2025-08-24T20:52:18"
    # Normalizar separadores
    normalizado = fecha_str.replace(":", "-", 2)
    # Probar formatos comunes
    formatos = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S+00:00",
    ]
    for fmt in formatos:
        try:
            dt = datetime.strptime(normalizado, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    log.debug("  No se pudo parsear CreateDate: %s", fecha_str)
    return None


def _clasificar_camara(
    bitrate_bps: int | None, fps: float | None,
) -> str:
    """Clasifica la cámara por bitrate y fps."""
    if fps is None or bitrate_bps is None:
        return "desconocida"

    bitrate_mbps = bitrate_bps / 1_000_000

    # B con fps cambiado (24 fps, bitrate ~40-50 Mbps — caso Termas)
    if fps is not None and 23.5 <= fps <= 24.5 and 35 <= bitrate_mbps <= 55:
        return "B (fps cambiado)"

    # Cámara A: bitrate >= 55 Mbps, fps ~29.97
    if bitrate_mbps >= BITRATE_A_MBPS and fps is not None and abs(fps - FPS_2997) < 0.5:
        return "A (LA +7h)"

    # Cámara B: 25 < bitrate < 55, fps ~29.97
    if BITRATE_B_MIN_MBPS < bitrate_mbps < BITRATE_B_MAX_MBPS and fps is not None and abs(fps - FPS_2997) < 0.5:
        return "B (UTC+1 −1h)"

    return "desconocida"


def _clasificar_camara_extendida(
    bitrate_bps: int | None, fps: float | None,
    offset_hrs: float | None,
) -> tuple[str, str]:
    """Clasifica cámara y genera nota de anomalía si aplica.

    Devuelve (camara, nota).
    """
    camara = _clasificar_camara(bitrate_bps, fps)
    nota = ""

    if offset_hrs is None or camara == "desconocida":
        if camara == "desconocida":
            nota = "perfil no reconocido"
        return camara, nota

    if camara.startswith("A"):
        if abs(offset_hrs - OFFSET_A_NORMAL) < 0.01:
            nota = ""
        elif abs(offset_hrs - 7.5) < 0.01:
            nota = "REVISAR (filename atrasado 30min, embebido OK)"
        else:
            nota = f"REVISAR (offset {offset_hrs:+.1f}h, esperado +7.0h)"
    elif camara.startswith("B"):
        if "fps" in camara:
            # B con fps cambiado — offset -1h esperado
            if abs(offset_hrs - OFFSET_B_NORMAL) < 0.01:
                nota = "24fps (config especial)"
            else:
                nota = f"REVISAR (24fps + offset {offset_hrs:+.1f}h)"
        elif abs(offset_hrs - OFFSET_B_NORMAL) < 0.01:
            nota = ""
        else:
            nota = f"REVISAR (reloj reconfigurado, offset {offset_hrs:+.1f}h)"

    return camara, nota


# ── Procesamiento principal ────────────────────────────────────────────────

def _procesar_video(
    ruta: str, exiftool: str, ffprobe: str,
) -> dict:
    """Procesa un video individual y devuelve un dict con toda la info."""
    nombre = Path(ruta).name
    resultado: dict = {
        "archivo": nombre,
        "ruta": ruta,
        "fecha": "",
        "filename_time": "",
        "create_date_utc": "",
        "hora_real_local": "",
        "offset_hrs": "",
        "fps": "",
        "bitrate_mbps": "",
        "camara": "",
        "notas": "",
    }

    # 1. Timestamp del filename
    ts_filename = _parsear_timestamp_filename(nombre)
    if ts_filename:
        resultado["filename_time"] = ts_filename.strftime("%Y-%m-%d %H:%M:%S")

    # 2. CreateDate embebido
    create_str = _extraer_create_date(exiftool, ruta)
    ts_utc = _parsear_create_date(create_str)
    if ts_utc:
        resultado["create_date_utc"] = ts_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

    # 3. fps y bitrate
    fps, bitrate_bps = _extraer_video_info(ffprobe, ruta)
    if fps is not None:
        resultado["fps"] = str(fps)
    if bitrate_bps is not None:
        resultado["bitrate_mbps"] = str(round(bitrate_bps / 1_000_000, 1))

    # 4. Hora real local
    if ts_utc:
        hora_real = ts_utc - OFFSET_ARGENTINA
        resultado["hora_real_local"] = hora_real.strftime("%Y-%m-%d %H:%M:%S")
        resultado["fecha"] = hora_real.strftime("%Y-%m-%d")

    # 5. Offset filename→embebido
    # ts_filename es naive (reloj de cámara, sin tz); ts_utc es aware.
    # Para calcular la diferencia horaria, ambos se tratan como números crudos.
    offset_hrs = None
    if ts_filename and ts_utc:
        diff = ts_utc.replace(tzinfo=None) - ts_filename
        offset_hrs = diff.total_seconds() / 3600
        resultado["offset_hrs"] = f"{offset_hrs:+.1f}h"

    # 6. Clasificar cámara y anomalías
    camara, nota = _clasificar_camara_extendida(bitrate_bps, fps, offset_hrs)
    resultado["camara"] = camara
    resultado["notas"] = nota

    return resultado


# ── Presentación ────────────────────────────────────────────────────────────

def _imprimir_tabla(resultados: list[dict]) -> None:
    """Imprime la tabla de resultados formateada."""
    if not resultados:
        log.info("No se encontraron videos .mp4 en la carpeta.")
        return

    # Ordenar por hora real local (vacíos al final)
    resultados_ord = sorted(
        resultados,
        key=lambda r: r["hora_real_local"] or "9999",
    )

    # Anchos de columna
    cols = [
        ("archivo", 42, "archivo"),
        ("fecha", 12, "fecha"),
        ("filename_time", 20, "filename"),
        ("create_date_utc", 24, "embebido UTC"),
        ("hora_real_local", 22, "hora real local"),
        ("offset_hrs", 9, "offset"),
        ("fps", 6, "fps"),
        ("bitrate_mbps", 10, "bitrate"),
        ("camara", 20, "camara"),
        ("notas", 48, "notas"),
    ]

    # Encabezado
    header = "  ".join(c[2].ljust(c[1]) for c in cols)
    separador = "  ".join("─" * c[1] for c in cols)
    log.info("")
    log.info(header)
    log.info(separador)

    # Filas
    for r in resultados_ord:
        fila = "  ".join(str(r.get(c[0], "")).ljust(c[1]) for c in cols)
        log.info(fila)


def _imprimir_resumen(resultados: list[dict]) -> None:
    """Imprime resumen: conteos por cámara y archivos a revisar."""
    if not resultados:
        log.info("No se encontraron videos para analizar.")
        return

    # Contar por cámara
    conteos: dict[str, int] = {}
    for r in resultados:
        cam = r["camara"] or "desconocida"
        conteos[cam] = conteos.get(cam, 0) + 1

    log.info("")
    log.info("══ RESUMEN ══")
    log.info(f"  Total de videos: {len(resultados)}")
    log.info("")
    log.info("  Por cámara:")
    for cam, n in sorted(conteos.items()):
        log.info(f"    {cam}: {n}")

    # Archivos a revisar
    revisar = [r for r in resultados if "REVISAR" in (r.get("notas") or "")]
    if revisar:
        log.info("")
        log.info(f"  Archivos marcados para revisión manual ({len(revisar)}):")
        for r in revisar:
            log.info(f"    • {r['archivo']}  →  {r['notas']}")
    else:
        log.info("")
        log.info("  No hay archivos marcados para revisión.")

    log.info("")
    log.info("  Hora real = CreateDate − 3h (embebido=UTC). Filename NO confiable.")


def _salir_json(resultados: list[dict]) -> None:
    """Imprime resultados como JSON a stdout (UTF-8)."""
    # En Windows con pipe, stdout puede estar en cp1252; reconfigurar a UTF-8
    # para que caracteres como − (U+2212) se escriban correctamente.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    json.dump(resultados, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


# ── Entry point ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description=(
            "Diagnostica cámaras Insta360 en una carpeta de videos 360°. "
            "Clasifica cámara (A/B), calcula hora real local y marca anomalías."
        ),
    )
    parser.add_argument(
        "--root", required=True,
        help="Carpeta raíz a escanear recursivamente (.mp4)",
    )
    parser.add_argument(
        "--solo-resumen", action="store_true",
        help="Imprimir solo el resumen, omitir la tabla por archivo",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Salida en formato JSON (a stdout)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Salida detallada (debug)",
    )
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Validar carpeta
    root = Path(args.root)
    if not root.is_dir():
        log.error("La carpeta no existe: %s", root)
        sys.exit(1)

    # Buscar herramientas externas
    exiftool = _buscar_exiftool()
    if not exiftool:
        log.error("exiftool no encontrado. Instalalo o agregalo al PATH.")
        sys.exit(1)
    ffprobe = _buscar_ffprobe()
    if not ffprobe:
        log.error("ffprobe no encontrado. Instalalo o agregalo al PATH.")
        sys.exit(1)

    log.info("Carpeta: %s", root)
    log.info("ExifTool: %s", exiftool)
    log.info("FFprobe:  %s", ffprobe)

    # Buscar archivos .mp4 recursivamente, ignorando ocultos (._*)
    archivos: list[Path] = []
    for archivo in root.rglob("*.mp4"):
        if archivo.name.startswith("._"):
            continue
        archivos.append(archivo)

    log.info("Videos encontrados: %d", len(archivos))

    if not archivos:
        if args.json:
            _salir_json([])
        else:
            log.info("No se encontraron archivos .mp4 en %s", root)
        return

    # Procesar cada video
    resultados: list[dict] = []
    for i, archivo in enumerate(archivos, 1):
        log.debug("[%d/%d] %s", i, len(archivos), archivo.name)
        info = _procesar_video(str(archivo), exiftool, ffprobe)
        resultados.append(info)

    # Salida
    if args.json:
        _salir_json(resultados)
    else:
        if not args.solo_resumen:
            _imprimir_tabla(resultados)
        _imprimir_resumen(resultados)


if __name__ == "__main__":
    main()
