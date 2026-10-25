"""Conexión a la base de datos.

Para migrar a PostgreSQL basta con cambiar URL_BASE_DATOS en .env.
"""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from auditoria.db.modelos import Base


def crear_motor(url_base_datos: str) -> Engine:
    """Crea el motor de conexión. En SQLite activa las claves foráneas."""
    es_sqlite = url_base_datos.startswith("sqlite")
    argumentos = {"check_same_thread": False} if es_sqlite else {}
    motor = create_engine(url_base_datos, connect_args=argumentos)

    if es_sqlite:
        @event.listens_for(motor, "connect")
        def _activar_claves_foraneas(conexion, _registro):
            cursor = conexion.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return motor


def inicializar_base_datos(motor: Engine) -> None:
    """Crea las tablas que no existan. No borra ni modifica datos existentes."""
    Base.metadata.create_all(motor)


def crear_fabrica_sesiones(motor: Engine) -> sessionmaker[Session]:
    """Devuelve una fábrica de sesiones. Usar con: `with fabrica() as sesion: ...`"""
    return sessionmaker(bind=motor, expire_on_commit=False)
