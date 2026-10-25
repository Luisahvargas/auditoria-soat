"""Servicio de auditorías.

Una auditoría solo guarda un identificador interno y una descripción opcional.
No se exigen datos personales para crearla.
"""

import re

from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.db.modelos import Auditoria
from auditoria.db.repositorios import RepositorioAuditorias, RepositorioTrazabilidad


class ErrorAuditoria(ValueError):
    """Error de validación sobre una auditoría."""


def listar_auditorias(sesion: Session) -> list[Auditoria]:
    return RepositorioAuditorias(sesion).listar()


def obtener_auditoria(sesion: Session, auditoria_id: int) -> Auditoria:
    auditoria = RepositorioAuditorias(sesion).obtener(auditoria_id)
    if auditoria is None:
        raise ErrorAuditoria("La auditoría no existe.")
    return auditoria


def crear_auditoria(
    sesion: Session, usuario_id: int, identificador: str, descripcion: str = "", perfil_aseguradora: str = "generica"
) -> Auditoria:
    """Crea una auditoría nueva. No hace commit."""
    identificador_limpio = (identificador or "").strip()
    if not identificador_limpio:
        raise ErrorAuditoria("El identificador interno es obligatorio.")
    if len(identificador_limpio) > 60 or not re.fullmatch(r"[\w\-./ ]+", identificador_limpio):
        raise ErrorAuditoria("El identificador solo admite letras, números, espacios, guiones, puntos y barras (máx. 60).")

    repositorio = RepositorioAuditorias(sesion)
    if repositorio.obtener_por_identificador(identificador_limpio):
        raise ErrorAuditoria(f"Ya existe una auditoría con el identificador '{identificador_limpio}'.")

    auditoria = repositorio.agregar(
        Auditoria(
            identificador=identificador_limpio,
            descripcion=(descripcion or "").strip() or None,
            perfil_aseguradora=perfil_aseguradora,
            usuario_creador_id=usuario_id,
        )
    )
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "auditoria_creada", auditoria_id=auditoria.id)
    return auditoria


def verificar_abierta(auditoria: Auditoria) -> None:
    """Las auditorías finalizadas no se modifican."""
    if auditoria.estado == catalogos.AUDITORIA_FINALIZADA:
        raise ErrorAuditoria("La auditoría está finalizada y no admite cambios.")


def cambiar_perfil(sesion: Session, auditoria_id: int, usuario_id: int, perfil: str) -> None:
    auditoria = obtener_auditoria(sesion, auditoria_id)
    verificar_abierta(auditoria)
    if auditoria.perfil_aseguradora != perfil:
        auditoria.perfil_aseguradora = perfil
        RepositorioTrazabilidad(sesion).registrar(usuario_id, "perfil_aseguradora_cambiado", perfil, auditoria_id)


def guardar_conclusion(sesion: Session, auditoria_id: int, usuario_id: int, conclusion: str, observaciones: str) -> None:
    """Guarda la conclusión y las observaciones del auditor (texto libre del auditor)."""
    auditoria = obtener_auditoria(sesion, auditoria_id)
    verificar_abierta(auditoria)
    auditoria.conclusion_auditor = (conclusion or "").strip() or None
    auditoria.observaciones_auditor = (observaciones or "").strip() or None
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "conclusion_guardada", auditoria_id=auditoria_id)
