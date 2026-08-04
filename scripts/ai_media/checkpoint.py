#!/usr/bin/env python3
"""
checkpoint.py — Herramientas para procesos de IA detenibles y retomables.

Los procesos de IA más lentos (keywords, descripciones, traducción, refinado,
tags, audio tagging, etc.) deben poder:
  1. DETENERSE con Ctrl+C de forma limpia (sin traceback feo).
  2. Guardar el progreso en la base de datos HASTA DONDE SE LLEGÓ (checkpoint),
     de modo que al re-ejecutar con --mode skip se retome solo lo pendiente.

Este módulo provee dos piezas reutilizables:

  ── Checkpoint ──────────────────────────────────────────────────────────────
  Commit por lote: hace conn.commit() cada `cada` ítems del bucle. Si el
  proceso se corta con Ctrl+C (o se cuelga), solo se pierde el último lote
  parcial (≤ `cada` ítems), no todo el recorrido.

      cp = Checkpoint(conn, cada=20, etiqueta="keywords")
      for item in items:
          ... procesar y escribir en conn ...
          cp.contar()
      cp.finalizar()          # commit final + reporte

  ── manejar_interrupcion ────────────────────────────────────────────────────
  Context manager que captura KeyboardInterrupt, commitea los pendientes de la
  conexión (si se pasó una), imprime un mensaje amigable por stderr y termina
  el proceso con sys.exit(130) (código estándar de Ctrl+C), sin traceback.

      with manejar_interrupcion(conn=conn, etiqueta="improve_db"):
          ... ejecutar pasos ...

  Se usa en los mains que NO tienen manejo de KeyboardInterrupt propio.
"""

import contextlib
import logging
import sys
from typing import Iterator, Optional

log = logging.getLogger(__name__)


class Checkpoint:
    """
    Guarda el progreso en la DB cada `cada` ítems procesados.

    Lleva un contador de ítems procesados OK y un acumulador de los ítems
    que aún no se guardaron (pendientes). `contar()` hace `conn.commit()`
    cada `cada` llamadas; `finalizar()` hace el commit final y loguea.
    """

    def __init__(
        self,
        conn,
        cada: int = 20,
        etiqueta: str = "proceso",
    ) -> None:
        """
        Args:
            conn: Conexión SQLite sobre la que commiter.
            cada: Cada cuántos ítems se hace conn.commit() (checkpoint).
            etiqueta: Nombre del proceso (para los mensajes de log).
        """
        if cada < 1:
            raise ValueError(f"'cada' debe ser >= 1 (recibido: {cada})")
        self.conn = conn
        self.cada = cada
        self.etiqueta = etiqueta
        self.procesados: int = 0    # ítems OK contados en total
        self.pendientes: int = 0    # ítems contados desde el último commit

    def contar(self) -> None:
        """
        Cuenta un ítem procesado y commitea cada `cada` ítems.

        Debe llamarse UNA vez por ítem procesado (éxito o error), justo
        después de escribir los cambios en la conexión. Cuando el acumulado
        de pendientes alcanza `cada`, se hace conn.commit() (checkpoint) y
        se reinicia el contador.
        """
        self.procesados += 1
        self.pendientes += 1
        if self.pendientes >= self.cada:
            self.conn.commit()
            log.info("  ✔ Checkpoint %s: %d ítems guardados.",
                     self.etiqueta, self.procesados)
            self.pendientes = 0

    def finalizar(self) -> None:
        """
        Commit final (por si quedan pendientes sin commiter) + reporte.

        Solo hace conn.commit() si quedaron ítems sin guardar desde el
        último checkpoint. Luego loguea el total de ítems procesados.
        """
        if self.pendientes > 0:
            try:
                self.conn.commit()
            except Exception:
                log.warning("  ⚠ No se pudo hacer el commit final de %s.",
                            self.etiqueta)
        self.pendientes = 0
        log.info("  ✔ Progreso guardado (%s): %d ítems.",
                 self.etiqueta, self.procesados)


@contextlib.contextmanager
def manejar_interrupcion(
    conn=None,
    etiqueta: str = "",
) -> Iterator[None]:
    """
    Captura KeyboardInterrupt dentro del bloque y termina de forma limpia.

    Si el bloque lanza KeyboardInterrupt (Ctrl+C), este context manager:
      1. Hace conn.commit() (si se pasó una conexión) para guardar los
         pendientes de la transacción abierta.
      2. Imprime un mensaje amigable por stderr (y por log).
      3. Sale con sys.exit(130) (código estándar de Ctrl+C), sin traceback.

    En un bloque normal (sin interrupción) no hace nada especial.

    Args:
        conn: Conexión SQLite opcional. Se commitea al capturar Ctrl+C.
        etiqueta: Nombre del proceso para el mensaje de log.
    """
    try:
        yield
    except KeyboardInterrupt:
        if conn is not None:
            try:
                conn.commit()
                log.info("  ✔ Interrupción: pendientes commiteados (%s).",
                         etiqueta)
            except Exception as e:
                log.warning("  ⚠ No se pudieron commitar los pendientes: %s", e)
        mensaje = "\n⚠️  Detenido por el usuario. Progreso guardado hasta donde se llegó."
        print(mensaje, file=sys.stderr)
        if etiqueta:
            log.warning("  %s detenido por Ctrl+C. Podés retomar con --mode skip.", etiqueta)
        # Sale con el código estándar de Ctrl+C (130) de forma limpia.
        sys.exit(130)