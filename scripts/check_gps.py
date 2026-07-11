"""Verifica GPS en fotos de fABIAN y otras carpetas."""
import subprocess
import glob
import os

exiftool = "C:\\Program Files\\digiKam\\exiftool.exe"

def check_gps(folder, n=5):
    fotos = glob.glob(os.path.join(folder, "*.jpg")) + glob.glob(os.path.join(folder, "*.jpeg"))
    fotos = fotos[:n]
    if not fotos:
        print(f"  No hay fotos en {folder}")
        return
    for f in fotos:
        cmd = [exiftool, "-j", "-GPSLatitude", "-GPSLongitude", "-GPSPosition", "-DateTimeOriginal", "-Model", f]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.stdout:
            data = r.stdout.strip()
            has_gps = "GPSLatitude" in data
            print(f"  {os.path.basename(f):40s} | GPS={'SI' if has_gps else 'NO':3s} | {data[:120]}")
        else:
            print(f"  {os.path.basename(f)} | ERROR")

# Probar varias carpetas
print("=== fABIAN ===")
check_gps("D:/Flujos/Celulares/fABIAN")

print("\n=== NEGRA ===")
check_gps("D:/Flujos/Celulares/NEGRA")

print("\n=== Lucas ===")
check_gps("D:/Flujos/Celulares/Lucas")

print("\n=== Agus ===")
check_gps("D:/Flujos/Celulares/Agus")

print("\n=== NaHUEL ===")
check_gps("D:/Flujos/Celulares/NaHUEL")

print("\n=== Juan Marco ===")
check_gps("D:/Flujos/Celulares/Juan Marco")

print("\n=== Fotos y videos Victor ===")
check_gps("D:/Flujos/Celulares/Fotos y videos Victor")
