"""
Mueve las imágenes descartadas del reporte de Prueba 1 a la carpeta excluir/.
"""
import json
from pathlib import Path

# Cargar reporte
with open("db/reporte_prueba1.json", "r") as f:
    reporte = json.load(f)

carpeta = Path(reporte["carpeta"])
excluir = carpeta / "excluir"
descartadas = reporte["descartadas"]

print(f"Moviendo {len(descartadas)} imagenes a {excluir}...")

excluir.mkdir(parents=True, exist_ok=True)

movidas = 0
errores = 0
for nombre in descartadas:
    origen = carpeta / nombre
    destino = excluir / nombre
    if not origen.exists():
        print(f"  No encontrada: {nombre}")
        errores += 1
        continue
    if destino.exists():
        # Evitar colisiones
        destino = excluir / f"{origen.stem}_dup{origen.suffix}"
    origen.rename(destino)
    movidas += 1

print(f"\nMovidas: {movidas}, Errores: {errores}")
print(f"Quedan en carpeta: {len(list(carpeta.glob('*.jpg')))} imagenes")
print(f"En excluir/: {len(list(excluir.glob('*.jpg')))} imagenes")
