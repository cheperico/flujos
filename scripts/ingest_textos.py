#!/usr/bin/env python3
"""
ingest_textos.py - Ingiere textos en archivos .md como medios type='text'.

El usuario escribe textos en archivos Markdown dentro de una carpeta `textos/`.
Cada archivo puede contener varios textos (colección): cada subtítulo `##` es un
texto individual. Si un archivo no tiene subtítulos, todo el cuerpo después del
frontmatter es un solo texto. El formato completo está documentado en
`textos/textos.md` (plantilla).

Uso:
    python scripts/ingest_textos.py --root textos --db db/flujos.db
    python scripts/ingest_textos.py --root <carpeta> --mode update --dry-run

Modos:
    skip     (default) solo ingesta textos nuevos (por file_hash)
    update   actualiza el contenido de textos existentes (sobrescribe)
    replace  limpia primero los textos type='text' de la carpeta y regenera
"""

import argparse
import hashlib
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime

_RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ_PROYECTO not in sys.path:
    sys.path.insert(0, _RAIZ_PROYECTO)

from db.util import abrir, resolver_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_textos")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _strip_comentarios_html(texto: str) -> str:
    """
    Elimina los comentarios HTML (<!-- ... -->) del texto.

    Si el bloque comienza al inicio del archivo (caso plantilla/documentación),
    se toma hasta el ÚLTIMO cierre `-->` para tolerar que la propia
    documentación mencione la sintaxis de comentario.
    """
    sin_comentarios = re.sub(r"<!--.*?-->", "", texto, flags=re.DOTALL)
    # Caso especial: archivo que empieza con un bloque de documentación que
    # menciona `<!-- ... -->` en su interior -> quitar hasta el último `-->`.
    if texto.lstrip().startswith("<!--") and "-->" in texto:
        ultimo = texto.rfind("-->")
        sin_comentarios = texto[ultimo + 3:]
    return sin_comentarios


def parsear_frontmatter(texto: str) -> tuple[dict, str]:
    """
    Extrae el frontmatter YAML entre dos líneas `---` y devuelve
    (campos, cuerpo_sin_frontmatter).

    Se hace un mini-parse de pares `clave: valor` por línea. Si `yaml` está
    disponible se prefiere; si no, se cae al parseo por líneas.
    """
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        return {}, texto

    fin = -1
    for i in range(1, len(lineas)):
        if lineas[i].strip() == "---":
            fin = i
            break
    if fin < 0:
        return {}, texto

    bloque = "\n".join(lineas[1:fin])
    cuerpo = "\n".join(lineas[fin + 1:])

    campos: dict = {}
    try:
        import yaml
        datos = yaml.safe_load(bloque)
        if isinstance(datos, dict):
            campos = datos
    except ImportError:
        for ln in lineas[1:fin]:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if ":" in ln:
                clave, _, valor = ln.partition(":")
                campos[clave.strip()] = valor.strip()
    return campos, cuerpo


def separar_textos(cuerpo: str) -> list[tuple[str, str]]:
    """
    Divide el cuerpo por subtítulos `## `. Devuelve una lista de (titulo, contenido).

    Si no hay subtítulos, devuelve una sola sección con titulo '' y todo el cuerpo.
    """
    lineas = cuerpo.splitlines()
    secciones: list[tuple[str, str]] = []
    titulo_actual = ""
    buffer: list[str] = []

    def cerrar():
        if titulo_actual or "".join(buffer).strip():
            secciones.append((titulo_actual, "\n".join(buffer).strip()))

    for ln in lineas:
        if ln.startswith("## "):
            cerrar()
            titulo_actual = ln[3:].strip()
            buffer = []
        else:
            buffer.append(ln)
    cerrar()

    return [(t, c) for t, c in secciones if c or t]


def sha256_texto(data: str) -> str:
    """SHA-256 de un fragmento de texto."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def parsear_fecha(fecha: str) -> str | None:
    """Normaliza una fecha a ISO. Acepta 'YYYY-MM-DD' o timestamp ISO completo."""
    if not fecha:
        return None
    fecha = fecha.strip().strip('"').strip("'")
    if not fecha:
        return None
    try:
        return datetime.fromisoformat(fecha).isoformat()
    except Exception:
        return fecha


# ---------------------------------------------------------------------------
# Lectura de archivos
# ---------------------------------------------------------------------------

_CLAVES_METADATA = {"autor", "fecha", "tags", "ubicacion"}


def _separar_metadata_texto(contenido: str) -> tuple[dict, str]:
    """
    Separa la metadata de un texto (líneas `clave: valor` al inicio de la
    sección, antes de la primera línea en blanco) del contenido propiamente
    dicho. Devuelve (metadata, contenido_sin_metadata).

    Solo se reconoce un conjunto fijo de claves (autor, fecha, tags, ubicacion);
    las líneas de prosa que lleven `:` NO se interpretan como metadata.
    Las claves sin valor (ej: `fecha:`) se guardan con valor None.
    """
    lineas = contenido.splitlines()
    meta: dict = {}
    i = 0
    while i < len(lineas):
        ln = lineas[i]
        m = re.match(r"^([A-Za-z_][\w]*)\s*:\s*(.*)$", ln)
        if m and m.group(1).strip().lower() in _CLAVES_METADATA:
            clave = m.group(1).strip().lower()
            valor = m.group(2).strip()
            meta[clave] = valor or None
            i += 1
        elif not ln.strip():
            i += 1  # salta la línea en blanco que separa metadata de contenido
            break
        else:
            break
    cuerpo = "\n".join(lineas[i:]).strip()
    return meta, cuerpo


def _unir_tags(*grupos) -> str | None:
    """Une y deduplica tags de varias fuentes (colección + texto)."""
    vistos: list[str] = []
    for grupo in grupos:
        if not grupo:
            continue
        for t in re.split(r"[,;\n]+", grupo):
            t = t.strip()
            if t and t not in vistos:
                vistos.append(t)
    return ", ".join(vistos) if vistos else None


_RE_COORDENADAS = re.compile(r"^-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?$")


def _parsear_ubicacion(valor: str | None) -> tuple[str | None, float | None, float | None]:
    """
    Parsea el valor del campo `ubicacion` de un texto.

    Devuelve (texto_ubicacion, lat, lon):
    - Si el valor es una coordenada 'lat, lon' (ej: -34.627328, -58.728783),
      devuelve el texto original + lat/lon numéricos.
    - Si es un nombre de lugar (ej: 'Moreno', 'Santiago del Estero'), devuelve
      el texto tal cual y lat/lon None.
    """
    if not valor:
        return None, None, None
    v = valor.strip()
    if _RE_COORDENADAS.match(v):
        partes = v.split(",")
        lat = float(partes[0].strip())
        lon = float(partes[1].strip())
        return v, lat, lon
    return v, None, None


def _leer_textos(carpeta_root: str) -> list[dict]:
    """
    Lee todos los .md de la carpeta y los descompone en textos individuales.
    Devuelve una lista de dicts con los campos listos para insertar.

    El archivo .md es un CONTENEDOR (equivalente a una carpeta para imágenes):
    cada subtítulo `##` es un TEXTO (un medio, su propio id). La metadata
    (autor, fecha, tags, ubicacion) es POR TEXTO: se lee de las líneas
    `clave: valor` al inicio de cada sección, no del frontmatter.
    """
    textos: list[dict] = []

    for filename in sorted(os.listdir(carpeta_root)):
        if not filename.lower().endswith(".md"):
            continue
        # Archivos de ejemplo/ocultos (prefijo `_`) NO se ingieren
        if filename.startswith("_"):
            log.info("  Ignorado (ejemplo/oculto): %s", filename)
            continue

        ruta_absoluta = os.path.join(carpeta_root, filename)
        relpath = os.path.relpath(ruta_absoluta, os.path.dirname(os.path.abspath(carpeta_root)))

        try:
            with open(ruta_absoluta, "r", encoding="utf-8") as f:
                contenido_raw = f.read()
        except (OSError, UnicodeDecodeError) as e:
            log.error("  No se pudo leer %s: %s", ruta_absoluta, e)
            continue

        # Quitar comentarios HTML (documentación, notas) antes de parsear
        contenido_limpio = _strip_comentarios_html(contenido_raw)
        campos, cuerpo = parsear_frontmatter(contenido_limpio)

        # Si tras quitar comentarios y frontmatter no queda cuerpo, es un archivo
        # de solo documentación/plantilla -> se salta (no genera texto fantasma).
        if not cuerpo.strip():
            continue

        # Metadata de la COLECCIÓN (del .md, NO de cada texto):
        # titulo (control/origen), compilador (quien armó el archivo, opcional),
        # tags (opcionales, se heredan a todos los textos del archivo).
        # `or ""` ANTES de str: los campos YAML vacíos (`key:`) llegan como None y
        # str(None) = 'None' (string literal). Con `or ""` el None se vuelve '' y el
        # `.strip() or ...` final lo resuelve a None/fallback correctamente.
        titulo_coleccion = str(campos.get("titulo") or "").strip() or os.path.splitext(filename)[0]
        compilador = str(campos.get("compilador") or "").strip() or None
        tags_coleccion = str(campos.get("tags") or "").strip() or None

        secciones = separar_textos(cuerpo)
        if not secciones:
            secciones = [("", cuerpo.strip())]

        for indice, (subtitulo, contenido) in enumerate(secciones):
            # Metadata del TEXTO: líneas `clave: valor` al inicio de la sección
            meta, cuerpo_texto = _separar_metadata_texto(contenido)

            titulo_final = subtitulo or titulo_coleccion
            # `or ""` ANTES de str: `_separar_metadata_texto` guarda None para
            # claves sin valor (`fecha:`) y str(None) = 'None' (string literal).
            autor = str(meta.get("autor") or "").strip() or None
            fecha_raw = str(meta.get("fecha") or "").strip() or None
            fecha_iso = parsear_fecha(fecha_raw) if fecha_raw else None
            tags_texto = str(meta.get("tags") or "").strip() or None
            ubicacion_raw = str(meta.get("ubicacion") or "").strip() or None
            # ubcion es un texto de lugar o una coordenada 'lat, lon'
            ubicacion, lat, lon = _parsear_ubicacion(ubicacion_raw)
            # Tags del texto + tags heredadas de la colección
            tags = _unir_tags(tags_coleccion, tags_texto)

            # Identidad del fragmento: título + metadata + contenido (para detectar cambios)
            meta_repr = ", ".join(f"{k}={v}" for k, v in sorted(meta.items()))
            identidad = f"{titulo_final}\n{meta_repr}\n{cuerpo_texto}".strip()

            textos.append({
                "titulo": titulo_final,
                "titulo_coleccion": titulo_coleccion,
                "subtitulo": subtitulo,
                "contenido": cuerpo_texto,
                "autor": autor,
                "fecha_iso": fecha_iso,
                "tags": tags,
                "ubicacion": ubicacion,
                "latitude": lat,
                "longitude": lon,
                "compilador": compilador,
                "indice": indice,
                "filename_original": titulo_final,
                "filepath_absoluto": ruta_absoluta,
                "filepath_relativo": relpath,
                "carpeta": os.path.basename(os.path.normpath(carpeta_root)),
                "file_hash": sha256_texto(identidad),
                "content_hash": sha256_texto(cuerpo_texto or ""),
                "size_bytes": len(cuerpo_texto or ""),
            })

    return textos


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Inicializa la DB con el schema (reusa lógica de ingest.py)."""
    from scripts.ingest import init_db as _init_db
    return _init_db(db_path)


def _insertar(conn: sqlite3.Connection, texto: dict) -> int:
    """Inserta un texto en media y devuelve su id."""
    cursor = conn.execute("""
        INSERT INTO media (
            filename_original, filepath_absoluto, filepath_relativo, carpeta,
            type, subtype, size_bytes, file_hash, content_hash,
            timestamp_original, timestamp_utc, author, latitude, longitude
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        texto["filename_original"],
        texto["filepath_absoluto"],
        texto["filepath_relativo"],
        texto["carpeta"],
        "text",
        "md",
        texto["size_bytes"],
        texto["file_hash"],
        texto["content_hash"],
        texto["fecha_iso"],
        texto["fecha_iso"],
        texto["autor"],
        texto.get("latitude"),
        texto.get("longitude"),
    ))
    media_id = cursor.lastrowid
    _insertar_metadata(conn, media_id, texto)
    return media_id


def _actualizar(conn: sqlite3.Connection, media_id: int, texto: dict):
    """Sobrescribe el contenido de un texto existente."""
    conn.execute("""
        UPDATE media SET
            file_hash = ?, content_hash = ?, size_bytes = ?, author = ?,
            timestamp_original = ?, timestamp_utc = ?, latitude = ?, longitude = ?
        WHERE id = ?
    """, (
        texto["file_hash"],
        texto["content_hash"],
        texto["size_bytes"],
        texto["autor"],
        texto["fecha_iso"],
        texto["fecha_iso"],
        texto.get("latitude"),
        texto.get("longitude"),
        media_id,
    ))
    _insertar_metadata(conn, media_id, texto)


def _insertar_metadata(conn: sqlite3.Connection, media_id: int, texto: dict):
    """Inserta o reemplaza las claves de metadata de un texto."""
    pares = {
        "texto_completo": texto["contenido"],
        "titulo_seccion": texto["subtitulo"] or "",
        "indice_seccion": str(texto["indice"]),
        # Clave estable (archivo + índice) para localizar un texto en update/skip
        # incluso si cambió su contenido (que altera file_hash).
        "origen_seccion": f"{texto['filepath_absoluto']}::{texto['indice']}",
    }
    if texto.get("tags"):
        pares["texto_tags"] = texto["tags"]
    if texto.get("ubicacion"):
        pares["texto_ubicacion"] = texto["ubicacion"]
    if texto.get("compilador"):
        # Metadata del archivo .md que armó la colección (no se usa aún,
        # solo se guarda como seguimiento de origen).
        pares["compilador"] = texto["compilador"]

    for clave, valor in pares.items():
        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
            (media_id, clave, valor),
        )


def _origen_seccion(texto: dict) -> str:
    """Clave estable de identidad de un texto: archivo + índice de sección."""
    return f"{texto['filepath_absoluto']}::{texto['indice']}"


def _cargar_existentes(conn: sqlite3.Connection) -> dict[str, int]:
    """
    Devuelve {origen_seccion: media_id} de todos los textos ya presentes en la DB.
    La clave `origen_seccion` (archivo+índice) es estable frente a cambios de
    contenido, por lo que permite detectar update/skip correctamente.
    """
    mapa: dict[str, int] = {}
    for mid, origen in conn.execute(
        "SELECT media_id, value FROM media_metadata WHERE key = 'origen_seccion'"
    ).fetchall():
        mapa[origen] = mid
    return mapa


def _insertar_actualizar(conn: sqlite3.Connection, texto: dict, mode: str,
                          existentes: dict[str, int]) -> tuple[str, int | None]:
    """Inserta o actualiza un texto según el modo. Devuelve (resultado, media_id)."""
    # Localizar por archivo + índice (clave estable, independiente del contenido)
    origen = _origen_seccion(texto)
    media_id = existentes.get(origen)

    if media_id is not None:
        if mode == "skip":
            return "skip", media_id
        _actualizar(conn, media_id, texto)
        # asegurar la marca de origen también en el registro actualizado
        _insertar_metadata(conn, media_id, texto)
        return "actualizado", media_id

    media_id = _insertar(conn, texto)
    return "insert", media_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ingiere archivos de texto (.md) de una carpeta como medios type 'text'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/ingest_textos.py --root textos
  python scripts/ingest_textos.py --root textos --db db/flujos.db --mode update
  python scripts/ingest_textos.py --root textos --dry-run
        """,
    )
    parser.add_argument("--root", default="textos", help="Carpeta donde estan los .md (default: textos)")
    parser.add_argument("--db", default=None, help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="Modo de ingesta (default: skip)")
    parser.add_argument("--dry-run", action="store_true", help="Previsualiza sin escribir en DB")

    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        log.error("La carpeta no existe: %s", args.root)
        sys.exit(1)

    db_path = resolver_db(args.db)
    log.info("Base de datos: %s", db_path)
    log.info("Carpeta raíz: %s", root)
    log.info("Modo: %s  |  dry_run=%s", args.mode, args.dry_run)

    textos = _leer_textos(root)
    if not textos:
        log.warning("No se generaron textos desde %s (¿solo documentación/plantilla?)", root)

    stats = {
        "textos": len(textos),
        "insert": 0,
        "actualizado": 0,
        "skip": 0,
        "error": 0,
        "borrado": 0,
    }

    conn = init_db(db_path)

    # replace: limpiar primero los textos de la carpeta
    if args.mode == "replace" and not args.dry_run:
        carpeta = os.path.basename(os.path.normpath(root))
        cursor = conn.execute(
            "DELETE FROM media WHERE type = 'text' AND carpeta = ?", (carpeta,)
        )
        stats["borrado"] = cursor.rowcount
        log.info("  replace: borrados %s textos existentes de carpeta '%s'", stats["borrado"], carpeta)
        conn.commit()

    # Mapa de textos ya presentes, por clave de origen estable
    existentes = _cargar_existentes(conn)

    for texto in textos:
        if args.dry_run:
            # Localizar por origen estable (independiente del contenido)
            media_id_existente = existentes.get(_origen_seccion(texto))
            if media_id_existente is not None and args.mode == "skip":
                resultado = "skip"
            elif media_id_existente is not None:
                resultado = "actualizado"
            else:
                resultado = "insert"
            media_id_str = "NEW"
        else:
            resultado, media_id_real = _insertar_actualizar(conn, texto, args.mode, existentes)
            media_id_str = str(media_id_real) if media_id_real is not None else "NEW"
            if media_id_real is not None:
                existentes.setdefault(_origen_seccion(texto), media_id_real)

        stats[resultado] += 1
        log.info("  [media %s] titulo=%s (idx %s) -> %s",
                 media_id_str, texto["titulo"], texto["indice"], resultado)

    conn.commit()

    # Resumen
    log.info("")
    log.info("=" * 60)
    log.info("  INGESTA DE TEXTOS COMPLETADA%s", "  (DRY RUN)" if args.dry_run else "")
    log.info("=" * 60)
    log.info("  Textos detectados:       %s", stats["textos"])
    log.info("  Insertados nuevos:       %s", stats["insert"])
    log.info("  Actualizados:            %s", stats["actualizado"])
    log.info("  Sin cambios (skip):      %s", stats["skip"])
    log.info("  Errores:                 %s", stats["error"])
    if stats["borrado"]:
        log.info("  Borrados (replace):      %s", stats["borrado"])
    log.info("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()