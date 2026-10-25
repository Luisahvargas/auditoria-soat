"""Prueba de arranque de la interfaz Streamlit con una carpeta de datos temporal."""

from streamlit.testing.v1 import AppTest

from auditoria.config import RAIZ_PROYECTO


def test_app_arranca_y_permite_crear_usuario(monkeypatch, tmp_path):
    monkeypatch.setenv("RUTA_DATOS", str(tmp_path))
    monkeypatch.setenv("URL_BASE_DATOS", "")
    monkeypatch.setenv("PROVEEDOR_IA", "desactivado")

    app = AppTest.from_file(str(RAIZ_PROYECTO / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Auditoría de cuentas médicas SOAT"
    assert (tmp_path / "auditoria.db").exists()

    # Crear un usuario ficticio desde el formulario de la barra lateral.
    app.sidebar.text_input[0].input("Auditor Ficticio Prueba")
    app.sidebar.button[0].click().run()

    assert not app.exception
    assert app.session_state["usuario_activo"]["nombre"] == "Auditor Ficticio Prueba"
