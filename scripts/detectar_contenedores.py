#!/usr/bin/env python3
"""
detectar_contenedores.py — Audita contenedores de video/audio (streams faltantes).

Inspecciona con ffprobe los archivos de video/audio indexados en la DB y
clasifica el estado del contenedor:

    ok             → tiene los streams esperados (video con audio, audio con audio)
    sin_video      → archivo de video sin stream de video (remux raro/corrupto)
    sin_audio      → video sin stream de audio (silente; puede ser normal)
    sin_contenido  → ni video ni audio (contenedor vacío o corrupto)
    error_ffprobe  → no se pudo leer con ffprobe (archivo dañado)
    archivo_faltante → el archivo ya no existe en disco (se anota y no se re-audita)

Guarda el resultado en media_metadata:
    - clave 'contenedor_estado'  → "ok"|"sin_video"|"sin_audio"|"sin_contenido"|"error_ffprobe"|"archivo_faltante"
    - clave 'contenedor_streams' → JSON con el detalle de los streams detectados

Uso:
    python scripts/detectar_contenedores.py                  # anota solo pendientes (skip)
    python scripts/detectar_contenedores.py --mode update    # re-audita todos
    python scripts/detectar_contenedores.py --mode replace   # limpia y re-audita todos
    python scripts/detectar_contenedores.py --dry-run        # solo reporta, no escribe
    python scripts/detectar_contenedores.py --type video     # solo videos
    python scripts/detectar_contenedores.py --ffprobe C:/ruta/ffprobe.exe

Modos:
    skip    → audita medios que aún no tienen 'contenedor_estado' (default)
    update  → re-audita TODOS los videos/audios con archivo existente
    replace → limpia las claves existentes y re-audita todos
"""

import argparse
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.util import abrir, resolver_db

CLAVE_ESTADO = "contenedor_estado"
CLAVE_STREAMS = "contenedor_streams"

TIPOS_AUDITABLES = ("video", "audio")


# ═══════════════════════════════════════════════════════════════
#  UTILIDADES DE FFPROBE
# ═══════════════════════════════════════════════════════════════


def _hallar_ffprobe(ruta_ffprobe: str | None) -> str:
    """Devuelve la ruta a ffprobe (explícita o la del PATH).

    Args:
        ruta_ffprobe: Ruta explícita opcional (--ffprobe).

    Returns:
        Ruta al ejecutable ffprobe.

    Raises:
        RuntimeError: si no se encuentra en el PATH ni es válida la explícita.
    """
    if ruta_ffprobe:
        if os.path.isfile(ruta_ffprobe):
            return ruta_ffprobe
        log.warning("  --ffprobe no existe: %s. Buscando en el PATH.", ruta_ffprobe)
    hallado = shutil.which("ffprobe")
    if not hallado:
        raise RuntimeError("ffprobe no está en el PATH. Instalá ffmpeg o usá --ffprobe.")
    return hallado


def _consultar_streams(ffprobe: str, ruta_archivo: str) -> dict | None:
    """Ejecuta ffprobe -show_streams -show_format y devuelve el JSON.

    Args:
        ffprobe: Ruta al ejecutable ffprobe.
        ruta_archivo: Ruta absoluta al archivo a inspeccionar.

    Returns:
        Dict con el JSON de ffprobe, o None si falló (timeout, returncode ≠ 0
        o JSON inválido).
    """
    cmd = [
        ffprobe, "-hide_banner", "-loglevel", "error",
        "-show_streams", "-show_format", "-of", "json",
        ruta_archivo,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        log.warning("  ffprobe timeout para %s", ruta_archivo)
        return None
    if proc.returncode != 0:
        log.warning("  ffprobe falló para %s: %s",
                    ruta_archivo, proc.stderr.strip()[:200])
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        log.warning("  JSON inválido de ffprobe para %s", ruta_archivo)
        return None


def _clasificar_contenedor(info: dict | None, tipo_media: str) -> tuple[str, list[dict] | None]:
    """Clasifica el estado del contenedor a partir del JSON de ffprobe.

    Args:
        info: JSON de ffprobe (puede ser None si falló la lectura).
        tipo_media: "video" o "audio" (tipo indexado en la DB).

    Returns:
        Tupla (estado, resumen_streams). resumen_streams es una lista de
        {codec_type, codec_name} por stream, o None si info es None.
    """
    if info is None:
        return "error_ffprobe", None

    streams = info.get("streams", [])
    tiene_video = any(s.get("codec_type") == "video" for s in streams)
    tiene_audio = any(s.get("codec_type") == "audio" for s in streams)

    if tipo_media == "audio":
        estado = "ok" if tiene_audio else "sin_audio"
    else:  # video
        if not tiene_video:
            estado = "sin_contenido" if not tiene_audio else "sin_video"
        elif not tiene_audio:
            estado = "sin_audio"
        else:
            estado = "ok"

    resumen = [
        {"codec_type": s.get("codec_type"), "codec_name": s.get("codec_name")}
        for s in streams
    ]
    return estado, resumen


# ═══════════════════════════════════════════════════════════════
#  QUERIES SEGÚN MODO
# ═══════════════════════════════════════════════════════════════


def _query_segun_modo(mode: str) -> str:
    """Arma el SELECT de medios según el modo de auditoría.

    Args:
        mode: "skip" (solo pendientes) | "update" | "replace" (todos).

    Returns:
        Query SQL con placeholders (?, ?) para los tipos y, en skip,
        un placeholder adicional para CLAVE_ESTADO.
    """
    base = (
        "SELECT id, filepath_absoluto, type, filename_original "
        "FROM media WHERE type IN (?, ?)"
    )
    if mode == "skip":
        return base + (
            " AND NOT EXISTS ("
            "   SELECT 1 FROM media_metadata mm "
            "   WHERE mm.media_id = media.id AND mm.key = ?"
            " )"
        )
    return base


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    """Entry point para la auditoría de contenedores desde flujos.py o CLI.

    Args:
        argv: Lista de argumentos (sin el nombre del script).
               Si es None, usa sys.argv[1:].

    Returns:
        Código de salida (0 = ok, 1 = error).
    """
    parser = argparse.ArgumentParser(
        description="Audita contenedores de video/audio con ffprobe y anota "
                    "el estado en media_metadata (clave 'contenedor_estado').",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None,
                        help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="skip: solo sin estado (default) | update: todos | "
                             "replace: limpia y re-audita todos")
    parser.add_argument("--type", dest="tipo", default="todos",
                        choices=["todos", "video", "audio"],
                        help="Qué tipos de medios auditar (default: todos)")
    parser.add_argument("--ffprobe", default=None,
                        help="Ruta explícita al ejecutable ffprobe (default: PATH)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo reportar sin escribir en la DB")
    parser.add_argument("--verbose", action="store_true",
                        help="Log detallado")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Consola Windows: permitir caracteres UTF-8 sin UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    # Resolver DB y ffprobe
    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("No existe la DB: %s", db_path)
        return 1
    try:
        ffprobe = _hallar_ffprobe(args.ffprobe)
    except RuntimeError as e:
        log.error("  %s", e)
        return 1

    tipos = TIPOS_AUDITABLES if args.tipo == "todos" else (args.tipo,)
    log.info("Auditoría de contenedores (mode=%s, tipo=%s)", args.mode, args.tipo)

    conn = abrir(db_path)
    conn.row_factory = sqlite3.Row

    if args.mode == "replace":
        conn.execute(
            "DELETE FROM media_metadata WHERE key IN (?, ?)",
            (CLAVE_ESTADO, CLAVE_STREAMS),
        )
        conn.commit()
        log.info("  [replace] Limpiadas claves %s/%s de la DB.", CLAVE_ESTADO, CLAVE_STREAMS)

    # Listar medios según modo
    params: list = [*tipos]
    if args.mode == "skip":
        params.append(CLAVE_ESTADO)
    rows = conn.execute(_query_segun_modo(args.mode), params).fetchall()

    if not rows:
        print("  No hay medios para auditar (mode=%s, tipo=%s)." % (args.mode, args.tipo))
        conn.close()
        return 0

    log.info("  Medios a auditar: %d", len(rows))

    # ── Dry-run: solo listar sin inspeccionar ──
    if args.dry_run:
        print("\n  [DRY-RUN] Medios a auditar (máx 10):")
        for r in rows[:10]:
            existe = os.path.isfile(r["filepath_absoluto"])
            print(f"  media {r['id']} [{r['type']}] {r['filename_original']} — "
                  f"archivo: {'OK' if existe else 'FALTA'}")
            if existe:
                print(f"    {r['filepath_absoluto']}")
        print(f"\n  Total: {len(rows)}")
        conn.close()
        return 0

    # ── Auditar con ffprobe ──
    conteo: dict[str, int] = {}
    problematicos: list[dict] = []
    ok = 0
    errors = 0
    faltantes = 0

    for r in rows:
        ruta = r["filepath_absoluto"]
        if not os.path.isfile(ruta):
            faltantes += 1
            # B2: anotar el estado para que el medio no quede "pendiente" en skip
            conn.execute(
                "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
                (r["id"], CLAVE_ESTADO, "archivo_faltante"),
            )
            conn.execute(
                "DELETE FROM media_metadata WHERE media_id = ? AND key = ?",
                (r["id"], CLAVE_STREAMS),
            )
            continue
        try:
            info = _consultar_streams(ffprobe, ruta)
            estado, resumen = _clasificar_contenedor(info, r["type"])
        except Exception as e:
            log.warning("  ⚠ Error auditando %s: %s", ruta, e)
            errors += 1
            continue

        conteo[estado] = conteo.get(estado, 0) + 1
        if estado != "ok":
            problematicos.append({
                "media_id": r["id"],
                "tipo": r["type"],
                "archivo": r["filename_original"],
                "ruta": ruta,
                "estado": estado,
                "streams": resumen,
            })

        # Anotar en DB (INSERT OR REPLACE por media+key)
        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
            (r["id"], CLAVE_ESTADO, estado),
        )
        if resumen is not None:
            conn.execute(
                "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
                (r["id"], CLAVE_STREAMS, json.dumps(resumen, ensure_ascii=False)),
            )
        ok += 1

    conn.commit()

    # ── Reporte ──
    print(f"\n  Auditoría completada: {ok} auditados, {errors} errores, {faltantes} archivos faltantes")
    print("  Resumen por estado:")
    if not conteo:
        print("    (sin resultados)")
    for estado, cantidad in sorted(conteo.items(), key=lambda x: -x[1]):
        print(f"    {estado:<16} {cantidad}")

    if problematicos:
        print(f"\n  Contenedores problemáticos ({len(problematicos)}):")
        for p in problematicos:
            streams_txt = (
                ", ".join(f"{s['codec_type']}:{s['codec_name']}" for s in p["streams"])
                if p["streams"] else "sin streams"
            )
            print(f"    media {p['media_id']} [{p['tipo']}] {p['archivo']}")
            print(f"      estado={p['estado']} | streams: {streams_txt}")
            print(f"      {p['ruta']}")
    else:
        print("\n  No se encontraron contenedores problemáticos.")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
