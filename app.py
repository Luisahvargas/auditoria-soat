"""Punto de entrada de la aplicación Streamlit.

Ejecutar con:  .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

import streamlit as st

from interfaz.componentes.selector_usuario import mostrar_selector_usuario
from interfaz.paginas.bienvenida import mostrar_bienvenida
from interfaz.recursos import obtener_configuracion

st.set_page_config(page_title="Auditoría SOAT", page_icon="🩺", layout="wide")

configuracion = obtener_configuracion()
usuario = mostrar_selector_usuario()
mostrar_bienvenida(configuracion, usuario)
