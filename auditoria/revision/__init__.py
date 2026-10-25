"""Revisión de una cuenta SOAT: lectura de folios, puntos de la lista del auditor e informe en texto."""

from auditoria.config import Configuracion
from auditoria.revision.cuenta import Cuenta, leer_cuenta
from auditoria.revision.informe import generar_texto
from auditoria.revision.puntos import Punto, revisar_cuenta


def auditar(archivos: list[tuple[str, bytes]], config: Configuracion) -> tuple[Cuenta, list[Punto], str]:
    """Lee la cuenta, revisa todos los puntos y devuelve (cuenta, puntos, texto para copiar)."""
    cuenta = leer_cuenta(archivos, config)
    puntos = revisar_cuenta(cuenta)
    return cuenta, puntos, generar_texto(cuenta, puntos)
