"""Tablas de la base de datos (SQLAlchemy).

En esta fase solo existen las tablas mínimas: usuarios, auditorías y registro de
trazabilidad. No se guarda información clínica todavía.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def ahora() -> datetime:
    """Fecha y hora local del equipo (Colombia no tiene horario de verano)."""
    return datetime.now().replace(microsecond=0)


class Base(DeclarativeBase):
    """Clase base de todas las tablas."""


class Usuario(Base):
    """Auditor que usa el sistema. Por ahora sin contraseña (inicio de sesión real en fase 11)."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)


class Auditoria(Base):
    """Una auditoría corresponde a una sola cuenta médica de una sola víctima.

    Solo guarda un identificador interno y una descripción opcional; ningún dato personal.
    """

    __tablename__ = "auditorias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identificador: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(30), default="abierta", nullable=False)
    usuario_creador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)

    usuario_creador: Mapped[Usuario] = relationship()


class RegistroTrazabilidad(Base):
    """Quién hizo qué y cuándo. El detalle nunca debe contener datos clínicos ni personales."""

    __tablename__ = "registro_trazabilidad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    auditoria_id: Mapped[int | None] = mapped_column(ForeignKey("auditorias.id"), nullable=True)
    accion: Mapped[str] = mapped_column(String(60), nullable=False)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)

    usuario: Mapped[Usuario] = relationship()
