#!/usr/bin/env python3
"""
test_gradiente.py - Prueba del cálculo de gradientes con datos simulados.

Crea una BD de prueba con puntos GPS que simulan un viaje con subidas y
bajadas, ejecuta gradiente.py y verifica que los cálculos sean correctos.

Uso:
    python scripts/test_gradiente.py
"""

import math
import os
import sqlite3
import sys
import tempfile
import subprocess

# Para poder importar gradiente
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.gradiente import haversine, calcular_gradientes, GRADIENT_COLUMNS


# ---------------------------------------------------------------------------
# Datos de prueba: viaje simulado con 10 puntos
# (lat, lon, altitud, timestamp)
# ---------------------------------------------------------------------------

PUNTOS_PRUEBA = [
    (-34.6037, -58.3816, 10,   "2025-08-10T10:00:00"),
    (-34.6000, -58.3800, 25,   "2025-08-10T10:05:00"),
    (-34.5900, -58.3700, 50,   "2025-08-10T10:10:00"),
    (-34.5800, -58.3600, 30,   "2025-08-10T10:15:00"),
    (-34.5700, -58.3500, 45,   "2025-08-10T10:20:00"),
    (-34.5600, -58.3400, 20,   "2025-08-10T10:25:00"),
    (-34.5500, -58.3300, 60,   "2025-08-10T10:30:00"),
    (-34.5400, -58.3200, 80,   "2025-08-10T10:35:00"),
    (-34.5350, -58.3150, 100,  "2025-08-10T10:40:00"),
    (-34.5300, -58.3100, 90,   "2025-08-10T10:45:00"),
]

# Punto extra sin altitud (para probar manejo de NULL)
PUNTO_SIN_ALT = (-34.5200, -58.3000, None, "2025-08-10T10:50:00")


def crear_db_test(db_path: str):
    """Crea una base de datos con los puntos de prueba."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Crear tabla media
    conn.execute("""
        CREATE TABLE IF NOT EXISTS media (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            filename_original TEXT NOT NULL DEFAULT 'test.jpg',
            filepath_absoluto TEXT NOT NULL DEFAULT 'test.jpg',
            filepath_relativo TEXT NOT NULL DEFAULT 'test.jpg',
            type              TEXT NOT NULL DEFAULT 'image',
            file_hash         TEXT NOT NULL UNIQUE,
            timestamp_utc     TEXT,
            latitude          REAL,
            longitude         REAL,
            altitude          REAL,
            geolocation_source TEXT DEFAULT 'metadata'
        )
    """)

    # Insertar puntos de prueba
    for i, (lat, lon, alt, ts) in enumerate(PUNTOS_PRUEBA):
        conn.execute("""
            INSERT INTO media (filename_original, filepath_absoluto, filepath_relativo,
                               type, file_hash, timestamp_utc,
                               latitude, longitude, altitude, geolocation_source)
            VALUES (?, ?, ?, 'image', ?, ?, ?, ?, ?, 'metadata')
        """, (
            f"punto_{i+1:02d}.jpg",
            f"D:/test/punto_{i+1:02d}.jpg",
            f"punto_{i+1:02d}.jpg",
            f"hash_test_{i+1:02d}",
            ts,
            lat, lon, alt,
        ))

    # Insertar punto sin altitud
    lat, lon, alt, ts = PUNTO_SIN_ALT
    conn.execute("""
        INSERT INTO media (filename_original, filepath_absoluto, filepath_relativo,
                           type, file_hash, timestamp_utc,
                           latitude, longitude, altitude, geolocation_source)
        VALUES (?, ?, ?, 'image', ?, ?, ?, ?, ?, 'metadata')
    """, (
        "punto_sin_alt.jpg",
        "D:/test/punto_sin_alt.jpg",
        "punto_sin_alt.jpg",
        "hash_test_sin_alt",
        ts,
        lat, lon, alt,
    ))

    conn.commit()
    conn.close()


def verificar_resultados(conn: sqlite3.Connection):
    """Verifica que los calculos de gradiente sean correctos."""
    print("\n" + "=" * 70)
    print("  VERIFICACION DE RESULTADOS")
    print("=" * 70)

    rows = conn.execute("""
        SELECT id, latitude, longitude, altitude,
               distance_from_prev_m, elevation_gain_m, gradient_pct,
               cumul_distance_m, cumul_elevation_gain_m
        FROM media
        ORDER BY timestamp_utc ASC
    """).fetchall()

    errores = 0
    verificaciones = 0

    prev_lat = None
    prev_lon = None
    prev_alt = None
    expected_cumul_dist = 0.0
    expected_cumul_gain = 0.0

    for i, row in enumerate(rows):
        mid, lat, lon, alt, d_prev, elev_gain, grad, cumul_dist, cumul_gain = row

        print(f"\n  Punto {i+1} (#{mid}): ({lat:.4f}, {lon:.4f}) alt={alt}")

        if i == 0:
            # Primer punto: debe tener NULL en prev y 0 en acumulados
            verificaciones += 1
            if d_prev is not None or elev_gain is not None or grad is not None:
                print(f"    [ERROR] Primer punto deberia tener NULL en columnas previas")
                print(f"       distance_from_prev_m={d_prev}, elevation_gain_m={elev_gain}, gradient_pct={grad}")
                errores += 1
            else:
                print(f"    [OK] Primer punto: columnas previas NULL (correcto)")

            verificaciones += 1
            if cumul_dist != 0 or cumul_gain != 0:
                print(f"    [ERROR] Primer punto deberia tener cumul=0")
                print(f"       cumul_distance_m={cumul_dist}, cumul_elevation_gain_m={cumul_gain}")
                errores += 1
            else:
                print(f"    [OK] Acumulados inicializados en 0 (correcto)")

            prev_lat, prev_lon, prev_alt = lat, lon, alt
            continue

        # Verificar distancia Haversine
        expected_dist = haversine(prev_lat, prev_lon, lat, lon)
        expected_cumul_dist += expected_dist

        verificaciones += 1
        if d_prev is None or abs(d_prev - expected_dist) > 0.01:
            print(f"    [ERROR] Distancia incorrecta")
            print(f"       Esperada: {expected_dist:.2f}m, Obtenida: {d_prev}m")
            errores += 1
        else:
            print(f"    [OK] Distancia: {d_prev:.2f}m (correcto)")

        # Verificar elevacion
        if alt is not None and prev_alt is not None:
            expected_elev = alt - prev_alt
            if elev_gain is None or abs(elev_gain - expected_elev) > 0.01:
                print(f"    [ERROR] Elevacion incorrecta")
                print(f"       Esperada: {expected_elev:+.1f}m, Obtenida: {elev_gain}m")
                errores += 1
            else:
                print(f"    [OK] Elevacion: {elev_gain:+.1f}m (correcto)")

            # Verificar gradiente
            if expected_dist > 0:
                expected_grad = (expected_elev / expected_dist) * 100
                if grad is None or abs(grad - expected_grad) > 0.001:
                    print(f"    [ERROR] Gradiente incorrecto")
                    print(f"       Esperada: {expected_grad:.4f}%, Obtenida: {grad}%")
                    errores += 1
                else:
                    print(f"    [OK] Gradiente: {grad:.4f}% (correcto)")

            # Acumular ganancia
            if expected_elev > 0:
                expected_cumul_gain += expected_elev

        # Verificar acumulados
        verificaciones += 1
        if cumul_dist is None or abs(cumul_dist - expected_cumul_dist) > 0.02:
            print(f"    [ERROR] Distancia acumulada incorrecta")
            print(f"       Esperada: {expected_cumul_dist:.2f}m, Obtenida: {cumul_dist}m")
            errores += 1
        else:
            print(f"    [OK] Dist. acumulada: {cumul_dist:.2f}m (correcto)")

        verificaciones += 1
        if cumul_gain is None or abs(cumul_gain - expected_cumul_gain) > 0.02:
            print(f"    [ERROR] Ganancia acumulada incorrecta")
            print(f"       Esperada: {expected_cumul_gain:.2f}m, Obtenida: {cumul_gain}m")
            errores += 1
        else:
            print(f"    [OK] Ganancia acumulada: {cumul_gain:.2f}m (correcto)")

        prev_lat, prev_lon, prev_alt = lat, lon, alt

    # Ultimo punto (punto sin altitud) - verificar que gradiente sea NULL
    ultimo = rows[-1]
    print(f"\n  Ultimo punto (#{ultimo[0]}): sin altitud")
    if ultimo[3] is None and ultimo[6] is None:
        print(f"    [OK] Gradiente NULL porque falta altitud (correcto)")
    else:
        print(f"    [ERROR] Gradiente deberia ser NULL sin altitud")
        errores += 1

    print(f"\n  Verificaciones: {verificaciones}")
    print(f"  Errores: {errores}")
    if errores == 0:
        print("  [OK] TODAS LAS VERIFICACIONES PASARON")
    else:
        print(f"  [ERROR] HAY {errores} ERROR(ES)")

    return errores


def main():
    print("=" * 70)
    print("  PRUEBA DE CALCULO DE GRADIENTES")
    print("=" * 70)

    # Crear BD temporal
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        print(f"\n  Creando base de datos de prueba: {db_path}")
        crear_db_test(db_path)

        # Conectar y calcular gradientes
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        # Agregar columnas primero (como haría el script)
        for col_name, col_type in GRADIENT_COLUMNS:
            try:
                conn.execute(f"ALTER TABLE media ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass
        conn.commit()

        print(f"  Puntos insertados: {len(PUNTOS_PRUEBA) + 1}")

        # Calcular gradientes
        print(f"\n  Ejecutando calcular_gradientes()...")
        stats = calcular_gradientes(conn, verbose=True)
        print(f"\n  Estadísticas: {stats}")

        # Verificar resultados
        errores = verificar_resultados(conn)

        # Probar dry-run (no debería modificar nada)
        print(f"\n  --- Prueba de dry-run ---")
        conn2 = sqlite3.connect(db_path)
        conn2.execute("PRAGMA journal_mode=WAL")
        stats_dry = calcular_gradientes(conn2, dry_run=True, verbose=False)
        print(f"  Dry-run stats: {stats_dry}")
        conn2.close()

        conn.close()

        # Probar CLI invocation
        print(f"\n  --- Prueba de CLI con --dry-run --verbose ---")
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "gradiente.py"),
             "--db", db_path, "--dry-run", "--verbose"],
            capture_output=True, text=True, timeout=30,
        )
        print(f"  Código de salida: {result.returncode}")
        if result.returncode != 0:
            print(f"  stderr: {result.stderr[:500]}")
        else:
            # Mostrar últimas líneas del output
            lines = result.stdout.strip().split("\n")
            for line in lines[-6:]:
                print(f"  {line}")

        # Resumen final
        print(f"\n{'='*70}")
        if errores == 0:
            print("  [OK] PRUEBA COMPLETA: TODAS LAS VERIFICACIONES PASARON")
        else:
            print(f"  [ERROR] PRUEBA COMPLETA: {errores} ERROR(ES) ENCONTRADOS")
        print(f"{'='*70}")

        return 0 if errores == 0 else 1

    finally:
        # Limpiar
        try:
            os.unlink(db_path)
        except:
            pass


if __name__ == "__main__":
    sys.exit(main())
