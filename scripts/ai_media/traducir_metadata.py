#!/usr/bin/env python3
"""
traducir_metadata.py — Traduce keywords y descripciones IA de EN → ES sobre la DB.

El pipeline nuevo genera keywords/descripciones con minicpm en INGLÉS y las
guarda en claves temporales (`ia_keywords_en`, `ia_description_en`). Este
script lee esas claves, traduce con un modelo de texto (qwen2.5:3b) y escribe
los resultados definitivos en español (`ia_keywords`, `ia_description`).

Por qué sobre la DB:
  - La traducción es texto puro (~2-9s por imagen) contra ~15-20s de visión.
  - No re-procesa imágenes: se puede re-ejecutar con --mode skip cuantas veces
    haga falta sin costo.
  - 1 sola llamada por imagen (keywords + descripción juntas en JSON).

Flujo completo:
  1. Visión:  improve_db --steps keywords,descriptions  → escribe *_en
  2. Traducción: este script → escribe ia_keywords/ia_description (ES)
  3. Refinamiento: refinar_keywords.py --mode update

Uso:
    python scripts/ai_media/traducir_metadata.py                  # ambos pasos
    python scripts/ai_media/traducir_metadata.py --paso keywords  # solo keywords
    python scripts/ai_media/traducir_metadata.py --paso descriptions
    python scripts/ai_media/traducir_metadata.py --dry-run        # previsualizar
    python scripts/ai_media/traducir_metadata.py --mode update    # re-traduce todo
    python scripts/ai_media/traducir_metadata.py --modelo qwen2.5:3b

Modos:
    skip    → solo registros que tienen EN y aún NO tienen ES (default)
    update  → re-traduce TODOS los registros que tienen EN (sobrescribe)
    replace → limpia el ES existente, luego traduce todo de nuevo

Nota: el género fotográfico queda pendiente (decisión del proyecto). Las
keywords se traducen tal cual; refinar_keywords.py fuerza "otras" si no hay.
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

# ── Modelo de texto para traducción ──────────────────────────────────────────
MODELO_TRADUCCION_DEFAULT = "qwen2.5:3b"

# ── Claves en DB ─────────────────────────────────────────────────────────────
CLAVE_KW_EN = "ia_keywords_en"
CLAVE_DESC_EN = "ia_description_en"
CLAVE_KW_ES = "ia_keywords"
CLAVE_DESC_ES = "ia_description"

# ── Glosario de cicloturismo (evita errores semánticos en la traducción) ─────
GLOSARIO = (
    "Glosario cicloturismo: road trip → viaje en ruta | repair → reparación | "
    "gear → equipamiento | cloth/fabric → tela | helmet → casco | "
    "bike/bicycle → bicicleta | pannier → alforja | gravel → ripio/grava | "
    "roadside → banquina | trail → sendero | handlebar → manubrio | "
    "pump → inflador | tire → cubierta | chain → cadena | "
    "wind → viento | sky → cielo | tree → árbol"
)

# ── Prompts de traducción ────────────────────────────────────────────────────

PROMPT_TRADUCIR_AMBOS = (
    "Traducí al ESPAÑOL rioplatense (Argentina) los siguientes datos de una imagen.\n"
    "Reglas:\n"
    "1. Keywords: SUSTANTIVOS, en el mismo orden, separadas por comas.\n"
    "2. NO dejes palabras en inglés, traducí TODAS.\n"
    "3. NO es portugués: en español se dice 'persona', 'objeto', 'color', 'acción'.\n"
    "4. Descripción: traducción natural y completa.\n"
    "5. Si una palabra está en el glosario, usá EXACTAMENTE la traducción del glosario.\n"
    + GLOSARIO + "\n"
    'Respondé SOLO con JSON: {{"keywords": "palabras en español separadas por comas", '
    '"description": "descripción en español"}}\n\n'
    "Keywords EN: {kw}\n"
    "Descripción EN: {desc}"
)

PROMPT_TRADUCIR_KEYWORDS = (
    "Traducí estas palabras clave del inglés al ESPAÑOL rioplatense (Argentina).\n"
    "Reglas:\n"
    "1. Devolvé SOLO las palabras en español, separadas por comas, en el mismo orden.\n"
    "2. Las palabras deben ser SUSTANTIVOS (no verbos ni frases verbales).\n"
    "3. NO dejes ninguna palabra en inglés, traducí TODAS.\n"
    "4. NO es portugués: recordá que en español se dice 'persona', 'objeto', 'color', 'acción'.\n"
    "5. Si una palabra está en el glosario, usá EXACTAMENTE la traducción del glosario.\n"
    + GLOSARIO + "\n\n"
    "Palabras en inglés: {kw}"
)

PROMPT_TRADUCIR_DESCRIPCION = (
    "Traducí este texto del inglés al ESPAÑOL rioplatense (Argentina).\n"
    "Reglas:\n"
    "1. Devolvé SOLO la traducción, sin comentarios.\n"
    "2. NO es portugués: en español se dice 'persona', 'objeto', 'imagen', 'acción'.\n"
    "3. Mantené el tono natural del español.\n\n"
    "Texto en inglés: {desc}"
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def leer_valor_db(valor: str | None) -> list[str]:
    """Convierte el valor de ia_keywords_* en DB a lista (JSON o string)."""
    if not valor:
        return []
    try:
        lista = json.loads(valor)
        if isinstance(lista, list):
            return [str(x) for x in lista]
    except (json.JSONDecodeError, TypeError):
        pass
    partes = [p.strip().strip("'\"").rstrip(".,;") for p in valor.split(",") if p.strip()]
    return partes


def reparar_json(texto: str) -> dict | None:
    """Parsea el JSON de respuesta con recorte de basura y cierre de brackets."""
    texto = texto.strip()
    ini = texto.find("{")
    fin = texto.rfind("}")
    if ini != -1 and fin != -1 and fin > ini:
        texto = texto[ini:fin + 1]
    intentos = [texto, texto.replace("'", '"')]
    for base in intentos:
        try:
            datos = json.loads(base)
            if isinstance(datos, dict):
                return datos
        except (json.JSONDecodeError, TypeError):
            pass
    # Cerrar brackets faltantes (JSON truncado al final)
    for base in intentos:
        for _ in range(8):
            abren = base.count("[") + base.count("{")
            cierran = base.count("]") + base.count("}")
            if abren == cierran:
                break
            if base.count("[") > base.count("]"):
                base = base.rstrip() + "]"
            elif base.count("{") > base.count("}"):
                base = base.rstrip() + "}"
            try:
                datos = json.loads(base)
                if isinstance(datos, dict):
                    return datos
            except (json.JSONDecodeError, TypeError):
                continue
    return None


def traducir_llamada(
    cliente,
    kw_en: list[str],
    desc_en: str,
    paso: str,
    modelo: str,
) -> tuple[list[str], str, str]:
    """
    Hace UNA llamada al modelo de texto y devuelve (keywords_es, descripcion_es, prompt_usado).

    Args:
        cliente: ollama.Client
        kw_en: keywords en inglés (lista)
        desc_en: descripción en inglés (string)
        paso: 'keywords' | 'descriptions' | 'ambos'
        modelo: modelo de texto

    Returns:
        (keywords_es, descripcion_es, prompt) — uno de los dos puede ser None.
    """
    kw_str = ", ".join(kw_en) if kw_en else ""
    desc_str = desc_en.strip() if desc_en else ""

    if paso == "keywords" or (paso == "ambos" and not desc_str):
        prompt = PROMPT_TRADUCIR_KEYWORDS.format(kw=kw_str)
        respuesta = cliente.chat(
            model=modelo,
            messages=[{"role": "user", "content": prompt}],
            options={"num_ctx": 2048, "temperature": 0.1},
        ).message.content.strip()
        # La respuesta es "palabras, separadas, por, comas"
        partes = [p.strip().strip("'\"") for p in respuesta.split(",") if p.strip()]
        partes = [p for p in partes if p]
        return (partes or None, None, "keywords")

    if paso == "descriptions" or (paso == "ambos" and not kw_str):
        prompt = PROMPT_TRADUCIR_DESCRIPCION.format(desc=desc_str)
        respuesta = cliente.chat(
            model=modelo,
            messages=[{"role": "user", "content": prompt}],
            options={"num_ctx": 4096, "temperature": 0.1},
        ).message.content.strip()
        return (None, respuesta or None, "descriptions")

    # ambos: una llamada JSON
    prompt = PROMPT_TRADUCIR_AMBOS.format(kw=kw_str, desc=desc_str)
    respuesta = cliente.chat(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
        options={"num_ctx": 4096, "temperature": 0.1},
    ).message.content.strip()

    datos = reparar_json(respuesta)
    if datos is None:
        log.warning("  No se pudo parsear JSON de traducción. Respuesta: %s", respuesta[:200])
        return (None, None, "ambos-json-error")

    keywords_es = None
    descripcion_es = None
    kws = datos.get("keywords")
    if isinstance(kws, str):
        partes = [p.strip().strip("'\"") for p in kws.split(",") if p.strip()]
        if partes:
            keywords_es = partes
    elif isinstance(kws, list):
        keywords_es = [str(x) for x in kws] or None
    desc = datos.get("description")
    if isinstance(desc, str) and desc.strip():
        descripcion_es = desc.strip()

    return (keywords_es, descripcion_es, "ambos-json")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Traduce keywords/descripciones IA de EN a ES sobre la DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None, help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--paso", default="ambos", choices=["keywords", "descriptions", "ambos"],
                        help="Qué traducir (default: ambos)")
    parser.add_argument("--modelo", default=MODELO_TRADUCCION_DEFAULT,
                        help=f"Modelo de texto para traducción (default: {MODELO_TRADUCCION_DEFAULT})")
    parser.add_argument("--mode", default="skip", choices=["skip", "update", "replace"],
                        help="skip: solo EN sin ES (default) | update: re-traduce todos | replace: limpia y traduce")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar a N registros (para pruebas)")
    parser.add_argument("--dry-run", action="store_true", help="Previsualizar sin escribir")
    parser.add_argument("--verbose", action="store_true", help="Log detallado")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolver DB
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from db.util import resolver_db

    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("No existe la DB: %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Construir query según modo y paso
    condiciones: list[str] = []
    if args.paso in ("keywords", "ambos"):
        condiciones.append(f"(SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_KW_EN}') IS NOT NULL")
    if args.paso in ("descriptions", "ambos"):
        condiciones.append(f"(SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_DESC_EN}') IS NOT NULL")
    if args.mode == "skip":
        if args.paso in ("keywords", "ambos"):
            condiciones.append(f"(SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_KW_ES}') IS NULL")
        if args.paso in ("descriptions", "ambos"):
            condiciones.append(f"(SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_DESC_ES}') IS NULL")

    where = " AND ".join(condiciones) if condiciones else "1=1"
    query = f"""
        SELECT m.id,
               (SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_KW_EN}') AS kw_en,
               (SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_DESC_EN}') AS desc_en,
               (SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_KW_ES}') AS kw_es,
               (SELECT value FROM media_metadata mm WHERE mm.media_id = m.id AND mm.key = '{CLAVE_DESC_ES}') AS desc_es
        FROM media m
        WHERE {where}
        ORDER BY m.id
    """
    rows = conn.execute(query).fetchall()
    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        print("  No hay registros para traducir.")
        conn.close()
        return

    log.info("  Registros a traducir: %d (paso=%s, mode=%s)", len(rows), args.paso, args.mode)

    # Limpiar en modo replace
    if args.mode == "replace":
        ids = [r["id"] for r in rows]
        if ids:
            conn.execute(
                f"DELETE FROM media_metadata WHERE media_id IN ({','.join('?' * len(ids))}) AND key IN (?, ?)",
                [*ids, CLAVE_KW_ES, CLAVE_DESC_ES])
            conn.commit()
            log.info("  Limpiado ES existente de %d registros", len(ids))

    if args.dry_run:
        print("\n  [DRY-RUN] Registros a traducir (máx 5):")
        for r in rows[:5]:
            kw_en = leer_valor_db(r["kw_en"])
            desc_en = r["desc_en"] or ""
            print(f"\n  media {r['id']}:")
            print(f"    KW_EN: {kw_en}")
            print(f"    DESC_EN: {desc_en[:120]}...")
        print(f"\n  Total: {len(rows)}")
        conn.close()
        return

    # Envolver el trabajo real con manejo de interrupción: al cortar con
    # Ctrl+C se commitean los pendientes (el guardado ya es por ítem cada 25)
    # y se sale con mensaje claro (manejar_interrupcion), sin traceback.
    from scripts.ai_media.checkpoint import manejar_interrupcion
    with manejar_interrupcion(conn=conn, etiqueta="traducir_metadata"):
        _ejecutar(conn, args, rows)


def _ejecutar(conn, args, rows) -> None:
    """
    Traduce los registros EN → ES sobre la DB (paso real del script).

    Separado de main() para poder envolverlo en manejar_interrupcion sin
    re-indentar el cuerpo (mismo nivel de indentación de función). El guardado
    por ítem (cada 25 registros) ya existía y no se modifica.
    """
    # Importar ollama y asegurar que el servidor esté corriendo
    try:
        import ollama
        from scripts.ai_media.ollama_client import asegurar_ollama
    except ImportError as e:
        log.error("No se pudo importar ollama: %s", e)
        conn.close()
        sys.exit(1)

    if not asegurar_ollama():
        log.error("Ollama no está disponible. Abortando traducción.")
        conn.close()
        sys.exit(1)

    cliente = ollama.Client(timeout=300)

    ok = 0
    errors = 0
    t_inicio = time.perf_counter()
    for i, r in enumerate(rows, 1):
        mid = r["id"]
        kw_en = leer_valor_db(r["kw_en"])
        desc_en = r["desc_en"] or ""

        try:
            keywords_es, descripcion_es, prompt_usado = traducir_llamada(
                cliente, kw_en, desc_en, args.paso, args.modelo)
        except Exception as e:
            log.warning("  ⚠ Error traduciendo media %s: %s", mid, e)
            errors += 1
            continue

        cambios = []
        if args.paso in ("keywords", "ambos") and keywords_es:
            conn.execute(
                "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
                (mid, CLAVE_KW_ES, ", ".join(keywords_es)))
            cambios.append(f"kw={keywords_es}")
        if args.paso in ("descriptions", "ambos") and descripcion_es:
            conn.execute(
                "INSERT OR REPLACE INTO media_metadata (media_id, key, value) VALUES (?, ?, ?)",
                (mid, CLAVE_DESC_ES, descripcion_es))
            cambios.append(f"desc={descripcion_es[:80]}...")

        if cambios:
            ok += 1
            if args.verbose:
                log.info("  [media %s] %s", mid, " | ".join(cambios))
            if i % 25 == 0:
                conn.commit()
                log.info("  Progreso: %d/%d (%d ok, %d err)", i, len(rows), ok, errors)
        else:
            log.warning("  ⚠ Sin resultado para media %s (paso=%s, prompt=%s)", mid, args.paso, prompt_usado)
            errors += 1

    conn.commit()
    total = time.perf_counter() - t_inicio
    log.info("  ✅ Traducción completa: %d ok | %d errores | %.1fs (%.2fs/img)",
             ok, errors, total, total / max(1, ok + errors))
    conn.close()


if __name__ == "__main__":
    main()
