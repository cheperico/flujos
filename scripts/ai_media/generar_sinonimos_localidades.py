#!/usr/bin/env python3
"""
generar_sinonimos_localidades.py — Propone la sección "localidades" de SINONIMOS.

Propone entradas para el diccionario SINONIMOS de refinar_keywords.py a partir
de FUENTES CONFIABLES: los nombres oficiales de localidad escritos por la API
Georef en `media.provincia`, `media.departamento`, `media.municipio`, más los
`waypoints.name` del GPX.

Algoritmo: cruza los tags observados en `--clave` (default ia_keywords) contra
los nombres oficiales por 3 categorías:
  A) EXACTO      → norm(tag) == norm(oficial)
  B) CERCANO     → levenshtein(norm(tag), norm(oficial)) <= 2 y concentrado
  C) TOKEN-SUBSET→ todos los tokens del tag están en el oficial (oficial con
                   más de 1 token) y concentrado
y emite un bloque SINONIMOS propuesto + un reporte de revisión. Un humano
revisa la salida y pega las entradas aprobadas en SINONIMOS.

SCRIPT READ-ONLY: nunca escribe la DB, nunca edita refinar_keywords.py.

Uso:
    python scripts/ai_media/generar_sinonimos_localidades.py
    python scripts/ai_media/generar_sinonimos_localidades.py --clave ia_keywords_transcripcion
    python scripts/ai_media/generar_sinonimos_localidades.py --db otra.db --verbose
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from typing import Any

log = logging.getLogger(__name__)

# Permitir ejecución standalone: agregar raíz del proyecto al path
# (mismo patrón que refinar_keywords.py; sin esto los imports de db.util
# y scripts.ai_media fallan con ModuleNotFoundError al correr directo).
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )

from db.util import abrir, resolver_db  # noqa: E402
from scripts.ai_media.refinar_keywords import SINONIMOS  # noqa: E402

# ── Palabras comunes que NO son nombres propios ──────────────────────────────
# Ensucia el fuzzy matching (p. ej. "monumento" ≈ "Monumento a la identidad
# nacional"). Matching se hace sobre la norma (minúsculas sin acentos), así
# que las entradas están escritas sin acentos.
COMUNES: set[str] = {
    "sol", "luna", "mar", "rio", "agua", "camino", "ciudad", "rojo", "roja",
    "roca", "oro", "hoja", "ropa", "tallo", "asfalto", "pasto", "palo",
    "saco", "alto", "gallo", "halo", "seto", "todo", "son", "morado",
    "momento", "borde", "senales", "seco", "cruz", "monumento", "complejo",
    "policia", "club", "aire", "radio", "rayo", "tirar", "horno", "lugar",
    "loro", "lujo", "antiguo", "colina", "barrera", "unido", "reunion",
    "soledad", "colonialismo", "identidad", "nacional", "pasarela", "laguna",
    "inri", "casa", "calle", "plaza", "parque", "puente", "iglesia",
    "escuela", "hospital", "estacion", "ruta", "viaje", "gente", "dia",
    "noche", "tarde", "manana", "bien", "buen", "buena", "tiempo", "vida",
    "mundo", "parte", "ano", "anos", "vez", "algo", "nada", "cada", "mas",
    "menos", "ser", "estar", "tener", "hacer", "decir", "ver", "mirar",
    "puede", "pueden", "hay", "fue", "era", "sin", "sobre", "entre",
    "desde", "hasta", "durante", "cuando", "donde", "como", "cual",
    "porque", "tumba", "senal", "cartel",
}


def norm(s: str) -> str:
    """Normaliza para comparación: minúsculas + sin acentos + espacios colapsados."""
    s = s.strip().lower()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_acentos)


def levenshtein(a: str, b: str) -> int:
    """Distancia de edición Levenshtein (DP simple).

    Devuelve 99 si la diferencia de longitud supera 3 (no vale la pena el DP).
    """
    if abs(len(a) - len(b)) > 3:
        return 99
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            costo = 0 if ca == cb else 1
            actual.append(min(prev[j] + 1, actual[j - 1] + 1, prev[j - 1] + costo))
        prev = actual
    return prev[-1]


def concentrada(tag: str, provs_oficial: set[str],
                provs_por_tag: dict[str, set[str]]) -> bool:
    """True si el tag aparece concentrado en UNA sola provincia que es
    subconjunto de las provincias del oficial.

    Si el oficial no tiene provincias registradas (ej: waypoint), devuelve
    True (no se puede desmentir la concentración).
    """
    if not provs_oficial:
        return True
    provs_tag = provs_por_tag.get(tag, set())
    if len(provs_tag) != 1:
        return False
    return provs_tag <= provs_oficial


def es_token_subset(norm_t: str, norm_o: str) -> bool:
    """True si todos los tokens de t están en o y o tiene más de 1 token."""
    tokens_t = set(norm_t.split())
    tokens_o = set(norm_o.split())
    return len(tokens_o) > 1 and bool(tokens_t) and tokens_t <= tokens_o


def _oficiales(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Colecta los nombres oficiales (Georef + waypoints) con tipo y provincias."""
    oficiales: list[dict[str, Any]] = []

    # Municipios y departamentos: agrupar provincias por nombre oficial
    for col in ("municipio", "departamento"):
        filas = conn.execute(
            f"SELECT {col} AS nombre, provincia FROM media "
            f"WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchall()
        provs_por_nombre: dict[str, set[str]] = {}
        for nombre, prov in filas:
            if prov:
                provs_por_nombre.setdefault(nombre, set()).add(prov)
        for nombre, provs in provs_por_nombre.items():
            oficiales.append({"nombre": nombre, "tipo": col, "provincias": provs})

    # Provincias
    filas = conn.execute(
        "SELECT DISTINCT provincia FROM media "
        "WHERE provincia IS NOT NULL AND provincia != ''"
    ).fetchall()
    for (prov,) in filas:
        oficiales.append({"nombre": prov, "tipo": "provincia", "provincias": {prov}})

    # Waypoints del GPX (sin provincia asociada)
    filas = conn.execute(
        "SELECT DISTINCT name FROM waypoints WHERE name IS NOT NULL AND name != ''"
    ).fetchall()
    for (name,) in filas:
        oficiales.append({"nombre": name, "tipo": "waypoint", "provincias": set()})

    for of in oficiales:
        of["norm"] = norm(of["nombre"])
    return oficiales


def _tags(conn: sqlite3.Connection, clave: str
          ) -> tuple[Counter, dict[str, list[tuple[str, str, str]]]]:
    """Lee los tags de la clave dada.

    Devuelve (counter de tags en minúsculas, contextos por tag) donde cada
    contexto es (provincia, municipio, departamento) del medio que lo lleva.
    El parsing soporta JSON array o texto separado por comas (mismo enfoque
    que obtener_keywords_db de refinar_keywords.py).
    """
    # Contexto geográfico por medio
    ctx_media: dict[int, tuple[str, str, str]] = {}
    filas = conn.execute(
        "SELECT id, provincia, municipio, departamento FROM media"
    ).fetchall()
    for mid, prov, muni, dep in filas:
        ctx_media[mid] = (prov or "", muni or "", dep or "")

    counter: Counter = Counter()
    contextos: dict[str, list[tuple[str, str, str]]] = {}
    filas = conn.execute(
        "SELECT media_id, value FROM media_metadata WHERE key = ?", (clave,)
    ).fetchall()
    for mid, valor in filas:
        if not valor:
            continue
        try:
            lista = json.loads(valor)
            if isinstance(lista, list):
                partes = [str(x) for x in lista]
            else:
                raise ValueError
        except (json.JSONDecodeError, TypeError, ValueError):
            partes = [p.strip().strip("'\"").rstrip(".,;") for p in valor.split(",") if p.strip()]
        for p in partes:
            p = p.strip().lower()
            if not p:
                continue
            counter[p] += 1
            contextos.setdefault(p, []).append(ctx_media.get(mid, ("", "", "")))
    return counter, contextos


def _provincias_por_tag(contextos: dict[str, list[tuple[str, str, str]]]
                        ) -> dict[str, set[str]]:
    """Provincias distintas (no vacías) de los medios que llevan cada tag."""
    resultado: dict[str, set[str]] = {}
    for tag, ctx_list in contextos.items():
        provs = {prov for prov, _, _ in ctx_list if prov}
        resultado[tag] = provs
    return resultado


def _mejor_coincidencia(tag: str, norm_t: str,
                        oficiales: list[dict[str, Any]],
                        provs_por_tag: dict[str, set[str]]
                        ) -> tuple[str, dict[str, Any], int] | None:
    """Devuelve (categoría, oficial, dist) con la mejor coincidencia o None.

    Preferencia: A (exacto) > B (cercano) > C (token-subset). En B se elige el
    de menor distancia; en C se queda con el primero (oficial con más tokens
    no suma).
    """
    # A) exacto
    for of in oficiales:
        if norm_t == of["norm"]:
            return ("A", of, 0)
    # B) cercano por distancia <= 2 y concentrado
    mejor_b: tuple[str, dict[str, Any], int] | None = None
    for of in oficiales:
        dist = levenshtein(norm_t, of["norm"])
        if dist <= 2 and concentrada(tag, of["provincias"], provs_por_tag):
            if mejor_b is None or dist < mejor_b[2]:
                mejor_b = ("B", of, dist)
    if mejor_b is not None:
        return mejor_b
    # C) token-subset concentrado
    for of in oficiales:
        if (es_token_subset(norm_t, of["norm"])
                and concentrada(tag, of["provincias"], provs_por_tag)):
            return ("C", of, len(of["norm"].split()))
    return None


def _ya_en_sinonimos(tag: str, canonico: str) -> bool:
    """True si el tag o el canónico ya están contemplados en SINONIMOS."""
    tag_l = tag.lower()
    canon_l = canonico.lower()
    if canon_l in SINONIMOS:
        return True
    for canon, variantes in SINONIMOS.items():
        if tag_l == canon.lower():
            return True
        if tag_l in [v.lower() for v in variantes]:
            return True
    return False


def _formatear_ctx(contextos: list[tuple[str, str, str]], maxi: int = 4) -> str:
    """Formatea los contextos (prov, muni, dep) de un tag para el reporte."""
    vistos: set[tuple[str, str]] = set()
    partes: list[str] = []
    for prov, muni, dep in contextos:
        clave = (prov, muni)
        if clave in vistos:
            continue
        vistos.add(clave)
        trozo = ", ".join(x for x in (prov, muni) if x)
        partes.append(trozo or "(sin geo)")
        if len(partes) >= maxi:
            break
    return " | ".join(partes)


def _reportar(conn: sqlite3.Connection, clave: str) -> None:
    """Ejecuta el análisis completo e imprime el reporte en stdout."""
    oficiales = _oficiales(conn)
    counter, contextos = _tags(conn, clave)
    provs_por_tag = _provincias_por_tag(contextos)

    n_oficiales = len(oficiales)
    n_tags = len(counter)
    n_freq1 = sum(1 for f in counter.values() if f == 1)

    print("\n  === GENERADOR DE SINÓNIMOS DE LOCALIDADES ===")
    print(f"  Oficiales (Georef + waypoints): {n_oficiales}  "
          f"(municipios: {sum(1 for o in oficiales if o['tipo'] == 'municipio')}, "
          f"departamentos: {sum(1 for o in oficiales if o['tipo'] == 'departamento')}, "
          f"provincias: {sum(1 for o in oficiales if o['tipo'] == 'provincia')}, "
          f"waypoints: {sum(1 for o in oficiales if o['tipo'] == 'waypoint')})")
    print(f"  Tags distintos ({clave}): {n_tags} | con frecuencia 1: {n_freq1}")
    print()

    # ── Emparejar tags contra oficiales ─────────────────────────────────────
    secciones: dict[str, list[tuple[str, int, dict[str, Any], int]]] = {
        "A": [], "B": [], "C": [],
    }
    candidatos_set: set[str] = set()
    for tag, freq in counter.items():
        norm_t = norm(tag)
        if len(norm_t) < 3 or norm_t in COMUNES:
            continue
        coincidencia = _mejor_coincidencia(tag, norm_t, oficiales, provs_por_tag)
        if coincidencia is None:
            continue
        cat, of, dist = coincidencia
        secciones[cat].append((tag, freq, of, dist))
        candidatos_set.add(tag)

    # ── Secciones A / B / C ─────────────────────────────────────────────────
    etiquetas = {"A": "EXACTOS", "B": "CERCANOS", "C": "TOKEN-SUBSET"}
    for cat in ("A", "B", "C"):
        fila = sorted(secciones[cat], key=lambda x: -x[1])
        print(f"  --- {cat}) {etiquetas[cat]} ({len(fila)}) ---")
        for tag, freq, of, dist in fila:
            ctx = _formatear_ctx(contextos.get(tag, []))
            if cat == "C":
                dist_txt = f"subset/{dist} tokens"
            else:
                dist_txt = f"dist {dist}"
            print(f"    {tag} (freq {freq}) -> '{of['nombre']}' "
                  f"[{of['tipo']}] ({dist_txt}) | ctx: {ctx}")
        print()

    # ── EXCLUIDOS (auditoría) ───────────────────────────────────────────────
    excluidos: list[tuple[str, int, dict[str, Any], int, str]] = []
    for tag, freq in counter.items():
        if tag in candidatos_set:
            continue
        norm_t = norm(tag)
        if len(norm_t) < 3:
            continue
        # ¿Algún oficial a distancia <= 2?
        cercanos = [(levenshtein(norm_t, of["norm"]), of) for of in oficiales]
        dist_min, of_cerca = min(cercanos, key=lambda x: x[0])
        if dist_min > 2:
            continue
        razones: list[str] = []
        if norm_t in COMUNES:
            razones.append("comun")
        if not concentrada(tag, of_cerca["provincias"], provs_por_tag):
            razones.append("no concentrada")
        if razones:
            excluidos.append((tag, freq, of_cerca, dist_min, " + ".join(razones)))
    excluidos.sort(key=lambda x: -x[1])
    print(f"  --- EXCLUIDOS (auditoría, máx 30) — cerca de un oficial pero "
          f"filtrados ({len(excluidos)}) ---")
    for tag, freq, of, dist, razon in excluidos[:30]:
        print(f"    {tag} (freq {freq}) -> cerca de '{of['nombre']}' "
              f"[{of['tipo']}] (dist {dist}) — {razon}")
    print()

    # ── AMBIGUOS (token-subset contra provincia) ────────────────────────────
    ambiguos = [
        (tag, freq, of, dist) for tag, freq, of, dist in secciones["C"]
        if of["tipo"] == "provincia"
    ]
    ambiguos.sort(key=lambda x: -x[1])
    print(f"  --- AMBIGUOS (decisión manual, {len(ambiguos)}) — token-subset "
          f"contra provincia ---")
    for tag, freq, of, dist in ambiguos:
        ctx = _formatear_ctx(contextos.get(tag, []))
        print(f"    {tag} (freq {freq}) -> '{of['nombre']}' [{of['tipo']}] "
              f"(nombre propio vs nombre de pila) | ctx: {ctx}")
    print()

    # ── VERIFICADOS (el tag ES el nombre oficial) ───────────────────────────
    verificados = sorted(secciones["A"], key=lambda x: -x[1])
    print(f"  --- VERIFICADOS (ya canónicos, {len(verificados)}) — el tag ES "
          f"el nombre oficial, no hay nada que unificar ---")
    for tag, freq, of, _ in verificados:
        ctx = _formatear_ctx(contextos.get(tag, []))
        print(f"    {tag} (freq {freq}) = '{of['nombre']}' [{of['tipo']}] | ctx: {ctx}")
    print()

    # ── PROPUESTA SINONIMOS ─────────────────────────────────────────────────
    # Candidatos B y C, sin ambiguos, sin los ya contemplados en SINONIMOS.
    propuesta: dict[str, set[str]] = {}
    propuesta_tipos: dict[str, str] = {}
    for cat in ("B", "C"):
        for tag, freq, of, dist in secciones[cat]:
            if of["tipo"] == "provincia":
                continue  # ambiguos, decisión manual
            canonico = of["nombre"].lower()
            if _ya_en_sinonimos(tag, canonico):
                continue
            propuesta.setdefault(canonico, set()).add(tag)
            propuesta_tipos[canonico] = of["tipo"]
    print(f"  --- PROPUESTA SINONIMOS (pegar en refinar_keywords.py, "
          f"{len(propuesta)} entradas) ---")
    if propuesta:
        print("  # Generado por generar_sinonimos_localidades.py")
        for canonico in sorted(propuesta):
            variantes = sorted(propuesta[canonico])
            tipo = propuesta_tipos[canonico]
            print(f'    "{canonico}": [{", ".join(repr(v) for v in variantes)}],'
                  f"  # {tipo}")
    else:
        print("    (sin propuestas nuevas: todo lo relevante ya está en SINONIMOS)")
    print()

    print("  Script read-only: no escribió la DB. Revisar y pegar la PROPUESTA "
          "en SINONIMOS de refinar_keywords.py, luego re-correr "
          "refinar_keywords --mode update.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Propone la sección 'localidades' de SINONIMOS cruzando "
                    "los nombres oficiales (Georef + waypoints GPX) contra los "
                    "tags de media_metadata. Read-only: no escribe nada.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default=None, help="Ruta a la base de datos (default: db/flujos.db)")
    parser.add_argument("--clave", default="ia_keywords",
                        help="Clave de media_metadata con los tags (default: ia_keywords). "
                             "Ej: ia_keywords_transcripcion")
    parser.add_argument("--verbose", action="store_true", help="Log detallado")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    db_path = resolver_db(args.db)
    if not os.path.isfile(db_path):
        print(f"  ERROR: No existe la DB: {db_path}")
        sys.exit(1)

    conn = abrir(db_path)
    try:
        _reportar(conn, args.clave)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
