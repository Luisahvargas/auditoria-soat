"""Elementos comunes de las pruebas: base de datos y carpeta de datos temporales."""

import pytest

from auditoria.auditorias import servicio as servicio_auditorias
from auditoria.config import Configuracion
from auditoria.db.sesion import crear_fabrica_sesiones, crear_motor, inicializar_base_datos
from auditoria.usuarios import servicio as servicio_usuarios


@pytest.fixture
def config_temporal(tmp_path) -> Configuracion:
    ruta = tmp_path / "datos"
    ruta.mkdir()
    return Configuracion(
        ruta_datos=ruta,
        url_base_datos=f"sqlite:///{(ruta / 'prueba.db').as_posix()}",
        proveedor_ia="desactivado",
        anthropic_api_key="",
        anthropic_modelo="",
    )


@pytest.fixture
def fabrica(config_temporal):
    motor = crear_motor(config_temporal.url_base_datos)
    inicializar_base_datos(motor)
    yield crear_fabrica_sesiones(motor)
    motor.dispose()


@pytest.fixture
def sesion(fabrica):
    with fabrica() as sesion:
        yield sesion


@pytest.fixture
def usuario_y_auditoria(sesion):
    """Usuario y auditoría ficticios. Devuelve (usuario_id, auditoria_id)."""
    usuario = servicio_usuarios.crear_usuario(sesion, "Auditor Ficticio")
    auditoria = servicio_auditorias.crear_auditoria(sesion, usuario.id, "PRUEBA-001")
    sesion.commit()
    return usuario.id, auditoria.id
