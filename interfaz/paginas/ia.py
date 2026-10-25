"""Análisis con IA: puente manual (sin costo) y API (preparada, desactivada)."""

import streamlit as st

from auditoria import catalogos
from auditoria.db.repositorios import RepositorioConsumoIA, RepositorioTrazabilidad
from auditoria.hallazgos import servicio as servicio_hallazgos
from auditoria.ia import puente_manual
from auditoria.ia.proveedor_base import ErrorProveedorIA, obtener_proveedor
from auditoria.ia.servicio import ejecutar_con_proveedor
from interfaz.estado import auditoria_finalizada, requerir_auditoria
from interfaz.recursos import obtener_configuracion, obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Análisis con IA")
    usuario, auditoria = requerir_auditoria()
    config = obtener_configuracion()
    proveedor = obtener_proveedor(config)

    st.caption(
        "Los resultados de IA son **sugerencias pendientes de revisión humana**: nunca confirman un hallazgo por sí solos "
        "y se muestran separados de las reglas automáticas."
    )
    if not proveedor.disponible():
        st.warning(proveedor.descripcion_estado())
    else:
        st.info(proveedor.descripcion_estado())

    pestanas = st.tabs(["1. Generar paquete", "2. Importar respuesta", "Historial"])
    with pestanas[0]:
        paquete = _generar(auditoria)
        if paquete and not proveedor.es_manual and proveedor.disponible() and not auditoria_finalizada():
            _envio_api(paquete, usuario, auditoria, proveedor)
    with pestanas[1]:
        _importar(usuario, auditoria, habilitado=proveedor.es_manual)
    with pestanas[2]:
        _historial(auditoria)


def _generar(auditoria):
    tipo = st.selectbox(
        "Tipo de análisis",
        list(puente_manual.PLANTILLAS),
        format_func=lambda t: puente_manual.PLANTILLAS[t][0],
        key="ia_tipo_generar",
    )
    with obtener_fabrica_sesiones()() as sesion:
        paquete = puente_manual.generar_paquete(sesion, auditoria["id"], tipo)

    if not paquete.archivos:
        st.info("No hay páginas para este tipo de análisis (por ejemplo, no hay páginas sin texto o no hay PDF cargados).")
        return None

    st.markdown("**Archivos que debe subir a claude.ai** (los originales, con el mismo nombre):")
    st.dataframe(
        [{"Archivo": a.nombre, "Páginas a analizar": a.paginas, "Motivo": a.motivo} for a in paquete.archivos],
        hide_index=True,
        width="stretch",
    )
    st.warning(
        "🔒 Al subir los PDF a claude.ai, los datos de la cuenta salen del equipo. Hágalo solo si la organización lo autorizó "
        "y con la cuenta definida para ello."
    )
    st.markdown(f"**Prompt para copiar** (plantilla `{paquete.version_prompt}`, esquema v{puente_manual.VERSION_ESQUEMA}):")
    st.code(paquete.texto_completo, language="markdown", wrap_lines=True, height=350)
    st.download_button(
        "Descargar prompt (.txt)",
        paquete.texto_completo.encode("utf-8"),
        file_name=f"prompt_{tipo}_{auditoria['identificador']}.txt",
        mime="text/plain",
    )
    st.caption("Pasos: 1) abra claude.ai · 2) adjunte los PDF de la tabla · 3) pegue el prompt · 4) copie la respuesta JSON y péguela en la pestaña 2.")
    return paquete


def _importar(usuario, auditoria, habilitado: bool) -> None:
    if not habilitado:
        st.info("La importación manual está disponible cuando PROVEEDOR_IA=puente_manual.")
        return
    if auditoria_finalizada():
        st.info("La auditoría está finalizada: no admite nuevas sugerencias de IA.")
        return
    with st.form("importar_ia"):
        tipo = st.selectbox(
            "Tipo de análisis que está importando",
            list(puente_manual.PLANTILLAS),
            format_func=lambda t: puente_manual.PLANTILLAS[t][0],
        )
        texto = st.text_area("Pegue aquí la respuesta JSON completa", height=300)
        if st.form_submit_button("Validar e importar", type="primary"):
            with obtener_fabrica_sesiones()() as sesion:
                try:
                    creados = puente_manual.importar_respuesta(sesion, auditoria["id"], usuario["id"], texto, tipo)
                    sesion.commit()
                except puente_manual.ErrorImportacionIA as error:
                    sesion.rollback()
                    st.error("No se importó nada. Corrija estos errores y vuelva a intentarlo:")
                    for detalle in error.errores:
                        st.code(detalle, language=None)
                    return
            st.success(
                f"Se importaron {len(creados)} sugerencia(s) de IA como «{catalogos.REVISION_PENDIENTE}». "
                "Revíselas en el **Panel de hallazgos** (filtro Origen: Sugerencia de IA)."
            )


def _envio_api(paquete, usuario, auditoria, proveedor) -> None:
    """Solo con la API activa: muestra lo que se enviará y exige confirmación."""
    st.divider()
    st.subheader("Enviar a la API (tiene costo)")
    st.markdown("Se enviarán **completos** estos archivos y el prompt mostrado arriba:")
    for archivo in paquete.archivos:
        st.markdown(f"- {archivo.nombre}")
    confirmado = st.checkbox("Confirmo que revisé lo que se enviará y que está autorizado.")
    if st.button("Enviar a la API", disabled=not confirmado):
        with obtener_fabrica_sesiones()() as sesion:
            try:
                creados = ejecutar_con_proveedor(sesion, obtener_configuracion(), auditoria["id"], usuario["id"], paquete, confirmado)
                sesion.commit()
            except puente_manual.ErrorImportacionIA as error:
                sesion.commit()  # Solo se guarda el consumo de tokens; la validación falló antes de crear hallazgos
                st.error("La respuesta de la API no es válida; no se importó nada: " + "; ".join(error.errores))
                return
            except ErrorProveedorIA as error:
                sesion.rollback()
                st.error(str(error))
                return
        st.success(f"Se importaron {len(creados)} sugerencia(s) pendientes de revisión humana.")


def _historial(auditoria) -> None:
    with obtener_fabrica_sesiones()() as sesion:
        sugerencias = servicio_hallazgos.listar(
            sesion, auditoria["id"], servicio_hallazgos.Filtros(solo_atencion=False, origenes=[catalogos.ORIGEN_IA])
        )
        importaciones = [r for r in RepositorioTrazabilidad(sesion).listar_por_auditoria(auditoria["id"]) if r.accion == "ia_importada"]
        tokens_entrada, tokens_salida = RepositorioConsumoIA(sesion).totales_por_auditoria(auditoria["id"])

    columnas = st.columns(3)
    columnas[0].metric("Sugerencias de IA", len(sugerencias))
    columnas[1].metric("Pendientes de revisión", sum(h.estado_revision == catalogos.REVISION_PENDIENTE for h in sugerencias))
    columnas[2].metric("Tokens de API (entrada / salida)", f"{tokens_entrada:,} / {tokens_salida:,}")
    if not importaciones:
        st.info("No se ha importado ningún análisis de IA en esta auditoría.")
        return
    st.dataframe(
        [{"Fecha": r.fecha, "Usuario": r.usuario.nombre, "Detalle": r.detalle} for r in importaciones],
        hide_index=True,
        width="stretch",
    )
