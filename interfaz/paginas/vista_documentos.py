"""Vista de documentos y páginas: imagen de la página, texto extraído y clasificación."""

import streamlit as st

from auditoria.documentos import inventario, lector_pdf
from interfaz.componentes.visuales import insignia_procesamiento, texto_no_confiable
from interfaz.estado import requerir_auditoria
from interfaz.recursos import obtener_configuracion, obtener_fabrica_sesiones

CLAVE_IR_A = "ir_a_pagina"  # Otras pantallas pueden pedir abrir {"documento_id": ..., "pagina": ...}


def mostrar() -> None:
    st.title("Vista de documentos y páginas")
    usuario, auditoria = requerir_auditoria()

    fabrica = obtener_fabrica_sesiones()
    with fabrica() as sesion:
        pdfs = [d for d in inventario.listar_documentos(sesion, auditoria["id"]) if d.tipo_archivo == "pdf" and d.numero_paginas]
    if not pdfs:
        st.info("No hay PDF legibles cargados en esta auditoría.")
        return

    destino = st.session_state.pop(CLAVE_IR_A, None)
    ids = [d.id for d in pdfs]
    nombres = {d.id: f"{d.nombre_original} ({d.numero_paginas} págs.)" for d in pdfs}
    if destino and destino["documento_id"] in ids:
        st.session_state["vista_documento"] = destino["documento_id"]
        st.session_state["vista_pagina"] = destino["pagina"]

    documento_id = st.selectbox("Documento", ids, format_func=nombres.get, key="vista_documento")
    documento = next(d for d in pdfs if d.id == documento_id)
    if st.session_state.get("vista_pagina", 1) > documento.numero_paginas:
        st.session_state["vista_pagina"] = 1
    numero = st.number_input(
        "Página del archivo", min_value=1, max_value=documento.numero_paginas, step=1, key="vista_pagina"
    )

    with fabrica() as sesion:
        from auditoria.db.repositorios import RepositorioDocumentos

        pagina = RepositorioDocumentos(sesion).obtener_pagina_por_numero(documento.id, int(numero))

    columna_imagen, columna_datos = st.columns([3, 2], gap="large")
    with columna_imagen:
        try:
            imagen = inventario.obtener_imagen_pagina(obtener_configuracion(), documento, int(numero))
            st.image(imagen, caption=f"{documento.nombre_original} — página {numero} del archivo", width="stretch")
        except lector_pdf.ErrorLecturaPDF as error:
            st.error(str(error))

    with columna_datos:
        insignia_procesamiento(documento.estado)
        st.markdown(f"**Página del archivo:** {numero} de {documento.numero_paginas}")
        st.markdown(f"**Página interna del documento:** {pagina.pagina_interna or 'no identificada'}")
        st.markdown(f"**Caracteres de texto:** {pagina.caracteres} · **Método:** {pagina.metodo_texto}")
        if pagina.requiere_analisis_visual:
            st.warning("Página sin texto suficiente: requiere OCR o análisis visual.")
        _clasificacion(pagina, usuario, auditoria)
        texto_no_confiable(pagina.texto)


def _clasificacion(pagina, usuario, auditoria) -> None:
    """Se completa en la Fase 6."""
