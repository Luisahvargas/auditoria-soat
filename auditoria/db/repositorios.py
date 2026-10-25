"""Repositorios: única vía de acceso a los datos.

La interfaz nunca escribe SQL directo; siempre pasa por estas clases.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from auditoria.db.modelos import (
    Auditoria,
    ConsumoIA,
    DatoFicha,
    Documento,
    EjecucionReglas,
    Hallazgo,
    Pagina,
    RegistroTrazabilidad,
    Usuario,
)


class RepositorioUsuarios:
    """Consultas y altas de usuarios."""

    def __init__(self, sesion: Session):
        self.sesion = sesion

    def listar_activos(self) -> list[Usuario]:
        consulta = select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre)
        return list(self.sesion.scalars(consulta))

    def obtener_por_id(self, usuario_id: int) -> Usuario | None:
        return self.sesion.get(Usuario, usuario_id)

    def obtener_por_nombre(self, nombre: str) -> Usuario | None:
        return self.sesion.scalars(select(Usuario).where(Usuario.nombre == nombre)).first()

    def agregar(self, usuario: Usuario) -> Usuario:
        self.sesion.add(usuario)
        self.sesion.flush()
        return usuario


class RepositorioAuditorias:
    """Consultas y altas de auditorías."""

    def __init__(self, sesion: Session):
        self.sesion = sesion

    def listar(self) -> list[Auditoria]:
        return list(self.sesion.scalars(select(Auditoria).order_by(Auditoria.fecha_creacion.desc(), Auditoria.id.desc())))

    def obtener(self, auditoria_id: int) -> Auditoria | None:
        return self.sesion.get(Auditoria, auditoria_id)

    def obtener_por_identificador(self, identificador: str) -> Auditoria | None:
        return self.sesion.scalars(select(Auditoria).where(Auditoria.identificador == identificador)).first()

    def agregar(self, auditoria: Auditoria) -> Auditoria:
        self.sesion.add(auditoria)
        self.sesion.flush()
        return auditoria


class RepositorioDocumentos:
    """Documentos cargados y sus páginas."""

    def __init__(self, sesion: Session):
        self.sesion = sesion

    def agregar(self, documento: Documento) -> Documento:
        self.sesion.add(documento)
        self.sesion.flush()
        return documento

    def obtener(self, documento_id: int) -> Documento | None:
        return self.sesion.get(Documento, documento_id)

    def obtener_por_hash(self, auditoria_id: int, hash_sha256: str) -> Documento | None:
        consulta = select(Documento).where(
            Documento.auditoria_id == auditoria_id, Documento.hash_sha256 == hash_sha256
        )
        return self.sesion.scalars(consulta).first()

    def listar_por_auditoria(self, auditoria_id: int, con_paginas: bool = False) -> list[Documento]:
        consulta = select(Documento).where(Documento.auditoria_id == auditoria_id).order_by(Documento.id)
        if con_paginas:
            consulta = consulta.options(selectinload(Documento.paginas))
        return list(self.sesion.scalars(consulta))

    def obtener_pagina(self, pagina_id: int) -> Pagina | None:
        return self.sesion.get(Pagina, pagina_id)

    def obtener_pagina_por_numero(self, documento_id: int, numero: int) -> Pagina | None:
        consulta = select(Pagina).where(Pagina.documento_id == documento_id, Pagina.numero == numero)
        return self.sesion.scalars(consulta).first()

    def listar_paginas_por_auditoria(self, auditoria_id: int) -> list[Pagina]:
        consulta = (
            select(Pagina)
            .join(Documento)
            .where(Documento.auditoria_id == auditoria_id)
            .options(selectinload(Pagina.documento))
            .order_by(Documento.id, Pagina.numero)
        )
        return list(self.sesion.scalars(consulta))


class RepositorioFicha:
    """Datos de la ficha maestra."""

    def __init__(self, sesion: Session):
        self.sesion = sesion

    def agregar(self, dato: DatoFicha) -> DatoFicha:
        self.sesion.add(dato)
        self.sesion.flush()
        return dato

    def obtener(self, dato_id: int) -> DatoFicha | None:
        return self.sesion.get(DatoFicha, dato_id)

    def listar_por_auditoria(self, auditoria_id: int) -> list[DatoFicha]:
        consulta = (
            select(DatoFicha)
            .where(DatoFicha.auditoria_id == auditoria_id)
            .options(selectinload(DatoFicha.documento))
            .order_by(DatoFicha.campo, DatoFicha.id)
        )
        return list(self.sesion.scalars(consulta))

    def borrar_automaticos_sin_revisar(self, auditoria_id: int, metodos: tuple[str, ...], estado_pendiente: str) -> int:
        """Borra datos extraídos automáticamente que el auditor aún no ha revisado (para re-extraer)."""
        resultado = self.sesion.execute(
            delete(DatoFicha).where(
                DatoFicha.auditoria_id == auditoria_id,
                DatoFicha.metodo.in_(metodos),
                DatoFicha.estado_validacion == estado_pendiente,
            )
        )
        return resultado.rowcount or 0


class RepositorioHallazgos:
    """Hallazgos de reglas, IA y auditor, y ejecuciones del motor de reglas."""

    def __init__(self, sesion: Session):
        self.sesion = sesion

    def agregar(self, hallazgo: Hallazgo) -> Hallazgo:
        self.sesion.add(hallazgo)
        self.sesion.flush()
        return hallazgo

    def obtener(self, hallazgo_id: int) -> Hallazgo | None:
        return self.sesion.get(Hallazgo, hallazgo_id)

    def listar_por_auditoria(self, auditoria_id: int, origen: str | None = None) -> list[Hallazgo]:
        consulta = select(Hallazgo).where(Hallazgo.auditoria_id == auditoria_id)
        if origen:
            consulta = consulta.where(Hallazgo.origen == origen)
        return list(self.sesion.scalars(consulta.order_by(Hallazgo.id)))

    def borrar_por_ids(self, ids: list[int]) -> None:
        if ids:
            self.sesion.execute(delete(Hallazgo).where(Hallazgo.id.in_(ids)))

    def agregar_ejecucion(self, ejecucion: EjecucionReglas) -> EjecucionReglas:
        self.sesion.add(ejecucion)
        self.sesion.flush()
        return ejecucion

    def ultima_ejecucion(self, auditoria_id: int) -> EjecucionReglas | None:
        consulta = (
            select(EjecucionReglas)
            .where(EjecucionReglas.auditoria_id == auditoria_id)
            .order_by(EjecucionReglas.fecha.desc(), EjecucionReglas.id.desc())
        )
        return self.sesion.scalars(consulta).first()


class RepositorioConsumoIA:
    """Registro de consumo de tokens (solo aplica a proveedores de pago, hoy desactivados)."""

    def __init__(self, sesion: Session):
        self.sesion = sesion

    def agregar(self, consumo: ConsumoIA) -> ConsumoIA:
        self.sesion.add(consumo)
        self.sesion.flush()
        return consumo

    def totales_por_auditoria(self, auditoria_id: int) -> tuple[int, int]:
        fila = self.sesion.execute(
            select(func.coalesce(func.sum(ConsumoIA.tokens_entrada), 0), func.coalesce(func.sum(ConsumoIA.tokens_salida), 0))
            .where(ConsumoIA.auditoria_id == auditoria_id)
        ).one()
        return int(fila[0]), int(fila[1])


class RepositorioTrazabilidad:
    """Registro de acciones de los usuarios."""

    def __init__(self, sesion: Session):
        self.sesion = sesion

    def registrar(
        self,
        usuario_id: int,
        accion: str,
        detalle: str | None = None,
        auditoria_id: int | None = None,
    ) -> RegistroTrazabilidad:
        registro = RegistroTrazabilidad(
            usuario_id=usuario_id, accion=accion, detalle=detalle, auditoria_id=auditoria_id
        )
        self.sesion.add(registro)
        self.sesion.flush()
        return registro

    def listar_por_usuario(self, usuario_id: int) -> list[RegistroTrazabilidad]:
        consulta = (
            select(RegistroTrazabilidad)
            .where(RegistroTrazabilidad.usuario_id == usuario_id)
            .order_by(RegistroTrazabilidad.fecha, RegistroTrazabilidad.id)
        )
        return list(self.sesion.scalars(consulta))

    def listar_por_auditoria(self, auditoria_id: int) -> list[RegistroTrazabilidad]:
        consulta = (
            select(RegistroTrazabilidad)
            .where(RegistroTrazabilidad.auditoria_id == auditoria_id)
            .options(selectinload(RegistroTrazabilidad.usuario))
            .order_by(RegistroTrazabilidad.fecha.desc(), RegistroTrazabilidad.id.desc())
        )
        return list(self.sesion.scalars(consulta))
