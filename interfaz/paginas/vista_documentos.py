"""Vista de documentos y páginas."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Vista de documentos y páginas")
    requerir_auditoria()
    pendiente_de_fase("La vista de páginas")
