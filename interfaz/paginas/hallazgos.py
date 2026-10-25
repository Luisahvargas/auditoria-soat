"""Panel de hallazgos: análisis automático, filtros y revisión humana."""

import json

import streamlit as st

from auditoria import catalogos
from auditoria.auditorias import servicio as servicio_auditorias
from auditoria.db.repositorios import RepositorioHallazgos
from auditoria.documentos import inventario
from auditoria.hallazgos import servicio
from auditoria.reglas.definiciones import ErrorReglas
from auditoria.reglas.motor import ejecutar_reglas
from auditoria.reglas.perfiles import listar_perfiles
from interfaz.componentes.visuales import escapar_markdown, etiqueta_origen, etiqueta_resultado
from interfaz.estado import auditoria_finalizada, ir_a_pagina, requerir_auditoria
from interfaz.recursos import obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Panel de hallazgos")
    usuario, auditoria = requerir_auditoria()
    fabrica = obtener_fabrica_sesiones()
    finalizada = auditoria_finalizada()

    st.caption(
        "El sistema señala lo que está mal o requiere verificación; **la decisión es suya**. "
        "Ningún hallazgo es una glosa: confírmelo, descártelo o modifíquelo."
    )

    with fabrica() as sesion:
        datos_auditoria = servicio_auditorias.obtener_auditoria(sesion, auditoria["id"])
        ultima = RepositorioHallazgos(sesion).ultima_ejecucion(auditoria["id"])
        documentos = inventario.listar_documentos(sesion, auditoria["id"], con_paginas=True)

    _analisis(datos_auditoria, ultima, usuario, auditoria, finalizada)
    _alertas(documentos)

    filtros = _filtros()
    with fabrica() as sesion:
        todos = servicio.listar(sesion, auditoria["id"], servicio.Filtros(solo_atencion=False))
        visibles = servicio.listar(sesion, auditoria["id"], filtros)

    atencion = [h for h in todos if h.estado_final in catalogos.ESTADOS_QUE_REQUIEREN_ATENCION]
    columnas = st.columns(4)
    columnas[0].metric("Requieren atención", len(atencion))
    columnas[1].metric("Pendientes de revisión", sum(h.estado_revision == catalogos.REVISION_PENDIENTE for h in atencion))
    columnas[2].metric("Sugerencias de IA", sum(h.origen == catalogos.ORIGEN_IA for h in todos))
    columnas[3].metric("Verificaciones sin hallazgo (ocultas)", len(todos) - len(atencion))

    if not visibles:
        st.info("No hay hallazgos con los filtros actuales." if todos else "Aún no hay resultados. Ejecute el análisis automático.")
    for hallazgo in visibles:
        _tarjeta(hallazgo, usuario, finalizada)

    if not finalizada:
        _hallazgo_propio(usuario, auditoria)


def _analisis(datos_auditoria, ultima, usuario, auditoria, finalizada) -> None:
    with st.container(border=True):
        perfiles = listar_perfiles()
        columnas = st.columns([2, 1])
        perfil = columnas[0].selectbox(
            "Perfil de aseguradora",
            list(perfiles),
            index=list(perfiles).index(datos_auditoria.perfil_aseguradora) if datos_auditoria.perfil_aseguradora in perfiles else 0,
            format_func=perfiles.get,
            disabled=finalizada,
        )
        if ultima:
            resumen = json.loads(ultima.resumen_json or "{}")
            columnas[1].caption(
                f"Último análisis: {ultima.fecha:%Y-%m-%d %H:%M} · {ultima.reglas_ejecutadas} reglas · perfil «{ultima.perfil_aseguradora}»"
            )
            with columnas[1].popover("Resultados por estado"):
                for estado, cantidad in resumen.items():
                    st.write(f"{etiqueta_resultado(estado)}: {cantidad}")
        else:
            columnas[1].caption("Aún no se ha ejecutado el análisis automático.")

        if finalizada:
            return
        if st.button("Ejecutar análisis automático (extracción + reglas)", type="primary"):
            try:
                with obtener_fabrica_sesiones()() as sesion:
                    servicio_auditorias.cambiar_perfil(sesion, auditoria["id"], usuario["id"], perfil)
                    resultado = ejecutar_reglas(sesion, auditoria["id"], usuario["id"])
                    sesion.commit()
            except ErrorReglas as error:
                st.error(f"Error en la configuración de reglas: {error}")
                return
            st.toast(
                f"Análisis terminado: {resultado.reglas_ejecutadas} reglas, {resultado.nuevos} resultados nuevos, "
                f"{resultado.conservados} ya revisados conservados."
            )
            st.rerun()


def _alertas(documentos) -> None:
    sin_texto = sum(p.requiere_analisis_visual for d in documentos for p in d.paginas)
    ilegibles = sum(p.legibilidad == catalogos.NO_LEGIBLE for d in documentos for p in d.paginas)
    pendientes = [d for d in documentos if d.estado in (catalogos.PROC_PENDIENTE, catalogos.PROC_ERROR)]
    if sin_texto:
        st.warning(
            f"⚠️ {sin_texto} página(s) sin texto **no fueron revisadas por las reglas**. Revíselas visualmente "
            "o use el análisis con IA (puente manual)."
        )
    if ilegibles:
        st.warning(f"🟣 {ilegibles} página(s) marcadas como ilegibles.")
    if pendientes:
        st.warning(f"⏳ {len(pendientes)} archivo(s) pendientes o con error de lectura: {', '.join(d.nombre_original for d in pendientes)}.")


def _filtros() -> servicio.Filtros:
    with st.expander("Filtros", expanded=False):
        ver_todo = st.toggle(
            "Mostrar también lo revisado sin hallazgo (No aplica, No evaluable, Sin inconsistencia)",
            value=False,
            help="Por defecto solo se muestra lo que requiere su atención.",
        )
        columnas = st.columns(5)
        categorias = columnas[0].multiselect("Categoría", sorted(_categorias()))
        severidades = columnas[1].multiselect("Severidad", list(catalogos.SEVERIDADES))
        estados = columnas[2].multiselect("Estado", list(catalogos.ESTADOS_RESULTADO))
        origenes = columnas[3].multiselect("Origen", list(catalogos.ORIGENES))
        revision = columnas[4].multiselect("Revisión", list(catalogos.ESTADOS_REVISION))
    return servicio.Filtros(
        solo_atencion=not ver_todo,
        categorias=categorias or None,
        severidades=severidades or None,
        estados=estados or None,
        origenes=origenes or None,
        revision=revision or None,
    )


def _categorias() -> set[str]:
    from auditoria.reglas.definiciones import cargar_reglas

    try:
        return {r.categoria for r in cargar_reglas()} | {"Análisis clínico (IA)", "Otra"}
    except ErrorReglas:
        return set()


def _tarjeta(hallazgo, usuario, finalizada) -> None:
    icono_revision = {
        catalogos.REVISION_PENDIENTE: "⏳",
        catalogos.REVISION_CONFIRMADO: "✔️",
        catalogos.REVISION_DESCARTADO: "✖️",
        catalogos.REVISION_MODIFICADO: "✏️",
    }.get(hallazgo.estado_revision, "")
    encabezado = f"{etiqueta_resultado(hallazgo.estado_final)} · {hallazgo.severidad} · {escapar_markdown(hallazgo.titulo)} {icono_revision}"
    with st.expander(encabezado):
        st.markdown(
            f"**Origen:** {etiqueta_origen(hallazgo.origen)}"
            + (f" · **Regla:** {hallazgo.regla_id} v{hallazgo.regla_version}" if hallazgo.regla_id else "")
            + f" · **Categoría:** {escapar_markdown(hallazgo.categoria)}"
        )
        if hallazgo.estado_resultado_auditor:
            st.markdown(f"**Estado original:** {hallazgo.estado_resultado} → **modificado por el auditor:** {hallazgo.estado_resultado_auditor}")
        st.markdown(escapar_markdown(hallazgo.explicacion).replace("\n", "  \n"))
        if hallazgo.referencia_normativa:
            st.caption(f"Referencia normativa: {escapar_markdown(hallazgo.referencia_normativa)}")
        if hallazgo.detalle_ia:
            _detalle_ia(hallazgo.detalle_ia)

        evidencias = hallazgo.evidencias
        if evidencias:
            st.markdown("**Evidencia**")
            st.dataframe(
                [{"Archivo": e.get("archivo"), "Página del archivo": e.get("pagina"), "Texto": e.get("texto")} for e in evidencias],
                hide_index=True,
                width="stretch",
            )
            con_pagina = [e for e in evidencias if e.get("documento_id") and e.get("pagina")]
            if con_pagina:
                columnas = st.columns([3, 1])
                opcion = columnas[0].selectbox(
                    "Ver página de origen",
                    range(len(con_pagina)),
                    format_func=lambda i: f"{con_pagina[i]['archivo']} — página {con_pagina[i]['pagina']}",
                    key=f"evid_{hallazgo.id}",
                    label_visibility="collapsed",
                )
                if columnas[1].button("Ver página", key=f"ver_{hallazgo.id}"):
                    ir_a_pagina(con_pagina[opcion]["documento_id"], con_pagina[opcion]["pagina"])
        else:
            st.caption("Sin evidencia documental asociada (por ejemplo, un dato que no se encontró).")

        _revision(hallazgo, usuario, finalizada)


def _detalle_ia(detalle: dict) -> None:
    st.markdown("**Detalle de la sugerencia de IA**")
    for titulo, clave in (
        ("Pregunta evaluada", "pregunta_clinica"),
        ("Conclusión preliminar", "conclusion_preliminar"),
        ("Acción sugerida", "accion_sugerida"),
        ("Confianza", "confianza"),
    ):
        if detalle.get(clave):
            st.markdown(f"*{titulo}:* {escapar_markdown(str(detalle[clave]))}")
    for titulo, clave in (
        ("Información contradictoria", "informacion_contradictoria"),
        ("Información faltante", "informacion_faltante"),
        ("Limitaciones", "limitaciones"),
    ):
        if detalle.get(clave):
            st.markdown(f"*{titulo}:*")
            for elemento in detalle[clave]:
                st.markdown(f"- {escapar_markdown(str(elemento))}")


def _revision(hallazgo, usuario, finalizada) -> None:
    st.divider()
    if hallazgo.estado_revision != catalogos.REVISION_PENDIENTE:
        quien = hallazgo.usuario_revision.nombre if hallazgo.usuario_revision else "—"
        fecha = f"{hallazgo.fecha_revision:%Y-%m-%d %H:%M}" if hallazgo.fecha_revision else ""
        st.markdown(f"**Revisión:** {hallazgo.estado_revision} por {escapar_markdown(quien)} el {fecha}")
        if hallazgo.comentario_auditor:
            st.markdown(f"**Comentario:** {escapar_markdown(hallazgo.comentario_auditor)}")
        if not finalizada and hallazgo.origen != catalogos.ORIGEN_AUDITOR and st.button("Reabrir revisión", key=f"reabrir_{hallazgo.id}"):
            with obtener_fabrica_sesiones()() as sesion:
                servicio.reabrir(sesion, hallazgo.id, usuario["id"])
                sesion.commit()
            st.rerun()
        return
    if finalizada:
        return

    with st.form(f"revisar_{hallazgo.id}"):
        st.markdown("**Su revisión**")
        decision = st.radio(
            "Decisión",
            [catalogos.REVISION_CONFIRMADO, catalogos.REVISION_DESCARTADO, catalogos.REVISION_MODIFICADO],
            horizontal=True,
        )
        nuevo_estado = st.selectbox("Nuevo estado (solo si modifica)", list(catalogos.ESTADOS_RESULTADO))
        comentario = st.text_area("Comentario (obligatorio para descartar o modificar)")
        if st.form_submit_button("Guardar revisión", type="primary"):
            try:
                with obtener_fabrica_sesiones()() as sesion:
                    servicio.revisar(sesion, hallazgo.id, usuario["id"], decision, comentario, nuevo_estado)
                    sesion.commit()
            except servicio.ErrorHallazgo as error:
                st.error(str(error))
            else:
                st.rerun()


def _hallazgo_propio(usuario, auditoria) -> None:
    with st.expander("➕ Registrar un hallazgo propio del auditor"):
        with st.form("hallazgo_auditor", clear_on_submit=True):
            titulo = st.text_input("Título")
            columnas = st.columns(3)
            categoria = columnas[0].text_input("Categoría", value="Otra")
            severidad = columnas[1].selectbox("Severidad", list(catalogos.SEVERIDADES))
            estado = columnas[2].selectbox("Estado", list(catalogos.ESTADOS_QUE_REQUIEREN_ATENCION))
            explicacion = st.text_area("Explicación")
            columnas = st.columns([3, 1])
            archivo = columnas[0].text_input("Archivo de la evidencia (opcional)")
            pagina = columnas[1].number_input("Página", min_value=0, value=0)
            texto = st.text_area("Texto de la evidencia (opcional)")
            if st.form_submit_button("Registrar"):
                evidencias = [{"archivo": archivo, "documento_id": None, "pagina": int(pagina) or None, "texto": texto}] if (archivo or texto) else []
                try:
                    with obtener_fabrica_sesiones()() as sesion:
                        servicio.agregar_hallazgo_auditor(
                            sesion, auditoria["id"], usuario["id"], titulo, categoria, severidad, estado, explicacion, evidencias
                        )
                        sesion.commit()
                except servicio.ErrorHallazgo as error:
                    st.error(str(error))
                else:
                    st.rerun()
