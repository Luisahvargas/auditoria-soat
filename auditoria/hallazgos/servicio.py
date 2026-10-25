"""Revisión humana de hallazgos y consulta con filtros.

Ningún hallazgo es definitivo por sí solo: el auditor lo confirma, descarta o
modifica, y queda registrado quién y cuándo (CLAUDE.md, principios 1, 10 y 11).
"""

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.servicio import obtener_auditoria, verificar_abierta
from auditoria.db.modelos import Hallazgo, ahora
from auditoria.db.repositorios import RepositorioHallazgos, RepositorioTrazabilidad


class ErrorHallazgo(ValueError):
    """Operación inválida sobre un hallazgo."""


@dataclass
class Filtros:
    solo_atencion: bool = True  # Principio 12: por defecto, solo lo que requiere atención
    categorias: list[str] | None = None
    severidades: list[str] | None = None
    estados: list[str] | None = None
    origenes: list[str] | None = None
    revision: list[str] | None = None


def listar(sesion: Session, auditoria_id: int, filtros: Filtros | None = None) -> list[Hallazgo]:
    filtros = filtros or Filtros()
    hallazgos = RepositorioHallazgos(sesion).listar_por_auditoria(auditoria_id)

    def pasa(h: Hallazgo) -> bool:
        if filtros.solo_atencion and h.estado_final not in catalogos.ESTADOS_QUE_REQUIEREN_ATENCION:
            return False
        if filtros.categorias and h.categoria not in filtros.categorias:
            return False
        if filtros.severidades and h.severidad not in filtros.severidades:
            return False
        if filtros.estados and h.estado_final not in filtros.estados:
            return False
        if filtros.origenes and h.origen not in filtros.origenes:
            return False
        if filtros.revision and h.estado_revision not in filtros.revision:
            return False
        return True

    orden_severidad = {s: i for i, s in enumerate(catalogos.SEVERIDADES)}
    orden_estado = {s: i for i, s in enumerate(catalogos.ESTADOS_RESULTADO)}
    return sorted(
        (h for h in hallazgos if pasa(h)),
        key=lambda h: (orden_estado.get(h.estado_final, 99), orden_severidad.get(h.severidad, 9), h.id),
    )


def _editable(sesion: Session, hallazgo_id: int) -> Hallazgo:
    hallazgo = RepositorioHallazgos(sesion).obtener(hallazgo_id)
    if hallazgo is None:
        raise ErrorHallazgo("El hallazgo no existe.")
    verificar_abierta(obtener_auditoria(sesion, hallazgo.auditoria_id))
    return hallazgo


def revisar(
    sesion: Session,
    hallazgo_id: int,
    usuario_id: int,
    decision: str,
    comentario: str = "",
    nuevo_estado: str | None = None,
) -> Hallazgo:
    """El auditor confirma, descarta o modifica un hallazgo. No hace commit.

    - Descartar o modificar exige un comentario que explique el motivo.
    - Modificar exige el nuevo estado de resultado.
    """
    if decision not in (catalogos.REVISION_CONFIRMADO, catalogos.REVISION_DESCARTADO, catalogos.REVISION_MODIFICADO):
        raise ErrorHallazgo(f"Decisión inválida: {decision}")
    comentario = (comentario or "").strip()
    if decision != catalogos.REVISION_CONFIRMADO and not comentario:
        raise ErrorHallazgo("Explique el motivo en el comentario para descartar o modificar un hallazgo.")
    if decision == catalogos.REVISION_MODIFICADO and nuevo_estado not in catalogos.ESTADOS_RESULTADO:
        raise ErrorHallazgo("Indique el nuevo estado de resultado.")

    hallazgo = _editable(sesion, hallazgo_id)
    hallazgo.estado_revision = decision
    hallazgo.comentario_auditor = comentario or None
    hallazgo.estado_resultado_auditor = nuevo_estado if decision == catalogos.REVISION_MODIFICADO else None
    hallazgo.usuario_revision_id = usuario_id
    hallazgo.fecha_revision = ahora()
    RepositorioTrazabilidad(sesion).registrar(
        usuario_id, "hallazgo_revisado", f"hallazgo_id={hallazgo.id}; decision={decision}", hallazgo.auditoria_id
    )
    return hallazgo


def reabrir(sesion: Session, hallazgo_id: int, usuario_id: int) -> Hallazgo:
    """Devuelve un hallazgo a 'pendiente de revisión humana'. No hace commit."""
    hallazgo = _editable(sesion, hallazgo_id)
    hallazgo.estado_revision = catalogos.REVISION_PENDIENTE
    hallazgo.estado_resultado_auditor = None
    hallazgo.usuario_revision_id = usuario_id
    hallazgo.fecha_revision = ahora()
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "hallazgo_reabierto", f"hallazgo_id={hallazgo.id}", hallazgo.auditoria_id)
    return hallazgo


def agregar_hallazgo_auditor(
    sesion: Session,
    auditoria_id: int,
    usuario_id: int,
    titulo: str,
    categoria: str,
    severidad: str,
    estado_resultado: str,
    explicacion: str,
    evidencias: list[dict] | None = None,
) -> Hallazgo:
    """Hallazgo propio del auditor (origen: conclusión del auditor). Queda confirmado. No hace commit."""
    verificar_abierta(obtener_auditoria(sesion, auditoria_id))
    if not (titulo or "").strip() or not (explicacion or "").strip():
        raise ErrorHallazgo("El título y la explicación son obligatorios.")
    if severidad not in catalogos.SEVERIDADES or estado_resultado not in catalogos.ESTADOS_RESULTADO:
        raise ErrorHallazgo("Severidad o estado de resultado inválidos.")
    hallazgo = RepositorioHallazgos(sesion).agregar(
        Hallazgo(
            auditoria_id=auditoria_id,
            origen=catalogos.ORIGEN_AUDITOR,
            titulo=titulo.strip()[:255],
            categoria=(categoria or "Otra").strip(),
            severidad=severidad,
            estado_resultado=estado_resultado,
            explicacion=explicacion.strip(),
            evidencias_json=json.dumps(evidencias or [], ensure_ascii=False),
            estado_revision=catalogos.REVISION_CONFIRMADO,
            usuario_revision_id=usuario_id,
            fecha_revision=ahora(),
            usuario_creacion_id=usuario_id,
        )
    )
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "hallazgo_auditor_creado", f"hallazgo_id={hallazgo.id}", auditoria_id)
    return hallazgo


def pendientes_de_revision(sesion: Session, auditoria_id: int) -> list[Hallazgo]:
    """Hallazgos que requieren atención y que el auditor aún no ha revisado."""
    return [
        h
        for h in RepositorioHallazgos(sesion).listar_por_auditoria(auditoria_id)
        if h.estado_revision == catalogos.REVISION_PENDIENTE and h.estado_final in catalogos.ESTADOS_QUE_REQUIEREN_ATENCION
    ]
