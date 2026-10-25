"""Interfaz común de los proveedores de IA.

Todos usan los mismos prompts y el mismo esquema (auditoria/ia/puente_manual.py y esquemas.py),
para que activar la API no requiera reprogramar.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from auditoria.config import Configuracion


class ErrorProveedorIA(Exception):
    """El proveedor no está disponible o falló."""


@dataclass
class ArchivoEnvio:
    nombre: str
    ruta: Path


@dataclass
class ResultadoProveedor:
    texto: str  # Respuesta JSON (se valida igual que en el puente manual)
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0


class ProveedorIA(ABC):
    nombre: str = ""
    es_manual: bool = False  # True: el usuario lleva el paquete a claude.ai y trae la respuesta
    tiene_costo: bool = False

    def __init__(self, config: Configuracion):
        self.config = config

    @abstractmethod
    def disponible(self) -> bool: ...

    @abstractmethod
    def descripcion_estado(self) -> str: ...

    def analizar(self, prompt: str, archivos: list[ArchivoEnvio], confirmado: bool) -> ResultadoProveedor:
        """Envía el análisis. Solo los proveedores automáticos lo implementan."""
        raise ErrorProveedorIA(f"El proveedor «{self.nombre}» no ejecuta análisis automáticos.")


def obtener_proveedor(config: Configuracion) -> ProveedorIA:
    from auditoria.ia.proveedor_anthropic import ProveedorAnthropic
    from auditoria.ia.proveedor_desactivado import ProveedorDesactivado
    from auditoria.ia.proveedor_ollama import ProveedorOllama
    from auditoria.ia.puente_manual_proveedor import ProveedorPuenteManual

    clases = {
        "desactivado": ProveedorDesactivado,
        "puente_manual": ProveedorPuenteManual,
        "anthropic": ProveedorAnthropic,
        "ollama": ProveedorOllama,
    }
    return clases.get(config.proveedor_ia, ProveedorDesactivado)(config)
