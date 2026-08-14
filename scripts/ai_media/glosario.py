#!/usr/bin/env python3
"""
glosario.py — Glosario de traducción EN→ES persistente para el pipeline.

Reemplaza la capa de traducción por IA (Ollama / translategemma) con un
glosario versionado en JSON (100% independiente de la DB) + un motor de
traducción clásico de respaldo (Google gratis o Argos offline).

La adaptación rioplatense (Argentina) es un requisito de PRIMERA clase:
viene del glosario (léxico manual del dominio) y de `reemplazos_descripcion`
(reglas post-traducción tipo "coche" → "auto"), NO del motor.

El glosario NUNCA lee la DB: solo se lee/escribe como archivo JSON.

Estructura del JSON (glosario_keywords.json en la raíz del proyecto):
    {
      "version": 1,
      "fecha": "AAAA-MM-DD",
      "palabras": {
        "bicycle": {"es": "bicicleta", "origen": "manual"},
        "street lamp": {"es": "farola", "origen": "db_seed"}
      },
      "reemplazos_descripcion": {"coche": "auto", ...},
      "metadatos": {"total_palabras": N, "fuentes": {"manual": N, "db_seed": N, "auto": N}}
    }

Prioridad de origen: manual > db_seed > auto. Al fusionar NUNCA se pisa una
entrada con origen de mayor prioridad.
"""

import json
import logging
import os
import re
from collections import Counter
from datetime import date

log = logging.getLogger(__name__)

# ── Reemplazos rioplatenses post-traducción (descripciones) ─────────────────
# Se aplican con regex de límite de palabra (word boundary), así "cochera" no
# se convierte en "autora". Claves en minúsculas.
REEMPLAZOS_DEFAULT: dict[str, str] = {
    "coche": "auto",
    "ordenador": "computadora",
    "movil": "celular",
    "zumo": "jugo",
    "chaqueta": "campera",
    "aparcamiento": "estacionamiento",
    "conducir": "manejar",
    "coger": "tomar",
    "tarta": "torta",
}

# Prioridad de origen: manual > db_seed > auto
PRIORIDAD_ORIGEN: dict[str, int] = {
    "manual": 3,
    "db_seed": 2,
    "auto": 1,
}


# ==============================================================================
# Motores de traducción clásicos (NO IA)
# ==============================================================================

class MotorGoogle:
    """Motor de traducción clásico vía deep_translator.GoogleTranslator.

    Gratis, sin API key. Límite ~5000 caracteres por request (las descripciones
    del corpus promedian ~1050, no es un problema). Falla con excepción si no
    hay red o el servicio responde mal.
    """

    def __init__(self) -> None:
        self._traductor = None

    def traducir(self, texto: str) -> str:
        """Traduce texto EN → ES. Devuelve "" si el texto está vacío."""
        if not texto or not texto.strip():
            return ""
        if self._traductor is None:
            from deep_translator import GoogleTranslator
            self._traductor = GoogleTranslator(source="en", target="es")
        return self._traductor.translate(texto) or ""


class MotorArgos:
    """Motor de traducción offline con Argos Translate.

    En el primer uso descarga e instala el paquete en→es (~100-200MB, una sola
    vez). Luego traduce 100% local, sin red.
    """

    def __init__(self) -> None:
        self._listo = False

    def _asegurar_paquete(self) -> None:
        """Descarga e instala el paquete en→es de Argos si falta."""
        import argostranslate.package
        import argostranslate.translate

        lenguas = argostranslate.translate.get_installed_languages()
        if any(l.code == "en" for l in lenguas) and any(l.code == "es" for l in lenguas):
            self._listo = True
            return

        argostranslate.package.update_package_index()
        disponibles = argostranslate.package.get_available_packages()
        paquete = next(
            (p for p in disponibles if p.from_code == "en" and p.to_code == "es"),
            None,
        )
        if paquete is None:
            raise RuntimeError("No se encontró paquete Argos en→es")
        ruta = paquete.download()
        argostranslate.package.install_from_path(ruta)
        self._listo = True

    def traducir(self, texto: str) -> str:
        """Traduce texto EN → ES. Devuelve "" si el texto está vacío."""
        if not texto or not texto.strip():
            return ""
        if not self._listo:
            self._asegurar_paquete()
        import argostranslate.translate
        return argostranslate.translate.translate(texto, "en", "es") or ""


def crear_motor(nombre: str) -> "MotorGoogle | MotorArgos | None":
    """Crea el motor de traducción según el nombre.

    Devuelve None para "glosario" y "ollama" (no usan motor clásico).
    """
    if nombre == "google":
        return MotorGoogle()
    if nombre == "argos":
        return MotorArgos()
    if nombre in ("glosario", "ollama"):
        return None
    log.warning("Motor de traducción desconocido: %s", nombre)
    return None


def traducir_con_motor(motor, texto: str) -> str:
    """Traduce con un motor clásico; devuelve "" ante cualquier fallo.

    Nunca lanza: si el motor falla (sin red, paquete faltante, etc.) loguea
    una advertencia y devuelve texto vacío para que el llamador decida.
    """
    if motor is None:
        log.warning("  Sin motor configurado: no se traduce '%s...'", (texto or "")[:60])
        return ""
    try:
        return motor.traducir(texto) or ""
    except Exception as e:
        log.warning("  ⚠ Error traduciendo con %s: %s", type(motor).__name__, e)
        return ""


# ==============================================================================
# Glosario
# ==============================================================================

def ruta_por_defecto() -> str:
    """Devuelve la ruta al glosario por defecto (raíz del proyecto)."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "glosario_keywords.json",
    )


class Glosario:
    """Glosario EN→ES persistente con prioridad de origen.

    Se guarda como JSON versionado en la raíz del proyecto y es 100%
    independiente de la DB (nunca la lee).
    """

    def __init__(
        self,
        ruta: str | None = None,
        motor: "MotorGoogle | MotorArgos | None" = None,
    ) -> None:
        self.ruta: str = ruta or ruta_por_defecto()
        self.motor = motor
        self.palabras: dict[str, dict[str, str]] = {}
        self.reemplazos: dict[str, str] = {}
        self.metadatos: dict = {
            "total_palabras": 0,
            "fuentes": {"manual": 0, "db_seed": 0, "auto": 0},
        }
        self.cargado = False

    # ── Carga / guardado ────────────────────────────────────────────────────

    def cargar(self) -> None:
        """Carga el glosario desde JSON si existe; si no, inicia vacío.

        `reemplazos_descripcion` siempre incluye la lista inicial por defecto
        (fusionada con lo que venga del archivo).
        """
        if os.path.isfile(self.ruta):
            try:
                with open(self.ruta, encoding="utf-8") as f:
                    datos = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                log.warning("  No se pudo leer el glosario %s: %s. Se inicia vacío.",
                            self.ruta, e)
                datos = {}
            palabras = datos.get("palabras") if isinstance(datos, dict) else None
            if isinstance(palabras, dict):
                for clave, valor in palabras.items():
                    if isinstance(valor, dict) and valor.get("es"):
                        self.palabras[str(clave).lower()] = {
                            "es": str(valor["es"]),
                            "origen": str(valor.get("origen", "auto")),
                        }
            reemplazos = datos.get("reemplazos_descripcion") if isinstance(datos, dict) else None
            if isinstance(reemplazos, dict):
                self.reemplazos = {
                    **REEMPLAZOS_DEFAULT,
                    **{str(k).lower(): str(v) for k, v in reemplazos.items()},
                }
            else:
                self.reemplazos = dict(REEMPLAZOS_DEFAULT)
        else:
            self.reemplazos = dict(REEMPLAZOS_DEFAULT)
        self.cargado = True

    def _actualizar_metadatos(self) -> None:
        """Recalcula totales y conteo por origen para `metadatos`."""
        conteo = Counter(v.get("origen", "auto") for v in self.palabras.values())
        self.metadatos = {
            "total_palabras": len(self.palabras),
            "fuentes": {o: int(conteo.get(o, 0)) for o in ("manual", "db_seed", "auto")},
        }

    def guardar(self) -> None:
        """Escribe el glosario a JSON de forma atómica (tmp + os.replace)."""
        self._actualizar_metadatos()
        datos = {
            "version": 1,
            "fecha": date.today().isoformat(),
            "palabras": self.palabras,
            "reemplazos_descripcion": self.reemplazos,
            "metadatos": self.metadatos,
        }
        tmp = self.ruta + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.ruta)
        except OSError as e:
            log.error("  No se pudo guardar el glosario %s: %s", self.ruta, e)

    # ── Fusión con prioridad ────────────────────────────────────────────────

    def agregar_entradas(self, entradas: dict[str, str], origen: str) -> None:
        """Fusiona entradas (clave EN → valor ES) respetando la prioridad.

        Nunca pisa una entrada existente con origen de mayor prioridad.
        Las claves se normalizan a minúsculas.
        """
        if origen not in PRIORIDAD_ORIGEN:
            log.warning("  Origen desconocido '%s': se ignoran sus entradas.", origen)
            return
        prioridad_nueva = PRIORIDAD_ORIGEN[origen]
        for clave, valor in entradas.items():
            if not clave or not valor:
                continue
            clave_norm = str(clave).strip().lower()
            valor_norm = str(valor).strip()
            if not clave_norm or not valor_norm:
                continue
            existente = self.palabras.get(clave_norm)
            if existente and PRIORIDAD_ORIGEN.get(existente["origen"], 0) > prioridad_nueva:
                continue
            self.palabras[clave_norm] = {"es": valor_norm, "origen": origen}

    # ── Traducción ──────────────────────────────────────────────────────────

    def traducir_keywords(self, lista_en: list[str]) -> tuple[list[str], list[str]]:
        """Traduce keywords EN → ES con el glosario.

        Por cada ítem: busca la frase exacta primero (soporta "bare branches");
        si no existe y el ítem tiene espacios, traduce palabra por palabra y
        une; si una palabra individual es desconocida, queda tal cual en EN en
        `traducidas` y se agrega a `desconocidas`.

        Returns:
            (traducidas, desconocidas) — listas de strings.
        """
        traducidas: list[str] = []
        desconocidas: list[str] = []
        vistos: set[str] = set()

        for item in lista_en:
            if not item:
                continue
            original = item.strip()
            clave = original.lower()
            if not clave:
                continue

            entrada = self.palabras.get(clave)
            if entrada:
                traducidas.append(entrada["es"])
            elif " " in clave:
                # Frase sin entrada exacta: traducir palabra por palabra
                partes: list[str] = []
                for pal in clave.split():
                    entrada_pal = self.palabras.get(pal)
                    if entrada_pal:
                        partes.append(entrada_pal["es"])
                    else:
                        partes.append(pal)
                        if pal not in vistos:
                            vistos.add(pal)
                            desconocidas.append(pal)
                traducidas.append(" ".join(partes))
            else:
                # Palabra desconocida: pasa tal cual (EN) y se reporta
                traducidas.append(original)
                if clave not in vistos:
                    vistos.add(clave)
                    desconocidas.append(clave)

        return traducidas, desconocidas

    def traducir_descripcion(self, texto_en: str) -> str:
        """Traduce una descripción EN → ES y aplica reemplazos rioplatenses.

        Usa el motor configurado (o Google por defecto) y luego aplica
        `reemplazos_descripcion` con límite de palabra, así "cochera" no se
        convierte en "autora".
        """
        if not texto_en or not texto_en.strip():
            return ""
        motor = self.motor or MotorGoogle()
        texto = traducir_con_motor(motor, texto_en)
        if not texto:
            return ""
        for clave, valor in self.reemplazos.items():
            texto = re.sub(rf"\b{re.escape(clave)}\b", valor, texto,
                           flags=re.IGNORECASE)
        return texto

    # ── Cobertura ───────────────────────────────────────────────────────────

    def cobertura(self, palabras: set[str]) -> float:
        """Fracción (0..1) de palabras en minúsculas cubiertas por el glosario."""
        if not palabras:
            return 0.0
        conjunto = {str(p).lower() for p in palabras if str(p).strip()}
        if not conjunto:
            return 0.0
        return len(conjunto & set(self.palabras)) / len(conjunto)


# ==============================================================================
# Singleton cacheado
# ==============================================================================

_GLOSARIO_CACHE: dict[str, Glosario] = {}


def cargar_glosario(ruta: str | None = None) -> Glosario:
    """Devuelve un Glosario cacheado (una instancia por ruta)."""
    ruta_efectiva = ruta or ruta_por_defecto()
    if ruta_efectiva not in _GLOSARIO_CACHE:
        glosario = Glosario(ruta_efectiva)
        glosario.cargar()
        _GLOSARIO_CACHE[ruta_efectiva] = glosario
    return _GLOSARIO_CACHE[ruta_efectiva]
