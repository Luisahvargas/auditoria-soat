"""Repositorios: única vía de acceso a los datos.

La interfaz nunca escribe SQL directo; siempre pasa por estas clases.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from auditoria.db.modelos import RegistroTrazabilidad, Usuario


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
