"""Exportación."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Exportación")
    requerir_auditoria()
    pendiente_de_fase("La exportación a Excel y PDF")
