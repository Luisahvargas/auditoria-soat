"""Ficha de datos generales."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Ficha de datos generales")
    requerir_auditoria()
    pendiente_de_fase("La ficha maestra")
