"""Perfiles de aseguradora (configuracion/aseguradoras/*.yaml).

Un perfil puede desactivar reglas o ajustar su severidad y parámetros sin duplicar código.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from auditoria import catalogos
from auditoria.config import RAIZ_PROYECTO
from auditoria.reglas.definiciones import ErrorReglas, Regla

RUTA_PERFILES = RAIZ_PROYECTO / "configuracion" / "aseguradoras"


class AjusteRegla(BaseModel):
    severidad: str | None = None
    parametros: dict[str, Any] = Field(default_factory=dict)


class Perfil(BaseModel):
    id: str
    nombre: str
    descripcion: str = ""
    reglas_desactivadas: list[str] = Field(default_factory=list)
    ajustes: dict[str, AjusteRegla] = Field(default_factory=dict)


def _leer_perfiles(carpeta: Path) -> dict[str, Perfil]:
    perfiles = {}
    for archivo in sorted(carpeta.glob("*.yaml")):
        try:
            perfil = Perfil.model_validate(yaml.safe_load(archivo.read_text(encoding="utf-8")) or {})
        except (yaml.YAMLError, ValidationError) as error:
            raise ErrorReglas(f"Perfil {archivo.name} inválido: {error}") from error
        perfiles[perfil.id] = perfil
    return perfiles


def listar_perfiles(carpeta: Path = RUTA_PERFILES) -> dict[str, str]:
    """Identificador -> nombre visible. 'generica' siempre existe."""
    perfiles = {p.id: p.nombre for p in _leer_perfiles(carpeta).values()}
    perfiles.setdefault("generica", "Genérica (sin ajustes de aseguradora)")
    return dict(sorted(perfiles.items(), key=lambda par: (par[0] != "generica", par[1])))


def cargar_perfil(perfil_id: str, carpeta: Path = RUTA_PERFILES) -> Perfil:
    perfiles = _leer_perfiles(carpeta)
    if perfil_id in perfiles:
        return perfiles[perfil_id]
    if perfil_id == "generica":
        return Perfil(id="generica", nombre="Genérica (sin ajustes de aseguradora)")
    raise ErrorReglas(f"El perfil de aseguradora '{perfil_id}' no existe.")


def aplicar_perfil(reglas: list[Regla], perfil: Perfil) -> list[Regla]:
    """Reglas efectivas: solo las activas y no desactivadas, con los ajustes del perfil."""
    ids = {r.id for r in reglas}
    desconocidas = (set(perfil.reglas_desactivadas) | set(perfil.ajustes)) - ids
    if desconocidas:
        raise ErrorReglas(f"El perfil '{perfil.id}' menciona reglas inexistentes: {', '.join(sorted(desconocidas))}")

    efectivas = []
    for regla in reglas:
        if not regla.activa or regla.id in perfil.reglas_desactivadas:
            continue
        ajuste = perfil.ajustes.get(regla.id)
        if ajuste:
            if ajuste.severidad and ajuste.severidad not in catalogos.SEVERIDADES:
                raise ErrorReglas(f"Perfil '{perfil.id}', {regla.id}: severidad inválida '{ajuste.severidad}'.")
            regla = regla.model_copy(
                update={
                    "severidad": ajuste.severidad or regla.severidad,
                    "parametros": {**regla.parametros, **ajuste.parametros},
                }
            )
        efectivas.append(regla)
    return efectivas
