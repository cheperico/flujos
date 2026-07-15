"""
Pipeline de limpieza de tandas de imágenes.

Lee una carpeta con imágenes, las agrupa por:
  1. Cercanía temporal (ventana configurable)
  2. Similitud visual (hash perceptual)

De cada grupo elige la mejor imagen (usando batch_selector)
y mueve las descartadas a una carpeta 'excluir/' para que
el ingest las ignore.

Uso:
    python scripts/limpiar_tandas.py D:/Flujos/Testeo/fABIAN
    python scripts/limpiar_tandas.py D:/Flujos/Testeo/fABIAN --ventana-temporal 10
    python scripts/limpiar_tandas.py D:/Flujos/Testeo/fABIAN --dry-run
    python scripts/limpiar_tandas.py D:/Flujos/Testeo/fABIAN --no-proxy --no-similitud
"""

import argparse
import json
import logging
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PIL import Image

# Permitir importar scripts/ como paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ai_media.image_analysis import extraer_keywords
from scripts.ai_media.batch_selector import seleccionar_mejor_imagen
from scripts.ai_media.proxy import obtener_proxy, limpiar_todos_los_proxies, NOMBRE_CARPETA_PROXIES
from scripts.ai_media.clustering import agrupar_por_tags, agrupar_por_embeddings

logger = logging.getLogger(__name__)

# Extensiones de imagen soportadas
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}


# ═══════════════════════════════════════════════════════════════
#  EXTRACCIÓN DE TIMESTAMPS
# ═══════════════════════════════════════════════════════════════

def _extraer_timestamp_nombre(nombre: str) -> Optional[datetime]:
    """
    Intenta extraer timestamp del nombre de archivo.

    Formatos soportados:
      - 20250907_140453.jpg    (YYYYMMDD_HHMMSS)
      - 2025-09-07 14.04.53.jpg
      - IMG_20250907_140453.jpg
      - 20250907_140453.jpg
      - VID_20250907_140453.mp4 (no aplica pero por las dudas)
    """
    import re
    sin_ext = Path(nombre).stem

    # YYYYMMDD_HHMMSS o YYYYMMDD-HHMMSS
    m = re.search(r"(\d{4})[_-]?(\d{2})[_-]?(\d{2})[_-]?(\d{2})[_-]?(\d{2})[_-]?(\d{2})", sin_ext)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(m.group(6))
            )
        except ValueError:
            pass

    # YYYY-MMDD-HHMMSS
    m = re.search(r"(\d{4})-(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", sin_ext)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(m.group(6))
            )
        except ValueError:
            pass

    return None


def _extraer_timestamp_exif(ruta: str) -> Optional[datetime]:
    """
    Intenta extraer timestamp de los metadatos EXIF de la imagen.
    """
    try:
        img = Image.open(ruta)
        exif = img.getexif()
        # Tag 36867 = DateTimeOriginal, 36868 = DateTimeDigitized, 306 = DateTime
        for tag in (36867, 36868, 306):
            val = exif.get(tag)
            if val:
                try:
                    return datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                except (ValueError, TypeError):
                    continue
    except Exception:
        pass
    return None


def _extraer_timestamp_modificacion(ruta: str) -> datetime:
    """Usa la fecha de modificación del archivo como fallback."""
    stat = Path(ruta).stat()
    return datetime.fromtimestamp(stat.st_mtime)


def obtener_timestamp(ruta: str) -> datetime:
    """
    Obtiene el mejor timestamp disponible para una imagen.

    Prioridad:
      1. Nombre de archivo (YYYYMMDD_HHMMSS)
      2. EXIF DateTimeOriginal
      3. Fecha de modificación del archivo
    """
    ts = _extraer_timestamp_nombre(ruta)
    if ts:
        return ts
    ts = _extraer_timestamp_exif(ruta)
    if ts:
        return ts
    return _extraer_timestamp_modificacion(ruta)


# ═══════════════════════════════════════════════════════════════
#  AGRUPAMIENTO TEMPORAL
# ═══════════════════════════════════════════════════════════════

def agrupar_por_tiempo(
    rutas: list[str],
    ventana_minutos: int = 5,
) -> list[list[str]]:
    """
    Agrupa imágenes por cercanía temporal.

    Dos imágenes están en el mismo grupo si su diferencia de timestamp
    es menor o igual a ventana_minutos.

    Args:
        rutas: Lista de rutas de imágenes.
        ventana_minutos: Ventana temporal en minutos.

    Returns:
        Lista de grupos (cada grupo es una lista de rutas).
    """
    # Ordenar por timestamp
    ordenadas = []
    for r in rutas:
        ts = obtener_timestamp(r)
        ordenadas.append((ts, r))
    ordenadas.sort(key=lambda x: x[0])

    if not ordenadas:
        return []

    grupos = []
    grupo_actual = [ordenadas[0][1]]
    ts_actual = ordenadas[0][0]

    for ts, ruta in ordenadas[1:]:
        if (ts - ts_actual).total_seconds() <= ventana_minutos * 60:
            grupo_actual.append(ruta)
        else:
            grupos.append(grupo_actual)
            grupo_actual = [ruta]
            ts_actual = ts

    if grupo_actual:
        grupos.append(grupo_actual)

    return grupos


# ═══════════════════════════════════════════════════════════════
#  AGRUPAMIENTO POR SIMILITUD VISUAL
# ═══════════════════════════════════════════════════════════════

def _hash_perceptual(ruta: str) -> Optional[str]:
    """
    Calcula el hash perceptual (pHash) de una imagen.
    Usa imagehash para comparar similitud visual.
    """
    try:
        from imagehash import phash
        with Image.open(ruta) as img:
            return phash(img)
    except Exception as e:
        logger.debug("Error calculando hash de %s: %s", Path(ruta).name, e)
        return None


def sub_agrupar_por_similitud(
    grupo: list[str],
    umbral_hamming: int = 5,
) -> list[list[str]]:
    """
    Dentro de un grupo temporal, sub-agrupa por similitud visual.

    Dos imágenes pertenecen al mismo sub-grupo si la distancia
    de Hamming entre sus hashes perceptuales es <= umbral_hamming.

    Args:
        grupo: Lista de rutas de imágenes (mismo grupo temporal).
        umbral_hamming: Distancia máxima para considerar similares (0-64).
                        Valores típicos: 3 (muy similar) a 10 (parecida).

    Returns:
        Lista de sub-grupos (cada uno es lista de rutas).
    """
    if len(grupo) <= 1:
        return [grupo]

    # Calcular hashes
    hash_por_ruta = {}
    for r in grupo:
        h = _hash_perceptual(r)
        if h is not None:
            hash_por_ruta[r] = h

    if not hash_por_ruta:
        return [grupo]

    # Agrupar por similitud (algoritmo greedy: el primero define el grupo)
    rutas_ordenadas = grupo  # ya vienen ordenadas por tiempo
    sub_grupos = []
    asignadas = set()

    for ruta in rutas_ordenadas:
        if ruta in asignadas:
            continue
        if ruta not in hash_por_ruta:
            # No tiene hash, va sola
            sub_grupos.append([ruta])
            asignadas.add(ruta)
            continue

        hash_ref = hash_por_ruta[ruta]
        grupo_sim = [ruta]
        asignadas.add(ruta)

        for otra in rutas_ordenadas:
            if otra in asignadas or otra not in hash_por_ruta:
                continue
            distancia = hash_ref - hash_por_ruta[otra]
            if distancia <= umbral_hamming:
                grupo_sim.append(otra)
                asignadas.add(otra)

        sub_grupos.append(grupo_sim)

    return sub_grupos


# ═══════════════════════════════════════════════════════════════
#  PIPELINE COMPLETO
# ═══════════════════════════════════════════════════════════════

def limpiar_tandas(
    carpeta: str,
    ventana_minutos: int = 5,
    umbral_hamming: int = 5,
    criterio: str = "calidad",
    modelo: str = "moondream:latest",
    usar_proxy: bool = True,
    usar_similitud: bool = True,
    criterio_agrupacion: str = "phash",
    carpeta_excluir: str = "excluir",
    dry_run: bool = False,
) -> dict:
    """
    Pipeline completo de limpieza de tandas.

    1. Escanea imágenes en la carpeta
    2. Agrupa por tiempo
    3. Sub-agrupa por similitud visual
    4. Selecciona la mejor de cada sub-grupo
    5. Mueve el resto a carpeta_excluir

    Args:
        carpeta: Directorio con las imágenes.
        ventana_minutos: Ventana temporal para agrupar (minutos).
        umbral_hamming: Umbral de similitud visual (0-64).
        criterio: Criterio de selección (calidad, tema, diversidad, descripcion).
        modelo: Modelo de visión de Ollama.
        usar_proxy: Si True, usa proxies redimensionados.
        usar_similitud: Si True, sub-agrupa (con el criterio indicado).
        criterio_agrupacion: Método de agrupamiento interno:
            - "phash": hash perceptual (imágenes casi idénticas)
            - "tags": palabras clave por IA (agrupación semántica simple)
            - "embeddings": embeddings de descripciones (agrupación semántica avanzada)
        carpeta_excluir: Nombre de la carpeta para imágenes descartadas.
        dry_run: Si True, solo muestra qué se haría sin ejecutar.

    Returns:
        Dict con estadísticas del proceso.
    """
    carpeta = Path(carpeta)
    if not carpeta.exists():
        raise FileNotFoundError(f"La carpeta no existe: {carpeta}")

    # 1. Escanear imágenes (excluyendo la carpeta de excluir)
    excluir_path = carpeta / carpeta_excluir
    rutas = sorted(
        str(p) for p in carpeta.rglob("*")
        if p.suffix.lower() in EXT_IMAGEN
        and not str(p).startswith(str(excluir_path))
        and NOMBRE_CARPETA_PROXIES not in p.parts
    )

    if not rutas:
        logger.warning("No se encontraron imágenes en %s", carpeta)
        return {"total": 0, "grupos": 0, "seleccionadas": [], "descartadas": []}

    logger.info("Imágenes encontradas: %d", len(rutas))

    # 2. Agrupar por tiempo
    grupos_temporales = agrupar_por_tiempo(rutas, ventana_minutos)
    logger.info("Grupos temporales (ventana=%d min): %d", ventana_minutos, len(grupos_temporales))

    # 3. Sub-agrupar según criterio
    grupos_finales = []
    for i, grupo in enumerate(grupos_temporales):
        if usar_similitud and len(grupo) > 1:
            if criterio_agrupacion == "phash":
                sub = sub_agrupar_por_similitud(grupo, umbral_hamming)
            elif criterio_agrupacion == "tags":
                sub = agrupar_por_tags(grupo, modelo_vision=modelo)
            elif criterio_agrupacion == "embeddings":
                sub = agrupar_por_embeddings(grupo, modelo_vision=modelo)
            else:
                logger.warning("Criterio de agrupación '%s' no reconocido, usando phash", criterio_agrupacion)
                sub = sub_agrupar_por_similitud(grupo, umbral_hamming)
            grupos_finales.extend(sub)
        else:
            grupos_finales.append(grupo)

    # Estadísticas de grupos
    grupos_unitarios = sum(1 for g in grupos_finales if len(g) == 1)
    grupos_multiples = sum(1 for g in grupos_finales if len(g) > 1)
    logger.info(
        "Grupos totales: %d (%d unitarios, %d múltiples)",
        len(grupos_finales), grupos_unitarios, grupos_multiples
    )

    # 4. Seleccionar mejor imagen de cada grupo múltiple
    seleccionadas = []
    descartadas = []

    for i, grupo in enumerate(grupos_finales):
        if len(grupo) <= 1:
            # Grupos de 1 imagen: se conserva directamente
            seleccionadas.append(grupo[0])
            continue

        logger.info(
            "Procesando grupo %d/%d: %d imágenes",
            i + 1, len(grupos_finales), len(grupo)
        )

        if dry_run:
            # En dry run, mostrar qué pasaría
            logger.info("  [DRY RUN] Se analizarían %d imágenes", len(grupo))
            seleccionadas.append(grupo[0])
            descartadas.extend(grupo[1:])
            continue

        try:
            # Seleccionar mejor imagen con batch_selector
            mejor = seleccionar_mejor_imagen(
                grupo,
                criterio=criterio,
                modelo=modelo,
                temperatura=0.2,
            )
            ruta_mejor = mejor["ruta"]
            seleccionadas.append(ruta_mejor)
            descartadas.extend(r for r in grupo if r != ruta_mejor)

            # Mostrar resultado
            logger.info(
                "  ✓ Mejor: %s (puntaje: %s)",
                Path(ruta_mejor).name, mejor.get("puntaje", "N/A")
            )
            for r in grupo:
                if r != ruta_mejor:
                    logger.info("    → Descartada: %s", Path(r).name)

        except Exception as e:
            logger.error("  ✗ Error procesando grupo: %s", e)
            # En caso de error, conservar todas (no descartar ninguna)
            seleccionadas.extend(grupo)

    # 5. Mover descartadas a carpeta excluir
    if not dry_run and descartadas:
        _mover_a_excluir(descartadas, carpeta, excluir_path)
        logger.info(
            "Movidas %d imágenes a %s", len(descartadas), excluir_path
        )

    # Reporte final
    reporte = {
        "carpeta": str(carpeta),
        "total": len(rutas),
        "grupos_temporales": len(grupos_temporales),
        "grupos_finales": len(grupos_finales),
        "grupos_unitarios": grupos_unitarios,
        "grupos_multiples": grupos_multiples,
        "seleccionadas": seleccionadas,
        "descartadas": descartadas,
        "conservadas": len(seleccionadas),
        "eliminadas": len(descartadas),
        "dry_run": dry_run,
        "criterio": criterio,
        "criterio_agrupacion": ("ninguno" if not usar_similitud else criterio_agrupacion),
        "modelo": modelo,
    }

    logger.info(
        "=== RESUMEN: %d conservadas, %d descartadas (de %d total) ===",
        len(seleccionadas), len(descartadas), len(rutas)
    )

    return reporte


def _mover_a_excluir(rutas: list[str], carpeta_raiz: Path, carpeta_excluir: Path):
    """
    Mueve las imágenes descartadas (y sus sidecars) a la carpeta de excluir,
    manteniendo la estructura relativa de subcarpetas contra carpeta_raiz.
    """
    for r in rutas:
        ruta = Path(r)
        # Calcular ruta relativa contra la raíz de escaneo
        try:
            rel = ruta.relative_to(carpeta_raiz)
        except ValueError:
            rel = ruta.name

        destino = carpeta_excluir / rel
        destino.parent.mkdir(parents=True, exist_ok=True)

        # Evitar colisiones en el destino
        if destino.exists():
            stem = destino.stem
            destino = destino.with_name(f"{stem}_descartada{destino.suffix}")

        # Mover sidecars: archivos que comparten el mismo stem
        for sidecar in ruta.parent.glob(f"{ruta.stem}.*"):
            if sidecar.name == ruta.name:
                continue  # es la imagen misma
            destino_sidecar = destino.with_suffix(sidecar.suffix)
            if destino_sidecar.exists():
                destino_sidecar = destino_sidecar.with_stem(
                    f"{destino_sidecar.stem}_descartada"
                )
            try:
                sidecar.rename(destino_sidecar)
                logger.debug("  Sidecar: %s -> %s", sidecar.name, destino_sidecar.name)
            except Exception as e:
                logger.error("Error moviendo sidecar %s: %s", sidecar, e)

        # Mover la imagen
        try:
            ruta.rename(destino)
            logger.debug("Movido: %s -> %s", ruta.name, destino)
        except Exception as e:
            logger.error("Error moviendo %s: %s", ruta, e)


def imprimir_reporte(reporte: dict):
    """Imprime un resumen formateado del proceso."""
    dry = " (DRY RUN - no se movieron archivos)" if reporte["dry_run"] else ""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"RESUMEN DE LIMPIEZA{dry}")
    print(sep)
    print(f"  Carpeta:        {reporte['carpeta']}")
    print(f"  Total imagenes: {reporte['total']}")
    print(f"  Grupos temp.:   {reporte['grupos_temporales']}")
    print(f"  Grupos finales: {reporte['grupos_finales']}")
    print(f"    - Unitarios:   {reporte['grupos_unitarios']}")
    print(f"    - Multiples:   {reporte['grupos_multiples']}")
    print(f"  Conservadas:    {reporte['conservadas']}")
    print(f"  Descartadas:    {reporte['eliminadas']}")
    print(f"  Criterio:       {reporte['criterio']}")
    print(f"  Agrupación:     {reporte['criterio_agrupacion']}")
    print(f"  Modelo:         {reporte['modelo']}")
    print(sep)

    if reporte["descartadas"] and not reporte["dry_run"]:
        print(f"\nImagenes movidas a 'excluir/':")
        for r in reporte["descartadas"][:10]:
            print(f"  - {r}")
        if len(reporte["descartadas"]) > 10:
            print(f"  ... y {len(reporte['descartadas']) - 10} mas")


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Pipeline de limpieza de tandas de imágenes.\n"
                    "Agrupa por tiempo y similitud visual, elige la mejor y "
                    "mueve el resto a una carpeta 'excluir/'.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("carpeta", help="Directorio con las imágenes")
    parser.add_argument("--ventana-temporal", type=int, default=5,
                        help="Ventana temporal en minutos para agrupar (default: 5)")
    parser.add_argument("--hash-umbral", type=int, default=5,
                        help="Umbral de similitud visual 0-64. Menor = más similar (default: 5)")
    parser.add_argument("--criterio", default="calidad",
                        choices=["calidad", "tema", "diversidad", "descripcion"],
                        help="Criterio de selección (default: calidad)")
    parser.add_argument("--modelo", default="moondream:latest",
                        choices=["moondream:latest", "qwen2.5vl:latest",
                                 "qwen2.5vl:3b", "llama3.2-vision:latest",
                                 "gemma4:e4b"],
                        help="Modelo de visión (default: moondream:latest)")
    parser.add_argument("--no-proxy", action="store_true",
                        help="No usar proxies (deshabilita redimensionado automático)")
    parser.add_argument("--no-similitud", action="store_true",
                        help="No sub-agrupar (solo agrupamiento temporal)")
    parser.add_argument("--criterio-agrupacion", default="phash",
                        choices=["phash", "tags", "embeddings"],
                        help="Método de agrupamiento interno (default: phash). "
                             "tags=keywords IA, embeddings=descripciones+embeddings")
    parser.add_argument("--carpeta-excluir", default="excluir",
                        help="Nombre de la carpeta para imágenes descartadas (default: excluir)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría sin mover archivos")
    parser.add_argument("--json", help="Exportar reporte a JSON")

    args = parser.parse_args()

    try:
        reporte = limpiar_tandas(
            carpeta=args.carpeta,
            ventana_minutos=args.ventana_temporal,
            umbral_hamming=args.hash_umbral,
            criterio=args.criterio,
            modelo=args.modelo,
            usar_proxy=not args.no_proxy,
            usar_similitud=not args.no_similitud,
            criterio_agrupacion=args.criterio_agrupacion,
            carpeta_excluir=args.carpeta_excluir,
            dry_run=args.dry_run,
        )

        imprimir_reporte(reporte)

        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                # Convertir rutas a strings relativos
                output = reporte.copy()
                output["seleccionadas"] = [str(Path(p).name) for p in reporte["seleccionadas"]]
                output["descartadas"] = [str(Path(p).name) for p in reporte["descartadas"]]
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"\nReporte exportado a: {args.json}")

    except Exception as e:
        logger.error("Error en el pipeline: %s", e)
        sys.exit(1)
