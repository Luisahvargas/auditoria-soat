"""Análisis con IA."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Análisis con IA")
    requerir_auditoria()
    pendiente_de_fase("El puente manual de IA")
