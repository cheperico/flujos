#!/usr/bin/env python3
"""
Flujos - Punto de entrada unificado

Uso:
  python flujos.py                                  -> Menu interactivo
  python flujos.py --tui                            -> Menu interactivo
  python flujos.py ingest --root D:/Medios ...      -> Ingestar medios
  python flujos.py query --distinct author --count   -> Consultar DB
  python flujos.py relocate --new-root E:/Medios     -> Relocalizar archivos
  python flujos.py check-db                          -> Inspeccionar DB
  python flujos.py check-gps                         -> Revisar GPS en archivos
  python flujos.py --help | --ayuda | -h             -> Esta ayuda
"""

import argparse
import io
import os
import sqlite3
import subprocess
import sys

# Forzar UTF-8 en consola Windows para poder usar caracteres Unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Asegurar que scripts/ este en el path para imports relativos
_scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


# ── Ayuda ────────────────────────────────────────────────────────────────────

AYUDA = """
███████╗██╗     ██╗   ██╗     ██╗ ██████╗ ███████╗
██╔════╝██║     ██║   ██║     ██║██╔═══██╗██╔════╝
█████╗  ██║     ██║   ██║     ██║██║   ██║███████╗
██╔══╝  ██║     ██║   ██║██   ██║██║   ██║╚════██║
██║     ███████╗╚██████╔╝╚█████╔╝╚██████╔╝███████║
╚═╝     ╚══════╝ ╚═════╝  ╚════╝  ╚═════╝ ╚══════╝

  Buenos Aires -> Tucuman                           

USO:
  python flujos.py <comando> [opciones]

COMANDOS:

  ingest      Ingerir medios desde una carpeta a la base de datos.
              Ej: python flujos.py ingest --root D:/Medios --verbose

  query       Consultar y explorar la base de datos.
              Ej: python flujos.py query --distinct author --count

  relocate    Actualizar rutas absolutas cuando los archivos se mudan.
              Ej: python flujos.py relocate --new-root E:/Medios

  check-db    Mostrar todos los registros de la base de datos.

  check-gps   Revisar que archivos tienen GPS en el sistema de archivos.

  undo-ingest       Deshacer una ingesta por batch ID.

  backfill-end-time Calcular end_time para registros existentes
                    que no lo tengan (migracion).

  improve-db        Ejecutar pasos de mejora sobre la DB (colores,
                    keywords, transcripcion, keypoints, timestamps, GPS).

  reset-db          Hace backup de la DB actual y crea una nueva
                    desde cero (schema limpio).

  --tui       Menu interactivo (tambien sin argumentos).

  --help, --ayuda, -h   Esta ayuda.

Si no se pasa ningun comando, arranca el menu interactivo.
"""


# ── TUI ──────────────────────────────────────────────────────────────────────

def limpiar_pantalla():
    os.system("cls" if sys.platform == "win32" else "clear")


def pausa():
    input("\n  Presiona Enter para continuar...")


def mostrar_bienvenida():
    limpiar_pantalla()
    print("███████╗██╗     ██╗   ██╗     ██╗ ██████╗ ███████╗")
    print("██╔════╝██║     ██║   ██║     ██║██╔═══██╗██╔════╝")
    print("█████╗  ██║     ██║   ██║     ██║██║   ██║███████╗")
    print("██╔══╝  ██║     ██║   ██║██   ██║██║   ██║╚════██║")
    print("██║     ███████╗╚██████╔╝╚█████╔╝╚██████╔╝███████║")
    print("╚═╝     ╚══════╝ ╚═════╝  ╚════╝  ╚═════╝ ╚══════╝")
    print()
    print("  Buenos Aires -> Tucuman")
    print()


def leer_db() -> str:
    """Resuelve la ruta a la DB por defecto."""
    return os.path.join(os.path.dirname(__file__), "db", "flujos.db")


def resumen_db(conn) -> str:
    """Devuelve un resumen con los totales de la DB."""
    total = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
    imagenes = conn.execute("SELECT COUNT(*) FROM media WHERE type='image'").fetchone()[0]
    videos = conn.execute("SELECT COUNT(*) FROM media WHERE type='video'").fetchone()[0]
    audios = conn.execute("SELECT COUNT(*) FROM media WHERE type='audio'").fetchone()[0]
    textos = conn.execute("SELECT COUNT(*) FROM media WHERE type='text'").fetchone()[0]
    otros = total - imagenes - videos - audios - textos
    con_gps = conn.execute("SELECT COUNT(*) FROM media WHERE latitude IS NOT NULL").fetchone()[0]
    sin_gps = conn.execute("SELECT COUNT(*) FROM media WHERE latitude IS NULL").fetchone()[0]
    con_color = conn.execute("SELECT COUNT(*) FROM media WHERE color_1_hex IS NOT NULL").fetchone()[0]
    sin_color = total - con_color
    autores = conn.execute("SELECT COUNT(DISTINCT author) FROM media WHERE author IS NOT NULL").fetchone()[0]
    return (
        f"  Total:      {total:>6d}\n"
        f"  Imagenes:   {imagenes:>6d}\n"
        f"  Videos:     {videos:>6d}\n"
        f"  Audios:     {audios:>6d}\n"
        f"  Textos:     {textos:>6d}\n"
        f"  Otros:      {otros:>6d}\n"
        f"  Con GPS:    {con_gps:>6d}\n"
        f"  Sin GPS:    {sin_gps:>6d}\n"
        f"  Con color:  {con_color:>6d}\n"
        f"  Sin color:  {sin_color:>6d}\n"
        f"  Autores:    {autores:>6d}"
    )


def opcion_ingresar():
    """Menu para configurar y ejecutar ingesta."""
    limpiar_pantalla()
    print("=== INGESTAR MEDIOS ===\n")

    root = input("  Carpeta raiz a escanear: ").strip()
    if not root:
        print("  Cancelado.")
        pausa()
        return
    if not os.path.isdir(root):
        print(f"  Error: la carpeta '{root}' no existe.")
        pausa()
        return

    verbose = input("  ?Modo verbose? (s/N): ").strip().lower() == "s"
    dry_run = input("  ?Solo previsualizar (dry-run)? (s/N): ").strip().lower() == "s"

    print("\n  Ejecutando ingesta...\n")

    from scripts import ingest
    ingest.main(["--root", root] +
                (["--verbose"] if verbose else []) +
                (["--dry-run"] if dry_run else []))

    pausa()


def opcion_consultar():
    """Menu para consultas comunes."""
    limpiar_pantalla()
    print("=== CONSULTAR BASE DE DATOS ===\n")

    from scripts import query

    print("  1) Ver resumen de la DB")
    print("  2) Listar tipos de medio")
    print("  3) Listar autores")
    print("  4) Listar carpetas")
    print("  5) Listar colores")
    print("  6) Buscar texto")
    print("  7) Consulta libre (escribo el flag)")
    print("  8) Inspeccion general de DB")
    print("  9) Revisar GPS")
    print("  0) Volver\n")

    opc = input("  Opcion: ").strip()

    if opc == "1":
        query.main(["--columns"])
    elif opc == "2":
        query.main(["--distinct", "type", "--count"])
    elif opc == "3":
        query.main(["--distinct", "author", "--count"])
    elif opc == "4":
        query.main(["--distinct", "carpeta", "--count"])
    elif opc == "5":
        query.main(["--distinct", "color_1_name_basic", "--count", "--where",
                     "color_1_name_basic IS NOT NULL"])
    elif opc == "6":
        texto = input("  Texto a buscar: ").strip()
        if texto:
            query.main(["--search", texto])
    elif opc == "7":
        flags = input("  Flags (ej: --distinct type --count): ").strip()
        if flags:
            query.main(flags.split())
    elif opc == "8":
        opcion_check_db()
        return
    elif opc == "9":
        opcion_check_gps()
        return
    elif opc == "0":
        return

    pausa()


def opcion_relocalizar():
    """Menu para relocalizar medios."""
    limpiar_pantalla()
    print("=== RELOCALIZAR MEDIOS ===\n")

    # Mostrar root actual
    db_path = leer_db()
    if os.path.isfile(db_path):
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute("SELECT value FROM config WHERE key = 'ingest_root'")
            row = cur.fetchone()
            if row:
                print(f"  Raiz actual en DB: {row[0]}")
        except sqlite3.OperationalError:
            pass
        conn.close()

    new_root = input("  Nueva raiz: ").strip()
    if not new_root:
        print("  Cancelado.")
        pausa()
        return

    if not os.path.isdir(new_root):
        r = input(f"  La carpeta '{new_root}' no existe. ?Continuar de todos modos? (s/N): ").strip().lower()
        if r != "s":
            print("  Cancelado.")
            pausa()
            return

    dry_run = input("  ?Solo previsualizar (dry-run)? (s/N): ").strip().lower() == "s"

    from scripts import relocate
    relocate.main(["--new-root", new_root] + (["--dry-run"] if dry_run else []))

    pausa()


def opcion_check_db():
    limpiar_pantalla()
    print("=== INSPECCION DE BASE DE DATOS ===\n")
    db_path = leer_db()
    if not os.path.isfile(db_path):
        print("  No se encuentra la base de datos.")
        pausa()
        return

    conn = sqlite3.connect(db_path)
    try:
        print(resumen_db(conn))
    except sqlite3.OperationalError as e:
        print(f"  Error: {e}")
    conn.close()

    print("\n  Ultimos registros:")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT id, filename_original, type, author, timestamp_utc FROM media ORDER BY id DESC LIMIT 5"
        )
        for row in cursor:
            print(f"  #{row[0]:>6d} [{row[2]:6s}] {row[1]} - {row[3] or '?'}")
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"  Error: {e}")

    pausa()


def opcion_check_gps():
    limpiar_pantalla()
    print("=== REVISAR GPS EN ARCHIVOS ===\n")
    db_path = leer_db()
    if not os.path.isfile(db_path):
        print("  No se encuentra la base de datos.")
        pausa()
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT filepath_absoluto FROM media WHERE type='image' AND latitude IS NULL ORDER BY RANDOM() LIMIT 5"
        )
        sin_gps = cursor.fetchall()
        if sin_gps:
            print("  Muestras de imagenes sin GPS en DB (5 al azar):")
            print()
            for (fp,) in sin_gps:
                print(f"    {fp}")
        else:
            print("  No hay imagenes sin GPS en la DB.")
    except sqlite3.OperationalError as e:
        print(f"  Error: {e}")
    conn.close()

    print()
    print("  Para un analisis completo, usa: python scripts/check_gps.py")
    pausa()


def opcion_undo_ingest():
    """Menu para deshacer una ingesta por batch_id."""
    limpiar_pantalla()
    print("=== DESHACER INGESTA ===\n")

    db_path = leer_db()
    if not os.path.isfile(db_path):
        print("  No se encuentra la base de datos.")
        pausa()
        return

    conn = sqlite3.connect(db_path)
    try:
        # Listar batches disponibles
        cursor = conn.execute(
            "SELECT ingest_batch_id, MIN(ingested_at), COUNT(*) FROM media "
            "WHERE ingest_batch_id IS NOT NULL "
            "GROUP BY ingest_batch_id ORDER BY MIN(ingested_at) DESC"
        )
        batches = cursor.fetchall()
        if not batches:
            print("  No hay ingestas con batch_id registradas.")
            conn.close()
            pausa()
            return

        print("  Ingresos disponibles:\n")
        for bid, ts, cnt in batches:
            root = conn.execute(
                "SELECT value FROM config WHERE key = 'current_ingest_batch'"
            ).fetchone()
            current = "  (actual)" if root and str(bid) == root[0] else ""
            print(f"  Batch #{bid}  -  {ts}  -  {cnt} medios{current}")
        print()

        bid_str = input("  Batch ID a deshacer (0 para cancelar): ").strip()
        if bid_str == "0" or not bid_str:
            print("  Cancelado.")
            conn.close()
            pausa()
            return

        bid = int(bid_str)
        confirm = input(f"  Esto borrara TODOS los medios del batch #{bid}. Confirmar? (s/N): ").strip().lower()
        if confirm != "s":
            print("  Cancelado.")
            conn.close()
            pausa()
            return

        deleted = conn.execute("DELETE FROM media WHERE ingest_batch_id = ?", (bid,)).rowcount
        conn.commit()
        print(f"  Eliminados {deleted} medios del batch #{bid}.")

    except (sqlite3.OperationalError, ValueError) as e:
        print(f"  Error: {e}")
    finally:
        conn.close()
    pausa()


def opcion_improve_db():
    """Menu para ejecutar pasos de mejora sobre la DB."""
    limpiar_pantalla()
    print("=== MEJORAR BASE DE DATOS ===\n")
    print("  1) Todos los pasos (skip)")
    print("  2) Colores dominantes")
    print("  3) Keywords con IA")
    print("  4) Descripciones con IA")
    print("  5) Transcripcion (audios/videos)")
    print("  6) Keypoints desde transcripciones")
    print("  7) Inferir timestamps")
    print("  8) Inferir GPS")
    print("  9) Elegir pasos manualmente")
    print("  0) Volver\n")

    from scripts import improve_db

    opc = input("  Opcion: ").strip()

    if opc == "1":
        improve_db.main([])
    elif opc == "2":
        improve_db.main(["--steps", "colors"])
    elif opc == "3":
        improve_db.main(["--steps", "keywords"])
    elif opc == "4":
        improve_db.main(["--steps", "descriptions"])
    elif opc == "5":
        improve_db.main(["--steps", "transcribe"])
    elif opc == "6":
        improve_db.main(["--steps", "keypoints"])
    elif opc == "7":
        improve_db.main(["--steps", "timestamps"])
    elif opc == "8":
        improve_db.main(["--steps", "gps"])
    elif opc == "9":
        pasos = input("  Pasos (separados por coma, ej: colors,keywords): ").strip()
        if pasos:
            improve_db.main(["--steps", pasos])
    elif opc == "0":
        return

    pausa()


def opcion_ayuda():
    """Submenu de ayuda con detalle por comando."""
    while True:
        limpiar_pantalla()
        print("============ AYUDA ============\n")
        print("  Elija un comando para ver su ayuda detallada:\n")
        print("  1) Ayuda general")
        print("  2) ingest  - Ingestion de medios")
        print("  3) query   - Consultas a la base de datos")
        print("  4) relocate - Relocalizar medios")
        print("  5) improve-db - Mejorar base de datos")
        print("  6) check-db / check-gps")
        print("  0) Volver\n")

        opc = input("  Opcion: ").strip()

        if opc == "1":
            limpiar_pantalla()
            print(AYUDA)
            pausa()
        elif opc == "2":
            import ingest
            ingest.main(["--help"])
            pausa()
        elif opc == "3":
            import query
            query.main(["--help"])
            pausa()
        elif opc == "4":
            import relocate
            relocate.main(["--help"])
            pausa()
        elif opc == "5":
            limpiar_pantalla()
            print("============ IMPROVE-DB ============\n")
            print("  Ejecuta pasos de mejora sobre la base de datos.")
            print("  Uso: python flujos.py improve-db [--steps X,Y] [--mode skip|update|replace]\n")
            print("  Pasos disponibles:")
            print("    colors        Extraer colores dominantes")
            print("    keywords      Etiquetar con IA")
            print("    descriptions  Describir con IA")
            print("    transcribe    Transcribir audios/videos")
            print("    keypoints     Poblar keypoints desde transcripciones")
            print("    timestamps    Inferir timestamps faltantes")
            print("    gps           Inferir GPS")
            print()
            print("  --list  para listar todos los pasos.")
            pausa()
        elif opc == "6":
            limpiar_pantalla()
            print("============ CHECK-DB ============\n")
            print("  Inspecciona todos los registros de la base de datos.")
            print("  Uso: python flujos.py check-db\n")
            print("============ CHECK-GPS ============\n")
            print("  Revisa que archivos tienen GPS en el sistema de archivos.")
            print("  Uso: python flujos.py check-gps\n")
            print("  Para un analisis completo: python scripts/check_gps.py")
            pausa()
        elif opc == "0":
            break
        else:
            print("  Opcion invalida.")
            pausa()


def tui():
    """Menu interactivo principal."""
    while True:
        mostrar_bienvenida()

        db_path = leer_db()
        if os.path.isfile(db_path):
            conn = sqlite3.connect(db_path)
            try:
                print(resumen_db(conn) + "\n")
            except sqlite3.OperationalError:
                print("  (Base de datos vacia o sin schema)\n")
            conn.close()
        else:
            print("  (Base de datos no encontrada - ejecuta 'ingest' primero)\n")

        print("  1) Ingestionar medios")
        print("  2) Deshacer ingesta")
        print("  3) Mejorar base de datos")
        print("  4) Consultar base de datos")
        print("  5) Relocalizar medios")
        print("  6) Reset DB (backup + limpiar)")
        print("  7) Ayuda")
        print("  0) Salir\n")

        opc = input("  Opcion: ").strip()

        if opc == "1">
            opcion_ingresar()
        elif opc == "2">
            opcion_undo_ingest()
        elif opc == "3">
            opcion_improve_db()
        elif opc == "4">
            opcion_consultar()
        elif opc == "5">
            opcion_relocalizar()
        elif opc == "6">
            opcion_reset_db()
        elif opc == "7">
            opcion_ayuda()
        elif opc == "0":
            limpiar_pantalla()
            print("  Chau.")
            break
        else:
            print("  Opcion invalida.")
            pausa()


# ── Backfill end_time ─────────────────────────────────────────────────────────

def opcion_backfill_end_time():
    """Calcula end_time para registros existentes que no lo tienen."""
    db_path = leer_db()
    if not os.path.isfile(db_path):
        print("  No se encuentra la base de datos.")
        return

    conn = sqlite3.connect(db_path)
    try:
        # Primero verificar si la columna existe
        cols = [row[1] for row in conn.execute("PRAGMA table_info(media)")]
        if "end_time" not in cols:
            print("  La columna end_time no existe en la DB.")
            print("  Ejecutá primero una ingesta o el schema.sql.")
            return

        # Contar cuántos faltan
        pendientes = conn.execute(
            "SELECT COUNT(*) FROM media WHERE end_time IS NULL AND timestamp_utc IS NOT NULL"
        ).fetchone()[0]

        if pendientes == 0:
            print("  Todos los registros ya tienen end_time.")
            return

        print(f"  Calculando end_time para {pendientes} registros...")

        # Punto: end_time = timestamp_utc
        updated_punto = conn.execute("""
            UPDATE media
            SET end_time = timestamp_utc
            WHERE end_time IS NULL
              AND timestamp_utc IS NOT NULL
              AND duration_secs IS NULL
        """).rowcount
        print(f"    Puntos (fotos/textos): {updated_punto} actualizados.")

        # Segmento: end_time = timestamp_utc + duration_secs
        updated_seg = conn.execute("""
            UPDATE media
            SET end_time = datetime(timestamp_utc, '+' || CAST(duration_secs AS TEXT) || ' seconds')
            WHERE end_time IS NULL
              AND timestamp_utc IS NOT NULL
              AND duration_secs IS NOT NULL
        """).rowcount
        print(f"    Segmentos (videos/audios): {updated_seg} actualizados.")

        conn.commit()
        print(f"\n  Total actualizados: {updated_punto + updated_seg}")

    except sqlite3.OperationalError as e:
        print(f"  Error: {e}")
    finally:
        conn.close()


# ── Reset DB ─────────────────────────────────────────────────────────────────

def opcion_reset_db():
    """Hace backup de la DB actual y crea una nueva desde cero."""
    db_path = leer_db()
    db_dir = os.path.dirname(db_path)

    if not os.path.isfile(db_path):
        print("  No hay base de datos que respaldar.")
        r = input("  ?Crear una DB vacia igual? (s/N): ").strip().lower()
        if r != "s":
            print("  Cancelado.")
            return
        print("  Creando DB vacia...")
        from scripts.ingest import init_db
        init_db(db_path)
        print(f"  DB creada: {db_path}")
        return

    # Contar registros
    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
    except sqlite3.OperationalError:
        total = 0
    conn.close()

    print(f"\n  Base de datos actual: {db_path}")
    print(f"  Registros en media:   {total}")

    # Confirmar
    r = input("\n  ?Hacer backup y borrar? (s/N): ").strip().lower()
    if r != "s":
        print("  Cancelado.")
        return

    # Backup
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"flujos_backup_{ts}.db"
    backup_path = os.path.join(db_dir, backup_name)

    import shutil
    try:
        shutil.copy2(db_path, backup_path)
        print(f"  Backup creado: {backup_name}")
    except Exception as e:
        print(f"  Error creando backup: {e}")
        r = input("  ?Continuar igual? (s/N): ").strip().lower()
        if r != "s":
            return

    # Borrar y crear nueva
    try:
        os.remove(db_path)
        print("  DB anterior eliminada.")
    except Exception as e:
        print(f"  Error eliminando DB: {e}")
        return

    from scripts.ingest import init_db
    init_db(db_path)
    print(f"  Nueva DB creada: {db_path}")
    print("  Lista para ingestar.")


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ("--tui", "--interactive")):
        tui()
        return

    if sys.argv[1] in ("--help", "--ayuda", "-h"):
        print(AYUDA)
        return

    comando = sys.argv[1]
    resto = sys.argv[2:]

    if comando == "ingest":
        from scripts import ingest
        ingest.main(resto)

    elif comando == "query":
        from scripts import query
        query.main(resto)

    elif comando == "relocate":
        from scripts import relocate
        relocate.main(resto)

    elif comando == "check-db":
        opcion_check_db()

    elif comando == "check-gps":
        opcion_check_gps()

    elif comando in ("undo-ingest", "undo"):
        opcion_undo_ingest()

    elif comando in ("backfill-end-time", "backfill"):
        opcion_backfill_end_time()

    elif comando == "improve-db":
        from scripts import improve_db
        improve_db.main(resto)

    elif comando in ("reset-db", "reset"):
        opcion_reset_db()

    else:
        print(f"Comando desconocido: {comando}")
        print(AYUDA)
        sys.exit(1)


if __name__ == "__main__":
    main()
