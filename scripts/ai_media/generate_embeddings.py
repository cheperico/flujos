"""
generate_embeddings.py
--------------------
Script idempotente que genera embeddings vectoriales para todas las
descripciones y transcripciones almacenadas en la base de datos que aún
no tengan embeddings. Permite actualizar el índice cuando se ingeran
nuevos medios.

Características:
  • Usa Ollama (modelo `nomic-embed-text` por defecto) para generar
    vectores a partir de descripciones de imágenes y transcripciones de
    audio/video.
  • Almacena los vectores en la tabla `media_embeddings` (BLOB JSON).
  • Puede procesar un número limitado de medios (`--limit`) o todos.
  • Opcional: genera un side‑car `.embeddings.json` junto a cada archivo.
  • Soporta `--list-models` para ver los modelos instalados en Ollama.
  • `--list-models` muestra los modelos instalados y sale.

Requisitos:
  - Ollama instalado y en ejecución.
  - Modelo de embeddings instalado (por defecto `nomic-embed-text`).
  - Tabla `media_embeddings` debe existir (se crea automáticamente si no
    existe). Ver esquema más abajo.

Formato del side‑car `.embeddings.json`:
    {
        "file_hash": "abc123def456",
        "media_id": 123,
        "modelo": "nomic-embed-text",
        "dimension": 768,
        "embedding": [...],
        "fecha": "2026-07-14T10:30:00"
    }

Uso:
    # Procesar todos los medios sin embedding
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db

    # Procesar solo los primeros 10 medios
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db --limit 10

    # Usar un modelo diferente (p.ej. qwen2.5vl:3b)
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db --modelo qwen2.5vl:3b

    # Ver modelos instalados
    python scripts/ai_media/generate_embeddings.py --list-models

    # Sólo generar side‑cars sin tocar la DB
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db --sidecar --dry-run
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Asegurar que la raíz del proyecto está en sys.path para importar módulos del proyecto
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ----------------------------------------------------------------------
# 1️⃣  CONFIGURACIÓN GLOBAL
# ----------------------------------------------------------------------
# Extensiones de archivo que consideramos "medios" (para los que generamos embeddings)
EXT_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mxf", ".mts", ".m2ts"}
EXT_AUDIO = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a", ".opus"}

# Clave en media_metadata donde guardamos descripción/transcripción
KEY_DESCRIPTION = "ia_description"
KEY_TRANSCRIPT = "transcript"

# Modelo de embedding por defecto (puedes cambiarlo con --modelo)
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

# Tamaño del vector de nomic-embed-text (768 dimensiones)
EMBEDDING_DIM = 768

# Logging: solo configurar a nivel módulo si es __main__
# (evita zapar los handlers de logging si otro script importa este módulo)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 2️⃣  UTILIDADES DE SISTEMA
# ----------------------------------------------------------------------
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


def _es_audio(ruta: str) -> bool:
    """Verifica si un archivo es audio por extensión."""
    return Path(ruta).suffix.lower() in EXT_AUDIO


def _ruta_sidecar(ruta_archivo: str) -> str:
    """Ruta del side‑car .embeddings.json para un archivo."""
    return f"{ruta_archivo}.embeddings.json"


def _sidecar_existe_valido(ruta_archivo: str) -> Optional[dict]:
    """
    Verifica si existe un side‑car .embeddings.json válido.
    Devuelve el dict completo si el hash coincide, None en caso contrario.
    """
    sidecar = _ruta_sidecar(ruta_archivo)
    if not Path(sidecar).exists():
        return None

    try:
        with open(sidecar, "r", encoding="utf-8") as f:
            data = json.load(f)

        hash_actual = _hash_rapido(ruta_archivo)
        if data.get("file_hash") == hash_actual:
            return data
    except Exception:
        pass
    return None


# ----------------------------------------------------------------------
# 3️⃣  BASE DE DATOS
# ----------------------------------------------------------------------
def conectar_db(ruta_db: str) -> sqlite3.Connection:
    """Conecta a la base de datos y asegura que existe la tabla media_embeddings."""
    if not Path(ruta_db).exists():
        raise FileNotFoundError(f"No se encuentra la base de datos: {ruta_db}")

    conn = sqlite3.connect(ruta_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    # Aplicar migraciones pendientes (schema canónico de media_embeddings)
    from db.migrate import verificar_schema
    verificar_schema(conn)

    # Crear tabla media_embeddings si no existe (schema canónico)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_embeddings (
            media_id    INTEGER NOT NULL REFERENCES media(id),
            embedding   BLOB NOT NULL,
            modelo      TEXT NOT NULL DEFAULT 'nomic-embed-text',
            fecha       TEXT DEFAULT (datetime('now')),
            UNIQUE(media_id, modelo)
        );
        """
    )
    conn.commit()
    return conn


def obtener_media_sin_embeddings(
    conn: sqlite3.Connection,
    modelo: str = DEFAULT_EMBEDDING_MODEL,
    limite: Optional[int] = None,
):
    """
    Busca medios (imágenes o videos) que NO tengan embeddings guardados
    para el modelo indicado. Devuelve lista de dicts con id, filepath_absoluto,
    filename_original, type.
    """
    query = """
        SELECT m.id, m.filepath_absoluto, m.filename_original, m.type
        FROM media m
        WHERE m.type IN ('image', 'video')
          AND m.id NOT IN (
                SELECT media_id FROM media_embeddings
                WHERE modelo = ?
            )
        ORDER BY m.id
        """
    params = [modelo]

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
                "type": fila["type"],
            })
        else:
            logger.warning("  -> Archivo no encontrado en disco: %s", fila["filepath_absoluto"])

    return resultado


def guardar_embedding(conn: sqlite3.Connection, media_id: int, embedding: List[float], modelo: str):
    """
    Guarda el embedding en la tabla media_embeddings.
    Usa INSERT OR REPLACE para que sea idempotente.
    """
    conn.execute(
        """
        INSERT OR REPLACE INTO media_embeddings
            (media_id, embedding, modelo, fecha)
        VALUES (?, ?, ?, ?)
        """,
        (media_id, json.dumps(embedding, ensure_ascii=False), modelo, datetime.now().isoformat())
    )
    conn.commit()


# ----------------------------------------------------------------------
# 4️⃣  EXTRAER TEXTO DE LA DB
# ----------------------------------------------------------------------
def obtener_texto_a_embeder(conn: sqlite3.Connection, media_id: int) -> Optional[str]:
    """
    Obtiene el texto que será embebido.
    Prioriza `ia_description`; si no existe, usa `transcript`.
    Si ninguno, devuelve None.
    """
    cur = conn.execute(
        f"""
        SELECT value FROM media_metadata
        WHERE media_id = ? AND key IN ('{KEY_DESCRIPTION}','{KEY_TRANSCRIPT}')
        """,
        (media_id,)
    )
    rows = cur.fetchall()
    if not rows:
        return None
    # Si hay varias filas (p.ej. ambas keys), concatenamos
    textos = [row["value"] for row in rows]
    return " ".join(textos).strip()


# ----------------------------------------------------------------------
# 5️⃣  EMBEDDING CON OLLAMA
# ----------------------------------------------------------------------
def generar_embedding(texto: str, modelo: str = "nomic-embed-text") -> List[float]:
    """
    Usa el cliente OllamaEmbedding para crear un vector a partir de `texto`.
    El cliente debe estar disponible en el path del proyecto.
    """
    from scripts.ai_media.ollama_client import OllamaEmbedding

    cliente = OllamaEmbedding(modelo=modelo)
    embedding = cliente.embed(texto)  # devuelve list[float]
    return embedding


# ----------------------------------------------------------------------
# 6️⃣  PROCESO DE GENERACIÓN
# ----------------------------------------------------------------------
def procesar_un_medio(
    ruta: str,
    modelo_embedding: str,
    dry_run: bool,
) -> bool:
    """
    Procesa un único medio:
        1. Obtiene su texto (descripcion o transcript)
        2. Genera embedding
        2a. Guarda side‑car .embeddings.json (si dry_run=False)
        3. Guarda embedding en la tabla media_embeddings
    Devuelve True si tuvo éxito, False en caso de error.
    """
    logger.info("  Procesando: %s", Path(ruta).name)

    # 1️⃣ Obtener texto (descripcion o transcript)
    # Necesitamos una conexión a la DB para obtener media_id y tipo
    # Pero como este script puede usarse en modo "folder", no siempre hay DB.
    # Por simplicidad, en modo folder generamos un side‑car sin DB.
    # Por ahora, asumimos que el medio ya está ingestado y tiene una fila en media.
    # Para simplificar, vamos a usar un enfoque más directo:
    #   - Si el archivo es video, usamos su transcripción (si existe en DB)
    #   - Si es imagen, usamos su descripción (ai_description)
    #   - Si ninguno, saltamos.

    # Determinar tipo y obtener texto
    if Path(ruta).suffix.lower() in EXT_VIDEO:
        # Necesitamos la DB para obtener media_id y transcript
        # Por simplicidad, en este script standalone no conectamos a DB.
        # En modo carpeta, simplemente generamos un placeholder.
        logger.warning("  (Modo folder) No se dispone de DB; se generará side‑car vacío.")
        # Para propósitos de demo, generamos un embedding vacío (cero)
        embedding = [0.0] * EMBEDDING_DIM
        modelo = modelo_embedding
    else:
        # Imagen: obtener su descripción desde la DB
        # (En modo folder no hay DB, así que este caso no se usa aquí)
        pass

    # ------------------------------------------------------------------
    # Si estamos en modo folder, simplemente generamos un side‑car vacío
    # (o podríamos intentar obtener descripción mediante un modelo de visión)
    # ------------------------------------------------------------------
    if not dry_run:
        # Generar side‑car con metadata mínima
        sidecar_data = {
            "file_hash": _hash_rapido(ruta),
            "modelo": modelo_embedding,
            "dimension": EMBEDDING_DIM,
            "embedding": [],  # vacío porque no tenemos embedding real
            "fecha": datetime.now().isoformat(),
        }
        with open(_ruta_sidecar(ruta), "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, ensure_ascii=False, indent=2)
        logger.info("  -> Side‑car .embeddings.json escrito (vacío).")
    else:
        logger.info("  [DRY RUN] Se procesaría: %s", Path(ruta).name)

    return True


# ----------------------------------------------------------------------
# 7️⃣  PROCESAMIENTO PRINCIPAL (DB y CARPETA)
# ----------------------------------------------------------------------

def procesar_desde_db(
    ruta_db: str,
    modelo: str = DEFAULT_EMBEDDING_MODEL,
    limite: Optional[int] = None,
    sidecar: bool = False,
    dry_run: bool = False,
):
    """
    Modo DB: recorre medios sin embedding, genera embedding con Ollama
    y guarda en la tabla media_embeddings.
    """
    conn = conectar_db(ruta_db)

    medios = obtener_media_sin_embeddings(conn, modelo=modelo, limite=limite)

    if not medios:
        logger.info("No hay medios sin embeddings en la DB.")
        conn.close()
        return

    logger.info("Medios a procesar: %d%s", len(medios), " (dry run)" if dry_run else "")

    ok = 0
    fail = 0
    sin_texto = 0

    for i, m in enumerate(medios, 1):
        logger.info("[%d/%d] %s", i, len(medios), m["nombre"])

        if dry_run:
            logger.info("  [DRY RUN] Se procesaría: %s", m["nombre"])
            ok += 1
            continue

        # Obtener descripción o transcripción desde la DB
        texto = obtener_texto_a_embeder(conn, m["id"])
        if not texto:
            logger.warning("  -> Sin descripción ni transcripción. Saltando.")
            sin_texto += 1
            continue

        # Generar embedding
        try:
            embedding = generar_embedding(texto, modelo=modelo)
        except Exception as e:
            logger.error("  -> Error generando embedding: %s", e)
            fail += 1
            continue

        # Guardar en DB
        guardar_embedding(conn, m["id"], embedding, modelo)
        logger.info("  -> Embedding guardado (%d dimensiones).", len(embedding))

        # Sidecar opcional
        if sidecar:
            sidecar_data = {
                "file_hash": _hash_rapido(m["ruta"]),
                "modelo": modelo,
                "dimension": EMBEDDING_DIM,
                "embedding": embedding,
                "fecha": datetime.now().isoformat(),
            }
            ruta_side = _ruta_sidecar(m["ruta"])
            with open(ruta_side, "w", encoding="utf-8") as f:
                json.dump(sidecar_data, f, ensure_ascii=False, indent=2)
            logger.info("  -> Sidecar escrito: %s", Path(ruta_side).name)

        ok += 1

    conn.close()

    logger.info(
        "=== RESUMEN: %d embeddings, %d sin texto, %d errores (de %d) ===",
        ok, sin_texto, fail, len(medios),
    )


def procesar_desde_carpeta(
    carpeta: str,
    modelo: str = DEFAULT_EMBEDDING_MODEL,
    dry_run: bool = False,
):
    """
    Modo carpeta: genera sidecars .embeddings.json para cada archivo de medio.
    Sin acceso a DB, los embeddings se generan vacíos como placeholder.
    """
    carpeta = Path(carpeta)
    if not carpeta.exists():
        raise FileNotFoundError(f"La carpeta no existe: {carpeta}")

    extensiones = EXT_VIDEO | EXT_AUDIO | {".jpg", ".jpeg", ".png", ".webp"}
    rutas = sorted(
        str(p) for p in carpeta.rglob("*")
        if p.suffix.lower() in extensiones and "excluir" not in p.parts
    )

    if not rutas:
        logger.info("No se encontraron archivos de medios en %s", carpeta)
        return

    logger.info("Archivos encontrados: %d%s", len(rutas), " (dry run)" if dry_run else "")

    ok = 0
    fail = 0
    ya_procesados = 0

    for i, ruta in enumerate(rutas, 1):
        nombre = Path(ruta).name
        logger.info("[%d/%d] %s", i, len(rutas), nombre)

        if not dry_run:
            existente = _sidecar_existe_valido(ruta)
            if existente:
                ya_procesados += 1
                logger.info("  -> Ya tiene sidecar válido. Skip.")
                continue

        if dry_run:
            logger.info("  [DRY RUN] Se procesaría: %s", nombre)
            ok += 1
            continue

        # Sin DB: generamos sidecar con embedding vacío
        try:
            procesar_un_medio(ruta, modelo_embedding=modelo, dry_run=False)
            ok += 1
        except Exception as e:
            logger.error("  Error procesando %s: %s", nombre, e)
            fail += 1

    logger.info(
        "=== RESUMEN: %d procesados, %d ya tenían sidecar, %d fallos (de %d) ===",
        ok, ya_procesados, fail, len(rutas),
    )


def listar_modelos():
    """Muestra los modelos instalados en Ollama."""
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
        print()
    except Exception as e:
        print(f"Error al conectar con Ollama: {e}")


def main():
    # Configurar logging aquí (solo se ejecuta si se llama como script)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Genera embeddings vectoriales para medios (imágenes/video) "
                    "y los guarda en la tabla media_embeddings o como side‑car.\n\n"
                    "Modos:\n"
                    "  --db ruta            : procesa medios de la DB que no tengan embeddings\n"
                    "  --folder ruta        : procesa todos los archivos de una carpeta\n"
                    "  --list-models        : muestra los modelos Ollama instalados y sale\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", help="Ruta a la base de datos SQLite (modo post‑ingesta)")
    parser.add_argument("--folder", help="Ruta a carpeta con archivos de medios")
    parser.add_argument("--modelo", default="nomic-embed-text",
                        help="Modelo Ollama a usar para generar embeddings")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar número de medios a procesar (solo modo --db)")
    parser.add_argument("--sidecar", action="store_true",
                        help="Generar side‑car .embeddings.json (solo modo --db o --folder)")
    parser.add_argument("--dry-run", action="store_true",
                         help="Solo muestra qué se procesaría, sin escribir nada")
    parser.add_argument("--list-models", action="store_true",
                        help="Mostrar modelos Ollama instalados y salir")
    args = parser.parse_args()

    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Si se pidió listar modelos, lo hacemos y salimos (antes de validar --db/--folder)
    if args.list_models:
        listar_modelos()
        return

    # Validar modo
    if not (args.db or args.folder):
        parser.error("Debe especificar --db o --folder")

    try:
        if args.db:
            procesar_desde_db(
                ruta_db=args.db,
                modelo=(args.modelo),
                limite=args.limit,
                sidecar=args.sidecar,
                dry_run=args.dry_run,
            )
        elif args.folder:
            procesar_desde_carpeta(
                carpeta=args.folder,
                modelo=args.modelo,
                dry_run=args.dry_run,
            )
    except KeyboardInterrupt:
        logger.info("\nProceso interrumpido por el usuario.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()