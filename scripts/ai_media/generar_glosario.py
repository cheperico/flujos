#!/usr/bin/env python3
"""
generar_glosario.py — Genera/amplía el glosario EN→ES desde fuentes manuales y la DB.

El glosario (glosario_keywords.json en la raíz del proyecto) alimenta la
traducción NO-AI de keywords/descripciones (ver glosario.py). Este script
lo construye a partir de tres fuentes, en orden de prioridad:

  1. MANUAL: SINONIMOS de refinar_keywords.py (léxico curado del dominio,
     incluye variantes EN) → origen 'manual'.
  2. DB (default, --solo-db): pares alineados ia_keywords_en / ia_keywords
     con voto por mayoría por palabra EN → ES → origen 'db_seed'.
  3. EXTENDER (--extender): palabras del corpus aún ausentes, traducidas con
     un motor clásico (google|argos) → origen 'auto'.

La fusión respeta la prioridad manual > db_seed > auto: nunca se pisa una
entrada de mayor prioridad.

Uso:
    python scripts/ai_media/generar_glosario.py                  # solo DB (default)
    python scripts/ai_media/generar_glosario.py --solo-db        # explícito
    python scripts/ai_media/generar_glosario.py --extender --motor google
    python scripts/ai_media/generar_glosario.py --extender --motor argos
    python scripts/ai_media/generar_glosario.py --dry-run        # previsualizar sin guardar
"""

import argparse
import logging
import os
import sqlite3
import sys
from collections import Counter, defaultdict

log = logging.getLogger(__name__)

# Permitir ejecución standalone: agregar raíz del proyecto al path
# (mismo patrón que los demás scripts de ai_media/).
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )


def leer_valor_db(valor: str | None) -> list[str]:
    """Convierte el valor de ia_keywords_* en DB a lista (JSON o string)."""
    if not valor:
        return []
    try:
        import json
        lista = json.loads(valor)
        if isinstance(lista, list):
            return [str(x) for x in lista]
    except (json.JSONDecodeError, TypeError):
        pass
    partes = [p.strip().strip("'\"").rstrip(".,;") for p in valor.split(",") if p.strip()]
    return partes


def leer_pares_db(db_path: str) -> list[tuple[list[str], list[str]]]:
    """Lee pares (kw_en, kw_es) alineados posicionalmente de la DB.

    Query de pares ia_keywords_en / ia_keywords. Solo se alinean las filas
    donde len(en) == len(es) (el prompt de traducción garantiza el orden);
    las demás se descartan para el voto.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        filas = conn.execute("""
            SELECT mm1.value AS kw_en, mm2.value AS kw_es
            FROM media_metadata mm1
            JOIN media_metadata mm2 ON mm1.media_id = mm2.media_id AND mm2.key = 'ia_keywords'
            WHERE mm1.key = 'ia_keywords_en'
        """).fetchall()
    finally:
        conn.close()

    pares: list[tuple[list[str], list[str]]] = []
    for fila in filas:
        en = leer_valor_db(fila["kw_en"])
        es = leer_valor_db(fila["kw_es"])
        if not en or not es or len(en) != len(es):
            continue
        pares.append((en, es))
    return pares


def votar_pares(pares: list[tuple[list[str], list[str]]]) -> dict[str, str]:
    """Voto por mayoría: palabra EN (case-insens) → palabra ES más frecuente.

    Se conserva la grafía ES más votada (y en empate, la primera vista).
    """
    votos: dict[str, Counter] = defaultdict(Counter)
    for en, es in pares:
        for palabra_en, palabra_es in zip(en, es):
            clave = palabra_en.strip().lower()
            valor = palabra_es.strip()
            if clave and valor:
                votos[clave][valor] += 1
    return {clave: cont.most_common(1)[0][0] for clave, cont in votos.items()}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Genera/amplía el glosario EN→ES (manual + DB + opcional motor)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None,
                        help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--solo-db", action="store_true",
                        help="Sembrar desde pares alineados de la DB (comportamiento por defecto)")
    parser.add_argument("--extender", action="store_true",
                        help="Además, traducir con un motor clásico las palabras del corpus que faltan")
    parser.add_argument("--motor", default="google", choices=["google", "argos"],
                        help="Motor clásico para --extender (default: google)")
    parser.add_argument("--salida", default=None,
                        help="Ruta del glosario JSON (default: raíz del proyecto)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Previsualizar conteos y cobertura sin guardar")
    parser.add_argument("--verbose", action="store_true", help="Log detallado")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    from db.util import resolver_db
    from scripts.ai_media.glosario import Glosario, crear_motor, traducir_con_motor, ruta_por_defecto

    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        log.error("  No existe la DB: %s", db_path)
        sys.exit(1)

    salida = args.salida or ruta_por_defecto()
    glosario = Glosario(salida)
    glosario.cargar()
    log.info("  Glosario: %s", salida)
    log.info("  Entradas previas: %d", len(glosario.palabras))

    # ── Fuente 1: manual (SINONIMOS de refinar_keywords.py) ────────────────
    from scripts.ai_media.refinar_keywords import SINONIMOS

    entradas_manual: dict[str, str] = {}
    for canonico, variantes in SINONIMOS.items():
        for variante in variantes:
            if variante and variante.strip():
                entradas_manual[variante.strip().lower()] = canonico
    glosario.agregar_entradas(entradas_manual, origen="manual")
    log.info("  Fuente manual: %d variantes → %d canónicos",
             len(entradas_manual), len(SINONIMOS))

    # ── Fuente 2: DB (pares alineados, default) ─────────────────────────────
    pares = leer_pares_db(db_path)
    log.info("  Pares alineados en DB: %d", len(pares))

    corpus_palabras: set[str] = set()
    for en, _es in pares:
        for palabra in en:
            if palabra.strip():
                corpus_palabras.add(palabra.strip().lower())

    entradas_db = votar_pares(pares)
    glosario.agregar_entradas(entradas_db, origen="db_seed")
    log.info("  Fuente DB: %d palabras únicas EN (voto por mayoría)", len(entradas_db))

    # ── Fuente 3 (opcional): extender con motor clásico ─────────────────────
    entradas_auto: dict[str, str] = {}
    if args.extender:
        motor = crear_motor(args.motor)
        faltantes = sorted(corpus_palabras - set(glosario.palabras))
        log.info("  Extendiendo con motor '%s': %d palabras faltantes",
                 args.motor, len(faltantes))
        for palabra in faltantes:
            # Cache por palabra: cada palabra se traduce UNA sola vez
            traducida = traducir_con_motor(motor, palabra)
            if traducida:
                entradas_auto[palabra] = traducida
        glosario.agregar_entradas(entradas_auto, origen="auto")
        log.info("  Fuente auto: %d palabras traducidas con motor", len(entradas_auto))

    # ── Reporte de cobertura ────────────────────────────────────────────────
    cobertura = glosario.cobertura(corpus_palabras)
    conteo = {
        origen: sum(1 for v in glosario.palabras.values() if v["origen"] == origen)
        for origen in ("manual", "db_seed", "auto")
    }
    print()
    log.info("  Total de entradas en glosario: %d", len(glosario.palabras))
    log.info("    manual:   %d", conteo["manual"])
    log.info("    db_seed:  %d", conteo["db_seed"])
    log.info("    auto:     %d", conteo["auto"])
    log.info("  Vocabulario del corpus: %d palabras únicas", len(corpus_palabras))
    log.info("  Cobertura del vocabulario: %.1f%% (%d/%d)",
             cobertura * 100,
             len(corpus_palabras & set(glosario.palabras)),
             len(corpus_palabras))

    if args.dry_run:
        print("\n  [DRY-RUN] No se guarda el glosario.")
        return

    glosario.guardar()
    log.info("  ✅ Glosario guardado en %s", salida)


if __name__ == "__main__":
    main()
