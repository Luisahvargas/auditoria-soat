"""Ollama (opcional): NO se implementa por ahora.

El equipo actual no tiene GPU dedicada ni RAM libre suficiente para modelos locales útiles.
Si en el futuro se instala en un equipo adecuado, se implementa aquí con la misma interfaz.
"""

import shutil

from auditoria.ia.proveedor_base import ProveedorIA


class ProveedorOllama(ProveedorIA):
    nombre = "ollama"

    def disponible(self) -> bool:
        return False

    def descripcion_estado(self) -> str:
        instalado = "instalado" if shutil.which("ollama") else "no instalado"
        return f"Ollama ({instalado}) no está implementado en esta versión: el hardware actual no es suficiente."
