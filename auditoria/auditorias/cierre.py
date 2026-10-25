"""Cierre de la auditoría: requisitos obligatorios, finalización y reapertura.

La auditoría solo se puede finalizar cuando el auditor completó los pasos obligatorios.
Finalizar no genera glosas ni rechaza la cuenta: deja constancia de la revisión.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.servicio import ErrorAuditoria, obtener_auditoria, verificar_abierta
from auditoria.db.modelos import ahora
from auditoria.db.repositorios import RepositorioDocumentos, RepositorioHallazgos, RepositorioTrazabilidad
from auditoria.hallazgos.servicio import pendientes_de_revision


@dataclass
class Requisito:
    nombre: str
    cumplido: bool
    detalle: str
    obligatorio: bool = True


def requisitos_de_cierre(sesion: Session, auditoria_id: int) -> list[Requisito]:
    auditoria = obtener_auditoria(sesion, auditoria_id)
    documentos = RepositorioDocumentos(sesion).listar_por_auditoria(auditoria_id, con_paginas=True)
    ultima = RepositorioHallazgos(sesion).ultima_ejecucion(auditoria_id)
    pendientes = pendientes_de_revision(sesion, auditoria_id)
    en_proceso = [d for d in documentos if d.estado == catalogos.PROC_EN_CURSO]
    ultima_carga = max((d.fecha_carga for d in documentos), default=None)
    sin_texto = sum(p.requiere_analisis_visual for d in documentos for p in d.paginas)
    con_error = [d for d in documentos if d.estado in (catalogos.PROC_ERROR, catalogos.PROC_PENDIENTE)]

    return [
        Requisito("Documentos cargados", bool(documentos), f"{len(documentos)} archivo(s)." if documentos else "No hay documentos cargados."),
        Requisito(
            "Sin documentos en procesamiento",
            not en_proceso,
            "Ninguno." if not en_proceso else f"{len(en_proceso)} archivo(s) siguen en procesamiento.",
        ),
        Requisito(
            "Análisis automático actualizado",
            bool(ultima and ultima_carga and ultima.fecha >= ultima_carga),
            "Ejecutado después de la última carga."
            if ultima and ultima_carga and ultima.fecha >= ultima_carga
            else "Ejecute el análisis automático después de cargar todos los documentos.",
        ),
        Requisito(
            "Hallazgos revisados por el auditor",
            not pendientes,
            "Todos revisados." if not pendientes else f"{len(pendientes)} hallazgo(s) que requieren atención siguen pendientes de revisión.",
        ),
        Requisito(
            "Conclusión del auditor registrada",
            bool(auditoria.conclusion_auditor),
            "Registrada." if auditoria.conclusion_auditor else "Escriba la conclusión del auditor.",
        ),
        Requisito(
            "Páginas sin texto revisadas visualmente",
            sin_texto == 0,
            "No hay páginas sin texto." if sin_texto == 0 else f"{sin_texto} página(s) no fueron revisadas por las reglas: confirme que las revisó visualmente.",
            obligatorio=False,
        ),
        Requisito(
            "Archivos leídos",
            not con_error,
            "Todos los archivos se leyeron." if not con_error else f"{len(con_error)} archivo(s) pendientes de lector o con error de lectura.",
            obligatorio=False,
        ),
    ]


def finalizar(sesion: Session, auditoria_id: int, usuario_id: int) -> None:
    """Marca la auditoría como finalizada si cumple los requisitos obligatorios. No hace commit."""
    auditoria = obtener_auditoria(sesion, auditoria_id)
    verificar_abierta(auditoria)
    faltantes = [r for r in requisitos_de_cierre(sesion, auditoria_id) if r.obligatorio and not r.cumplido]
    if faltantes:
        raise ErrorAuditoria("No se puede finalizar: " + " ".join(f"{r.nombre}: {r.detalle}" for r in faltantes))
    auditoria.estado = catalogos.AUDITORIA_FINALIZADA
    auditoria.usuario_finalizacion_id = usuario_id
    auditoria.fecha_finalizacion = ahora()
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "auditoria_finalizada", auditoria_id=auditoria_id)


def reabrir(sesion: Session, auditoria_id: int, usuario_id: int, motivo: str) -> None:
    """Reabre una auditoría finalizada; exige motivo y queda registrado. No hace commit."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorAuditoria("Indique el motivo para reabrir la auditoría.")
    auditoria = obtener_auditoria(sesion, auditoria_id)
    if auditoria.estado != catalogos.AUDITORIA_FINALIZADA:
        raise ErrorAuditoria("La auditoría no está finalizada.")
    auditoria.estado = catalogos.AUDITORIA_ABIERTA
    auditoria.usuario_finalizacion_id = None
    auditoria.fecha_finalizacion = None
    # El motivo es texto del auditor; se guarda recortado y sin datos del documento.
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "auditoria_reabierta", f"motivo={motivo[:200]}", auditoria_id)
