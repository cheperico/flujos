"""
Manejo de proxies (imágenes redimensionadas) para acelerar el análisis con IA.

Reduce imágenes grandes a un tamaño máximo configurable (por defecto 800px)
para que los modelos de visión de Ollama procesen menos datos innecesarios.

Los proxies se guardan en una carpeta `.proxies/` dentro del mismo directorio
de las imágenes originales (auto-contenido y cacheable).

Uso básico:
    from scripts.ai_media.proxy import obtener_proxy, limpiar_proxies

    ruta_proxy = obtener_proxy("foto_grande.jpg")
    # ruta_proxy apunta a .proxies/foto_grande.jpg (redimensionada)
"""

import logging
import hashlib
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Configuración por defecto
# 800px: ~4x menos tokens de visión que 1600px (1085 vs 2500 medidos con
# qwen2.5vl:3b), 2.5x más rápido por imagen y menos presión sobre el
# umbral de degradación acumulativa (swap). Calidad de tags/descripciones
# sigue siendo buena para este modelo.
MAX_LADO_PX = 800           # lado mayor máximo en píxeles (~0.5MP en 4:3)
CALIDAD_JPEG = 85           # calidad JPEG del proxy
NOMBRE_CARPETA_PROXIES = ".proxies"


def _carpeta_proxies(ruta_imagen: str) -> Path:
    """Devuelve la carpeta de proxies para el directorio de la imagen."""
    return Path(ruta_imagen).parent / NOMBRE_CARPETA_PROXIES


def _hash_archivo(ruta: str) -> str:
    """Hash rápido del archivo para detectar cambios (primeros 4KB + tamaño)."""
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        h.update(f.read(4096))
        stat = Path(ruta).stat()
        h.update(str(stat.st_size).encode())
        h.update(str(stat.st_mtime).encode())
    return h.hexdigest()[:12]


def _ruta_proxy(ruta_imagen: str) -> Path:
    """Devuelve la ruta esperada del proxy."""
    original = Path(ruta_imagen)
    return _carpeta_proxies(ruta_imagen) / original.name


def _ruta_hash(ruta_imagen: str) -> Path:
    """Devuelve la ruta del archivo de hash del proxy."""
    original = Path(ruta_imagen)
    return _carpeta_proxies(ruta_imagen) / f"{original.name}.hash"


def proxy_es_valido(ruta_imagen: str) -> bool:
    """
    Verifica si el proxy existe y está actualizado respecto al original.

    Args:
        ruta_imagen: Ruta a la imagen original.

    Returns:
        True si el proxy existe y el hash coincide.
    """
    proxy = _ruta_proxy(ruta_imagen)
    hash_file = _ruta_hash(ruta_imagen)

    if not proxy.exists() or not hash_file.exists():
        return False

    try:
        hash_guardado = hash_file.read_text().strip()
        hash_actual = _hash_archivo(ruta_imagen)
        return hash_guardado == hash_actual
    except Exception:
        return False


def crear_proxy(
    ruta_imagen: str,
    max_lado: int = MAX_LADO_PX,
    calidad: int = CALIDAD_JPEG,
    sobreescribir: bool = False,
) -> str:
    """
    Crea un proxy redimensionado de la imagen.

    Args:
        ruta_imagen: Ruta a la imagen original.
        max_lado: Tamaño máximo del lado mayor en píxeles.
        calidad: Calidad JPEG (1-100).
        sobreescribir: Si True, regenera el proxy aunque exista.

    Returns:
        Ruta al archivo proxy creado.

    Raises:
        FileNotFoundError: Si la imagen original no existe.
        ValueError: Si la imagen no se puede abrir.
    """
    original = Path(ruta_imagen)
    if not original.exists():
        raise FileNotFoundError(f"No se encuentra la imagen: {ruta_imagen}")

    # Si el proxy ya existe y es válido, no regenerar
    if not sobreescribir and proxy_es_valido(ruta_imagen):
        logger.debug("Proxy válido existe para %s", original.name)
        return str(_ruta_proxy(ruta_imagen))

    try:
        img = Image.open(original)
    except Exception as e:
        raise ValueError(f"No se pudo abrir la imagen {ruta_imagen}: {e}")

    # Redimensionar si es necesario
    ancho, alto = img.size
    if ancho <= max_lado and alto <= max_lado:
        # La imagen ya es más chica que el límite — copiar tal cual
        logger.debug("Imagen %s ya es pequeña (%dx%d)", original.name, ancho, alto)
        proxy = original
    else:
        # Calcular nuevas dimensiones manteniendo aspecto
        if ancho >= alto:
            nuevo_ancho = max_lado
            nuevo_alto = int(alto * max_lado / ancho)
        else:
            nuevo_alto = max_lado
            nuevo_ancho = int(ancho * max_lado / alto)

        img_redim = img.resize((nuevo_ancho, nuevo_alto), Image.LANCZOS)

        # Guardar proxy
        carpeta = _carpeta_proxies(ruta_imagen)
        carpeta.mkdir(parents=True, exist_ok=True)
        proxy = carpeta / original.name

        img_redim.save(proxy, "JPEG", quality=calidad, optimize=True)
        logger.debug("Proxy creado: %s (%dx%d -> %dx%d)",
                     original.name, ancho, alto, nuevo_ancho, nuevo_alto)

    # Guardar hash del original para detectar cambios futuros
    if proxy != original:
        hash_file = _ruta_hash(ruta_imagen)
        hash_file.write_text(_hash_archivo(ruta_imagen))

    return str(proxy)


def obtener_proxy(
    ruta_imagen: str,
    usar_proxy: bool = True,
    max_lado: int = MAX_LADO_PX,
    calidad: int = CALIDAD_JPEG,
) -> str:
    """
    Devuelve la ruta a usar para análisis (proxy o original).

    Si usar_proxy=True y la imagen es más grande que max_lado,
    crea (o reusa) el proxy automáticamente.

    Args:
        ruta_imagen: Ruta a la imagen original.
        usar_proxy: Si True, usa proxy para imágenes grandes.
        max_lado: Lado máximo para el proxy.
        calidad: Calidad JPEG del proxy.

    Returns:
        Ruta a la imagen que debe usarse para el análisis.
    """
    if not usar_proxy:
        return ruta_imagen

    original = Path(ruta_imagen)
    if not original.exists():
        return ruta_imagen

    # Solo crear proxy si la imagen es más grande que el límite
    try:
        with Image.open(original) as img:
            ancho, alto = img.size
            if ancho <= max_lado and alto <= max_lado:
                return ruta_imagen
    except Exception:
        return ruta_imagen

    # Crear proxy
    return crear_proxy(ruta_imagen, max_lado=max_lado, calidad=calidad)


def limpiar_proxies(ruta_imagen: str):
    """
    Elimina el proxy y su hash para una imagen específica.

    Args:
        ruta_imagen: Ruta a la imagen original.
    """
    for p in [_ruta_proxy(ruta_imagen), _ruta_hash(ruta_imagen)]:
        try:
            if p.exists():
                p.unlink()
                logger.debug("Eliminado: %s", p.name)
        except Exception as e:
            logger.warning("No se pudo eliminar %s: %s", p, e)


def limpiar_todos_los_proxies(directorio: str):
    """
    Elimina toda la carpeta de proxies de un directorio.

    Args:
        directorio: Directorio que contiene la carpeta .proxies.
    """
    carpeta = Path(directorio) / NOMBRE_CARPETA_PROXIES
    if carpeta.exists():
        import shutil
        try:
            shutil.rmtree(carpeta)
            logger.info("Carpeta de proxies eliminada: %s", carpeta)
        except Exception as e:
            logger.error("No se pudo eliminar %s: %s", carpeta, e)
