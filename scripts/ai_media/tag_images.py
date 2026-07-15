"""
Etiquetado de imágenes con IA — extrae keywords y las guarda en DB y/o sidecar.

Dos modos de operación:

1. **Post-ingesta** (--db): conecta a la DB existente, busca imágenes sin
   etiquetar, extrae keywords con moondream y guarda en media_metadata.

2. **Pre-ingesta / autónomo** (--folder): procesa imágenes de una carpeta
   y genera sidecars .tags.json sin tocar la DB. El ingest puede levantar
   esos sidecars después.

Formato del sidecar .tags.json:
    {
        "file_hash": "abc123def456",
        "tags": ["bicicleta", "ruta", "atardecer"],
        "modelo": "moondream:latest",
        "fecha": "2026-07-14T10:30:00"
    }

Uso:
    # Post-ingesta: etiquetar imágenes en DB que aún no tienen tags
    python scripts/ai_media/tag_images.py --db db/flujos.db

    # Post-ingesta: solo 20 imágenes, con modelo específico
    python scripts/ai_media/tag_images.py --db db/flujos.db --limit 20 --modelo qwen2.5vl:3b

    # Post-ingesta: generar también sidecars
    python scripts/ai_media/tag_images.py --db db/flujos.db --sidecar

    # Autónomo: etiquetar carpeta completa, crear sidecars
    python scripts/ai_media/tag_images.py --folder D:/Fotos --sidecar

    # Solo ver qué se haría
    python scripts/ai_media/tag_images.py --db db/flujos.db --dry-run
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Permitir importar scripts/ como paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.ai_media.image_analysis import extraer_keywords
from scripts.ai_media.proxy import limpiar_todos_los_proxies

logger = logging.getLogger(__name__)

# Extensiones de imagen soportadas
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp", ".heic", ".heif"}

# Clave en media_metadata para los tags IA
KEY_AI_TAGS = "ai_tags"

# Tamaño del modelo whisper disponible
MODELOS_VISION = ["moondream:latest", "qwen2.5vl:latest", "qwen2.5vl:3b",
                  "llama3.2-vision:latest", "gemma4:e4b"]


# ═══════════════════════════════════════════════════════════════
#  UTILIDADES
# ═══════════════════════════════════════════════════════════════

def _hash_rapido(ruta: str) -> str:
    """
    Fingerprint rápido tipo ingest: tamaño + fecha modificación.
    Para detectar cambios en la imagen y decidir si un sidecar es válido.
    """
    import hashlib
    stat = Path(ruta).stat()
    h = hashlib.md5()
    h.update(str(stat.st_size).encode())
    h.update(str(stat.st_mtime).encode())
    return h.hexdigest()[:12]


def _es_imagen(ruta: str) -> bool:
    """Verifica si un archivo es imagen por extensión."""
    return Path(ruta).suffix.lower() in EXT_IMAGEN


# ═══════════════════════════════════════════════════════════════
#  SIDECAR .tags.json
# ═══════════════════════════════════════════════════════════════

def _ruta_sidecar(ruta_imagen: str) -> str:
    """Devuelve la ruta del sidecar .tags.json para una imagen."""
    return f"{ruta_imagen}.tags.json"


def _sidecar_existe_valido(ruta_imagen: str) -> Optional[list[str]]:
    """
    Verifica si existe un sidecar válido para la imagen.

    El sidecar es válido si:
      - El archivo .tags.json existe
      - El file_hash coincide con el de la imagen actual

    Returns:
        Lista de tags si el sidecar es válido, None si no.
    """
    sidecar = _ruta_sidecar(ruta_imagen)
    if not Path(sidecar).exists():
        return None

    try:
        with open(sidecar, "r", encoding="utf-8") as f:
            data = json.load(f)

        hash_actual = _hash_rapido(ruta_imagen)
        if data.get("file_hash") == hash_actual:
            return data.get("tags", [])
    except Exception:
        pass

    return None


def _escribir_sidecar(ruta_imagen: str, tags: list[str], modelo: str):
    """Escribe el sidecar .tags.json junto a la imagen."""
    sidecar = _ruta_sidecar(ruta_imagen)
    data = {
        "file_hash": _hash_rapido(ruta_imagen),
        "tags": tags,
        "modelo": modelo,
        "fecha": datetime.now().isoformat(),
    }
    try:
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("  -> Sidecar escrito: %s", Path(sidecar).name)
    except Exception as e:
        logger.warning("  -> Error escribiendo sidecar %s: %s", sidecar, e)


# ═══════════════════════════════════════════════════════════════
#  BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

def conectar_db(ruta_db: str) -> sqlite3.Connection:
    """Conecta a la DB y verifica que tenga las tablas esperadas."""
    if not Path(ruta_db).exists():
        raise FileNotFoundError(f"No se encuentra la DB: {ruta_db}")

    conn = sqlite3.connect(ruta_db)
    conn.row_factory = sqlite3.Row

    # Verificar que exista la tabla media
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='media'"
    )
    if not cursor.fetchone():
        raise RuntimeError(
            f"La DB {ruta_db} no contiene la tabla 'media'. "
            "¿Es la base de datos correcta?"
        )

    return conn


def obtener_imagenes_sin_tags(
    conn: sqlite3.Connection, limite: Optional[int] = None
) -> list[dict]:
    """
    Busca imágenes en la DB que aún no tienen ai_tags en media_metadata.

    Returns:
        Lista de dicts con id, filepath_absoluto, filename_original.
    """
    query = """
        SELECT m.id, m.filepath_absoluto, m.filename_original
        FROM media m
        WHERE m.type = 'image'
        AND m.id NOT IN (
            SELECT mm.media_id
            FROM media_metadata mm
            WHERE mm.key = ?
        )
        ORDER BY m.id
    """
    params = [KEY_AI_TAGS]

    if limite:
        query += " LIMIT ?"
        params.append(limite)

    cursor = conn.execute(query, params)
    filas = cursor.fetchall()

    # Verificar que los archivos realmente existan en disco
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
            logger.warning(
                "  -> Imagen no encontrada en disco, skip: %s", ruta
            )

    return resultado


def guardar_tags_en_db(conn: sqlite3.Connection, media_id: int, tags: list[str]):
    """
    Guarda los tags de una imagen en media_metadata.

    Usa INSERT OR REPLACE para sobreescribir si ya existiera (por si
    se quiere re-etiquetar después).
    """
    try:
        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) "
            "VALUES (?, ?, ?)",
            (media_id, KEY_AI_TAGS, json.dumps(tags, ensure_ascii=False)),
        )
        conn.commit()
    except Exception as e:
        logger.error("  -> Error guardando tags en DB (id=%d): %s", media_id, e)


# ═══════════════════════════════════════════════════════════════
#  ETIQUETADO IA
# ═══════════════════════════════════════════════════════════════

def etiquetar_imagen(
    ruta: str,
    modelo: str = "moondream:latest",
    usar_proxy: bool = True,
) -> list[str]:
    """
    Extrae keywords de una imagen usando moondream.

    Args:
        ruta: Ruta a la imagen.
        modelo: Modelo de visión.
        usar_proxy: Si True, redimensiona la imagen antes de enviar a la IA.

    Returns:
        Lista de keywords.

    Raises:
        FileNotFoundError: Si la imagen no existe.
        ValueError: Si falla la extracción.
    """
    # extraer_keywords ya maneja proxies internamente
    keywords = extraer_keywords(
        ruta,
        modelo=modelo,
        temperatura=0.2,
        usar_proxy=usar_proxy,
    )
    return keywords


# ═══════════════════════════════════════════════════════════════
#  FLUJO PRINCIPAL
# ═══════════════════════════════════════════════════════════════

def procesar_imagen(
    ruta: str,
    modelo: str,
    usar_proxy: bool,
    sidecar: bool,
    dry_run: bool,
) -> Optional[list[str]]:
    """
    Procesa una imagen: extrae tags y opcionalmente guarda sidecar.

    Returns:
        Lista de tags, o None si falló.
    """
    if dry_run:
        logger.info("  [DRY RUN] Se etiquetaría: %s", Path(ruta).name)
        return None

    try:
        tags = etiquetar_imagen(ruta, modelo=modelo, usar_proxy=usar_proxy)
        logger.info("  Tags (%d): %s", len(tags), ", ".join(tags))

        # Sidecar
        if sidecar:
            _escribir_sidecar(ruta, tags, modelo)

        return tags

    except Exception as e:
        logger.error("  Error etiquetando %s: %s", Path(ruta).name, e)
        return None


def procesar_desde_db(
    ruta_db: str,
    modelo: str = "moondream:latest",
    limite: Optional[int] = None,
    sidecar: bool = False,
    usar_proxy: bool = True,
    dry_run: bool = False,
):
    """
    Modo post-ingesta: etiqueta imágenes de la DB.
    """
    logger.info("Conectando a DB: %s", ruta_db)
    conn = conectar_db(ruta_db)

    imagenes = obtener_imagenes_sin_tags(conn, limite=limite)

    if not imagenes:
        logger.info("No hay imágenes sin etiquetar en la DB.")
        conn.close()
        return

    logger.info(
        "Imágenes a procesar: %d%s",
        len(imagenes),
        " (dry run)" if dry_run else "",
    )

    ok = 0
    fail = 0

    for i, img in enumerate(imagenes, 1):
        logger.info(
            "[%d/%d] %s", i, len(imagenes), img["nombre"]
        )

        if dry_run:
            logger.info("  [DRY RUN] Se etiquetaría: %s", img["nombre"])
            ok += 1
            continue

        tags = procesar_imagen(
            img["ruta"],
            modelo=modelo,
            usar_proxy=usar_proxy,
            sidecar=sidecar,
            dry_run=False,
        )

        if tags:
            guardar_tags_en_db(conn, img["id"], tags)
            ok += 1
        else:
            fail += 1

    conn.close()

    logger.info(
        "=== RESUMEN: %d etiquetadas, %d fallos (de %d) ===",
        ok, fail, len(imagenes),
    )


def procesar_desde_carpeta(
    carpeta: str,
    modelo: str = "moondream:latest",
    sidecar: bool = True,
    usar_proxy: bool = True,
    dry_run: bool = False,
):
    """
    Modo autónomo: etiqueta imágenes de una carpeta y genera sidecars.
    """
    carpeta = Path(carpeta)
    if not carpeta.exists():
        raise FileNotFoundError(f"La carpeta no existe: {carpeta}")

    # Buscar imágenes
    rutas = sorted(
        str(p) for p in carpeta.rglob("*")
        if _es_imagen(str(p)) and "excluir" not in p.parts
    )

    if not rutas:
        logger.info("No se encontraron imágenes en %s", carpeta)
        return

    logger.info(
        "Imágenes encontradas: %d%s",
        len(rutas),
        " (dry run)" if dry_run else "",
    )

    ok = 0
    fail = 0
    ya_etiquetadas = 0

    for i, ruta in enumerate(rutas, 1):
        nombre = Path(ruta).name
        logger.info("[%d/%d] %s", i, len(rutas), nombre)

        # Verificar si ya tiene sidecar válido
        if sidecar and not dry_run:
            tags_existentes = _sidecar_existe_valido(ruta)
            if tags_existentes is not None:
                logger.info(
                    "  -> Ya tiene sidecar válido (%d tags). Skip.",
                    len(tags_existentes),
                )
                ya_etiquetadas += 1
                continue

        if dry_run:
            logger.info("  [DRY RUN] Se etiquetaría: %s", nombre)
            ok += 1
            continue

        tags = procesar_imagen(
            ruta,
            modelo=modelo,
            usar_proxy=usar_proxy,
            sidecar=sidecar,
            dry_run=False,
        )

        if tags:
            ok += 1
        else:
            fail += 1

    logger.info(
        "=== RESUMEN: %d nuevas, %d ya tenían sidecar, %d fallos (de %d) ===",
        ok, ya_etiquetadas, fail, len(rutas),
    )


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Etiquetar imágenes con IA (moondream).\n\n"
                    "Dos modos:\n"
                    "  --db ruta    : etiqueta imágenes de la DB (post-ingesta)\n"
                    "  --folder ruta: etiqueta imágenes de una carpeta (genera sidecars)\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Modo
    modo = parser.add_argument_group("Modo de operación")
    modo.add_argument("--db", help="Ruta a la base de datos SQLite (modo post-ingesta)")
    modo.add_argument("--folder", help="Ruta a carpeta con imágenes (modo autónomo)")

    # Opciones generales
    parser.add_argument("--modelo", default="moondream:latest",
                        choices=MODELOS_VISION,
                        help="Modelo de visión (default: moondream:latest)")
    parser.add_argument("--no-proxy", action="store_true",
                        help="No usar proxies (deshabilita redimensionado automático)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría sin ejecutar")

    # Opciones modo DB
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar cantidad de imágenes a procesar (solo modo --db)")
    parser.add_argument("--sidecar", action="store_true",
                        help="Generar también sidecar .tags.json (solo modo --db)")

    args = parser.parse_args()

    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Validar que se especificó un modo
    if not args.db and not args.folder:
        parser.error("Debe especificar --db o --folder")

    usar_proxy = not args.no_proxy

    try:
        if args.db:
            procesar_desde_db(
                ruta_db=args.db,
                modelo=args.modelo,
                limite=args.limit,
                sidecar=args.sidecar,
                usar_proxy=usar_proxy,
                dry_run=args.dry_run,
            )

        if args.folder:
            # En modo folder, los sidecars se generan siempre (es el propósito del modo)
            procesar_desde_carpeta(
                carpeta=args.folder,
                modelo=args.modelo,
                sidecar=True,
                usar_proxy=usar_proxy,
                dry_run=args.dry_run,
            )

    except KeyboardInterrupt:
        logger.info("\nProceso interrumpido por el usuario.")
        sys.exit(1)

    except Exception as e:
        logger.error("Error general: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
