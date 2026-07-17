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
  python flujos.py geocode                           -> Geocodificar coordenadas GPS a localidad/provincia
  python flujos.py geocode --limit 100               -> Con limite de registros
  python flujos.py gradient                          -> Calcular gradientes de ruta (pendiente/esfuerzo fisico entre puntos GPS)
  python flujos.py gradient --dry-run                -> Previsualizar gradientes sin escribir en DB
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

  geocode     Geocodificar coordenadas GPS (lat,lon) a provincia/localidad
              usando la API Georef Argentina (batch).
              Ej: python flujos.py geocode --limit 100

  gradient    Calcular gradientes de ruta entre puntos GPS consecutivos.
              Calcula distancia, pendiente y esfuerzo fisico acumulado.
              Ej: python flujos.py gradient --dry-run --verbose

  undo-ingest       Deshacer una ingesta por batch ID.

  backfill-end-time Calcular end_time para registros existentes
                    que no lo tengan (migracion).

  improve-db        Ejecutar pasos de mejora sobre la DB (colores,
                    keywords, transcripcion, keypoints, timestamps, GPS).

  reset-db          Hace backup de la DB actual y crea una nueva
                     desde cero (schema limpio).

  backup-db         Solo backup (sin borrar): copia la DB actual con timestamp.

  restore-db        Restaura la DB desde un backup previo.

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


def leer_db(db_path: str | None = None) -> str:
    """Resuelve la ruta a la DB. Si se pasa una, la usa; si no, la default."""
    if db_path:
        return os.path.abspath(db_path)
    return os.path.join(os.path.dirname(__file__), "db", "flujos.db")


def resumen_db(conn) -> str:
    """Devuelve un resumen con los totales de la DB."""
    total = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
    imagenes = conn.execute("SELECT COUNT(*) FROM media WHERE type='image'").fetchone()[0]
    videos = conn.execute("SELECT COUNT(*) FROM media WHERE type='video'").fetchone()[0]
    audios = conn.execute("SELECT COUNT(*) FROM media WHERE type='audio'").fetchone()[0]
    textos = conn.execute("SELECT COUNT(*) FROM media WHERE type='text'").fetchone()[0]
    otros = total - imagenes - videos - audios - textos
    return (
        f"  Total:      {total:>6d}\n"
        f"  Imagenes:   {imagenes:>6d}\n"
        f"  Videos:     {videos:>6d}\n"
        f"  Audios:     {audios:>6d}\n"
        f"  Textos:     {textos:>6d}\n"
        f"  Otros:      {otros:>6d}"
    )


def opcion_preparar(db_path: str | None = None):
    """Menu: Preparar medios (pre-ingesta)."""
    while True:
        limpiar_pantalla()
        print("=== PREPARAR MEDIOS ===\n")
        print("  1) Limpieza de tandas")
        print("  0) Volver\n")

        opc = input("  Opcion: ").strip()
        if opc == "1":
            from scripts import limpiar_tandas
            ruta = input("  Carpeta a limpiar: ").strip()
            if ruta and os.path.isdir(ruta):
                dry_run = input("  ?Solo previsualizar (s/N): ").strip().lower() == "s"
                limpiar_tandas.main(["--carpeta", ruta] + (["--dry-run"] if dry_run else []))
            elif ruta:
                print("  Carpeta no encontrada.")
            pausa()
        elif opc == "0":
            break
        else:
            print("  Opcion invalida.")
            pausa()


def opcion_ingesta(db_path: str | None = None):
    """Menu: Ingesta de medios."""
    while True:
        limpiar_pantalla()
        print("=== INGESTA ===\n")
        print("  1) Hacer ingesta")
        print("  2) Deshacer ingesta")
        print("  0) Volver\n")

        opc = input("  Opcion: ").strip()
        if opc == "1":
            limpiar_pantalla()
            print("=== HACER INGESTA ===\n")
            root = input("  Carpeta raiz a escanear: ").strip()
            if not root:
                print("  Cancelado.")
                pausa()
                continue
            if not os.path.isdir(root):
                print(f"  Error: la carpeta '{root}' no existe.")
                pausa()
                continue

            verbose = input("  ?Modo verbose? (s/N): ").strip().lower() == "s"
            dry_run = input("  ?Solo previsualizar (dry-run)? (s/N): ").strip().lower() == "s"
            custom_db = input(f"  ?Usar otra DB? (default: {leer_db(db_path)}) [Enter para default]: ").strip()

            print("\n  Ejecutando ingesta...\n")
            from scripts import ingest
            args = ["--root", root]
            if verbose:
                args.append("--verbose")
            if dry_run:
                args.append("--dry-run")
            if custom_db:
                args.extend(["--db", custom_db])
            elif db_path:
                args.extend(["--db", db_path])
            ingest.main(args)
            pausa()

        elif opc == "2":
            opcion_undo_ingest(db_path)

        elif opc == "0":
            break
        else:
            print("  Opcion invalida.")
            pausa()


def opcion_listar(db_path: str | None = None):
    """Submenu: listar distintos aspectos de la DB."""
    from scripts import query
    db_flag = ["--db", db_path] if db_path else []

    while True:
        limpiar_pantalla()
        print("=== LISTAR ===\n")
        print("  1) Tipos de medio")
        print("  2) Autores")
        print("  3) Carpetas")
        print("  4) Colores basicos")
        print("  5) Provincias (geocode)")
        print("  6) Buscar texto")
        print("  7) Consulta libre (flags directos a query.py)")
        print("  8) Revisar GPS en archivos")
        print("  9) Detalle completo de registros (todas las columnas)")
        print("  0) Volver\n")

        opc = input("  Opcion: ").strip()
        if opc == "1":
            query.main(["--distinct", "type", "--count"] + db_flag)
        elif opc == "2":
            query.main(["--distinct", "author", "--count"] + db_flag)
        elif opc == "3":
            query.main(["--distinct", "carpeta", "--count"] + db_flag)
        elif opc == "4":
            query.main(["--distinct", "color_1_name_basic", "--count", "--where",
                        "color_1_name_basic IS NOT NULL"] + db_flag)
        elif opc == "5":
            query.main(["--distinct", "provincia", "--count", "--where",
                        "provincia IS NOT NULL"] + db_flag)
        elif opc == "6":
            texto = input("  Texto a buscar: ").strip()
            if texto:
                query.main(["--search", texto] + db_flag)
        elif opc == "7":
            flags = input("  Flags (ej: --distinct type --count): ").strip()
            if flags:
                query.main(flags.split())
        elif opc == "8":
            opcion_check_gps(db_path)
        elif opc == "9":
            opcion_detalle_db(db_path)
        elif opc == "0":
            break
        else:
            print("  Opcion invalida.")
        if opc not in ("9", "8", "0"):
            pausa()


def opcion_consultar(db_path: str | None = None):
    """Menu: Consultar base de datos."""
    while True:
        limpiar_pantalla()
        print("=== CONSULTAR BASE DE DATOS ===\n")
        print("  1) Ver resumen de la DB")
        print("  2) Listar...")
        print("  0) Volver\n")

        opc = input("  Opcion: ").strip()
        if opc == "1":
            opcion_check_db(db_path)
        elif opc == "2":
            opcion_listar(db_path)
        elif opc == "0":
            break
        else:
            print("  Opcion invalida.")
            pausa()


def opcion_relocalizar(db_path: str | None = None):
    """Menu para relocalizar medios."""
    limpiar_pantalla()
    print("=== RELOCALIZAR MEDIOS ===\n")

    db_path = leer_db(db_path)
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


def opcion_check_db(db_path: str | None = None):
    limpiar_pantalla()
    print("=== INSPECCION DE BASE DE DATOS ===\n")
    db_path = leer_db(db_path)
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


def opcion_exportar(db_path: str | None = None):
    """Menu: Exportar DB a medios (relocalizar)."""
    while True:
        limpiar_pantalla()
        print("=== EXPORTAR DB A MEDIOS ===\n")
        print("  Actualiza las rutas cuando los archivos se mudan de ubicacion.\n")
        print("  1) Relocalizar medios (cambiar raiz)")
        print("  0) Volver\n")

        opc = input("  Opcion: ").strip()
        if opc == "1":
            opcion_relocalizar(db_path)
        elif opc == "0":
            break
        else:
            print("  Opcion invalida.")
            pausa()


def opcion_gradient():
    """Menu para calcular gradientes de ruta entre puntos GPS consecutivos."""
    limpiar_pantalla()
    print("=== CALCULAR GRADIENTES DE RUTA ===\n")

    print("  1) Calcular gradientes")
    print("  2) Previsualizar (dry-run)")
    print("  3) Previsualizar con detalle (dry-run + verbose)")
    print("  0) Volver\n")

    opc = input("  Opcion: ").strip()

    from scripts import gradiente

    if opc == "1":
        modo = _preguntar_modo()
        args = ["--db", leer_db()]
        if modo != "skip":
            args += ["--mode", modo]
        gradiente.main(args)
    elif opc == "2":
        gradiente.main(["--db", leer_db(), "--dry-run"])
    elif opc == "3":
        gradiente.main(["--db", leer_db(), "--dry-run", "--verbose"])
    elif opc == "0":
        return

    pausa()


def opcion_check_gps(db_path: str | None = None):
    limpiar_pantalla()
    print("=== REVISAR GPS EN ARCHIVOS ===\n")
    db_path = leer_db(db_path)
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
    print("  Para un analisis completo, usa: python flujos.py check-gps --db ruta")
    pausa()


def opcion_detalle_db(db_path: str | None = None):
    """Muestra todas las columnas de los ultimos registros."""
    limpiar_pantalla()
    print("=== DETALLE COMPLETO DE REGISTROS ===\n")

    db_path = leer_db(db_path)
    if not os.path.isfile(db_path):
        print("  No se encuentra la base de datos.")
        pausa()
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Obtener nombres de columnas
        cols = [row[1] for row in conn.execute("PRAGMA table_info(media)")]
        print(f"  {len(cols)} columnas en media\n")

        # Pedir cantidad
        try:
            n = int(input("  Cantidad de registros a mostrar (default 10): ").strip() or "10")
        except ValueError:
            n = 10

        cursor = conn.execute(
            f"SELECT * FROM media ORDER BY id DESC LIMIT {n}"
        )
        rows = cursor.fetchall()

        if not rows:
            print("  No hay registros.")
            conn.close()
            pausa()
            return

        for row in rows:
            print(f"  ── #{row['id']} ──")
            for col in cols:
                val = row[col]
                if val is not None:
                    val_str = str(val)
                    if len(val_str) > 60:
                        val_str = val_str[:57] + "..."
                    print(f"    {col:<25s} {val_str}")
            print()

        print(f"  {len(rows)} registros mostrados.")

    except sqlite3.OperationalError as e:
        print(f"  Error: {e}")
    finally:
        conn.close()

    pausa()


def opcion_undo_ingest(db_path: str | None = None):
    """Menu para deshacer una ingesta por batch_id."""
    limpiar_pantalla()
    print("=== DESHACER INGESTA ===\n")

    db_path = leer_db(db_path)
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

        # Obtener batch actual una vez, no por cada fila
        current_batch = conn.execute(
            "SELECT value FROM config WHERE key = 'current_ingest_batch'"
        ).fetchone()
        current_batch_str = current_batch[0] if current_batch else ""

        print("  Ingresos disponibles:\n")
        for bid, ts, cnt in batches:
            current = "  (actual)" if str(bid) == current_batch_str else ""
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


def _verificar_ollama(modelos: list[str] | None = None) -> bool:
    """Verifica que Ollama esté corriendo y (opcional) que los modelos estén disponibles.
    
    Args:
        modelos: lista de nombres de modelo a verificar (ej: ["qwen2.5vl:7b"])
    
    Returns:
        True si Ollama está disponible (y los modelos si se pidieron), False si no.
    """
    import urllib.request
    import json

    try:
        req = urllib.request.Request("http://localhost:11434/api/tags",
                                     method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        print("  ⚠️  Ollama NO está corriendo.")
        print("     Los pasos de IA (keywords, descripciones, transcripcion)")
        print("     requieren Ollama con los modelos necesarios.")
        print("     Ejecutá: ollama serve  (o abrí Ollama Desktop)\n")
        return False

    if modelos:
        disponibles = [m["name"] for m in data.get("models", [])]
        faltan = [m for m in modelos if m not in disponibles]
        if faltan:
            print(f"  ⚠️  Modelos faltantes en Ollama: {', '.join(faltan)}")
            print("     Ejecutá: ollama pull " + " ".join(faltan))
            print()
            return False

    return True


_PASOS_IA = {"keywords", "descriptions", "transcribe"}


def _ejecutar_improve_db(pasos: str | None = None, modo: str = "skip"):
    """Ejecuta improve_db, verificando Ollama si el/los paso(s) lo requieren."""
    from scripts import improve_db

    # Determinar si los pasos requieren IA
    pasos_set = set()
    if pasos:
        pasos_set = set(p.strip() for p in pasos.split(","))
    else:
        # Sin --steps, improve_db corre todos los pasos
        pasos_set = {"keywords", "descriptions", "transcribe", "colors",
                     "keypoints", "timestamps", "gps"}

    if pasos_set & _PASOS_IA:
        if not _verificar_ollama():
            r = input("  ?Continuar de todos modos? (s/N): ").strip().lower()
            if r != "s":
                print("  Cancelado.")
                return

    args = []
    if pasos:
        args += ["--steps", pasos]
    if modo != "skip":
        args += ["--mode", modo]
    improve_db.main(args)


def _preguntar_modo():
    """Pregunta modo de ejecución y lo devuelve como string."""
    print("  Modo:")
    print("    s) Skip — solo pendientes (default)")
    print("    u) Update — actualizar existentes")
    print("    r) Replace — borrar y regenerar")
    m = input("  Modo (s/u/r) [s]: ").strip().lower()
    if m == "u":
        return "update"
    elif m == "r":
        return "replace"
    return "skip"


def opcion_improve_db():
    """Menu para ejecutar pasos de mejora sobre la DB (2 partes)."""
    parte = 1
    while True:
        limpiar_pantalla()
        print("=== MEJORAR BASE DE DATOS ===\n")

        if parte == 1:
            print("  -- Pasos de IA y color --\n")
            print("  1) Todos los pasos (skip)")
            print("  2) Elegir pasos manualmente")
            print("  3) Colores dominantes")
            print("  4) Keywords con IA")
            print("  5) Descripcion con IA")
            print("  6) Keywords + Descripcion (pasada unica, mas lenta)")
            print("  7) Transcripcion (audios/videos)")
            print("  8) Keypoints de transcripciones")
            print("  9) Siguiente >>")
            print("  0) Volver\n")
        else:
            print("  -- Pasos de inferencia y enriquecimiento --\n")
            print("  1) Inferir timestamps")
            print("  2) Inferir GPS")
            print("  3) Localizacion (provincia, municipio, localidad)")
            print("  4) Condiciones climaticas")
            print("  5) Dia de la semana")
            print("  6) Embeddings")
            print("  9) << Anterior")
            print("  0) Volver\n")

        opc = input("  Opcion: ").strip()

        if parte == 1:
            if opc == "1":
                _ejecutar_improve_db()
                pausa()
            elif opc == "2":
                pasos = input("  Pasos (separados por coma, ej: colors,keywords): ").strip()
                if pasos:
                    modo = _preguntar_modo()
                    _ejecutar_improve_db(pasos=pasos, modo=modo)
                pausa()
            elif opc == "3":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="colors", modo=modo)
                pausa()
            elif opc == "4":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="keywords", modo=modo)
                pausa()
            elif opc == "5":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="descriptions", modo=modo)
                pausa()
            elif opc == "6":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="keywords,descriptions", modo=modo)
                pausa()
            elif opc == "7":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="transcribe", modo=modo)
                pausa()
            elif opc == "8":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="keypoints", modo=modo)
                pausa()
            elif opc == "9":
                parte = 2
            elif opc == "0":
                break
            else:
                print("  Opcion invalida.")
                pausa()

        else:  # parte == 2
            if opc == "1":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="timestamps", modo=modo)
                pausa()
            elif opc == "2":
                modo = _preguntar_modo()
                _ejecutar_improve_db(pasos="gps", modo=modo)
                pausa()
            elif opc == "3":
                opcion_geocode()
            elif opc == "4":
                opcion_weather()
            elif opc == "5":
                opcion_dia_semana()
            elif opc == "6":
                opcion_embeddings()
            elif opc == "9":
                parte = 1
            elif opc == "0":
                break
            else:
                print("  Opcion invalida.")
                pausa()


def opcion_weather():
    """Submenu: condiciones climaticas desde Open-Meteo."""
    limpiar_pantalla()
    print("=== CONDICIONES CLIMATICAS ===\n")

    print("  1) Obtener datos climaticos")
    print("  2) Previsualizar (dry-run)")
    print("  0) Volver\n")

    opc = input("  Opcion: ").strip()

    import subprocess
    script = os.path.join(os.path.dirname(__file__), "scripts", "fetch_weather.py")
    db_flag = ["--db", leer_db()]

    if opc == "1":
        modo = _preguntar_modo()
        if modo != "skip":
            subprocess.run([sys.executable, script] + db_flag + ["--mode", modo])
        else:
            subprocess.run([sys.executable, script] + db_flag)
    elif opc == "2":
        subprocess.run([sys.executable, script] + db_flag + ["--dry-run"])
    elif opc == "0":
        return

    pausa()


def opcion_dia_semana():
    """Submenu: calcular día de la semana de cada medio."""
    limpiar_pantalla()
    print("=== DIA DE LA SEMANA ===\n")

    print("  1) Calcular dia de la semana")
    print("  2) Previsualizar (dry-run)")
    print("  0) Volver\n")

    opc = input("  Opcion: ").strip()

    import subprocess
    script = os.path.join(os.path.dirname(__file__), "scripts", "dia_semana.py")
    db_flag = ["--db", leer_db()]

    if opc == "1":
        modo = _preguntar_modo()
        if modo != "skip":
            subprocess.run([sys.executable, script] + db_flag + ["--mode", modo])
        else:
            subprocess.run([sys.executable, script] + db_flag)
    elif opc == "2":
        subprocess.run([sys.executable, script] + db_flag + ["--dry-run"])
    elif opc == "0":
        return

    pausa()


def opcion_embeddings():
    """Submenu: generar embeddings vectoriales para búsqueda semántica."""
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "scripts", "ai_media", "generate_embeddings.py")
    db_flag = ["--db", leer_db()]

    limpiar_pantalla()
    print("=== EMBEDDINGS ===\n")

    print("  1) Generar embeddings (solo pendientes)")
    print("  2) Previsualizar (dry-run)")
    print("  3) Ver modelos Ollama instalados")
    print("  0) Volver\n")

    opc = input("  Opcion: ").strip()

    if opc == "1":
        subprocess.run([sys.executable, script] + db_flag)
    elif opc == "2":
        subprocess.run([sys.executable, script] + db_flag + ["--dry-run"])
    elif opc == "3":
        subprocess.run([sys.executable, script] + ["--list-models"])
    elif opc == "0":
        return

    pausa()


def opcion_geocode():
    """Menu para geocodificación inversa de coordenadas GPS."""
    limpiar_pantalla()
    print("=== LOCALIZACION (Geocodificar GPS) ===\n")

    print("  1) Ejecutar geocodificacion")
    print("  2) Previsualizar (dry-run)")
    print("  0) Volver\n")

    opc = input("  Opcion: ").strip()

    from scripts import geocode

    if opc == "1":
        modo = _preguntar_modo()
        args = ["--db", leer_db()]
        if modo != "skip":
            args += ["--mode", modo]
        geocode.main(args)
    elif opc == "2":
        geocode.main(["--db", leer_db(), "--dry-run"])
    elif opc == "0":
        return

    pausa()


def opcion_mantenimiento(db_path: str | None = None):
    """Menu: mantenimiento general de la DB (backup, restore, exportar, gradientes, etc)."""
    while True:
        limpiar_pantalla()
        print("=== MANTENIMIENTO DB ===\n")
        print("  1) Relocalizar medios (cambio de raiz)")
        print("  2) Calcular gradientes de ruta")
        print("  3) Backfill end_time")
        print("  4) Backup DB (solo backup, sin borrar)")
        print("  5) Restore DB desde backup")
        print("  6) Resetear DB (backup + limpiar)")
        print("  0) Volver\n")

        opc = input("  Opcion: ").strip()

        if opc == "1":
            opcion_relocalizar(db_path)
        elif opc == "2":
            opcion_gradient()
        elif opc == "3":
            opcion_backfill_end_time(db_path)
        elif opc == "4":
            opcion_backup_db(db_path)
        elif opc == "5":
            opcion_restore_db(db_path)
        elif opc == "6":
            opcion_reset_db(db_path)
        elif opc == "0":
            break
        else:
            print("  Opcion invalida.")
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
        print("  6) geocode - Geocodificar coordenadas GPS")
        print("  7) gradient - Calcular gradientes de ruta")
        print("  8) check-db / check-gps")
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
            print("============ GEOCODE ============\n")
            print("  Geocodifica coordenadas GPS (lat,lon) a provincia/localidad")
            print("  usando la API Georef Argentina (batch).\n")
            print("  Uso: python flujos.py geocode [--limit N] [--dry-run]\n")
            print("  Tambien desde consola:")
            print("    python scripts/geocode.py --coords -34.6037,-58.3816")
            pausa()
        elif opc == "7":
            limpiar_pantalla()
            print("============ GRADIENT ============\n")
            print("  Calcula pendientes y esfuerzo fisico entre puntos GPS")
            print("  consecutivos, ordenados por timestamp.\n")
            print("  Columnas que actualiza:\n")
            print("    distance_from_prev_m    Distancia Haversine (m)")
            print("    elevation_gain_m        Cambio de elevacion (m)")
            print("    gradient_pct            Pendiente porcentual")
            print("    cumul_distance_m        Distancia acumulada (m)")
            print("    cumul_elevation_gain_m  Ganancia elevacion acumulada (m)\n")
            print("  Uso: python flujos.py gradient [--dry-run] [--verbose]\n")
            print("  Tambien desde consola:")
            print("    python scripts/gradiente.py --dry-run --verbose")
            pausa()
        elif opc == "8":
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
                print(resumen_db(conn))
                print("  Para ver el detalle completo: Menu 4 > Ver resumen\n")
            except sqlite3.OperationalError:
                print("  (Base de datos vacia o sin schema)\n")
            conn.close()
        else:
            print("  (Base de datos no encontrada - ejecuta 'Ingesta' primero)\n")

        print("  1) Preparar medios")
        print("  2) Ingesta")
        print("  3) Mejorar base de datos")
        print("  4) Consultar base de datos")
        print("  5) Mantenimiento DB")
        print("  6) Ayuda")
        print("  0) Salir\n")

        opc = input("  Opcion: ").strip()

        if opc == "1":
            opcion_preparar()
        elif opc == "2":
            opcion_ingesta()
        elif opc == "3":
            opcion_improve_db()
        elif opc == "4":
            opcion_consultar()
        elif opc == "5":
            opcion_mantenimiento()
        elif opc == "6":
            opcion_ayuda()
        elif opc == "0":
            limpiar_pantalla()
            print("  Chau.")
            break
        else:
            print("  Opcion invalida.")
            pausa()


# ── Backfill end_time ─────────────────────────────────────────────────────────

def opcion_backfill_end_time(db_path: str | None = None):
    """Calcula end_time para registros existentes que no lo tienen."""
    db_path = leer_db(db_path)
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

        # Preguntar modo
        modo = _preguntar_modo()

        if modo == "replace":
            print("  Modo replace: limpiando end_time existentes...")
            conn.execute("UPDATE media SET end_time = NULL WHERE timestamp_utc IS NOT NULL")
            conn.commit()

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


# ── Backup / Restore DB ──────────────────────────────────────────────────────

def listar_backups(db_path: str | None = None) -> list[tuple[str, str, int]]:
    """Lista archivos de backup en el directorio de la DB.
    Returns:
        Lista de (ruta_completa, nombre_archivo, tamaño_bytes) ordenados por fecha descendente.
    """
    db_path = leer_db(db_path)
    db_dir = os.path.dirname(db_path)
    backups = []
    for f in os.listdir(db_dir):
        if f.startswith("flujos_backup_") and f.endswith(".db"):
            ruta = os.path.join(db_dir, f)
            backups.append((ruta, f, os.path.getsize(ruta)))
    backups.sort(key=lambda x: x[0], reverse=True)
    return backups


def opcion_backup_db(db_path: str | None = None):
    """Solo backup de la DB (sin reset)."""
    db_path = leer_db(db_path)
    if not os.path.isfile(db_path):
        print("  No hay base de datos para respaldar.")
        pausa()
        return

    from datetime import datetime
    import shutil

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_dir = os.path.dirname(db_path)
    backup_name = f"flujos_backup_{ts}.db"
    backup_path = os.path.join(db_dir, backup_name)

    conn = sqlite3.connect(db_path)
    total = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
    conn.close()

    print(f"\n  DB actual:    {db_path}")
    print(f"  Registros:    {total}")
    print(f"  Backup:       {backup_name}")
    r = input("\n  ?Crear backup? (s/N): ").strip().lower()
    if r != "s":
        print("  Cancelado.")
        pausa()
        return

    try:
        shutil.copy2(db_path, backup_path)
        print(f"  ✅ Backup creado: {backup_name}")
    except Exception as e:
        print(f"  ❌ Error creando backup: {e}")

    pausa()


def opcion_restore_db(db_path: str | None = None):
    """Restaura la DB desde un backup."""
    db_path = leer_db(db_path)
    db_dir = os.path.dirname(db_path)

    backups = listar_backups(db_path)
    if not backups:
        print("  No hay backups disponibles en el directorio de la DB.")
        pausa()
        return

    print("  Backups disponibles:\n")
    for i, (ruta, name, size) in enumerate(backups, 1):
        size_mb = size / (1024 * 1024)
        print(f"  {i}) {name}  ({size_mb:.1f} MB)")

    print("  0) Cancelar\n")

    try:
        sel = int(input("  ?Cual restaurar? (numero): ").strip())
    except ValueError:
        sel = 0

    if sel < 1 or sel > len(backups):
        print("  Cancelado.")
        pausa()
        return

    backup_path = backups[sel - 1][0]
    backup_name = backups[sel - 1][1]

    print(f"\n  Esto REEMPLAZARÁ la DB actual con: {backup_name}")
    r = input("  ?Confirmar restauracion? (s/N): ").strip().lower()
    if r != "s":
        print("  Cancelado.")
        pausa()
        return

    import shutil
    try:
        # Cerrar cualquier conexión (no podemos forzarlo, pero asumimos que no hay)
        shutil.copy2(backup_path, db_path)
        print(f"  ✅ DB restaurada desde: {backup_name}")
    except Exception as e:
        print(f"  ❌ Error restaurando backup: {e}")

    pausa()


# ── Reset DB ─────────────────────────────────────────────────────────────────

def opcion_reset_db(db_path: str | None = None):
    """Hace backup de la DB actual y crea una nueva desde cero."""
    db_path = leer_db(db_path)
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

    # Extraer --db de los args para comandos que no pasan resto a sub-scripts
    def _extract_db(args: list[str]) -> tuple[str | None, list[str]]:
        if "--db" in args:
            idx = args.index("--db")
            if idx + 1 < len(args):
                db_val = args[idx + 1]
                del args[idx + 1]
                del args[idx]
                return db_val, args
        return None, args

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
        db_val, _ = _extract_db(resto)
        opcion_check_db(db_val)

    elif comando == "check-gps":
        db_val, _ = _extract_db(resto)
        opcion_check_gps(db_val)

    elif comando in ("undo-ingest", "undo"):
        db_val, _ = _extract_db(resto)
        opcion_undo_ingest(db_val)

    elif comando in ("backfill-end-time", "backfill"):
        db_val, _ = _extract_db(resto)
        opcion_backfill_end_time(db_val)

    elif comando == "improve-db":
        from scripts import improve_db
        improve_db.main(resto)

    elif comando in ("reset-db", "reset"):
        db_val, _ = _extract_db(resto)
        opcion_reset_db(db_val)

    elif comando in ("backup-db", "backup"):
        db_val, _ = _extract_db(resto)
        opcion_backup_db(db_val)

    elif comando in ("restore-db", "restore"):
        db_val, _ = _extract_db(resto)
        opcion_restore_db(db_val)

    elif comando == "geocode":
        from scripts import geocode
        geocode.main(resto)

    elif comando == "gradient":
        from scripts import gradiente
        gradiente.main(resto)

    else:
        print(f"Comando desconocido: {comando}")
        print(AYUDA)
        sys.exit(1)


if __name__ == "__main__":
    main()
