#!/usr/bin/env python3
"""
test_motor_loop.py — Tests del núcleo matemático del motor de loop (`loop_engine`).

Cubre la matemática de `docs/motor_loop.md` §3:
    - Segmentos horarios (calcular_segmentos) con el arco nocturno 16→13.
    - Fracción de arco (hora_en_fraccion) para caso normal y nocturno.
    - Posición de un medio (posicionar_medio / posicionar_hora).
    - armado de spec (armar_spec) y descarte cuando cae fuera del arco.
    - Normalización: menos de 2 horas → todas las horas.

Nota importante sobre cobertura temporal: cuando las horas elegidas incluyen
un segmento que CRUZA medianoche (ej. 16→13), ese segmento abarca de por sí
todo el día ([16,24) ∪ [0,13]), por lo que ningún medio queda descartado por
hora salvo los sin timestamp. Para verificar el descarte fuera del arco se usa
un set de horas sin cruce (ej. [10,16]) que deja un hueco real.

Uso:
    python scripts/ai_media/test_motor_loop.py
    (usa solo asserts, no requiere pytest)
"""

import os
import sys

# La consola de Windows por defecto usa cp1252, que no puede codificar la
# flecha '→' (U+2192) ni '✔' usadas en los mensajes. Reconfiguramos stdout a
# UTF-8 con fallback 'replace' para que el test corra en cualquier terminal
# sin lanzar UnicodeEncodeError (mismo fix que en limpiar_tandas.imprimir_reporte).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass  # Python < 3.7 o stdout sin reconfigure

# Directorios en sys.path: proyecto raíz y scripts/ai_media/ (para importar
# loop_engine directamente. Sin disparar el __init__.py del paquete, que
# arrastraría ollama_client y demás dependencias pesadas).
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_DIR)))
sys.path.insert(0, _DIR)

import loop_engine  # noqa: E402

PASS = 0
FAIL = 0


def _assert(condicion: bool, mensaje: str) -> None:
    """Registra un assert simple con conteo global de pass/fail."""
    global PASS, FAIL
    if condicion:
        PASS += 1
        print(f"  ok   {mensaje}")
    else:
        FAIL += 1
        print(f"  FAIL {mensaje}")


def _casi(a: float, b: float, tol: float = 1e-6) -> bool:
    """Comparación de flotantes con tolerancia."""
    return abs(a - b) <= tol


def test_calcular_segmentos() -> None:
    print("\n[test_calcular_segmentos]")
    segs = loop_engine.calcular_segmentos([7, 16, 13, 18], 300)
    _assert(len(segs) == 3, f"N=4 → 3 segmentos (got {len(segs)})")

    # Seg 0: 7→16, arco 9
    _assert(segs[0]["from"] == 7 and segs[0]["to"] == 16, "seg0 from=7 to=16")
    _assert(_casi(segs[0]["arco_horas"], 9.0), "seg0 arco=9 (16-7)")
    _assert(_casi(segs[0]["t_start"], 0.0), "seg0 t_start=0")
    _assert(_casi(segs[0]["duracion_seg"], 100.0), "seg0 dur=100")

    # Seg 1: 16→13, arco 21 (cruza medianoche)
    _assert(segs[1]["from"] == 16 and segs[1]["to"] == 13, "seg1 from=16 to=13")
    _assert(_casi(segs[1]["arco_horas"], 21.0), "seg1 arco=21 (cruza noche)")
    _assert(_casi(segs[1]["t_start"], 100.0), "seg1 t_start=100")

    # Seg 2: 13→18, arco 5
    _assert(segs[2]["from"] == 13 and segs[2]["to"] == 18, "seg2 from=13 to=18")
    _assert(_casi(segs[2]["arco_horas"], 5.0), "seg2 arco=5")
    _assert(_casi(segs[2]["t_start"], 200.0), "seg2 t_start=200")
    _assert(_casi(segs[2]["t_end"], 300.0), "seg2 t_end=300")

    # Validación
    for caso in (([7], 300), ([7, 16], 0), ([7, 16], -5)):
        try:
            loop_engine.calcular_segmentos(caso[0], caso[1])
            _assert(False, f"debería lanzar ValueError para {caso}")
        except ValueError:
            _assert(True, f"ValueError para {caso}")


def test_hora_en_fraccion() -> None:
    print("\n[test_hora_en_fraccion]")
    segs = loop_engine.calcular_segmentos([7, 16, 13, 18], 300)
    seg_diurno = segs[0]     # 7→16
    seg_nocturno = segs[1]   # 16→13 (cruza medianoche)

    # Caso normal: hora 8 en 7→16
    f = loop_engine.hora_en_fraccion(8.0, seg_diurno)
    _assert(f is not None and _casi(f, 1 / 9), f"h=8 en 7→16 → 1/9 (got {f})")

    # Fuera del arco diurno (7→16)
    _assert(loop_engine.hora_en_fraccion(5.0, seg_diurno) is None, "h=5 fuera de 7→16")
    _assert(loop_engine.hora_en_fraccion(20.0, seg_diurno) is None, "h=20 fuera de 7→16")

    # Caso nocturno: h=22 en 16→13 → (22-16)/21 = 6/21
    f_noct = loop_engine.hora_en_fraccion(22.0, seg_nocturno)
    _assert(f_noct is not None and _casi(f_noct, 6 / 21, 1e-6),
            f"h=22 en 16→13 → 6/21 (got {f_noct})")

    # Caso nocturno madrugada: h=3 → (3+24-16)/21 = 11/21
    f_madrugada = loop_engine.hora_en_fraccion(3.0, seg_nocturno)
    _assert(f_madrugada is not None and _casi(f_madrugada, 11 / 21, 1e-6),
            f"h=3 en 16→13 → 11/21 (got {f_madrugada})")

    # La madrugada NO cae en el segmento diurno 7→16
    _assert(loop_engine.hora_en_fraccion(3.0, seg_diurno) is None,
            "h=3 fuera del segmento diurno")

    # Límites
    _assert(loop_engine.hora_en_fraccion(7.0, seg_diurno) is not None, "h=7 borde inicio")
    _assert(_casi(loop_engine.hora_en_fraccion(16.0, seg_diurno) or -1, 1.0),
            "h=16 borde fin de 7→16 → frac 1.0")


def test_posicionar_medio() -> None:
    print("\n[test_posicionar_medio]")
    segs = loop_engine.calcular_segmentos([7, 16, 13, 18], 300)

    # h=8 cae en seg0 (7→16), t_loop = 0 + (1/9)*100 = 100/9 ≈ 11.111
    pos = loop_engine.posicionar_medio(8.0, segs)
    _assert(pos is not None and pos["seg_i"] == 0, "h=8 → seg_i 0")
    _assert(_casi(pos["t_loop"], 100.0 / 9, 1e-3),
            f"h=8 → t_loop≈11.111 (got {pos['t_loop']})")

    # medianoche (0:30) → cae SOLO en el segmento nocturno 16→13
    pos_noc = loop_engine.posicionar_medio(0.5, segs)
    _assert(pos_noc is not None and pos_noc["seg_i"] == 1,
            f"h=0.5 → seg nocturno (i=1) (got {pos_noc})")

    # posicionar_hora == posicionar_medio (alias)
    a = loop_engine.posicionar_medio(8.0, segs)
    b = loop_engine.posicionar_hora(8.0, segs)
    _assert(a == b, "posicionar_medio == posicionar_hora")


def test_descarte_fuera_de_arco() -> None:
    print("\n[test_descarte_fuera_de_arco]")
    # Sin segmento que cruce medianoche: [10,16] cubre SOLO 10..16.
    # Cualquier medio fuera de ese rango debe descartarse.
    segs_sin_hueco = loop_engine.calcular_segmentos([10, 16], 300)
    _assert(loop_engine.posicionar_hora(12.0, segs_sin_hueco) is not None,
            "h=12 dentro de 10→16 → posicionado")
    _assert(loop_engine.posicionar_hora(8.0, segs_sin_hueco) is None,
            "h=8 antes de 10 → descartado")
    _assert(loop_engine.posicionar_hora(20.0, segs_sin_hueco) is None,
            "h=20 después de 16 → descartado")


def test_armar_spec() -> None:
    print("\n[test_armar_spec]")
    # Con [7,16,13,18] el cruce 16→13 cubre todo el día → solo se descarta el
    # medio SIN hora.
    horas = [7, 16, 13, 18]
    loop = 300
    medios = [
        {"media_id": 1, "tipo": "image", "hora": 8.0},     # diurno matinal
        {"media_id": 2, "tipo": "image", "hora": 0.5},    # madrugada → arco nocturno
        {"media_id": 3, "tipo": "image", "hora": 14.0},   # tarde
        {"media_id": 4, "tipo": "image", "hora": 5.0},    # madrugada → arco nocturno
        {"media_id": 5, "tipo": "image"},                 # SIN hora → descartado
    ]
    chiches = [
        {"hora": 12.0, "texto": "Es el mediodía"},   # cae en seg0
        {"hora": 2.0, "texto": "Es la noche"},       # cae en seg1 (noche)
        {"hora": 20.0, "texto": "Salió el sol"},     # cae en seg1 (noche)
    ]
    spec = loop_engine.armar_spec(horas, loop, medios, chiches)

    _assert(_casi(spec["loop_secs"], 300), "loop_secs pasó a la spec")
    _assert(len(spec["segmentos"]) == 3, "spec tiene 3 segmentos")

    # Medios: el 5 (sin hora) NO aparece; el resto sí.
    ids = [m["media_id"] for m in spec["medios"]]
    _assert(1 in ids and 2 in ids and 3 in ids and 4 in ids,
            "medios 1,2,3,4 incluidos (cubren todo el día)")
    _assert(5 not in ids, "medio 5 (sin hora) descartado")

    for m in spec["medios"]:
        _assert(m.get("t_loop") is not None and 0 <= m["t_loop"] < 300,
                f"t_loop de media {m['media_id']} en [0,300)")

    # Chiches: los 3 caen dentro.
    _assert(len(spec["chiches"]) == 3,
            f"3 chiches posicionados (got {len(spec['chiches'])})")
    for c in spec["chiches"]:
        _assert(c["tipo"] == "chiche" and 0 <= c["t"] < 300, f"chiche '{c['texto']}' ok")

    # Chiche de madrugada (hora 2, "Es la noche") → arco nocturno [100,200]
    noche = [c for c in spec["chiches"] if c["texto"] == "Es la noche"]
    _assert(noche and 100.0 <= noche[0]["t"] <= 200.0,
            f"'Es la noche' cae en [100,200] (got {noche[0]['t'] if noche else None})")

    # Descarte real: horas [10,16] sin cruce → medio en 8:00 NO aparece.
    segs_min = loop_engine.calcular_segmentos([10, 16], 300)
    spec_min = loop_engine.armar_spec(
        [10, 16], 300,
        [{"media_id": 10, "tipo": "image", "hora": 8.0},
         {"media_id": 11, "tipo": "image", "hora": 12.0}],
        [],
    )
    ids_min = [m["media_id"] for m in spec_min["medios"]]
    _assert(11 in ids_min and 10 not in ids_min,
            "con [10,16]: media 12h incluido, media 8h descartado")


def test_todas_las_horas() -> None:
    print("\n[test_todas_las_horas]")
    horas = list(range(24))
    segs = loop_engine.calcular_segmentos(horas, 300)
    _assert(len(segs) == 23, f"24 horas → 23 segmentos (got {len(segs)})")
    _assert(_casi(segs[0]["duracion_seg"], 300 / 23), "duración de cada segmento")
    _assert(loop_engine.posicionar_medio(0.0, segs) is not None,
            "h=0 cae en el primer segmento (00→01)")


def main() -> None:
    global PASS, FAIL
    print("Testing loop_engine ...")
    test_calcular_segmentos()
    test_hora_en_fraccion()
    test_posicionar_medio()
    test_descarte_fuera_de_arco()
    test_armar_spec()
    test_todas_las_horas()

    print("\n──────────────────────────────")
    print(f"  Resultado: {PASS} ok | {FAIL} fail")
    if FAIL:
        sys.exit(1)
    print("  ✔ Todos los tests pasaron.")


if __name__ == "__main__":
    main()