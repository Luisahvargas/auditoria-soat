"""Resumen de auditoría."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Resumen de auditoría")
    requerir_auditoria()
    pendiente_de_fase("El resumen y cierre de la auditoría")
