"""Carga y validación de las reglas definidas en YAML (configuracion/reglas/*.yaml)."""

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from auditoria import catalogos
from auditoria.config import RAIZ_PROYECTO

RUTA_REGLAS = RAIZ_PROYECTO / "configuracion" / "reglas"


class ErrorReglas(ValueError):
    """Error en la configuración de reglas o perfiles (se muestra tal cual al usuario)."""


class Regla(BaseModel):
    id: str
    nombre: str
    descripcion: str
    categoria: str
    funcion: str
    parametros: dict[str, Any] = Field(default_factory=dict)
    evidencia_necesaria: str
    severidad: str
    resultado_esperado: str
    explicacion: str
    aplicabilidad: str
    referencia_normativa: str = catalogos.PENDIENTE_VALIDACION
    version: str
    fecha_validacion: date | None = None
    activa: bool = True

    @field_validator("severidad")
    @classmethod
    def _severidad_valida(cls, valor: str) -> str:
        if valor not in catalogos.SEVERIDADES:
            raise ValueError(f"severidad debe ser una de {catalogos.SEVERIDADES}")
        return valor

    @field_validator("referencia_normativa")
    @classmethod
    def _referencia_no_vacia(cls, valor: str) -> str:
        return valor.strip() or catalogos.PENDIENTE_VALIDACION


def cargar_reglas(carpeta: Path = RUTA_REGLAS) -> list[Regla]:
    """Lee todas las reglas de la carpeta y valida su estructura e identificadores únicos."""
    from auditoria.reglas.verificaciones import VERIFICACIONES

    reglas: list[Regla] = []
    for archivo in sorted(carpeta.glob("*.yaml")):
        try:
            datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise ErrorReglas(f"{archivo.name}: YAML inválido: {error}") from error
        for indice, bruto in enumerate(datos.get("reglas", []), start=1):
            try:
                regla = Regla.model_validate(bruto)
            except ValidationError as error:
                raise ErrorReglas(f"{archivo.name}, regla #{indice}: {error}") from error
            if regla.funcion not in VERIFICACIONES:
                raise ErrorReglas(f"{archivo.name}, {regla.id}: la función '{regla.funcion}' no existe.")
            reglas.append(regla)

    ids = [r.id for r in reglas]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ErrorReglas(f"Identificadores de regla repetidos: {', '.join(repetidos)}")
    return reglas
