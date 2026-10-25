"""Carga de documentos."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Carga de documentos")
    requerir_auditoria()
    pendiente_de_fase("La carga y lectura de documentos")
