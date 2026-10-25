"""Esquema JSON obligatorio de las respuestas de IA (puente manual y API usan el mismo).

Toda respuesta queda como "pendiente de revisión humana": la IA nunca confirma un hallazgo.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from auditoria import catalogos

VERSION_ESQUEMA = "1.0"
ESTADO_PENDIENTE_IA = "pendiente de revisión humana"
TIPOS_ANALISIS = ("clasificacion_paginas", "extraccion_ficha", "analisis_clinico")

# Estados que obligan a citar al menos una evidencia (archivo + página + texto).
ESTADOS_CON_EVIDENCIA_OBLIGATORIA = (
    catalogos.CONTRADICCION,
    catalogos.POSIBLE_INCONSISTENCIA,
    catalogos.ILEGIBLE,
    catalogos.SIN_INCONSISTENCIA,
)


class EvidenciaIA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archivo: str = Field(min_length=1, description="Nombre exacto del archivo PDF.")
    pagina: int = Field(ge=1, description="Página del ARCHIVO PDF (no la numeración impresa).")
    texto: str = Field(min_length=1, description="Texto literal del documento que respalda el análisis.")


class AnalisisIA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identificador: str = Field(min_length=1)
    pregunta_clinica: str = Field(min_length=1, description="Pregunta evaluada.")
    conclusion_preliminar: str = Field(min_length=1)
    estado_resultado: Literal[catalogos.ESTADOS_RESULTADO]  # type: ignore[valid-type]
    severidad: Literal[catalogos.SEVERIDADES]  # type: ignore[valid-type]
    evidencias: list[EvidenciaIA]
    informacion_contradictoria: list[str]
    informacion_faltante: list[str]
    limitaciones: list[str]
    confianza: Literal["alta", "media", "baja"]
    accion_sugerida: str = Field(min_length=1)
    estado: Literal[ESTADO_PENDIENTE_IA]  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _evidencia_obligatoria(self):
        if self.estado_resultado in ESTADOS_CON_EVIDENCIA_OBLIGATORIA and not self.evidencias:
            raise ValueError(f"el estado «{self.estado_resultado}» exige al menos una evidencia con archivo y página")
        return self


class RespuestaIA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_esquema: Literal[VERSION_ESQUEMA]  # type: ignore[valid-type]
    tipo_analisis: Literal[TIPOS_ANALISIS]  # type: ignore[valid-type]
    auditoria: str = Field(min_length=1, description="Identificador interno de la auditoría.")
    analisis: list[AnalisisIA]

    @field_validator("analisis")
    @classmethod
    def _identificadores_unicos(cls, analisis: list[AnalisisIA]) -> list[AnalisisIA]:
        ids = [a.identificador for a in analisis]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"identificadores repetidos: {', '.join(repetidos)}")
        return analisis


def esquema_json() -> dict:
    """Esquema JSON que se entrega a la IA junto con el prompt."""
    return RespuestaIA.model_json_schema()
