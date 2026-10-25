"""Resumen único de la auditoría.

La pantalla de resumen, el Excel y el informe PDF se construyen con este mismo
resumen, para que lo exportado coincida con lo que se ve en pantalla.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.cierre import Requisito, requisitos_de_cierre
from auditoria.auditorias.servicio import obtener_auditoria
from auditoria.db.modelos import Hallazgo
from auditoria.db.repositorios import (
    RepositorioConsumoIA,
    RepositorioDocumentos,
    RepositorioHallazgos,
    RepositorioUsuarios,
)
from auditoria.extraccion import ficha as servicio_ficha
from auditoria.extraccion.extractor import cargar_definicion
from auditoria.hallazgos.servicio import Filtros, listar


@dataclass
class FilaDocumento:
    archivo: str
    tipo: str
    estado: str
    paginas: int | None
    sin_texto: int
    sin_confirmar: int
    ilegibles: int
    hash_sha256: str
    fecha_carga: datetime
    mensaje: str


@dataclass
class FilaFicha:
    bloque: str
    campo: str
    valores: str
    fuentes: int
    discrepancia: bool
    corregidos: int


@dataclass
class FilaHallazgo:
    id: int
    origen: str
    regla: str
    titulo: str
    categoria: str
    severidad: str
    estado_resultado: str
    estado_final: str
    requiere_atencion: bool
    revision: str
    revisor: str
    fecha_revision: datetime | None
    comentario: str
    explicacion: str
    referencia_normativa: str
    evidencias: list[dict]


@dataclass
class ResumenAuditoria:
    identificador: str
    descripcion: str
    perfil_aseguradora: str
    estado: str
    creada_por: str
    fecha_creacion: datetime
    finalizada_por: str
    fecha_finalizacion: datetime | None
    conclusion_auditor: str
    observaciones_auditor: str
    documentos: list[FilaDocumento]
    ficha: list[FilaFicha]
    edad_al_accidente: str
    ultima_ejecucion: str
    reglas_ejecutadas: int
    resultados_por_estado: dict[str, int]
    hallazgos: list[FilaHallazgo]
    requisitos: list[Requisito]
    tokens_ia: tuple[int, int]
    generado: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))

    @property
    def finalizada(self) -> bool:
        return self.estado == catalogos.AUDITORIA_FINALIZADA

    @property
    def hallazgos_atencion(self) -> list[FilaHallazgo]:
        return [h for h in self.hallazgos if h.requiere_atencion]

    @property
    def hubo_ia(self) -> bool:
        return any(h.origen == catalogos.ORIGEN_IA for h in self.hallazgos)

    @property
    def no_evaluables(self) -> list[FilaHallazgo]:
        return [h for h in self.hallazgos if h.estado_final == catalogos.NO_EVALUABLE]

    def contar(self, origen: str | None = None, revision: str | None = None, solo_atencion: bool = True) -> int:
        return sum(
            1
            for h in (self.hallazgos_atencion if solo_atencion else self.hallazgos)
            if (origen is None or h.origen == origen) and (revision is None or h.revision == revision)
        )


def _fila_hallazgo(h: Hallazgo) -> FilaHallazgo:
    return FilaHallazgo(
        id=h.id,
        origen=h.origen,
        regla=f"{h.regla_id} v{h.regla_version}" if h.regla_id else "",
        titulo=h.titulo,
        categoria=h.categoria,
        severidad=h.severidad,
        estado_resultado=h.estado_resultado,
        estado_final=h.estado_final,
        requiere_atencion=h.estado_final in catalogos.ESTADOS_QUE_REQUIEREN_ATENCION,
        revision=h.estado_revision,
        revisor=h.usuario_revision.nombre if h.usuario_revision else "",
        fecha_revision=h.fecha_revision,
        comentario=h.comentario_auditor or "",
        explicacion=h.explicacion,
        referencia_normativa=h.referencia_normativa or "",
        evidencias=h.evidencias,
    )


def construir_resumen(sesion: Session, auditoria_id: int) -> ResumenAuditoria:
    auditoria = obtener_auditoria(sesion, auditoria_id)
    usuarios = RepositorioUsuarios(sesion)
    documentos = RepositorioDocumentos(sesion).listar_por_auditoria(auditoria_id, con_paginas=True)
    ficha = servicio_ficha.construir_ficha(sesion, auditoria_id)
    definicion = cargar_definicion()
    ultima = RepositorioHallazgos(sesion).ultima_ejecucion(auditoria_id)
    finalizador = usuarios.obtener_por_id(auditoria.usuario_finalizacion_id) if auditoria.usuario_finalizacion_id else None

    return ResumenAuditoria(
        identificador=auditoria.identificador,
        descripcion=auditoria.descripcion or "",
        perfil_aseguradora=auditoria.perfil_aseguradora,
        estado=auditoria.estado,
        creada_por=auditoria.usuario_creador.nombre,
        fecha_creacion=auditoria.fecha_creacion,
        finalizada_por=finalizador.nombre if finalizador else "",
        fecha_finalizacion=auditoria.fecha_finalizacion,
        conclusion_auditor=auditoria.conclusion_auditor or "",
        observaciones_auditor=auditoria.observaciones_auditor or "",
        documentos=[
            FilaDocumento(
                archivo=d.nombre_original,
                tipo=d.tipo_archivo.upper(),
                estado=d.estado,
                paginas=d.numero_paginas,
                sin_texto=sum(p.requiere_analisis_visual for p in d.paginas),
                sin_confirmar=sum(not p.tipo_confirmado for p in d.paginas),
                ilegibles=sum(p.legibilidad == catalogos.NO_LEGIBLE for p in d.paginas),
                hash_sha256=d.hash_sha256,
                fecha_carga=d.fecha_carga,
                mensaje=d.mensaje or "",
            )
            for d in documentos
        ],
        ficha=[
            FilaFicha(
                bloque=definicion.bloques[bloque],
                campo=e.campo.etiqueta,
                valores=" | ".join(v.mostrar for v in e.valores),
                fuentes=sum(len(v.datos) for v in e.valores),
                discrepancia=e.discrepancia,
                corregidos=sum(d.valor_corregido is not None for v in e.valores for d in v.datos),
            )
            for bloque, estados in ficha.items()
            for e in estados
        ],
        edad_al_accidente=servicio_ficha.edad_al_accidente(ficha).explicacion,
        ultima_ejecucion=f"{ultima.fecha:%Y-%m-%d %H:%M} (perfil {ultima.perfil_aseguradora})" if ultima else "No se ha ejecutado",
        reglas_ejecutadas=ultima.reglas_ejecutadas if ultima else 0,
        resultados_por_estado=json.loads(ultima.resumen_json) if ultima else {},
        hallazgos=[_fila_hallazgo(h) for h in listar(sesion, auditoria_id, Filtros(solo_atencion=False))],
        requisitos=requisitos_de_cierre(sesion, auditoria_id),
        tokens_ia=RepositorioConsumoIA(sesion).totales_por_auditoria(auditoria_id),
    )


def lineas_evidencia(resumen: ResumenAuditoria) -> list[dict]:
    """Referencias de evidencia por archivo y página (para la hoja de evidencias)."""
    filas = []
    for h in resumen.hallazgos:
        for e in h.evidencias:
            filas.append(
                {
                    "hallazgo": h.id,
                    "origen": h.origen,
                    "estado": h.estado_final,
                    "archivo": e.get("archivo") or "",
                    "pagina": e.get("pagina"),
                    "texto": e.get("texto") or "",
                }
            )
    return sorted(filas, key=lambda f: (f["archivo"], f["pagina"] or 0, f["hallazgo"]))
