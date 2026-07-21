#!/usr/bin/env python3
"""
Test unitario para db/migrate.py.

Verifica que el sistema de migraciones funcione correctamente:
- Detectar version 0 (sin versionar)
- Aplicar migraciones en orden
- Ser idempotente (no falla si se llama dos veces)
- Crear las tablas esperadas en cada version
"""

import os
import sys
import sqlite3

# Agregar la raiz del proyecto al path para poder importar db.migrate
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrate import schema_version, verificar_schema, SCHEMA_VERSION, _MIGRACIONES


def test_schema_version_0():
    """DB sin tabla config debe reportar version 0."""
    conn = sqlite3.connect(':memory:')
    assert schema_version(conn) == 0, "DB vacia deberia tener version 0"
    conn.close()
    print("  OK test_schema_version_0")


def test_schema_version_0_with_config():
    """DB con config pero sin schema_version debe reportar version 0."""
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    assert schema_version(conn) == 0, "Config sin schema_version deberia ser 0"
    conn.close()
    print("  OK test_schema_version_0_with_config")


def test_migration_from_0():
    """Migracion desde version 0 debe llegar a SCHEMA_VERSION."""
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    verificar_schema(conn)
    assert schema_version(conn) == SCHEMA_VERSION, \
        f"Esperaba version {SCHEMA_VERSION}, obtuve {schema_version(conn)}"
    conn.close()
    print(f"  OK test_migration_from_0 (v{SCHEMA_VERSION})")


def test_tables_created():
    """Migracion desde 0 debe crear todas las tablas."""
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    verificar_schema(conn)

    tables = set(row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ))

    # Tablas esperadas en todas las versiones
    if SCHEMA_VERSION >= 2:
        assert 'tracks' in tables, "Falta tabla tracks"
        assert 'waypoints' in tables, "Falta tabla waypoints"

    conn.close()
    print(f"  OK test_tables_created (v{SCHEMA_VERSION})")


def test_idempotent():
    """Llamar verificar_schema dos veces no debe fallar ni cambiar la version."""
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    verificar_schema(conn)
    v1 = schema_version(conn)
    verificar_schema(conn)
    v2 = schema_version(conn)
    assert v1 == v2, f"Version cambio de {v1} a {v2} en segunda llamada"
    conn.close()
    print("  OK test_idempotent")


def test_migration_order():
    """Las migraciones deben estar ordenadas por version ascendente."""
    versions = [v for v, _, _ in _MIGRACIONES]
    assert versions == sorted(versions), \
        f"Migraciones desordenadas: {versions}"
    # No debe haber saltos
    for i, v in enumerate(versions):
        expected = i + 1  # version 1 deberia estar en indice 0
        assert v == expected, \
            f"Migracion {v} en indice {i}, se esperaba version {expected}"
    print(f"  OK test_migration_order ({versions})")


def test_live_db_has_schema():
    """La DB real debe tener schema_version >= 1."""
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "db", "flujos.db"
    )
    if not os.path.isfile(db_path):
        print("  ⚠ test_live_db_has_schema: DB no encontrada, saltando")
        return

    conn = sqlite3.connect(db_path)
    v = schema_version(conn)
    assert v >= 1, f"DB real tiene version {v}, esperado >= 1"
    conn.close()
    print(f"  OK test_live_db_has_schema (v{v})")


def test_all_migrations_run():
    """Ejecutar todas las migraciones individualmente verifica que cada una funciona."""
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")

    for version, desc, sqls in _MIGRACIONES:
        print(f"  Probando migracion v{version}: {desc[:50]}...")
        for sql in sqls:
            if sql.strip():
                conn.execute(sql)
        # Actualizar version manual
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        conn.commit()

    conn.close()
    print("  OK test_all_migrations_run")


if __name__ == "__main__":
    print(f"\n=== Tests de migraciones (schema v{SCHEMA_VERSION}) ===\n")
    test_schema_version_0()
    test_schema_version_0_with_config()
    test_migration_from_0()
    test_tables_created()
    test_idempotent()
    test_migration_order()
    test_all_migrations_run()
    test_live_db_has_schema()
    print("\nOK Todos los tests pasaron.\n")
