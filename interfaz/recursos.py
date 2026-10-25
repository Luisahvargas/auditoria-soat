"""Recursos compartidos de la interfaz: configuración y conexión a la base de datos.

Se crean una sola vez por proceso de Streamlit (st.cache_resource).
"""

import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from auditoria.config import Configuracion, cargar_configuracion, preparar_carpetas
from auditoria.db.sesion import crear_fabrica_sesiones, crear_motor, inicializar_base_datos


@st.cache_resource
def obtener_configuracion() -> Configuracion:
    config = cargar_configuracion()
    preparar_carpetas(config)
    return config


@st.cache_resource
def obtener_fabrica_sesiones() -> sessionmaker[Session]:
    motor = crear_motor(obtener_configuracion().url_base_datos)
    inicializar_base_datos(motor)
    return crear_fabrica_sesiones(motor)
