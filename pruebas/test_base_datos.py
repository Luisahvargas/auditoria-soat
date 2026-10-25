"""Pruebas de la base de datos y de los usuarios locales.

Usan una base temporal; los nombres son ficticios.
"""

import pytest
from sqlalchemy import inspect

from auditoria.config import cargar_configuracion
from auditoria.db.repositorios import RepositorioTrazabilidad
from auditoria.db.sesion import crear_fabrica_sesiones, crear_motor, inicializar_base_datos
from auditoria.usuarios import servicio


@pytest.fixture
def fabrica(tmp_path):
    motor = crear_motor(f"sqlite:///{(tmp_path / 'prueba.db').as_posix()}")
    inicializar_base_datos(motor)
    yield crear_fabrica_sesiones(motor)
    motor.dispose()


def test_se_crean_las_tablas_minimas(tmp_path):
    archivo = tmp_path / "prueba.db"
    motor = crear_motor(f"sqlite:///{archivo.as_posix()}")
    inicializar_base_datos(motor)

    assert archivo.exists()
    assert {"usuarios", "auditorias", "registro_trazabilidad"} <= set(inspect(motor).get_table_names())
    motor.dispose()


def test_inicializar_dos_veces_no_borra_datos(tmp_path):
    url = f"sqlite:///{(tmp_path / 'prueba.db').as_posix()}"
    motor = crear_motor(url)
    inicializar_base_datos(motor)
    with crear_fabrica_sesiones(motor)() as sesion:
        servicio.crear_usuario(sesion, "Auditor Ficticio Uno")
        sesion.commit()

    inicializar_base_datos(motor)
    with crear_fabrica_sesiones(motor)() as sesion:
        assert [u.nombre for u in servicio.listar_usuarios(sesion)] == ["Auditor Ficticio Uno"]
    motor.dispose()


def test_crear_usuario_queda_en_trazabilidad(fabrica):
    with fabrica() as sesion:
        usuario = servicio.crear_usuario(sesion, "  Auditor   Ficticio  ")
        servicio.registrar_seleccion(sesion, usuario.id)
        sesion.commit()

        assert usuario.nombre == "Auditor Ficticio"
        registros = RepositorioTrazabilidad(sesion).listar_por_usuario(usuario.id)
        assert [r.accion for r in registros] == ["usuario_creado", "usuario_seleccionado"]
        assert all(r.fecha is not None for r in registros)


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 121])
def test_nombre_de_usuario_invalido(fabrica, nombre):
    with fabrica() as sesion, pytest.raises(servicio.ErrorUsuario):
        servicio.crear_usuario(sesion, nombre)


def test_no_se_permiten_usuarios_duplicados(fabrica):
    with fabrica() as sesion:
        servicio.crear_usuario(sesion, "Auditor Ficticio")
        with pytest.raises(servicio.ErrorUsuario):
            servicio.crear_usuario(sesion, "Auditor Ficticio")


def test_seleccionar_usuario_inexistente(fabrica):
    with fabrica() as sesion, pytest.raises(servicio.ErrorUsuario):
        servicio.registrar_seleccion(sesion, 999)


def test_configuracion_por_defecto_sin_ia(monkeypatch, tmp_path):
    for variable in ("RUTA_DATOS", "URL_BASE_DATOS", "PROVEEDOR_IA", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    config = cargar_configuracion(tmp_path / "no_existe.env")

    assert config.proveedor_ia == "desactivado"
    assert not config.ia_anthropic_disponible
    assert config.url_base_datos.startswith("sqlite:///")
    assert config.url_base_datos.endswith("datos/auditoria.db")


def test_proveedor_ia_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVEEDOR_IA", "otro")
    with pytest.raises(ValueError):
        cargar_configuracion(tmp_path / "no_existe.env")
