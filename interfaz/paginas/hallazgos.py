"""Panel de hallazgos."""

import streamlit as st

from interfaz.componentes.visuales import pendiente_de_fase
from interfaz.estado import requerir_auditoria


def mostrar() -> None:
    st.title("Panel de hallazgos")
    requerir_auditoria()
    pendiente_de_fase("El motor de reglas y el panel de hallazgos")
