#!/usr/bin/env python3
"""
repetir_contenido.py — Detecta contenido repetido por coincidencias de audio.

Compara la pista de audio de los medios (videos/audios) y encuentra pares
que comparten el mismo pasaje sonoro (escena repetida, clip reutilizado,
audio duplicado, etc.). Solo reporta; no escribe en la DB.

Método:
    1. ffmpeg extrae el audio a mono 16 kHz (en memoria, reutiliza la rutina
       de audio_tagging.py).
    2. Se calcula un vector de energía RMS por ventana de VENTANA_SECS (2 s,
       hop 0.5 s).
    3. Para cada par de archivos se hace cross-correlación coseno del vector
       RMS: el pico indica cuánto se parecen (0-1) y en qué momento (lag) del
       segundo archivo empieza la coincidencia.
    4. Se reportan los pares con similitud >= umbral y duración del pasaje
       coincidente >= min-duracion-segs.

Uso:
    python scripts/repetir_contenido.py                       # compara todos contra todos
    python scripts/repetir_contenido.py --contra D:/ruta.mp4  # un archivo contra el resto
    python scripts/repetir_contenido.py --limite 10           # prueba con los primeros 10
    python scripts/repetir_contenido.py --umbral 0.75
    python scripts/repetir_contenido.py --min-duracion-segs 3
    python scripts/repetir_contenido.py --json reporte.json
"""

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.util import abrir, resolver_db
from scripts.ai_media.audio_tagging import _extraer_audio_ffmpeg

VENTANA_SECS = 2.0      # duración de cada ventana de energía (en segundos)
HOP_SECS = 0.5           # avance entre ventanas (en segundos)
TASA_RMS = 8000          # tasa de muestreo para el cálculo de RMS (downsample)

TIPOS_CON_AUDIO = ("video", "audio")


# ═══════════════════════════════════════════════════════════════
#  FEATURES DE AUDIO
# ═══════════════════════════════════════════════════════════════


def _feature_rms(ruta_archivo: str) -> list[float] | None:
    """Extrae el audio de un archivo y devuelve el vector de energía RMS.

    Cada elemento del vector es la energía RMS de una ventana de
    VENTANA_SECS segundos (hop HOP_SECS). Se baja a TASA_RMS para
    hacer la comparación económica.

    Args:
        ruta_archivo: Ruta absoluta al archivo de audio/video.

    Returns:
        Lista de floats (energía RMS por ventana), o None si el archivo
        no tiene audio o falló la extracción.
    """
    try:
        samples, rate = _extraer_audio_ffmpeg(ruta_archivo)
    except RuntimeError as e:
        log.debug("  Sin audio en %s: %s", ruta_archivo, e)
        return None
    if not samples:
        return None

    # Downsample simple a TASA_RMS (promedio cada `factor` muestras)
    factor = max(1, rate // TASA_RMS)
    if factor > 1:
        n = len(samples) // factor
        arr = np.asarray(samples[: n * factor], dtype=np.float64)
        muestras = arr.reshape(n, factor).mean(axis=1).tolist()
        rate = TASA_RMS
    else:
        muestras = samples

    tam_ventana = max(1, int(VENTANA_SECS * rate))
    paso = max(1, int(HOP_SECS * rate))
    features: list[float] = []
    i = 0
    while i + tam_ventana <= len(muestras):
        ventana = muestras[i:i + tam_ventana]
        rms = math.sqrt(sum(x * x for x in ventana) / len(ventana))
        features.append(rms)
        i += paso
    return features


# ═══════════════════════════════════════════════════════════════
#  COMPARACIÓN ENTRE ARCHIVOS
# ═══════════════════════════════════════════════════════════════


def _correlacion_max(a: list[float], b: list[float]) -> tuple[float, int, int]:
    """Cross-correlación coseno entre el vector corto `a` y el largo `b`.

    Calcula la similitud coseno de `a` contra cada segmento de la misma
    longitud dentro de `b` (convolución por numpy) y devuelve el pico.

    Args:
        a: Vector de features del archivo corto (candidato).
        b: Vector de features del archivo largo (base).

    Returns:
        Tupla (similitud, inicio_b, fin_b):
            - similitud: máximo coseno en [0, 1] (0 = nada que ver).
            - inicio_b / fin_b: índice de ventana en `b` donde empieza/termina
              el pasaje más parecido a `a`.
    """
    an = np.asarray(a, dtype=np.float64)
    bn = np.asarray(b, dtype=np.float64)
    la = len(an)
    lb = len(bn)
    if la < 2 or lb < la:
        return 0.0, 0, 0

    # Normalizar `a` y `b` (restar media)
    an = an - an.mean()
    bn = bn - bn.mean()
    norma_a = float(np.sqrt((an * an).sum()))
    if norma_a == 0:
        return 0.0, 0, 0

    # Convolución: corr[i] = suma(an * bn[i:i+la]) para cada desplazamiento
    corr = np.correlate(bn, an, mode="valid")  # longitud = lb - la + 1

    # Energía local de cada segmento de bn (para normalizar el coseno)
    cum = np.concatenate(([0.0], np.cumsum(bn * bn)))
    energia_local = cum[la:] - cum[:-la]
    denom = np.sqrt(energia_local * (norma_a ** 2))
    denom[denom == 0] = 1.0
    sim = corr / denom

    idx = int(np.argmax(sim))
    valor = float(sim[idx])
    return valor, idx, idx + la


def _segundos_desde_inicio(idx: int) -> float:
    """Convierte un índice de ventana a segundos desde el inicio del audio."""
    return round(idx * HOP_SECS, 2)


# ═══════════════════════════════════════════════════════════════
#  ARMADO DEL REPORTE
# ═══════════════════════════════════════════════════════════════


def _formatear_tiempo(segundos: float) -> str:
    """Formatea segundos como mm:ss."""
    s = int(segundos)
    return f"{s // 60}:{s % 60:02d}"


def _formatear_pasaje(inicio_s: float, fin_s: float) -> str:
    """Formatea un pasaje de audio como 'mm:ss → mm:ss'."""
    return f"{_formatear_tiempo(inicio_s)} → {_formatear_tiempo(fin_s)}"


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    """Entry point para la detección de contenido repetido.

    Args:
        argv: Lista de argumentos (sin el nombre del script).
               Si es None, usa sys.argv[1:].

    Returns:
        Código de salida (0 = ok, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Detecta contenido repetido por coincidencias de audio "
                    "(cross-correlación de energía RMS). Solo reporta.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None,
                        help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--contra", default=None,
                        help="Comparar solo este archivo contra el resto (ruta absoluta)")
    parser.add_argument("--limite", type=int, default=None,
                        help="Limitar a N archivos (para pruebas; no aplica con --contra)")
    parser.add_argument("--umbral", type=float, default=0.80,
                        help="Similitud mínima del pasaje para reportar (default: 0.80)")
    parser.add_argument("--min-duracion-segs", type=float, default=4.0,
                        help="Duración mínima del pasaje coincidente (default: 4 s)")
    parser.add_argument("--top", type=int, default=20,
                        help="Cuántos pares reportar (default: 20)")
    parser.add_argument("--json", default=None,
                        help="Exportar el reporte a JSON")
    parser.add_argument("--verbose", action="store_true",
                        help="Log detallado")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Consola Windows: permitir caracteres UTF-8 (→, ↔, etc.) sin UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if not 0 <= args.umbral <= 1:
        log.error("  --umbral debe estar entre 0 y 1 (recibido: %s)", args.umbral)
        return 1

    # ── Recolectar archivos ──
    archivos: list[tuple[int, str, str, str]] = []  # (media_id, type, filename, ruta)

    if args.contra:
        ruta_contra = os.path.abspath(args.contra)
        if not os.path.isfile(ruta_contra):
            log.error("  No existe el archivo: %s", ruta_contra)
            return 1
        db_path = resolver_db(args.db)
        conn = abrir(db_path)
        conn.row_factory = None
        try:
            rows = conn.execute(
                "SELECT id, type, filename_original, filepath_absoluto "
                "FROM media WHERE type IN (?, ?) AND filepath_absoluto IS NOT NULL "
                "AND filepath_absoluto != ?",
                (*TIPOS_CON_AUDIO, ruta_contra),
            ).fetchall()
        finally:
            conn.close()
        archivos = [tuple(r) for r in rows]
        log.info("Comparando %s contra %d medios de la DB", ruta_contra, len(archivos))
    else:
        db_path = resolver_db(args.db)
        conn = abrir(db_path)
        conn.row_factory = None
        try:
            rows = conn.execute(
                "SELECT id, type, filename_original, filepath_absoluto "
                "FROM media WHERE type IN (?, ?) AND filepath_absoluto IS NOT NULL "
                "ORDER BY duration_secs DESC",
                TIPOS_CON_AUDIO,
            ).fetchall()
        finally:
            conn.close()
        archivos = [tuple(r) for r in rows]
        if args.limite:
            archivos = archivos[: args.limite]
        log.info("Comparando %d medios entre sí (mode: todos contra todos)", len(archivos))

    if not archivos:
        print("  No hay medios de audio/video con archivo para comparar.")
        return 0

    # ── Extraer features de audio (con fallback silencioso) ──
    features: dict[str, list[float]] = {}   # ruta → vector RMS
    sin_audio: list[str] = []
    for _mid, _tipo, nombre, ruta in archivos:
        if not os.path.isfile(ruta):
            sin_audio.append(nombre)
            continue
        feat = _feature_rms(ruta)
        if feat is None:
            sin_audio.append(nombre)
        else:
            features[ruta] = feat

    log.info("  Features de audio extraídos: %d | sin audio/error: %d",
             len(features), len(sin_audio))
    if not features:
        print("  No se pudo extraer audio de ningún archivo.")
        return 1

    # ── Comparar pares ──
    rutas = list(features.keys())
    reportes: list[dict] = []
    pares_evaluados = 0

    if args.contra:
        # contra: base = features de la DB, corto = archivo único.
        # M2: el más corto va como `a` (candidato), el más largo como `b`
        # (base) — igual que en all-pairs — para no obtener falso negativo
        # si el clip consultado es MÁS LARGO que el medio de la DB.
        feat_contra = _feature_rms(ruta_contra)
        if feat_contra is None:
            log.error("  No se pudo extraer audio de --contra: %s", ruta_contra)
            return 1
        for ruta in rutas:
            pares_evaluados += 1
            if len(feat_contra) <= len(features[ruta]):
                a, b = feat_contra, features[ruta]
                sim, inicio_b, fin_b = _correlacion_max(a, b)
                reporte = {
                    "contra": os.path.basename(ruta_contra),
                    "base": os.path.basename(ruta),
                    "similitud": round(sim, 3),
                    "duracion_pasaje_s": round((fin_b - inicio_b) * HOP_SECS, 1),
                    "inicio_contra_s": 0.0,
                    "inicio_base_s": _segundos_desde_inicio(inicio_b),
                    "fin_base_s": _segundos_desde_inicio(fin_b),
                }
            else:
                # contra más largo que el medio: el pasaje detectado cae en el contra
                a, b = features[ruta], feat_contra
                sim, inicio_b, fin_b = _correlacion_max(a, b)
                log.info("  --contra más largo que %s: el pasaje se ubica en el contra.",
                         os.path.basename(ruta))
                reporte = {
                    "contra": os.path.basename(ruta_contra),
                    "base": os.path.basename(ruta),
                    "similitud": round(sim, 3),
                    "duracion_pasaje_s": round((fin_b - inicio_b) * HOP_SECS, 1),
                    "inicio_contra_s": _segundos_desde_inicio(inicio_b),
                    "fin_contra_s": _segundos_desde_inicio(fin_b),
                    "inicio_base_s": 0.0,
                    "fin_base_s": round(len(a) * HOP_SECS, 1),
                }
            if reporte["similitud"] >= args.umbral and reporte["duracion_pasaje_s"] >= args.min_duracion_segs:
                reportes.append(reporte)
    else:
        for i in range(len(rutas)):
            for j in range(i + 1, len(rutas)):
                ruta_a, ruta_b = rutas[i], rutas[j]
                pares_evaluados += 1
                # El más corto como `a` (candidato), el más largo como `b` (base)
                if len(features[ruta_a]) <= len(features[ruta_b]):
                    a, b = features[ruta_a], features[ruta_b]
                    nombre_a, nombre_b = os.path.basename(ruta_a), os.path.basename(ruta_b)
                else:
                    a, b = features[ruta_b], features[ruta_a]
                    nombre_a, nombre_b = os.path.basename(ruta_b), os.path.basename(ruta_a)
                sim, inicio_b, fin_b = _correlacion_max(a, b)
                duracion_pasaje = (fin_b - inicio_b) * HOP_SECS
                if sim >= args.umbral and duracion_pasaje >= args.min_duracion_segs:
                    reportes.append({
                        "archivo_a": nombre_a,
                        "archivo_b": nombre_b,
                        "similitud": round(sim, 3),
                        "duracion_pasaje_s": round(duracion_pasaje, 1),
                        "inicio_a_s": 0.0,
                        "inicio_b_s": _segundos_desde_inicio(inicio_b),
                        "fin_b_s": _segundos_desde_inicio(fin_b),
                    })

    reportes.sort(key=lambda r: -r["similitud"])
    reportes = reportes[: args.top]

    # ── Reporte ──
    print(f"\n  Pares evaluados: {pares_evaluados} | "
          f"coincidencias (sim>={args.umbral}, duración>={args.min_duracion_segs}s): {len(reportes)}")

    if sin_audio:
        print(f"\n  Sin audio o error de extracción ({len(sin_audio)}):")
        for nombre in sin_audio[:10]:
            print(f"    - {nombre}")

    if reportes:
        print(f"\n  Contenido posiblemente repetido ({len(reportes)}):")
        for r in reportes:
            if args.contra:
                if "fin_contra_s" in r:
                    pasaje = f"pasaje en CONTRA={_formatear_pasaje(r['inicio_contra_s'], r['fin_contra_s'])}"
                else:
                    pasaje = f"pasaje={_formatear_pasaje(r['inicio_base_s'], r['fin_base_s'])}"
                print(f"    • {r['contra']} ~ {r['base']}  "
                      f"similitud={r['similitud']:.2f}  "
                      f"{pasaje} ({r['duracion_pasaje_s']}s)")
            else:
                print(f"    • {r['archivo_a']} ~ {r['archivo_b']}  "
                      f"similitud={r['similitud']:.2f}  "
                      f"pasaje en B={_formatear_pasaje(r['inicio_b_s'], r['fin_b_s'])} "
                      f"({r['duracion_pasaje_s']}s)")
    else:
        print("\n  No se encontraron coincidencias por audio.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "umbral": args.umbral,
                "min_duracion_segs": args.min_duracion_segs,
                "pares_evaluados": pares_evaluados,
                "coincidencias": reportes,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n  Reporte exportado a: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
