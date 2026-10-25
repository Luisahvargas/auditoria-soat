"""Tablas de la base de datos (SQLAlchemy).

Todo registro relevante guarda usuario y fecha. Los archivos no se guardan en la
base de datos: solo su ruta dentro de la carpeta de datos y su hash SHA-256.
"""

import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from auditoria import catalogos


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
    estado: Mapped[str] = mapped_column(String(30), default=catalogos.AUDITORIA_ABIERTA, nullable=False)
    perfil_aseguradora: Mapped[str] = mapped_column(String(60), default="generica", nullable=False)
    conclusion_auditor: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones_auditor: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_creador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)
    usuario_finalizacion_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_finalizacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    usuario_creador: Mapped[Usuario] = relationship(foreign_keys=[usuario_creador_id])


class Documento(Base):
    """Archivo cargado a una auditoría (PDF, XML o JSON). El original nunca se modifica."""

    __tablename__ = "documentos"
    __table_args__ = (UniqueConstraint("auditoria_id", "hash_sha256", name="uq_documento_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("auditorias.id"), nullable=False)
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_archivo: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf, xml, json
    ruta_relativa: Mapped[str] = mapped_column(String(500), nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_paginas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(30), default=catalogos.PROC_PENDIENTE, nullable=False)
    mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_carga_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)

    paginas: Mapped[list["Pagina"]] = relationship(
        back_populates="documento", order_by="Pagina.numero", cascade="all, delete-orphan"
    )


class Pagina(Base):
    """Una página de un PDF. `numero` es SIEMPRE la página del archivo original (desde 1).

    `pagina_interna` es la numeración impresa en el documento (por ejemplo "2 de 5"), si se detecta.
    """

    __tablename__ = "paginas"
    __table_args__ = (UniqueConstraint("documento_id", "numero", name="uq_pagina_numero"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id"), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    pagina_interna: Mapped[str | None] = mapped_column(String(30), nullable=True)
    texto: Mapped[str] = mapped_column(Text, default="", nullable=False)  # Contenido NO confiable
    caracteres: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metodo_texto: Mapped[str] = mapped_column(String(20), default="Texto PDF", nullable=False)
    requiere_analisis_visual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legibilidad: Mapped[str] = mapped_column(String(20), default=catalogos.LEGIBILIDAD_SIN_EVALUAR, nullable=False)
    tipo_propuesto: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confianza_clasificacion: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tipo_confirmado: Mapped[str | None] = mapped_column(String(80), nullable=True)
    usuario_clasificacion_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_clasificacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    documento: Mapped[Documento] = relationship(back_populates="paginas")

    @property
    def tipo_efectivo(self) -> str | None:
        """La clasificación del auditor prevalece sobre la propuesta automática."""
        return self.tipo_confirmado or self.tipo_propuesto


class DatoFicha(Base):
    """Un valor de la ficha maestra con su origen y evidencia.

    Un mismo campo puede tener varios registros (uno por fuente). Nunca se sobrescribe
    en silencio: si el auditor corrige, se conserva el valor original y el corregido.
    """

    __tablename__ = "datos_ficha"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("auditorias.id"), nullable=False)
    campo: Mapped[str] = mapped_column(String(80), nullable=False)  # ej. "paciente.fecha_nacimiento"
    valor: Mapped[str] = mapped_column(Text, nullable=False)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documentos.id"), nullable=True)
    numero_pagina: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    metodo: Mapped[str] = mapped_column(String(20), nullable=False)
    confianza: Mapped[str | None] = mapped_column(String(10), nullable=True)
    estado_validacion: Mapped[str] = mapped_column(String(40), default=catalogos.VALIDACION_PENDIENTE, nullable=False)
    valor_corregido: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_validacion_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_validacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    usuario_creacion_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)

    documento: Mapped[Documento | None] = relationship()
    usuario_validacion: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_validacion_id])

    @property
    def valor_efectivo(self) -> str:
        return self.valor_corregido if self.valor_corregido is not None else self.valor


class EjecucionReglas(Base):
    """Cada vez que se ejecuta el motor de reglas sobre una auditoría."""

    __tablename__ = "ejecuciones_reglas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("auditorias.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    perfil_aseguradora: Mapped[str] = mapped_column(String(60), nullable=False)
    reglas_ejecutadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resumen_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)


class Hallazgo(Base):
    """Resultado de una regla, una sugerencia de IA o una conclusión del auditor."""

    __tablename__ = "hallazgos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("auditorias.id"), nullable=False)
    origen: Mapped[str] = mapped_column(String(40), nullable=False)
    regla_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    regla_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    clave: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Huella para no duplicar al re-ejecutar
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    categoria: Mapped[str] = mapped_column(String(80), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), nullable=False)
    estado_resultado: Mapped[str] = mapped_column(String(80), nullable=False)
    explicacion: Mapped[str] = mapped_column(Text, nullable=False)
    referencia_normativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidencias_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    detalle_ia_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado_revision: Mapped[str] = mapped_column(String(40), default=catalogos.REVISION_PENDIENTE, nullable=False)
    estado_resultado_auditor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    comentario_auditor: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_revision_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_revision: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ejecucion_id: Mapped[int | None] = mapped_column(ForeignKey("ejecuciones_reglas.id"), nullable=True)
    usuario_creacion_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)

    usuario_revision: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_revision_id])

    @property
    def evidencias(self) -> list[dict]:
        return json.loads(self.evidencias_json or "[]")

    @property
    def detalle_ia(self) -> dict | None:
        return json.loads(self.detalle_ia_json) if self.detalle_ia_json else None

    @property
    def estado_final(self) -> str:
        """Estado que vale tras la revisión: el del auditor si lo modificó."""
        return self.estado_resultado_auditor or self.estado_resultado


class ConsumoIA(Base):
    """Consumo de tokens por auditoría cuando se use una API de pago (hoy desactivada)."""

    __tablename__ = "consumo_ia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("auditorias.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    proveedor: Mapped[str] = mapped_column(String(30), nullable=False)
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_salida: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora, nullable=False)


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
