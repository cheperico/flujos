"""
generate_embeddings.py
--------------------
Script idempotente que genera embeddings vectoriales para los medios de la
base de datos. El texto a embeber se construye de forma multi‑fuente a partir
de los metadatos enriquecidos del pipeline (descripción IA, keywords, sonidos,
transcripción por segmentos, caption de Telegram), de modo que los audios y
videos con transcripción también quedan indexados para búsqueda semántica.

Características:
  • Usa Ollama (modelo `nomic-embed-text` por defecto) para generar
    vectores a partir del texto combinado de cada medio.
  • Almacena los vectores en la tabla `media_embeddings` (BLOB JSON),
    con `INSERT OR REPLACE` para ser idempotente.
  • `--mode skip|update|replace` controla qué medios se procesan:
      skip    → solo medios que aún NO tienen embedding para el modelo
      update  → reprocesa TODOS los medios del modelo (sobrescribe)
      replace → borra los embeddings del modelo y regenera todos
  • Puede procesar un número limitado de medios (`--limit`) o todos.
  • Opcional: genera un side‑car `.embeddings.json` junto a cada archivo.
  • Soporta `--list-models` para ver los modelos instalados en Ollama.

Texto construido (en orden de prioridad y composición):
  1. Transcripción por segmentos (`whisper_segments` en media_metadata o
     keypoints `transcription` en media_keypoints), unida en orden temporal.
  2. `ia_description` (descripción de visión).
  3. `ia_keywords` (keywords de visión, normalizadas).
  4. `ia_keywords_transcripcion` (keywords del sentido de la transcripción).
  5. `ia_keywords_sonido` (sonidos ambientales detectados).
  6. `text` del mensaje de Telegram vinculado (`media.telegram_message_id`),
     si existe y no está vacío.

El texto total se limita a `MAX_TEXTO_CHARS` caracteres recortando en un
límite de palabra limpio. Si el texto construido queda vacío, el medio se
salta (no se genera embedding).

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
    # Procesar todos los medios sin embedding (skip, default)
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db

    # Procesar solo los primeros 10 medios
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db --limit 10

    # Reprocesar TODOS los medios del modelo (sobrescribe)
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db --mode update

    # Limpiar embeddings del modelo y regenerar todos
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db --mode replace

    # Previsualizar qué se procesaría sin tocar la DB (no llama a Ollama)
    python scripts/ai_media/generate_embeddings.py --db db/flujos.db --dry-run

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

# Claves en media_metadata / media_keypoints usadas como fuentes de texto
KEY_DESCRIPTION = "ia_description"
KEY_KEYWORDS = "ia_keywords"
KEY_KEYWORDS_TRANSCRIPCION = "ia_keywords_transcripcion"
KEY_KEYWORDS_SONIDO = "ia_keywords_sonido"
KEY_WHISPER_SEGMENTS = "whisper_segments"
# Keypoints de transcripción (tabla media_keypoints, clave 'transcription')
KEYPOINT_TRANSCRIPCION = "transcription"

# Tamaño máximo del texto que se envía al modelo de embeddings.
# nomic-embed-text tiene ~8192 tokens de contexto; 6000 caracteres en español
# (~1500-2000 tokens) deja margen holgado. El recorte se hace en un límite de
# palabra limpio (sin partir términos).
MAX_TEXTO_CHARS = 6000

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


def obtener_medios_para_embeddings(
    conn: sqlite3.Connection,
    modelo: str = DEFAULT_EMBEDDING_MODEL,
    modo: str = "skip",
    limite: Optional[int] = None,
):
    """
    Busca los medios (imágenes, videos o audios) a procesar según el modo.

    - `skip`:    medios que NO tengan embeddings guardados para el modelo
    - `update`:  TODOS los medios (sobrescribe con INSERT OR REPLACE)
    - `replace`: TODOS los medios (la limpieza previa se hace aparte)

    Devuelve lista de dicts con id, filepath_absoluto, filename_original, type.
    Solo se incluyen archivos que existen en disco.
    """
    if modo not in ("skip", "update", "replace"):
        raise ValueError(f"Modo inválido: {modo!r}. Esperado: skip, update, replace")

    base = """
        SELECT m.id, m.filepath_absoluto, m.filename_original, m.type
        FROM media m
        WHERE m.type IN ('image', 'video', 'audio')
        """

    if modo == "skip":
        query = base + """
            AND m.id NOT IN (
                SELECT media_id FROM media_embeddings
                WHERE modelo = ?
            )
            ORDER BY m.id
            """
        params: List = [modelo]
    else:
        query = base + " ORDER BY m.id"
        params = []

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
def _obtener_valor_metadata(conn: sqlite3.Connection, media_id: int, clave: str) -> Optional[str]:
    """Lee el value de media_metadata para (media_id, clave), o None."""
    fila = conn.execute(
        "SELECT value FROM media_metadata WHERE media_id = ? AND key = ?",
        (media_id, clave),
    ).fetchone()
    return fila["value"] if fila else None


def _normalizar_keywords(valor: Optional[str]) -> str:
    """
    Normaliza un campo de keywords a un string limpio separado por espacios.

    Soporta string plano separado por comas/puntos y coma/saltos de línea
    (`"retrato, montaña, bicicleta"`) y JSON (`["retrato", "montaña"]` o
    `{"keywords": [...]}`). Elimina duplicados consecutivos.
    """
    if not valor:
        return ""
    texto = str(valor).strip()
    if not texto:
        return ""

    partes: List[str] = []

    # Caso JSON (lista o dict con clave 'keywords')
    if texto.startswith("[") or texto.startswith("{"):
        try:
            datos = json.loads(texto)
            if isinstance(datos, list):
                partes = [str(x) for x in datos]
            elif isinstance(datos, dict):
                kws = datos.get("keywords") or datos.get("palabras_clave") or []
                partes = [str(x) for x in kws] if isinstance(kws, list) else [str(kws)]
        except (json.JSONDecodeError, TypeError):
            partes = []

    # String plano: separar por comas, punto y coma o saltos de línea
    if not partes:
        partes = re.split(r"[,;\n]+", texto)

    palabras: List[str] = []
    for p in partes:
        limpia = str(p).strip().strip(" \t.,;:¿?¡!\"'()[]{}")
        if limpia and limpia not in palabras:
            palabras.append(limpia)
    return " ".join(palabras)


def _combinar_segmentos_json(segmentos_json: Optional[str]) -> str:
    """
    Parsea el JSON de `whisper_segments` (lista de dicts con "inicio" y "texto")
    y concatena los textos en orden temporal por "inicio". Devuelve '' si no
    hay contenido útil.
    """
    if not segmentos_json:
        return ""
    try:
        segmentos = json.loads(segmentos_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning("  -> whisper_segments JSON inválido, ignorado.")
        return ""
    if not isinstance(segmentos, list):
        logger.warning("  -> whisper_segments no es una lista, ignorado.")
        return ""

    pares: List[tuple] = []
    for seg in segmentos:
        if not isinstance(seg, dict):
            continue
        texto = str(seg.get("texto", "") or "").strip()
        if not texto:
            continue
        try:
            inicio = float(seg.get("inicio", 0) or 0)
        except (TypeError, ValueError):
            inicio = 0.0
        pares.append((inicio, texto))

    pares.sort(key=lambda t: t[0])
    return " ".join(t for _, t in pares).strip()


def _obtener_transcripcion(conn: sqlite3.Connection, media_id: int, tipo: str) -> str:
    """
    Obtiene la transcripción por segmentos de un medio (audio/video).

    Prefiere la clave `whisper_segments` de media_metadata (JSON con los
    segmentos en orden). Si no existe o está vacía, fallback a los keypoints
    `transcription` de media_keypoints ordenados por timestamp_offset_secs.
    """
    # 1) whisper_segments (JSON en media_metadata) — funciona para cualquier tipo
    seg_json = _obtener_valor_metadata(conn, media_id, KEY_WHISPER_SEGMENTS)
    texto = _combinar_segmentos_json(seg_json)
    if texto:
        return texto

    # 2) Keypoints de transcripción (solo audio/video tienen sentido)
    if tipo not in ("audio", "video"):
        return ""

    filas = conn.execute(
        """
        SELECT value FROM media_keypoints
        WHERE media_id = ? AND key = ?
        ORDER BY timestamp_offset_secs ASC
        """,
        (media_id, KEYPOINT_TRANSCRIPCION),
    ).fetchall()
    fragmentos = [f["value"].strip() for f in filas if f["value"] and f["value"].strip()]
    return " ".join(fragmentos).strip()


def _obtener_texto_telegram(conn: sqlite3.Connection, media_id: int) -> str:
    """
    Si el medio está vinculado a un mensaje de Telegram (media.telegram_message_id),
    devuelve el `text` del mensaje (caption). '' si no hay o está vacío.
    """
    fila = conn.execute(
        """
        SELECT tg.text
        FROM media m
        JOIN telegram_messages tg ON tg.id = m.telegram_message_id
        WHERE m.id = ?
        """,
        (media_id,),
    ).fetchone()
    if fila and fila["text"] and str(fila["text"]).strip():
        return str(fila["text"]).strip()
    return ""


def _recortar_texto(texto: str, max_chars: int) -> str:
    """
    Recorta el texto a `max_chars` caracteres cortando en el último espacio
    disponible (no parte palabras). Si el texto no tiene espacios dentro del
    recorte, corta duro en `max_chars`.
    """
    if len(texto) <= max_chars:
        return texto.strip()
    recorte = texto[:max_chars]
    idx = recorte.rfind(" ")
    if idx >= max_chars // 2:
        return recorte[:idx].rstrip()
    return recorte.rstrip()


def obtener_texto_a_embeder(
    conn: sqlite3.Connection, media_id: int, tipo: str
) -> Optional[str]:
    """
    Construye el texto enriquecido multi‑fuente que será embebido.

    Orden de composición (concatenado con espacios, en este orden):
      1. Transcripción por segmentos (`whisper_segments` o keypoints
         `transcription`) — tiene prioridad porque es el contenido más denso.
      2. `ia_description` (descripción de visión).
      3. `ia_keywords` (keywords de visión, normalizadas).
      4. `ia_keywords_transcripcion` (si existe).
      5. `ia_keywords_sonido` (si existe).
      6. `text` del mensaje de Telegram vinculado (si existe y no está vacío).

    El total se limita a MAX_TEXTO_CHARS caracteres sin partir palabras.
    Devuelve None si al final el texto queda vacío.
    """
    partes: List[str] = []

    # 1) Transcripción (mayor densidad semántica; puede existir en cualquier tipo)
    transc = _obtener_transcripcion(conn, media_id, tipo)
    if transc:
        partes.append(transc)

    # 2) Descripción IA
    desc = _obtener_valor_metadata(conn, media_id, KEY_DESCRIPTION)
    if desc and str(desc).strip():
        partes.append(str(desc).strip())

    # 3) Keywords de visión (string plano o JSON)
    kw = _normalizar_keywords(_obtener_valor_metadata(conn, media_id, KEY_KEYWORDS))
    if kw:
        partes.append(kw)

    # 4) Keywords del sentido de la transcripción (si apareciera)
    kwt = _normalizar_keywords(_obtener_valor_metadata(conn, media_id, KEY_KEYWORDS_TRANSCRIPCION))
    if kwt:
        partes.append(kwt)

    # 5) Sonidos ambientales detectados (si existen)
    kws = _normalizar_keywords(_obtener_valor_metadata(conn, media_id, KEY_KEYWORDS_SONIDO))
    if kws:
        partes.append(kws)

    # 6) Caption de Telegram vinculado (si existe y no está vacío)
    tg = _obtener_texto_telegram(conn, media_id)
    if tg:
        partes.append(tg)

    if not partes:
        return None

    texto = " ".join(partes).strip()
    return _recortar_texto(texto, MAX_TEXTO_CHARS)


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
    modo: str = "skip",
):
    """
    Modo DB: recorre medios según el modo (skip|update|replace), construye el
    texto multi‑fuente, genera el embedding con Ollama y lo guarda en la tabla
    media_embeddings.

    En `--dry-run` NO se llama a Ollama: se construye el texto de cada medio y se
    reporta cuántos quedarían con contenido para embedar (y cuántos sin texto).
    """
    conn = conectar_db(ruta_db)

    # Modo replace: borrar embeddings existentes del modelo antes de regenerar.
    # En dry-run NO se borra nada, solo se informa cuántos se borrarían.
    if modo == "replace":
        if dry_run:
            n_existentes = conn.execute(
                "SELECT COUNT(*) FROM media_embeddings WHERE modelo = ?", (modelo,)
            ).fetchone()[0]
            logger.info("  [replace] (dry run) Se borrarían %d embeddings del modelo '%s'.",
                        n_existentes, modelo)
        else:
            borrados = conn.execute(
                "DELETE FROM media_embeddings WHERE modelo = ?", (modelo,)
            ).rowcount
            conn.commit()
            logger.info("  [replace] Embeddings borrados del modelo '%s': %d", modelo, borrados)

    medios = obtener_medios_para_embeddings(
        conn, modelo=modelo, modo=modo, limite=limite
    )

    if not medios:
        logger.info("No hay medios a procesar (modo=%s).", modo)
        conn.close()
        return

    logger.info("Medios a procesar: %d (modo=%s)%s",
                len(medios), modo, " (dry run)" if dry_run else "")

    ok = 0
    fail = 0
    sin_texto = 0

    for i, m in enumerate(medios, 1):
        # Construir el texto multi‑fuente (en dry-run NO generamos embedding)
        texto = obtener_texto_a_embeder(conn, m["id"], m["type"])
        if not texto:
            sin_texto += 1
            logger.info("[%d/%d] %s - sin texto construible. Saltando.",
                        i, len(medios), m["nombre"])
            continue

        if dry_run:
            logger.info("[%d/%d] %s (%d chars) - se procesaría.",
                        i, len(medios), m["nombre"], len(texto))
            ok += 1
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
        "=== RESUMEN: %d con texto, %d sin texto, %d errores (de %d) ===",
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
        description="Genera embeddings vectoriales para medios (imágenes/video/audio) "
                    "a partir del texto enriquecido multi‑fuente de la DB "
                    "(transcripción por segmentos, descripción, keywords, sonidos, "
                    "caption de Telegram) y los guarda en media_embeddings o como side‑car.\n\n"
                    "Modos:\n"
                    "  --db ruta            : procesa medios de la DB (con --mode skip|update|replace)\n"
                    "  --folder ruta        : procesa todos los archivos de una carpeta (sidecars)\n"
                    "  --mode MODO          : skip (default) solo pendientes | update todos | replace limpia y regenera\n"
                    "  --list-models        : muestra los modelos Ollama instalados y sale\n\n"
                    "Fuentes del texto a embeber (en orden):\n"
                    "  1. whisper_segments / keypoints transcription (transcripción)\n"
                    "  2. ia_description\n"
                    "  3. ia_keywords\n"
                    "  4. ia_keywords_transcripcion\n"
                    "  5. ia_keywords_sonido\n"
                    "  6. text del mensaje de Telegram vinculado\n\n"
                    "Ejemplos:\n"
                    "  python scripts/ai_media/generate_embeddings.py --db db/flujos.db\n"
                    "  python scripts/ai_media/generate_embeddings.py --db db/flujos.db --mode update\n"
                    "  python scripts/ai_media/generate_embeddings.py --db db/flujos.db --mode replace --dry-run\n"
                    "  python scripts/ai_media/generate_embeddings.py --db db/flujos.db --limit 20 --dry-run",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", help="Ruta a la base de datos SQLite (modo post‑ingesta)")
    parser.add_argument("--folder", help="Ruta a carpeta con archivos de medios")
    parser.add_argument("--modelo", default="nomic-embed-text",
                        help="Modelo Ollama a usar para generar embeddings")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="skip: solo sin embedding (default) | update: todos (sobrescribe) | replace: limpia y regenera")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar número de medios a procesar (solo modo --db)")
    parser.add_argument("--sidecar", action="store_true",
                        help="Generar side‑car .embeddings.json (solo modo --db o --folder)")
    parser.add_argument("--dry-run", action="store_true",
                         help="Solo muestra qué se procesaría, sin escribir nada (no llama a Ollama)")
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
                modo=args.mode,
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