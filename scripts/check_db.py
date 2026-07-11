import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "db/flujos.db"

conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== MEDIA ===")
c.execute("SELECT id, filename_original, type, sidecar_parsed, sidecar_xml, timestamp_original, timestamp_utc, timezone_note FROM media ORDER BY id")
for row in c.fetchall():
    ts = row[4] or "-"
    print(f"  id={row[0]:2d} | {row[1]:35s} | {row[2]:6s} | xml={row[3]} | ts_orig={ts}")

print()
print("=== MEDIA_METADATA (primeros 40) ===")
c.execute("SELECT m.id, m.filename_original, mm.key, mm.value FROM media_metadata mm JOIN media m ON m.id = mm.media_id ORDER BY m.id, mm.key LIMIT 40")
for row in c.fetchall():
    val = str(row[3])[:80]
    print(f"  id={row[0]:2d} | {row[1]:30s} | {row[2]:45s} = {val}")

print()
print("=== TOTALES ===")
c.execute("SELECT COUNT(*) FROM media")
print(f"  Total media: {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM media_metadata")
print(f"  Total metadata: {c.fetchone()[0]}")

conn.close()
