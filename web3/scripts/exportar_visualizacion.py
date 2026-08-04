"""
Exporta datos de flujos.db → visualizacion.db para la visualización web3.
Lee la tabla media + media_metadata y reconstruye medios.
También exporta telegram_messages (chat) con sus fotos vinculadas.
"""
import sqlite3
import os
import sys
import json
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FLUJOS_DB = os.path.join(BASE, 'db', 'flujos.db')
VIZ_DB = os.path.join(BASE, 'web3', 'db', 'visualizacion.db')

def main():
    print(f"Leyendo {FLUJOS_DB}...")
    src = sqlite3.connect(FLUJOS_DB)
    src.row_factory = sqlite3.Row

    # Obtener metadata tags de media_metadata
    meta = {}
    cur = src.execute("SELECT media_id, key, value FROM media_metadata WHERE key IN ('dia_semana','weather_label','ia_description')")
    for r in cur:
        meta.setdefault(r['media_id'], {})[r['key']] = r['value']

    # Obtener embeddings 2D (si existen)
    embs = {}
    try:
        cur = src.execute("SELECT media_id, embedding FROM media_embeddings WHERE modelo='nomic-embed-text'")
        for r in cur:
            blob = r['embedding']
            if blob and len(blob) >= 16:
                # Podría ser embedding de 768 o de 2 dims. Guardamos como placeholder.
                embs[r['media_id']] = blob
    except:
        pass

    # Obtener registros
    cur = src.execute("""
        SELECT id, filename_original, carpeta, type, subtype,
               filepath_absoluto, filepath_relativo, size_bytes, timestamp_utc, duration_secs,
               latitude, longitude, localidad, municipio, provincia,
               author,
               color_1_hex, color_1_name_basic,
               color_2_hex, color_2_name_basic,
               color_3_hex, color_3_name_basic
        FROM media
        ORDER BY id
    """)
    filas = cur.fetchall()
    print(f"  {len(filas)} registros leídos")

    # Construir visualizacion.db
    if os.path.exists(VIZ_DB):
        os.remove(VIZ_DB)
    dst = sqlite3.connect(VIZ_DB)
    dst.execute("PRAGMA journal_mode=WAL")
    dst.execute("PRAGMA foreign_keys=ON")

    dst.executescript("""
        CREATE TABLE medios (
            id INTEGER PRIMARY KEY,
            archivo TEXT NOT NULL,
            carpeta TEXT,
            tipo TEXT,
            subtipo TEXT,
            ruta_absoluta TEXT,
            ruta_relativa TEXT NOT NULL,
            tamano_bytes INTEGER,
            fecha TEXT,
            hora TEXT,
            franja_horaria TEXT,
            mes TEXT,
            anio TEXT,
            duracion_seg REAL,
            ancho INTEGER,
            alto INTEGER,
            latitud REAL,
            longitud REAL,
            localidad TEXT,
            municipio TEXT,
            provincia TEXT,
            autor TEXT,
            color_1 TEXT,
            color_1_hex TEXT,
            color_2 TEXT,
            color_2_hex TEXT,
            color_3 TEXT,
            color_3_hex TEXT,
            dia_semana TEXT,
            clima TEXT,
            descripcion TEXT,
            embedding_x REAL,
            embedding_y REAL,
            cluster REAL
        );

        CREATE TABLE categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo TEXT NOT NULL,
            valor TEXT NOT NULL,
            conteo INTEGER DEFAULT 0,
            UNIQUE(grupo, valor)
        );

        CREATE TABLE medio_categoria (
            medio_id INTEGER NOT NULL,
            categoria_id INTEGER NOT NULL,
            PRIMARY KEY(medio_id, categoria_id)
        );

        CREATE TABLE telegram_messages (
            id INTEGER PRIMARY KEY,
            message_id INTEGER,
            chat_id INTEGER,
            from_name TEXT,
            text TEXT,
            date_utc TEXT,
            message_type TEXT,
            has_media INTEGER DEFAULT 0,
            fotos TEXT
        );
    """)

    insert_sql = """
        INSERT INTO medios (
            id, archivo, carpeta, tipo, subtipo,
            ruta_absoluta, ruta_relativa, tamano_bytes,
            fecha, hora, mes, anio, duracion_seg,
            latitud, longitud, localidad, municipio, provincia,
            autor,
            color_1, color_1_hex,
            color_2, color_2_hex,
            color_3, color_3_hex,
            dia_semana, clima, descripcion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    count = 0
    for r in filas:
        ts = r['timestamp_utc']
        fecha = hora = mes = anio = None
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                fecha = dt.strftime('%Y-%m-%d')
                hora = dt.strftime('%H:%M')
                mes = str(dt.month)
                anio = str(dt.year)
            except:
                pass

        m = meta.get(r['id'], {})
        dia_sem = m.get('dia_semana')
        clima = m.get('weather_label')
        desc = m.get('ia_description')

        vals = (
            r['id'],
            r['filename_original'],
            r['carpeta'],
            r['type'],
            r['subtype'],
            r['filepath_absoluto'],
            r['filepath_relativo'],
            r['size_bytes'],
            fecha, hora, mes, anio,
            r['duration_secs'],
            r['latitude'], r['longitude'],
            r['localidad'], r['municipio'], r['provincia'],
            r['author'],
            r['color_1_name_basic'], r['color_1_hex'],
            r['color_2_name_basic'], r['color_2_hex'],
            r['color_3_name_basic'], r['color_3_hex'],
            dia_sem, clima, desc
        )
        try:
            dst.execute(insert_sql, vals)
            count += 1
        except Exception as e:
            print(f"  Error insertando id {r['id']}: {e}")

    dst.commit()

    # Actualizar categorías desde tipos
    cur = dst.execute("SELECT tipo, COUNT(*) FROM medios WHERE tipo IS NOT NULL GROUP BY tipo")
    for r in cur:
        dst.execute("INSERT OR IGNORE INTO categorias (grupo, valor, conteo) VALUES ('tipo', ?, ?)", (r[0], r[1]))
    dst.commit()

    # ── Exportar Telegram (chat) ─────────────────────────────
    # Mapa: telegram_messages.id (PK) → lista de media_ids de fotos
    fotos_map = {}
    for r in src.execute("""
        SELECT message_id, media_id FROM telegram_media
        WHERE media_type = 'photo' AND media_id IS NOT NULL
        ORDER BY message_id, media_order
    """):
        fotos_map.setdefault(r['message_id'], []).append(r['media_id'])

    # Mapa: id → tiene media adjunta (para has_media)
    has_media_ids = set(r[0] for r in src.execute("SELECT DISTINCT message_id FROM telegram_media"))

    tg_count = 0
    cur = src.execute("""
        SELECT id, message_id, chat_id, from_name, text, date_utc, message_type
        FROM telegram_messages
        ORDER BY id
    """)
    for r in cur:
        mid = r['id']
        fotos_json = json.dumps(fotos_map.get(mid, []))
        has = 1 if mid in has_media_ids else 0
        dst.execute(
            "INSERT INTO telegram_messages (id, message_id, chat_id, from_name, text, date_utc, message_type, has_media, fotos)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, r['message_id'], r['chat_id'], r['from_name'], r['text'], r['date_utc'], r['message_type'], has, fotos_json)
        )
        tg_count += 1
    dst.commit()

    # Resumen
    print(f"\n  Insertados: {count} registros")
    cur = dst.execute("SELECT tipo, COUNT(*) FROM medios GROUP BY tipo ORDER BY COUNT(*) DESC")
    for r in cur:
        print(f"    {r[0]}: {r[1]}")
    cur = dst.execute("SELECT MIN(fecha), MAX(fecha) FROM medios")
    dr = cur.fetchone()
    print(f"  Rango fechas: {dr[0]} -> {dr[1]}")
    cur = dst.execute("SELECT COUNT(*) FROM medios WHERE provincia IS NOT NULL")
    print(f"  Con provincia: {cur.fetchone()[0]}")
    cur = dst.execute("SELECT COUNT(*) FROM medios WHERE latitud IS NOT NULL")
    print(f"  Con GPS: {cur.fetchone()[0]}")
    cur = dst.execute("SELECT COUNT(*) FROM medios WHERE municipio IS NOT NULL")
    print(f"  Con municipio: {cur.fetchone()[0]}")
    cur = dst.execute("SELECT COUNT(*) FROM telegram_messages")
    print(f"  Telegram mensajes: {cur.fetchone()[0]}")
    cur = dst.execute("SELECT COUNT(*) FROM telegram_messages WHERE fotos IS NOT NULL AND fotos != '[]'")
    print(f"  Telegram con fotos: {cur.fetchone()[0]}")

    src.close()
    dst.close()
    print(f"\nOK {VIZ_DB} actualizada ({count} registros, {tg_count} mensajes telegram)")

if __name__ == '__main__':
    main()
