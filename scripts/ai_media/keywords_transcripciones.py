#!/usr/bin/env python3
"""
keywords_transcripciones.py — Extrae keywords desde transcripciones de audio/video.

Las transcripciones de audios y videos existen en `media_metadata` con la clave
`whisper_segments` (JSON array de segmentos `{"inicio": ..., "fin": ..., "texto": ...}`).
Este script combina los textos de los segmentos en un solo texto (en orden por
`inicio`) y llama a un modelo de texto de Ollama (qwen2.5:3b) para extraer las
keywords relevantes en español.

El resultado se guarda en `media_metadata` con la clave NUEVA
`ia_keywords_transcripcion` (NO se mezcla con `ia_keywords`, que es de visión
para imágenes).

Uso:
    python scripts/ai_media/keywords_transcripciones.py                  # skip: solo pendientes
    python scripts/ai_media/keywords_transcripciones.py --mode update    # re-procesa todos
    python scripts/ai_media/keywords_transcripciones.py --mode replace   # limpia y regenera
    python scripts/ai_media/keywords_transcripciones.py --dry-run        # previsualiza sin escribir
    python scripts/ai_media/keywords_transcripciones.py --dry-run --probar-ollama  # + llama al modelo
    python scripts/ai_media/keywords_transcripciones.py --limit 5        # procesa solo 5 registros
    python scripts/ai_media/keywords_transcripciones.py --modelo qwen3.5:4b

Modos:
    skip    → solo audios/videos con whisper_segments que aún NO tienen
              ia_keywords_transcripcion (default)
    update  → re-procesa TODOS los con whisper_segments (sobrescribe)
    replace → limpia el ia_keywords_transcripcion existente y regenera

Nota: si el texto combinado es vacío o tiene menos de MIN_TEXTO_LEN (15) caracteres,
el registro se salta y se loguea (no hay contenido útil para extraer keywords).
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time

log = logging.getLogger(__name__)

# ── Claves en DB ─────────────────────────────────────────────────────────────
CLAVE_SEGMENTOS = "whisper_segments"           # clave de entrada (transcripción)
CLAVE_SALIDA = "ia_keywords_transcripcion"     # clave de salida (keywords)

# ── Modelo de texto para extracción de keywords ──────────────────────────────
MODELO_TEXTO_DEFAULT = "qwen2.5:3b"

# ── Umbrales ─────────────────────────────────────────────────────────────────
MIN_TEXTO_LEN = 40            # menos caracteres → no hay contenido útil
MAX_TEXTO_CHARS = 6000        # truncar el texto que se envía al modelo
MAX_KEYWORDS = 8              # recortar a 8 keywords como máximo
TIMEOUT_SEG = 120             # timeout de la llamada a Ollama

# ── Prompt de extracción ─────────────────────────────────────────────────────
PROMPT_KEYWORDS_TRANSCRIPCION = (
    "Leé esta transcripción de audio/video y entendé el SENTIDO GENERAL de lo que "
    "se está diciendo (de qué trata realmente, el contexto, la situación).\n"
    "Reglas:\n"
    "1. Devolvé SOLO entre 5 y 8 keywords, en ESPAÑOL, separadas por comas.\n"
    "2. Las keywords deben capturar el SIGNIFICADO, no solo palabras literales: "
    "temas centrales, conceptos, lugares, actividades, personas, clima, emociones, "
    "objetos, transporte, comida, sensaciones. Si se habla de 'la subida al cerro "
    "fue dura, las piernas no daban más', sirve 'esfuerzo' o 'cansancio' aunque no "
    "sean palabras textuales.\n"
    "3. Filtrá el ruido del habla: muletillas ('mmm', 'este', 'eh', 'bueno', "
    "'digamos', repeticiones), fragmentos sin contenido y nombres propios sueltos "
    "sin contexto.\n"
    '4. Respondé SOLO con la lista de keywords, sin texto adicional ni explicaciones.\n\n'
    "Transcripción:\n"
)

# Muletillas / ruido común del habla que el modelo podría dejar pasar
MULETILLAS = {
    "mmm", "mm", "eh", "este", "bueno", "digamos", "o sea", "sabés", "sabes",
    "viste", "mirá", "mirá vos", "básicamente", "obviamente", "tipo",
    "como que", "no sé", "y", "o", "que", "a", "en", "de", "la", "el", "un",
}

# Patrones basura que a veces regurgita el modelo (parte del prompt)
PATRONES_BASURA = [
    r"^keywords?\s*[:：]",
    r"^lista\s*[:：]",
    r"^las\s+palabras\s+clave",
    r"^aquí",
    r"^aqu\s*í",
    r"^transcripci[oó]n",
    r"^\d+[.)]\s*",           # numeración "1. perro"
    r"^[\"'.*-]+",
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def combinar_texto_segmentos(segmentos_json: str) -> str:
    """
    Parsea el JSON de `whisper_segments` y concatena los textos en orden por `inicio`.

    Args:
        segmentos_json: Valor de media_metadata (JSON array de dicts).

    Returns:
        Texto único con todos los segmentos unidos por espacio ('' si no hay).
    """
    if not segmentos_json:
        return ""
    try:
        segmentos = json.loads(segmentos_json)
    except (json.JSONDecodeError, TypeError):
        log.warning("  No se pudo parsear whisper_segments (JSON inválido).")
        return ""
    if not isinstance(segmentos, list):
        log.warning("  whisper_segments no es una lista.")
        return ""

    # Ordenar por inicio (float/int) y concatenar respetando ese orden
    textos: list[tuple[float, str]] = []
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
        textos.append((inicio, texto))

    textos.sort(key=lambda t: t[0])
    return " ".join(t for _, t in textos).strip()


def _limpiar_keyword(palabra: str) -> str:
    """Limpia una keyword individual (espacios, puntuación, numeración)."""
    p = palabra.strip().lower()
    for pat in PATRONES_BASURA:
        p = re.sub(pat, "", p)
    p = p.strip(" ,.;:-—_\"'()[]{}").strip()
    return p


def _es_basura(palabra: str) -> bool:
    """Determina si una keyword es ruido (muletilla, demasiado corta, etc.)."""
    if not palabra:
        return True
    if len(palabra) < 2:
        return True
    if palabra in MULETILLAS:
        return True
    # Palabras sin vocales → casi seguro ruido
    if not re.search(r"[aeiouáéíóú]", palabra):
        return True
    return False


def _parsear_keywords(respuesta: str) -> list[str]:
    """
    Convierte la respuesta del modelo en lista de keywords.

    Soporta tres formatos:
      - JSON:  ["perro", "ruta"]  o  {"keywords": ["perro", "ruta"]}
      - Texto: "perro, ruta, sol"
      - Texto con numeración: "1. perro 2. ruta"

    Args:
        respuesta: Texto crudo devuelto por Ollama.

    Returns:
        Lista de keywords limpias (sin ruido).
    """
    if not respuesta:
        return []
    texto = respuesta.strip()

    # 1. Intentar parsear como JSON
    try:
        datos = json.loads(texto)
        if isinstance(datos, list):
            partes = [str(x) for x in datos]
        elif isinstance(datos, dict):
            kws = datos.get("keywords") or datos.get("palabras_clave") or []
            partes = [str(x) for x in kws] if isinstance(kws, list) else [str(kws)]
        else:
            partes = []
    except (json.JSONDecodeError, TypeError):
        partes = []

    # 2. Fallback: separar por comas / saltos de línea
    if not partes:
        partes = re.split(r"[,;\n]+", texto)

    resultado = []
    for p in partes:
        limpia = _limpiar_keyword(p)
        if limpia and not _es_basura(limpia) and limpia not in resultado:
            resultado.append(limpia)
    return resultado


def extraer_keywords_transcripcion(
    cliente,
    texto: str,
    modelo: str,
) -> list[str]:
    """
    Llama al modelo de texto y devuelve las keywords de la transcripción.

    Args:
        cliente: ollama.Client
        texto: Texto combinado de la transcripción.
        modelo: Nombre del modelo de texto (ej: qwen2.5:3b).

    Returns:
        Lista de keywords en español.
    """
    # Truncar textos muy largos (protección de contexto)
    if len(texto) > MAX_TEXTO_CHARS:
        log.debug("  Texto truncado a %d caracteres (original: %d)", MAX_TEXTO_CHARS, len(texto))
        texto = texto[:MAX_TEXTO_CHARS]

    # Concatenación directa (evita problemas si el texto transcrito contiene llaves)
    prompt = PROMPT_KEYWORDS_TRANSCRIPCION + texto
    respuesta = cliente.chat(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
        options={"num_ctx": 4096, "temperature": 0.2},
    ).message.content.strip()

    return _parsear_keywords(respuesta)[:MAX_KEYWORDS]


# ── Queries según modo ───────────────────────────────────────────────────────


def _query_segun_modo(mode: str) -> tuple[str, list]:
    """
    Devuelve (query, params) para listar los medios a procesar según el modo.

    skip    → audios/videos con whisper_segments y SIN ia_keywords_transcripcion
    update  → audios/videos con whisper_segments (todos)
    replace → audios/videos con whisper_segments (todos; el clean va aparte)
    """
    base = """
        SELECT m.id, m.filename_original, m.type,
               mm.value AS segments_json
        FROM media m
        JOIN media_metadata mm
          ON mm.media_id = m.id AND mm.key = ?
        WHERE m.type IN ('audio', 'video')
    """
    if mode == "skip":
        query = base + """
            AND NOT EXISTS (
                SELECT 1 FROM media_metadata out_
                WHERE out_.media_id = m.id AND out_.key = ?
            )
            ORDER BY m.id
        """
        return query, [CLAVE_SEGMENTOS, CLAVE_SALIDA]
    return base + " ORDER BY m.id", [CLAVE_SEGMENTOS]


# ── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Extrae keywords de transcripciones de audio/video (whisper_segments) "
                    "y las guarda en media_metadata con clave 'ia_keywords_transcripcion'.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None, help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="skip: solo sin keywords (default) | update: todos | replace: limpia y regenera")
    parser.add_argument("--modelo", default=MODELO_TEXTO_DEFAULT,
                        help=f"Modelo de texto para extracción (default: {MODELO_TEXTO_DEFAULT})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar a N registros (para pruebas)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Previsualizar sin escribir (con --probar-ollama además llama al modelo)")
    parser.add_argument("--probar-ollama", action="store_true",
                        help="Solo con --dry-run: hace la llamada real a Ollama y muestra las keywords propuestas")
    parser.add_argument("--verbose", action="store_true", help="Log detallado")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.probar_ollama and not args.dry_run:
        log.warning("  --probar-ollama solo tiene efecto con --dry-run. Se ignora.")

    # Resolver DB (permite ejecución standalone desde cualquier directorio)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from db.util import abrir, resolver_db

    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("No existe la DB: %s", db_path)
        sys.exit(1)

    conn = abrir(db_path)
    conn.row_factory = sqlite3.Row

    # ── Modo replace: limpiar la clave de salida antes de regenerar ──
    if args.mode == "replace":
        conn.execute(
            "DELETE FROM media_metadata WHERE key = ?", (CLAVE_SALIDA,)
        )
        conn.commit()
        log.info("  [replace] Limpiado ia_keywords_transcripcion de la DB.")

    query, params = _query_segun_modo(args.mode)
    rows = conn.execute(query, params).fetchall()
    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        print("  No hay registros con whisper_segments para procesar.")
        conn.close()
        return

    log.info("  Registros con whisper_segments: %d (mode=%s, modelo=%s)",
             len(rows), args.mode, args.modelo)

    # ── Dry-run (sin escribir) ──
    if args.dry_run:
        print("\n  [DRY-RUN] Registros a procesar (máx 5):")
        for r in rows[:5]:
            texto = combinar_texto_segmentos(r["segments_json"])
            estado = "OK" if len(texto) >= MIN_TEXTO_LEN else "SKIP (texto corto)"
            print(f"\n  media {r['id']} [{r['type']}] {r['filename_original']}")
            print(f"    estado: {estado} | texto: {len(texto)} chars")
            print(f"    preview: {texto[:150]}...")

            if args.probar_ollama and len(texto) >= MIN_TEXTO_LEN:
                try:
                    import ollama
                    from scripts.ai_media.ollama_client import asegurar_ollama
                    if asegurar_ollama():
                        cliente = ollama.Client(timeout=TIMEOUT_SEG)
                        keywords = extraer_keywords_transcripcion(
                            cliente, texto, args.modelo)
                        print(f"    keywords propuestas: {', '.join(keywords) if keywords else '—'}")
                    else:
                        print("    ⚠ Ollama no disponible, no se probó la llamada.")
                except Exception as e:
                    print(f"    ⚠ Error llamando a Ollama: {e}")

        print(f"\n  Total: {len(rows)}")
        conn.close()
        return

    # ── Modo real: procesar (envuelto en manejar_interrupcion) ──
    # Al cortar con Ctrl+C se commitean los pendientes (el guardado ya es por
    # ítem cada 25) y se sale con mensaje claro, sin traceback.
    from scripts.ai_media.checkpoint import manejar_interrupcion
    with manejar_interrupcion(conn=conn, etiqueta="keywords_transcripciones"):
        _ejecutar(conn, args, rows)


def _ejecutar(conn, args, rows) -> None:
    """
    Extrae las keywords de las transcripciones y las escribe en la DB.

    Separado de main() para poder envolverlo en manejar_interrupcion sin
    re-indentar el cuerpo (mismo nivel de indentación de función). El
    guardado por ítem (cada 25) ya existía y no se modifica.
    """
    # ── Modo real: importar ollama y asegurar que el servidor esté corriendo ──
    try:
        import ollama
        from scripts.ai_media.ollama_client import asegurar_ollama
    except ImportError as e:
        log.error("No se pudo importar ollama: %s", e)
        conn.close()
        sys.exit(1)

    if not asegurar_ollama():
        log.error("Ollama no está disponible. Abortando.")
        conn.close()
        sys.exit(1)

    cliente = ollama.Client(timeout=TIMEOUT_SEG)

    ok = 0
    errors = 0
    vacios = 0
    t_inicio = time.perf_counter()
    for i, r in enumerate(rows, 1):
        mid = r["id"]
        texto = combinar_texto_segmentos(r["segments_json"])

        if len(texto) < MIN_TEXTO_LEN:
            log.info("  [media %s] texto demasiado corto (%d chars), skip.", mid, len(texto))
            vacios += 1
            continue

        try:
            keywords = extraer_keywords_transcripcion(cliente, texto, args.modelo)
        except Exception as e:
            log.warning("  ⚠ Error extrayendo keywords de media %s: %s", mid, e)
            errors += 1
            continue

        if not keywords:
            log.warning("  ⚠ Sin keywords devueltas para media %s.", mid)
            errors += 1
            continue

        conn.execute(
            "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
            (mid, CLAVE_SALIDA, ", ".join(keywords)),
        )
        ok += 1
        if args.verbose:
            log.info("  [media %s] keywords: %s", mid, ", ".join(keywords))
        if i % 25 == 0:
            conn.commit()
            log.info("  Progreso: %d/%d (%d ok, %d err, %d vacíos)", i, len(rows), ok, errors, vacios)

    conn.commit()
    total = time.perf_counter() - t_inicio
    log.info("  ✅ Keywords de transcripciones: %d ok | %d errores | %d vacíos | %.1fs (%.2fs/media)",
             ok, errors, vacios, total, total / max(1, len(rows)))
    conn.close()


if __name__ == "__main__":
    main()
