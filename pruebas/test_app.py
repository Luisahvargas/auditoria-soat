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
    assert [t.label for t in app.tabs][0] == "❌ Errores (1)"
    # El error se muestra como tarjeta roja con el nombre del punto.
    assert any("Número de factura" in e.value for e in app.error)


def test_detalle_en_vinetas():
    """El detalle 'A | B | C' se muestra como lista (solo se cargan las funciones auxiliares de app.py)."""
    codigo = (RAIZ_PROYECTO / "app.py").read_text(encoding="utf-8")
    espacio: dict = {}
    exec(codigo.split("# ------")[0], espacio)
    resultado = espacio["detalle_en_vinetas"]("No coincide. FURIPS: «01/10/2026» (folio 1) | SIRAS: «30/09/2026» (folio 141).")
    assert resultado.startswith("**No coincide\\.**")
    assert "\n- FURIPS: «01/10/2026» \\(folio 1\\)" in resultado
    assert "\n- SIRAS:" in resultado
