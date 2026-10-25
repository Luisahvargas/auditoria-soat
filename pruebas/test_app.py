"""Pruebas de la interfaz Streamlit con una carpeta de datos temporal (datos ficticios)."""

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from auditoria.config import RAIZ_PROYECTO

PAGINAS = ["inicio", "carga", "inventario", "vista_documentos", "ficha", "hallazgos", "ia", "resumen", "exportacion"]


@pytest.fixture(autouse=True)
def entorno_temporal(monkeypatch, tmp_path):
    monkeypatch.setenv("RUTA_DATOS", str(tmp_path))
    monkeypatch.setenv("URL_BASE_DATOS", "")
    monkeypatch.setenv("PROVEEDOR_IA", "desactivado")
    st.cache_resource.clear()  # Cada prueba usa su propia base de datos
    yield tmp_path
    st.cache_resource.clear()


def test_app_arranca_y_permite_crear_usuario_y_auditoria(entorno_temporal):
    app = AppTest.from_file(str(RAIZ_PROYECTO / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "Auditoría de cuentas médicas SOAT"
    assert (entorno_temporal / "auditoria.db").exists()

    # Crear un usuario ficticio desde la barra lateral.
    app.sidebar.text_input[0].input("Auditor Ficticio Prueba")
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert app.session_state["usuario_activo"]["nombre"] == "Auditor Ficticio Prueba"

    # Crear una auditoría ficticia.
    app.text_input[0].input("DEMO-0001")
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["auditoria_activa"]["identificador"] == "DEMO-0001"


def _ejecutar_pagina(nombre_modulo: str) -> None:
    import importlib

    import streamlit as st

    from interfaz.componentes.barra_lateral import mostrar_barra_lateral
    from interfaz.paginas import inicio

    st.session_state["pagina_inicio"] = st.Page(inicio.mostrar, title="Inicio", url_path="inicio")
    mostrar_barra_lateral()
    importlib.import_module(f"interfaz.paginas.{nombre_modulo}").mostrar()


def _preparar_usuario_y_auditoria():
    from interfaz.recursos import obtener_fabrica_sesiones
    from auditoria.auditorias import servicio as servicio_auditorias
    from auditoria.usuarios import servicio as servicio_usuarios

    from auditoria.documentos import inventario
    from interfaz.recursos import obtener_configuracion
    from pruebas import generadores

    with obtener_fabrica_sesiones()() as sesion:
        usuario = servicio_usuarios.crear_usuario(sesion, "Auditor Ficticio")
        auditoria = servicio_auditorias.crear_auditoria(sesion, usuario.id, "DEMO-0002")
        for nombre, contenido in (
            ("cuenta.pdf", generadores.cuenta_ficticia(lado_informe="izquierda", placa_poliza="XYZ987")),
            ("mixto.pdf", generadores.pdf_con_pagina_en_blanco_e_imagen()),
            ("factura.xml", b"<ficticio/>"),
        ):
            inventario.cargar_archivo(sesion, obtener_configuracion(), auditoria.id, usuario.id, nombre, contenido)
        from auditoria.reglas.motor import ejecutar_reglas

        ejecutar_reglas(sesion, auditoria.id, usuario.id)
        sesion.commit()
        return {"id": usuario.id, "nombre": usuario.nombre}, {
            "id": auditoria.id,
            "identificador": auditoria.identificador,
            "estado": auditoria.estado,
        }


@pytest.mark.parametrize("pagina", PAGINAS)
def test_cada_pagina_carga_sin_errores(pagina):
    usuario, auditoria = _preparar_usuario_y_auditoria()
    app = AppTest.from_function(_ejecutar_pagina, args=(pagina,), default_timeout=60)
    app.session_state["usuario_activo"] = usuario
    app.session_state["auditoria_activa"] = auditoria
    app.run()
    assert not app.exception, app.exception


def _app_pagina(pagina):
    usuario, auditoria = _preparar_usuario_y_auditoria()
    app = AppTest.from_function(_ejecutar_pagina, args=(pagina,), default_timeout=60)
    app.session_state["usuario_activo"] = usuario
    app.session_state["auditoria_activa"] = auditoria
    return app.run(), auditoria


def test_exportacion_genera_excel_y_pdf_desde_la_interfaz():
    app, auditoria = _app_pagina("exportacion")
    next(b for b in app.button if b.label == "Generar Excel").click().run()
    next(b for b in app.button if b.label == "Generar informe PDF").click().run()
    assert not app.exception, app.exception
    assert app.session_state[f"exportacion_excel_{auditoria['id']}"][:2] == b"PK"  # xlsx = zip
    assert app.session_state[f"exportacion_pdf_{auditoria['id']}"][:4] == b"%PDF"


def test_panel_permite_revisar_un_hallazgo():
    from auditoria import catalogos
    from auditoria.hallazgos import servicio
    from interfaz.recursos import obtener_fabrica_sesiones

    app, auditoria = _app_pagina("hallazgos")
    with obtener_fabrica_sesiones()() as sesion:
        pendientes_antes = len(servicio.pendientes_de_revision(sesion, auditoria["id"]))
    # El primer formulario de revisión: confirmar (opción por defecto) y guardar.
    next(b for b in app.button if b.label == "Guardar revisión").click().run()
    assert not app.exception, app.exception
    with obtener_fabrica_sesiones()() as sesion:
        assert len(servicio.pendientes_de_revision(sesion, auditoria["id"])) == pendientes_antes - 1
        assert any(h.estado_revision == catalogos.REVISION_CONFIRMADO for h in servicio.listar(sesion, auditoria["id"]))


@pytest.mark.parametrize("pagina", [p for p in PAGINAS if p != "inicio"])
def test_paginas_piden_auditoria_si_no_hay(pagina):
    app = AppTest.from_function(_ejecutar_pagina, args=(pagina,), default_timeout=60)
    app.session_state["usuario_activo"] = {"id": 1, "nombre": "Nadie"}
    app.run()
    assert not app.exception, app.exception
    assert any("Seleccione o cree una auditoría" in w.value for w in app.warning)
