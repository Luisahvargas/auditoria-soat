"""Inventario de archivos."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Inventario de archivos")
    requerir_auditoria()
    pendiente_de_fase("El inventario documental")
