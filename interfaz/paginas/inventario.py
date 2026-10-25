"""Inventario de archivos de la auditoría activa y sus secciones documentales."""

import streamlit as st

from auditoria import catalogos
from auditoria.documentos import clasificador, inventario, ocr
from interfaz.componentes.visuales import etiqueta_procesamiento, insignia_procesamiento
from interfaz.estado import auditoria_finalizada, requerir_auditoria
from interfaz.recursos import obtener_configuracion, obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Inventario de archivos")
    usuario, auditoria = requerir_auditoria()

    with obtener_fabrica_sesiones()() as sesion:
        documentos = inventario.listar_documentos(sesion, auditoria["id"], con_paginas=True)

    if not documentos:
        st.info("Aún no hay documentos. Cárguelos en **Carga de documentos**.")
        return

    filas = []
    for d in documentos:
        es_pdf = d.tipo_archivo == "pdf"
        filas.append(
            {
                "Archivo": d.nombre_original,
                "Tipo": d.tipo_archivo.upper(),
                "Estado": etiqueta_procesamiento(d.estado),
                "Páginas": d.numero_paginas,
                "Sin texto": sum(p.requiere_analisis_visual for p in d.paginas) if es_pdf else None,
                "Sin confirmar": sum(not p.tipo_confirmado for p in d.paginas) if es_pdf else None,
                "Ilegibles": sum(p.legibilidad == catalogos.NO_LEGIBLE for p in d.paginas) if es_pdf else None,
                "Tamaño (KB)": round(d.tamano_bytes / 1024, 1),
                "SHA-256": d.hash_sha256[:16] + "…",
                "Cargado": d.fecha_carga,
            }
        )

    columnas = st.columns(4)
    columnas[0].metric("Archivos", len(filas))
    columnas[1].metric("Páginas", sum(f["Páginas"] or 0 for f in filas))
    columnas[2].metric("Páginas sin texto", sum(f["Sin texto"] or 0 for f in filas))
    columnas[3].metric(
        "Archivos que requieren atención",
        sum(d.estado in (catalogos.PROC_REQUIERE_REVISION, catalogos.PROC_ERROR, catalogos.PROC_PENDIENTE) for d in documentos),
    )
    st.caption(ocr.estado_ocr(obtener_configuracion()).mensaje)

    pestana_archivos, pestana_secciones = st.tabs(["Archivos", "Secciones documentales"])
    with pestana_archivos:
        st.dataframe(filas, hide_index=True, width="stretch")
        for d in documentos:
            with st.container(border=True):
                st.markdown(f"**{d.nombre_original}**")
                insignia_procesamiento(d.estado)
                if d.mensaje:
                    st.caption(d.mensaje)
                st.caption(f"SHA-256: `{d.hash_sha256}`")

    with pestana_secciones:
        _secciones(documentos, usuario, auditoria)


def _secciones(documentos, usuario, auditoria) -> None:
    st.caption(
        "Agrupación preliminar de páginas consecutivas del mismo tipo. "
        "La clasificación automática es una propuesta: confírmela o corríjala."
    )
    pdfs = [d for d in documentos if d.tipo_archivo == "pdf" and d.paginas]
    if not pdfs:
        st.info("No hay PDF con páginas.")
        return

    nombres_tipos = clasificador.cargar_tipos().nombres
    for documento in pdfs:
        secciones = clasificador.agrupar_secciones(documento.paginas)
        st.markdown(f"#### {documento.nombre_original}")
        st.dataframe(
            [
                {
                    "Tipo": s.tipo,
                    "Páginas del archivo": f"{s.pagina_inicio}-{s.pagina_fin}" if s.pagina_fin != s.pagina_inicio else str(s.pagina_inicio),
                    "N.º páginas": len(s.paginas),
                    "Revisar": "⚠️ Dudosa" if s.dudosa else "",
                    "Motivo": " ".join(s.motivos),
                }
                for s in secciones
            ],
            hide_index=True,
            width="stretch",
        )
        if auditoria_finalizada():
            continue
        with st.form(f"confirmar_seccion_{documento.id}"):
            st.markdown("Confirmar o corregir el tipo de un rango de páginas")
            columnas = st.columns([1, 1, 2])
            desde = columnas[0].number_input("Desde la página", 1, documento.numero_paginas, 1, key=f"desde_{documento.id}")
            hasta = columnas[1].number_input("Hasta la página", 1, documento.numero_paginas, documento.numero_paginas, key=f"hasta_{documento.id}")
            tipo = columnas[2].selectbox("Tipo documental", nombres_tipos, key=f"tipo_{documento.id}")
            if st.form_submit_button("Guardar"):
                if hasta < desde:
                    st.error("El rango no es válido.")
                else:
                    with obtener_fabrica_sesiones()() as sesion:
                        clasificador.confirmar_seccion(sesion, documento.id, list(range(int(desde), int(hasta) + 1)), tipo, usuario["id"])
                        sesion.commit()
                    st.rerun()

    if not auditoria_finalizada() and st.button("Volver a proponer la clasificación automática"):
        with obtener_fabrica_sesiones()() as sesion:
            clasificador.reclasificar_auditoria(sesion, auditoria["id"], usuario["id"])
            sesion.commit()
        st.toast("Clasificación automática actualizada (se respetan las páginas confirmadas).")
        st.rerun()
