"""
Cliente compartido para modelos de visión y lenguaje de Ollama.

Proporciona una interfaz unificada para:
  - Analizar imágenes con modelos de visión (qwen2.5vl, moondream, llama3.2-vision, gemma4)
  - Consultar modelos de texto
  - Listar y seleccionar modelos disponibles

Modelos de visión recomendados (ordenados por capacidad):
  1. moondream:latest (1.7 GB) — rápido y ligero (default)
  2. qwen2.5vl:3b (3.2 GB) — liviano
  3. qwen2.5vl:latest (6.0 GB) — mejor equilibrio calidad/velocidad
  4. llama3.2-vision:latest (7.8 GB) — buena calidad general
  5. gemma4:e4b (9.6 GB) — multimodal potente

Uso básico:
    from scripts.ai_media.ollama_client import OllamaVision

    cliente = OllamaVision(modelo="qwen2.5vl:latest")
    respuesta = cliente.analizar_imagen("ruta/a/imagen.jpg",
                                        "Describí esta imagen en una frase")
    print(respuesta)
"""

import logging
from pathlib import Path
from typing import Optional

import ollama

logger = logging.getLogger(__name__)

# Modelos de visión disponibles en el sistema
MODELOS_VISION = [
    "qwen2.5vl:latest",
    "qwen2.5vl:3b",
    "moondream:latest",
    "llama3.2-vision:latest",
    "gemma4:e4b",
]

# Modelos de texto disponibles
MODELOS_TEXTO = [
    "qwen3.5:9b",
    "qwen3.5:4b",
    "deepseek-r1:latest",
    "llama3.1:8b-instruct-q4_K_M",
    "llama3.2:3b-instruct-q4_K_M",
]


class OllamaVision:
    """Cliente para analizar imágenes usando modelos de visión de Ollama."""

    def __init__(self, modelo: str = "moondream:latest", timeout: int = 120):
        """
        Args:
            modelo: Nombre del modelo de visión a usar.
            timeout: Timeout en segundos para la consulta.
        """
        if modelo not in self._listar_modelos_disponibles():
            logger.warning(
                "Modelo '%s' no encontrado entre los disponibles. "
                "Se intentará cargar igualmente.", modelo
            )
        self.modelo = modelo
        self.timeout = timeout

    @staticmethod
    def _listar_modelos_disponibles() -> list[str]:
        """Devuelve lista de modelos instalados en Ollama."""
        try:
            response = ollama.list()
            # Ollama Python >=0.3 devuelve ListResponse con .models
            # Versiones anteriores devuelven dict con clave "models"
            if hasattr(response, "models"):
                modelos = response.models
            elif isinstance(response, dict):
                modelos = response.get("models", [])
            else:
                modelos = list(response)
            return [m.model if hasattr(m, "model") else str(m) for m in modelos]
        except Exception as e:
            logger.warning("No se pudo listar modelos de Ollama: %s", e)
            return []

    def analizar_imagen(
        self,
        ruta_imagen: str,
        prompt: str = "Describí esta imagen en una frase breve.",
        temperatura: float = 0.3,
    ) -> str:
        """
        Analiza una imagen con el modelo de visión.

        Args:
            ruta_imagen: Ruta al archivo de imagen.
            prompt: Instrucción/pregunta sobre la imagen.
            temperatura: Control de creatividad (0.0 = determinista, 1.0 = creativo).

        Returns:
            Texto con la respuesta del modelo.
        """
        ruta = Path(ruta_imagen)
        if not ruta.exists():
            raise FileNotFoundError(f"No se encuentra la imagen: {ruta_imagen}")

        logger.info("Analizando imagen: %s con modelo %s", ruta.name, self.modelo)

        try:
            # Leer imagen como bytes
            with open(ruta, "rb") as f:
                imagen_bytes = f.read()

            response = ollama.chat(
                model=self.modelo,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [imagen_bytes],
                    }
                ],
                options={"temperature": temperatura},
            )
            texto = response["message"]["content"].strip()
            logger.debug("Respuesta obtenida (%d caracteres)", len(texto))
            return texto

        except Exception as e:
            logger.error("Error al analizar imagen con %s: %s", self.modelo, e)
            raise

    def analizar_imagenes(
        self,
        rutas_imagenes: list[str],
        prompt: str = "Describí esta imagen en una frase breve.",
        temperatura: float = 0.3,
    ) -> list[dict]:
        """
        Analiza múltiples imágenes y devuelve resultados.

        Args:
            rutas_imagenes: Lista de rutas a imágenes.
            prompt: Prompt para cada imagen.
            temperatura: Control de creatividad.

        Returns:
            Lista de dicts con {"ruta": str, "respuesta": str, "error": str|None}
        """
        resultados = []
        for ruta in rutas_imagenes:
            try:
                respuesta = self.analizar_imagen(ruta, prompt, temperatura)
                resultados.append({"ruta": ruta, "respuesta": respuesta, "error": None})
            except Exception as e:
                logger.error("Error en %s: %s", ruta, e)
                resultados.append({"ruta": ruta, "respuesta": None, "error": str(e)})
        return resultados

    def cambiar_modelo(self, nuevo_modelo: str):
        """Cambia el modelo de visión activo."""
        logger.info("Cambiando modelo: %s -> %s", self.modelo, nuevo_modelo)
        self.modelo = nuevo_modelo


class OllamaEmbedding:
    """Cliente para generar embeddings vectoriales usando Ollama.

    Uso:
        cliente = OllamaEmbedding(modelo="nomic-embed-text")
        vector = cliente.embed("Texto a embedder")
        print(len(vector))  # 768 para nomic-embed-text
    """

    def __init__(self, modelo: str = "nomic-embed-text", timeout: int = 60):
        self.modelo = modelo
        self.timeout = timeout

    def embed(self, texto: str) -> list[float]:
        """
        Genera un embedding vectorial para el texto dado.

        Args:
            texto: Texto a embedder.

        Returns:
            Lista de floats con el vector de embedding.
        """
        try:
            response = ollama.embeddings(model=self.modelo, prompt=texto)
            vector = response.get("embedding", [])
            if not vector:
                raise ValueError("Ollama devolvió un embedding vacío")
            return vector
        except Exception as e:
            logger.error("Error generando embedding con %s: %s", self.modelo, e)
            raise


