"""Gestión del usuario activo y su trazabilidad.

Por ahora el usuario se selecciona o crea localmente, sin contraseña.
Toda acción relevante queda asociada a un usuario y una fecha.
"""

from sqlalchemy.orm import Session

from auditoria.db.modelos import Usuario
from auditoria.db.repositorios import RepositorioTrazabilidad, RepositorioUsuarios

LONGITUD_MAXIMA_NOMBRE = 120


class ErrorUsuario(ValueError):
    """Error de validación al crear o seleccionar un usuario."""


def listar_usuarios(sesion: Session) -> list[Usuario]:
    return RepositorioUsuarios(sesion).listar_activos()


def crear_usuario(sesion: Session, nombre: str) -> Usuario:
    """Crea un usuario nuevo y registra la acción. No hace commit."""
    nombre_limpio = " ".join((nombre or "").split())
    if not nombre_limpio:
        raise ErrorUsuario("El nombre del usuario no puede estar vacío.")
    if len(nombre_limpio) > LONGITUD_MAXIMA_NOMBRE:
        raise ErrorUsuario(f"El nombre no puede superar {LONGITUD_MAXIMA_NOMBRE} caracteres.")

    repositorio = RepositorioUsuarios(sesion)
    if repositorio.obtener_por_nombre(nombre_limpio):
        raise ErrorUsuario(f"Ya existe un usuario llamado '{nombre_limpio}'.")

    usuario = repositorio.agregar(Usuario(nombre=nombre_limpio))
    RepositorioTrazabilidad(sesion).registrar(usuario.id, "usuario_creado")
    return usuario


def registrar_seleccion(sesion: Session, usuario_id: int) -> None:
    """Deja constancia de que el usuario empezó a trabajar. No hace commit."""
    if RepositorioUsuarios(sesion).obtener_por_id(usuario_id) is None:
        raise ErrorUsuario("El usuario seleccionado no existe.")
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "usuario_seleccionado")
