"""Prueba de la pantalla de Streamlit con una cuenta FICTICIA."""

from streamlit.testing.v1 import AppTest

from auditoria.config import RAIZ_PROYECTO
from pruebas import generadores


def test_app_arranca_sin_archivos():
    app = AppTest.from_file(str(RAIZ_PROYECTO / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "Auditoría de cuenta SOAT"


def test_app_audita_y_muestra_texto_para_copiar(monkeypatch):
    from auditoria.config import cargar_configuracion
    from auditoria.revision import auditar

    resultado = auditar([("cuenta.pdf", generadores.cuenta_ficticia(factura="FE-2002"))], cargar_configuracion())
    app = AppTest.from_file(str(RAIZ_PROYECTO / "app.py"), default_timeout=60)
    app.session_state["resultado"] = resultado
    app.run()
    assert not app.exception
    assert "ERRORES ENCONTRADOS" in app.code[0].value
    assert any(m.label == "❌ Errores" and m.value == "1" for m in app.metric)
