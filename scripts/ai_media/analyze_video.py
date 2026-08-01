"""
Análisis visual de videos con IA — detecta cambios de escena + intervalos
fijos, extrae fotogramas clave y los analiza con modelos de visión Ollama.

Algoritmo:
  1. Obtener duración del video (ffprobe)
  2. Detectar cambios de escena (ffmpeg scene detection)
  3. Generar puntos de análisis: scene changes + relleno cada N segundos
  4. Extraer fotogramas en esos timestamps
  5. Analizar cada fotograma con moondream (tags + descripción)
  6. Guardar resultados en DB y/o sidecar

Formato del sidecar .video.json:
    {
        "file_hash": "abc123def456",
        "duracion_seg": 600.0,
        "intervalo": 30,
        "sensibilidad_escena": 0.4,
        "modelo": "moondream:latest",
        "fecha": "2026-07-14T10:30:00",
        "fotogramas": [
            {"timestamp": 0.0,  "tags": ["paisaje", "ruta", "campo"],     "descripcion": "...", "origen": "escena"},
            {"timestamp": 30.0, "tags": ["paisaje", "arboles", "sombra"], "descripcion": "...", "origen": "intervalo"},
            ...
        ]
    }

Uso:
    # Analizar un video
    python scripts/ai_media/analyze_video.py --file video.mp4

    # Analizar desde DB
    python scripts/ai_media/analyze_video.py --db db/flujos.db

    # Analizar con intervalo personalizado
    python scripts/ai_media/analyze_video.py --file video.mp4 --interval 15

    # Solo ver qué se haría
    python scripts/ai_media/analyze_video.py --db db/flujos.db --dry-run
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Permitir importar scripts/ como paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.ai_media.image_analysis import extraer_keywords, describir_imagen, MODELO_VISION_DEFAULT

logger = logging.getLogger(__name__)

# Extensiones de video
EXT_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mxf", ".mts", ".m2ts"}

# Claves en media_metadata
KEY_VIDEO_ANALYSIS = "video_analysis"

# Modelos de visión recomendados
MODELOS_RECOMENDADOS = ["moondream:latest", "qwen2.5vl:latest", "qwen2.5vl:3b",
                        "llama3.2-vision:latest", "gemma4:e4b"]

# Sensibilidad por defecto para scene detection (0.0 - 1.0, menor = más sensible)
SENSIBILIDAD_ESCENA = 0.4


# ═══════════════════════════════════════════════════════════════
#  UTILIDADES
# ═══════════════════════════════════════════════════════════════

def _hash_rapido(ruta: str) -> str:
    """Fingerprint rápido: tamaño + fecha modificación."""
    import hashlib
    stat = Path(ruta).stat()
    h = hashlib.md5()
    h.update(str(stat.st_size).encode())
    h.update(str(stat.st_mtime).encode())
    return h.hexdigest()[:12]


def _es_video(ruta: str) -> bool:
    """Verifica si un archivo es video por extensión."""
    return Path(ruta).suffix.lower() in EXT_VIDEO


def _duracion_video(ruta: str) -> float:
    """Obtiene la duración en segundos usando ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        ruta,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as e:
        raise RuntimeError(f"Error obteniendo duración de {ruta}: {e}")


# ═══════════════════════════════════════════════════════════════
#  SCENE DETECTION (ffmpeg)
# ═══════════════════════════════════════════════════════════════

def _detectar_cambios_escena(
    ruta: str,
    sensibilidad: float = SENSIBILIDAD_ESCENA,
) -> list[float]:
    """
    Detecta cambios de escena en un video usando ffmpeg.

    Args:
        ruta: Ruta al video.
        sensibilidad: Threshold de scene detection (0.0-1.0).
                      Menor valor = detecta cambios más sutiles.

    Returns:
        Lista de timestamps (segundos) donde ocurren cambios de escena.
    """
    cmd = [
        "ffmpeg",
        "-i", ruta,
        "-filter:v", f"select='gt(scene,{sensibilidad})',showinfo",
        "-f", "null", "-",
    ]

    logger.info("  Detectando cambios de escena (sensibilidad=%.2f)...", sensibilidad)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=3600,  # 1 hora máx para videos muy largos
        )
    except subprocess.TimeoutExpired:
        logger.warning("  Scene detection timed out. Continuando sin detección.")
        return []

    stderr = result.stderr
    timestamps = []

    for line in stderr.splitlines():
        if "pts_time:" in line:
            match = re.search(r"pts_time:([0-9.]+)", line)
            if match:
                ts = round(float(match.group(1)), 1)
                if ts not in timestamps:
                    timestamps.append(ts)

    logger.info("  Cambios de escena detectados: %d", len(timestamps))
    return timestamps


# ═══════════════════════════════════════════════════════════════
#  PLAN DE MUESTREO
# ═══════════════════════════════════════════════════════════════

def _generar_puntos_muestreo(
    duracion: float,
    cambios_escena: list[float],
    intervalo: float = 30.0,
) -> list[dict]:
    """
    Genera la lista de timestamps a analizar combinando:
    - Cambios de escena
    - Relleno cada 'intervalo' segundos entre cambios

    Args:
        duracion: Duración del video en segundos.
        cambios_escena: Lista de timestamps con cambios de escena.
        intervalo: Segundos máximos entre fotogramas.

    Returns:
        Lista de dicts con {"timestamp": float, "origen": "escena"|"intervalo"}.
        Ordenada por timestamp. Sin duplicados.
    """
    puntos: list[dict] = []
    visitados: set[float] = set()

    def agregar(ts: float, origen: str):
        # Redondear a 1 decimal y evitar duplicados muy cercanos
        ts_rounded = round(ts, 1)
        if ts_rounded in visitados:
            return
        # No permitir duplicados a menos de 1s de distancia
        for v in visitados:
            if abs(v - ts_rounded) < 1.0:
                return
        visitados.add(ts_rounded)
        puntos.append({"timestamp": ts_rounded, "origen": origen})

    # Siempre incluir el segundo 0
    agregar(0.0, "intervalo")

    # Puntos por cambios de escena
    for ts in cambios_escena:
        if 0 < ts < duracion:
            agregar(ts, "escena")

    # Relleno cada intervalo donde no haya scene change
    ts_actual = 0.0
    while ts_actual < duracion:
        agregar(ts_actual, "intervalo")
        ts_actual += intervalo

    # Asegurar incluir el final aproximado
    if duracion > 0:
        agregar(duracion - 1, "intervalo")

    # Ordenar por timestamp
    puntos.sort(key=lambda p: p["timestamp"])

    return puntos


# ═══════════════════════════════════════════════════════════════
#  EXTRACCIÓN DE FOTOGRAMAS
# ═══════════════════════════════════════════════════════════════

def _extraer_fotograma(
    ruta_video: str,
    timestamp: float,
    output_path: str,
) -> bool:
    """
    Extrae un fotograma en un timestamp dado usando ffmpeg.

    Returns:
        True si se extrajo correctamente, False si no.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", ruta_video,
        "-vframes", "1",
        "-q:v", "2",
        output_path,
    ]
    try:
        subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=60,
        )
        return Path(output_path).exists()
    except Exception as e:
        logger.warning("  Error extrayendo fotograma en t=%.1f: %s", timestamp, e)
        return False


# ═══════════════════════════════════════════════════════════════
#  SIDECAR .video.json
# ═══════════════════════════════════════════════════════════════

def _ruta_sidecar(ruta_video: str) -> str:
    """Ruta del sidecar .video.json para un video."""
    return f"{ruta_video}.video.json"


def _sidecar_existe_valido(ruta_video: str) -> Optional[dict[str, Any]]:
    """Verifica si existe un sidecar válido."""
    sidecar = _ruta_sidecar(ruta_video)
    if not Path(sidecar).exists():
        return None

    try:
        with open(sidecar, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("file_hash") == _hash_rapido(ruta_video):
            return data
    except Exception:
        pass
    return None


def _escribir_sidecar(ruta_video: str, resultado: dict[str, Any]):
    """Escribe el sidecar .video.json."""
    sidecar = _ruta_sidecar(ruta_video)
    try:
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        logger.info("  -> Sidecar escrito: %s", Path(sidecar).name)
    except Exception as e:
        logger.warning("  -> Error escribiendo sidecar: %s", e)


# ═══════════════════════════════════════════════════════════════
#  BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

def conectar_db(ruta_db: str) -> sqlite3.Connection:
    if not Path(ruta_db).exists():
        raise FileNotFoundError(f"No se encuentra la DB: {ruta_db}")

    conn = sqlite3.connect(ruta_db)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='media'"
    )
    if not cursor.fetchone():
        raise RuntimeError(f"La DB {ruta_db} no contiene la tabla 'media'")

    return conn


def obtener_videos_sin_analisis(
    conn: sqlite3.Connection, limite: Optional[int] = None
) -> list[dict]:
    """Busca videos en la DB que no tienen análisis visual."""
    query = """
        SELECT m.id, m.filepath_absoluto, m.filename_original
        FROM media m
        WHERE m.type = 'video'
        AND m.id NOT IN (
            SELECT mm.media_id
            FROM media_metadata mm
            WHERE mm.key = ?
        )
        ORDER BY m.id
    """
    params = [KEY_VIDEO_ANALYSIS]

    if limite:
        query += " LIMIT ?"
        params.append(limite)

    cursor = conn.execute(query, params)
    filas = cursor.fetchall()

    resultado = []
    for fila in filas:
        ruta = fila["filepath_absoluto"]
        if Path(ruta).exists():
            resultado.append({
                "id": fila["id"],
                "ruta": ruta,
                "nombre": fila["filename_original"],
            })
        else:
            logger.warning("  -> Video no encontrado en disco: %s", ruta)

    return resultado


def guardar_en_db(
    conn: sqlite3.Connection, media_id: int, resultado: dict[str, Any]
):
    """Guarda el análisis visual en media_metadata."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
            "VALUES (?, ?, ?)",
            (media_id, KEY_VIDEO_ANALYSIS,
             json.dumps(resultado.get("fotogramas", []), ensure_ascii=False)),
        )
        conn.commit()
    except Exception as e:
        logger.error("  -> Error guardando en DB (id=%d): %s", media_id, e)


# ═══════════════════════════════════════════════════════════════
#  ANÁLISIS IA DE FOTOGRAMAS
# ═══════════════════════════════════════════════════════════════

def analizar_fotograma(
    ruta_fotograma: str,
    modelo: str = MODELO_VISION_DEFAULT,
    usar_proxy: bool = True,
) -> dict[str, Any]:
    """
    Analiza un fotograma con IA: extrae tags + descripción.

    Returns:
        Dict con "tags" y "descripcion".
    """
    tags = extraer_keywords(
        ruta_fotograma,
        modelo=modelo,
        temperatura=0.2,
        usar_proxy=usar_proxy,
    )

    descripcion = describir_imagen(
        ruta_fotograma,
        modelo=modelo,
        temperatura=0.3,
        usar_proxy=usar_proxy,
    )

    return {
        "tags": tags,
        "descripcion": descripcion.strip().strip('"'),
    }


# ═══════════════════════════════════════════════════════════════
#  PROCESAMIENTO DE VIDEO
# ═══════════════════════════════════════════════════════════════

def analizar_video(
    ruta: str,
    modelo: str = MODELO_VISION_DEFAULT,
    intervalo: float = 30.0,
    sensibilidad: float = SENSIBILIDAD_ESCENA,
    usar_proxy: bool = True,
    dry_run: bool = False,
) -> Optional[dict[str, Any]]:
    """
    Analiza un video completo: scene detection + muestreo + IA.

    Returns:
        Dict con el análisis completo, o None si falló.
    """
    nombre = Path(ruta).name

    if dry_run:
        logger.info("  [DRY RUN] Se analizaría: %s", nombre)
        return None

    # 1. Duración
    logger.info("  Obteniendo duración...")
    try:
        duracion = _duracion_video(ruta)
    except Exception as e:
        logger.error("  Error obteniendo duración: %s", e)
        return None

    logger.info("  Duración: %.1f seg (%.1f min)", duracion, duracion / 60)

    # 2. Scene detection
    try:
        cambios = _detectar_cambios_escena(ruta, sensibilidad=sensibilidad)
    except Exception as e:
        logger.warning("  Error en scene detection: %s. Continuando sin escenas.", e)
        cambios = []

    # 3. Puntos de muestreo
    puntos = _generar_puntos_muestreo(duracion, cambios, intervalo=intervalo)
    logger.info("  Puntos de análisis: %d (%d escenas + %d intervalos)",
                len(puntos),
                sum(1 for p in puntos if p["origen"] == "escena"),
                sum(1 for p in puntos if p["origen"] == "intervalo"))

    # 4. Extraer y analizar fotogramas
    fotogramas_analizados = []
    total = len(puntos)

    with tempfile.TemporaryDirectory(prefix="fotogramas_") as tmpdir:
        for i, punto in enumerate(puntos, 1):
            ts = punto["timestamp"]

            logger.info("  [%d/%d] t=%.1fs (%s)",
                        i, total, ts, punto["origen"])

            # Extraer fotograma
            frame_path = os.path.join(tmpdir, f"frame_{ts:.1f}.jpg")
            ok = _extraer_fotograma(ruta, ts, frame_path)

            if not ok:
                logger.warning("  -> No se pudo extraer fotograma en t=%.1f", ts)
                fotogramas_analizados.append({
                    "timestamp": ts,
                    "tags": [],
                    "descripcion": "",
                    "origen": punto["origen"],
                })
                continue

            # Analizar con IA
            try:
                resultado = analizar_fotograma(
                    frame_path, modelo=modelo, usar_proxy=usar_proxy
                )
            except Exception as e:
                logger.warning("  -> Error analizando fotograma t=%.1f: %s", ts, e)
                resultado = {"tags": [], "descripcion": ""}

            fotogramas_analizados.append({
                "timestamp": ts,
                "tags": resultado["tags"],
                "descripcion": resultado["descripcion"],
                "origen": punto["origen"],
            })

            # Log corto
            if resultado["tags"]:
                logger.info("    Tags (%d): %s",
                            len(resultado["tags"]),
                            ", ".join(resultado["tags"][:4]))

    # 5. Armar resultado final
    resultado_final = {
        "file_hash": _hash_rapido(ruta),
        "duracion_seg": round(duracion, 1),
        "intervalo": intervalo,
        "sensibilidad_escena": sensibilidad,
        "modelo": modelo,
        "fecha": datetime.now().isoformat(),
        "fotogramas": fotogramas_analizados,
    }

    return resultado_final


# ═══════════════════════════════════════════════════════════════
#  FLUJOS PRINCIPALES
# ═══════════════════════════════════════════════════════════════

def procesar_desde_db(
    ruta_db: str,
    modelo: str = MODELO_VISION_DEFAULT,
    intervalo: float = 30.0,
    sensibilidad: float = SENSIBILIDAD_ESCENA,
    usar_proxy: bool = True,
    limite: Optional[int] = None,
    sidecar: bool = False,
    dry_run: bool = False,
):
    logger.info("Conectando a DB: %s", ruta_db)
    conn = conectar_db(ruta_db)

    videos = obtener_videos_sin_analisis(conn, limite=limite)

    if not videos:
        logger.info("No hay videos sin analizar en la DB.")
        conn.close()
        return

    logger.info("Videos a procesar: %d%s", len(videos),
                " (dry run)" if dry_run else "")

    ok = 0
    fail = 0

    for i, vid in enumerate(videos, 1):
        logger.info("[%d/%d] %s", i, len(videos), vid["nombre"])

        if dry_run:
            ok += 1
            continue

        # Verificar sidecar existente
        if sidecar:
            existente = _sidecar_existe_valido(vid["ruta"])
            if existente is not None:
                logger.info("  -> Ya tiene sidecar válido (%d fotogramas). Skip.",
                            len(existente.get("fotogramas", [])))
                guardar_en_db(conn, vid["id"], existente)
                ok += 1
                continue

        resultado = analizar_video(
            vid["ruta"],
            modelo=modelo,
            intervalo=intervalo,
            sensibilidad=sensibilidad,
            usar_proxy=usar_proxy,
            dry_run=False,
        )

        if resultado:
            # Sidecar
            if sidecar:
                _escribir_sidecar(vid["ruta"], resultado)
            # DB
            guardar_en_db(conn, vid["id"], resultado)
            ok += 1
        else:
            fail += 1

    conn.close()

    logger.info("=== RESUMEN: %d analizados, %d fallos (de %d) ===",
                ok, fail, len(videos))


def procesar_desde_carpeta(
    carpeta: str,
    modelo: str = MODELO_VISION_DEFAULT,
    intervalo: float = 30.0,
    sensibilidad: float = SENSIBILIDAD_ESCENA,
    usar_proxy: bool = True,
    dry_run: bool = False,
):
    carpeta = Path(carpeta)
    if not carpeta.exists():
        raise FileNotFoundError(f"La carpeta no existe: {carpeta}")

    rutas = sorted(
        str(p) for p in carpeta.rglob("*")
        if _es_video(str(p))
    )

    if not rutas:
        logger.info("No se encontraron videos en %s", carpeta)
        return

    logger.info("Videos encontrados: %d%s", len(rutas),
                " (dry run)" if dry_run else "")

    ok = 0
    fail = 0
    ya_analizados = 0

    for i, ruta in enumerate(rutas, 1):
        nombre = Path(ruta).name
        logger.info("[%d/%d] %s", i, len(rutas), nombre)

        if not dry_run:
            existente = _sidecar_existe_valido(ruta)
            if existente is not None:
                logger.info("  -> Ya tiene sidecar válido (%d fotogramas). Skip.",
                            len(existente.get("fotogramas", [])))
                ya_analizados += 1
                continue

        if dry_run:
            ok += 1
            continue

        resultado = analizar_video(
            ruta, modelo=modelo, intervalo=intervalo,
            sensibilidad=sensibilidad, usar_proxy=usar_proxy,
            dry_run=False,
        )

        if resultado:
            _escribir_sidecar(ruta, resultado)
            ok += 1
        else:
            fail += 1

    logger.info("=== RESUMEN: %d nuevos, %d ya tenían sidecar, %d fallos (de %d) ===",
                ok, ya_analizados, fail, len(rutas))


def procesar_archivo_individual(
    ruta: str,
    modelo: str = MODELO_VISION_DEFAULT,
    intervalo: float = 30.0,
    sensibilidad: float = SENSIBILIDAD_ESCENA,
    usar_proxy: bool = True,
    json_out: Optional[str] = None,
):
    if not Path(ruta).exists():
        raise FileNotFoundError(f"No se encuentra: {ruta}")

    if not _es_video(ruta):
        raise ValueError(f"No es un video soportado: {Path(ruta).suffix}")

    resultado = analizar_video(
        ruta, modelo=modelo, intervalo=intervalo,
        sensibilidad=sensibilidad, usar_proxy=usar_proxy,
        dry_run=False,
    )

    if not resultado:
        logger.error("Error analizando video.")
        return

    # Mostrar resumen
    fotos = resultado["fotogramas"]
    print(f"\n  Duración: {resultado['duracion_seg']:.0f}s "
          f"({resultado['duracion_seg']/60:.0f} min)")
    print(f"  Fotogramas analizados: {len(fotos)}")
    print(f"  Modelo: {resultado['modelo']}")
    print()

    for f in fotos[:5]:
        tags_str = ", ".join(f["tags"][:4])
        print(f"  [{f['timestamp']:6.1f}s] ({f['origen']:>9s}) {tags_str}")
    if len(fotos) > 5:
        print(f"  ... y {len(fotos) - 5} fotogramas más")

    # Sidecar
    _escribir_sidecar(ruta, resultado)

    # JSON externo
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        print(f"  JSON exportado: {json_out}")


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def listar_modelos():
    from scripts.ai_media.ollama_client import asegurar_ollama
    if not asegurar_ollama():
        print("  ⚠️  Ollama no está disponible. No se pueden listar modelos.")
        return
    try:
        import ollama
        response = ollama.list()
        if hasattr(response, "models"):
            modelos = response.models
        elif isinstance(response, dict):
            modelos = response.get("models", [])
        else:
            modelos = list(response)

        print("=== Modelos instalados en Ollama ===\n")
        for m in modelos:
            nombre = m.model if hasattr(m, "model") else str(m)
            print(f"  {nombre}")
        print("\nRecomendados para visión:")
        for m in MODELOS_RECOMENDADOS:
            print(f"  - {m}")
        print()
    except Exception as e:
        print(f"Error al conectar con Ollama: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Análisis visual de videos con IA.\n\n"
                    "Combina detección de cambios de escena (ffmpeg) con muestreo\n"
                    "cada N segundos para analizar fotogramas clave con modelos\n"
                    "de visión (moondream).\n\n"
                    "Modos:\n"
                    "  --file ruta    : analiza un solo video\n"
                    "  --db ruta      : procesa videos de la DB (post-ingesta)\n"
                    "  --folder ruta  : analiza todos los videos de una carpeta\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    modo = parser.add_argument_group("Modo de operación")
    modo.add_argument("--file", help="Ruta a un archivo de video")
    modo.add_argument("--db", help="Ruta a la base de datos SQLite")
    modo.add_argument("--folder", help="Ruta a carpeta con videos")

    parser.add_argument("--modelo", default=MODELO_VISION_DEFAULT,
                        help=f"Modelo de visión. Usar --list-models para "
                             f"ver los instalados. (default: {MODELO_VISION_DEFAULT})")
    parser.add_argument("--interval", type=float, default=30.0,
                        help="Segundos máximos entre fotogramas (default: 30)")
    parser.add_argument("--sensibilidad", type=float, default=SENSIBILIDAD_ESCENA,
                        help="Sensibilidad de detección de escenas 0.0-1.0, "
                             "menor = más sensible (default: 0.4)")
    parser.add_argument("--no-proxy", action="store_true",
                        help="No usar proxies (deshabilita redimensionado)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría")
    parser.add_argument("--list-models", action="store_true",
                        help="Mostrar modelos Ollama instalados y salir")

    # Modo DB
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar cantidad (solo modo --db)")
    parser.add_argument("--sidecar", action="store_true",
                        help="Generar sidecar .video.json (solo modo --db)")

    # Exportación individual
    parser.add_argument("--json", help="Exportar resultado a JSON (solo modo --file)")

    args = parser.parse_args()

    if args.list_models:
        listar_modelos()
        return

    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    modos = [args.file, args.db, args.folder]
    activos = sum(1 for m in modos if m)
    if activos == 0:
        parser.error("Debe especificar --file, --db o --folder")
    if activos > 1:
        parser.error("Use solo un modo a la vez (--file, --db o --folder)")

    usar_proxy = not args.no_proxy

    try:
        if args.file:
            procesar_archivo_individual(
                ruta=args.file,
                modelo=args.modelo,
                intervalo=args.interval,
                sensibilidad=args.sensibilidad,
                usar_proxy=usar_proxy,
                json_out=args.json,
            )

        elif args.db:
            procesar_desde_db(
                ruta_db=args.db,
                modelo=args.modelo,
                intervalo=args.interval,
                sensibilidad=args.sensibilidad,
                usar_proxy=usar_proxy,
                limite=args.limit,
                sidecar=args.sidecar,
                dry_run=args.dry_run,
            )

        elif args.folder:
            procesar_desde_carpeta(
                carpeta=args.folder,
                modelo=args.modelo,
                intervalo=args.interval,
                sensibilidad=args.sensibilidad,
                usar_proxy=usar_proxy,
                dry_run=args.dry_run,
            )

    except KeyboardInterrupt:
        logger.info("\nProceso interrumpido por el usuario.")
        sys.exit(1)

    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
