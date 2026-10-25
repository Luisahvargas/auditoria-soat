"""Inventario de archivos de la auditoría activa."""

import streamlit as st

from auditoria import catalogos
from auditoria.documentos import inventario
from interfaz.componentes.visuales import etiqueta_procesamiento, insignia_procesamiento
from interfaz.estado import requerir_auditoria
from interfaz.recursos import obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Inventario de archivos")
    _, auditoria = requerir_auditoria()

    with obtener_fabrica_sesiones()() as sesion:
        documentos = inventario.listar_documentos(sesion, auditoria["id"], con_paginas=True)
        filas, detalles = [], []
        for d in documentos:
            sin_texto = sum(1 for p in d.paginas if p.requiere_analisis_visual)
            sin_clasificar = sum(1 for p in d.paginas if not p.tipo_efectivo)
            filas.append(
                {
                    "Archivo": d.nombre_original,
                    "Tipo": d.tipo_archivo.upper(),
                    "Estado": etiqueta_procesamiento(d.estado),
                    "Páginas": d.numero_paginas,
                    "Sin texto": sin_texto if d.tipo_archivo == "pdf" else None,
                    "Sin clasificar": sin_clasificar if d.tipo_archivo == "pdf" else None,
                    "Tamaño (KB)": round(d.tamano_bytes / 1024, 1),
                    "SHA-256": d.hash_sha256[:16] + "…",
                    "Cargado": d.fecha_carga,
                }
            )
            detalles.append((d.nombre_original, d.estado, d.mensaje, d.hash_sha256))

    if not filas:
        st.info("Aún no hay documentos. Cárguelos en **Carga de documentos**.")
        return

    total_paginas = sum(f["Páginas"] or 0 for f in filas)
    columnas = st.columns(4)
    columnas[0].metric("Archivos", len(filas))
    columnas[1].metric("Páginas", total_paginas)
    columnas[2].metric("Páginas sin texto", sum(f["Sin texto"] or 0 for f in filas))
    columnas[3].metric(
        "Requieren atención",
        sum(1 for _, estado, _, _ in detalles if estado in (catalogos.PROC_REQUIERE_REVISION, catalogos.PROC_ERROR, catalogos.PROC_PENDIENTE)),
    )

    st.dataframe(filas, hide_index=True, width="stretch")

    st.subheader("Detalle por archivo")
    for nombre, estado, mensaje, hash_completo in detalles:
        with st.container(border=True):
            st.markdown(f"**{nombre}**")
            insignia_procesamiento(estado)
            if mensaje:
                st.caption(mensaje)
            st.caption(f"SHA-256: `{hash_completo}`")
