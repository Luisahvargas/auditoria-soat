"""Punto de entrada de la aplicación Streamlit.

Ejecutar con:  .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

import streamlit as st

from interfaz.componentes.barra_lateral import mostrar_barra_lateral
from interfaz.paginas import (
    carga,
    exportacion,
    ficha,
    hallazgos,
    ia,
    inicio,
    inventario,
    resumen,
    vista_documentos,
)

st.set_page_config(page_title="Auditoría SOAT", page_icon="🩺", layout="wide")

pagina_inicio = st.Page(inicio.mostrar, title="Inicio", icon="🏠", url_path="inicio", default=True)
st.session_state["pagina_inicio"] = pagina_inicio

paginas = {
    "General": [pagina_inicio],
    "Documentos": [
        st.Page(carga.mostrar, title="Carga de documentos", icon="📤", url_path="carga"),
        st.Page(inventario.mostrar, title="Inventario de archivos", icon="🗂️", url_path="inventario"),
        st.Page(vista_documentos.mostrar, title="Vista de documentos", icon="📄", url_path="documentos"),
    ],
    "Auditoría": [
        st.Page(ficha.mostrar, title="Ficha de datos generales", icon="🧾", url_path="ficha"),
        st.Page(hallazgos.mostrar, title="Panel de hallazgos", icon="🔎", url_path="hallazgos"),
        st.Page(ia.mostrar, title="Análisis con IA", icon="🤖", url_path="ia"),
        st.Page(resumen.mostrar, title="Resumen y cierre", icon="📋", url_path="resumen"),
        st.Page(exportacion.mostrar, title="Exportación", icon="📦", url_path="exportacion"),
    ],
}

navegacion = st.navigation(paginas)
mostrar_barra_lateral()
navegacion.run()
