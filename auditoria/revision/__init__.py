"""Revisión de una cuenta SOAT: lectura de folios, puntos de la lista del auditor e informe en texto."""

from auditoria.config import Configuracion
from auditoria.revision.cuenta import Cuenta, leer_cuenta
from auditoria.revision.informe import generar_texto
from auditoria.revision.puntos import Punto, revisar_cuenta


def auditar(
    archivos: list[tuple[str, bytes]],
    config: Configuracion,
    tipos_por_archivo: dict[str, str | None] | None = None,
    etiquetas: dict[str, str] | None = None,
    factura_esperada: str | None = None,
) -> tuple[Cuenta, list[Punto], str]:
    """Lee la cuenta, revisa todos los puntos y devuelve (cuenta, puntos, texto para copiar).

    - tipos_por_archivo: tipo documental sugerido por el nombre del archivo (si el folio no trae título).
    - etiquetas: nombre corto de cada archivo para citar los folios (p. ej. "FEV folio 2").
    - factura_esperada: número de factura según el nombre de los archivos (cuentas por documentos separados).
    """
    cuenta = leer_cuenta(archivos, config, tipos_por_archivo, etiquetas)
    cuenta.factura_esperada = factura_esperada
    puntos = revisar_cuenta(cuenta)
    return cuenta, puntos, generar_texto(cuenta, puntos)
