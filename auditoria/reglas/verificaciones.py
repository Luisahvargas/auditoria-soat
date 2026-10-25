"""Funciones de verificación de las reglas.

Cada función recibe el contexto de la auditoría y la regla (con sus parámetros) y
devuelve una lista de resultados con estado, explicación y evidencias.

Principios: no inventar, la ausencia de un dato no prueba un error, y lo extraído
automáticamente puede tener errores (por eso las diferencias entre datos no
validados se reportan como "Posible inconsistencia").
"""

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import date

from auditoria import catalogos
from auditoria.documentos.clasificador import agrupar_secciones
from auditoria.reglas.contexto import ContextoAuditoria, Evidencia, Resultado, normalizar_conservando_longitud
from auditoria.texto import calcular_edad, leer_fecha, normalizar

VERIFICACIONES: dict[str, Callable] = {}

VALIDADOS = (catalogos.VALIDACION_VALIDADO, catalogos.VALIDACION_CORREGIDO)


def verificacion(nombre: str):
    """Registra una función de verificación con el nombre que se usa en el YAML."""

    def registrar(funcion):
        VERIFICACIONES[nombre] = funcion
        return funcion

    return registrar


# =====================================================================
# Utilidades
# =====================================================================


def _todos_validados(estado_campo) -> bool:
    return all(d.estado_validacion in VALIDADOS for v in estado_campo.valores for d in v.datos)


def _evidencias_campo(ctx: ContextoAuditoria, estado_campo) -> list[Evidencia]:
    return [ctx.evidencia_dato(d) for v in estado_campo.valores for d in v.datos]


def _valores_texto(estado_campo) -> str:
    return "; ".join(
        f"«{v.mostrar}» ({len(v.datos)} fuente{'s' if len(v.datos) != 1 else ''})" for v in estado_campo.valores
    )


def _similitud_nombres(a: str, b: str) -> float:
    """Proporción de palabras compartidas (tolerante al orden y a nombres incompletos)."""
    palabras_a = {p for p in normalizar(a).split() if len(p) > 1}
    palabras_b = {p for p in normalizar(b).split() if len(p) > 1}
    if not palabras_a or not palabras_b:
        return 0.0
    if palabras_a <= palabras_b or palabras_b <= palabras_a:
        return 1.0
    return len(palabras_a & palabras_b) / len(palabras_a | palabras_b)


def _fecha_unica(ctx: ContextoAuditoria, campo_id: str) -> tuple[date | None, str]:
    """Fecha de un campo si tiene un único valor. Devuelve (fecha, motivo si no hay)."""
    estado = ctx.campo(campo_id)
    if estado.sin_dato:
        return None, f"no se identificó «{estado.campo.etiqueta}»"
    if len(estado.valores) > 1:
        return None, f"«{estado.campo.etiqueta}» tiene valores distintos"
    fecha = leer_fecha(estado.valores[0].mostrar)
    return (fecha, "") if fecha else (None, f"«{estado.campo.etiqueta}» no se pudo interpretar como fecha")


# =====================================================================
# R01, R02, R04, R05, R07, R08: comparación de un campo entre soportes
# =====================================================================


@verificacion("comparar_campos")
def comparar_campos(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    resultados = []
    tolerantes = regla.parametros.get("nombres_tolerantes", False)
    for campo_id in regla.parametros["campos"]:
        estado = ctx.campo(campo_id)
        etiqueta = estado.campo.etiqueta
        fuentes = sum(len(v.datos) for v in estado.valores)

        if estado.sin_dato:
            resultados.append(
                Resultado(catalogos.NO_EVALUABLE, f"No se identificó «{etiqueta}» en los soportes revisados.", detalle=etiqueta)
            )
            continue
        if fuentes < 2:
            resultados.append(
                Resultado(
                    catalogos.NO_EVALUABLE,
                    f"«{etiqueta}» aparece en una sola fuente; no hay con qué compararlo.",
                    _evidencias_campo(ctx, estado),
                    etiqueta,
                )
            )
            continue

        distintos = len(estado.valores) > 1
        if distintos and tolerantes and estado.campo.tipo == "nombre":
            base = estado.valores[0].mostrar
            distintos = any(_similitud_nombres(base, v.mostrar) < 1.0 for v in estado.valores[1:])

        if not distintos:
            resultados.append(
                Resultado(
                    catalogos.SIN_INCONSISTENCIA,
                    f"«{etiqueta}» coincide en {fuentes} fuentes: {estado.valores[0].mostrar}.",
                    _evidencias_campo(ctx, estado),
                    etiqueta,
                )
            )
            continue

        if _todos_validados(estado):
            estado_resultado = catalogos.CONTRADICCION
            nota = "Todos los valores fueron validados por el auditor."
        else:
            estado_resultado = catalogos.POSIBLE_INCONSISTENCIA
            nota = "Los valores provienen de extracción automática: confirme la lectura en las páginas citadas."
        resultados.append(
            Resultado(
                estado_resultado,
                f"«{etiqueta}» tiene valores distintos entre soportes: {_valores_texto(estado)}. {nota}",
                _evidencias_campo(ctx, estado),
                etiqueta,
            )
        )
    if regla.parametros.get("advertir_xml_rips_pendiente") and ctx.documentos_estructurados():
        for resultado in resultados:
            resultado.explicacion += " No se comparó contra el XML/RIPS cargado: su lector está pendiente (Fase 5)."
    return resultados


# =====================================================================
# R03: edad
# =====================================================================


@verificacion("edad_incompatible")
def edad_incompatible(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    nacimiento, motivo_n = _fecha_unica(ctx, "paciente.fecha_nacimiento")
    accidente, motivo_a = _fecha_unica(ctx, "accidente.fecha")
    if not nacimiento or not accidente:
        return [Resultado(catalogos.NO_EVALUABLE, f"No se puede calcular la edad: {motivo_n or motivo_a}.")]

    evidencias = _evidencias_campo(ctx, ctx.campo("paciente.fecha_nacimiento")) + _evidencias_campo(
        ctx, ctx.campo("accidente.fecha")
    )
    if nacimiento > accidente:
        return [
            Resultado(
                catalogos.POSIBLE_INCONSISTENCIA,
                f"La fecha de nacimiento ({nacimiento:%d/%m/%Y}) es posterior a la del accidente ({accidente:%d/%m/%Y}).",
                evidencias,
            )
        ]

    calculada = calcular_edad(nacimiento, accidente)
    registrada = ctx.campo("paciente.edad")
    if registrada.sin_dato:
        return [
            Resultado(
                catalogos.NO_EVALUABLE,
                f"Edad calculada a la fecha del accidente: {calculada} años. No hay edad registrada en los documentos para comparar.",
                evidencias,
            )
        ]

    tolerancia = int(regla.parametros.get("tolerancia_anios", 0))
    resultados = []
    for valor in registrada.valores:
        edad = int(valor.normalizado) if valor.normalizado.isdigit() else None
        evidencias_valor = [ctx.evidencia_dato(d) for d in valor.datos]
        if edad is None:
            resultados.append(Resultado(catalogos.NO_EVALUABLE, f"La edad registrada «{valor.mostrar}» no es un número.", evidencias_valor))
        elif abs(edad - calculada) > tolerancia:
            resultados.append(
                Resultado(
                    catalogos.POSIBLE_INCONSISTENCIA,
                    f"Edad registrada: {edad} años; edad calculada a la fecha del accidente ({accidente:%d/%m/%Y}) "
                    f"con nacimiento el {nacimiento:%d/%m/%Y}: {calculada} años.",
                    evidencias + evidencias_valor,
                    f"edad {edad}",
                )
            )
        else:
            resultados.append(
                Resultado(
                    catalogos.SIN_INCONSISTENCIA,
                    f"Edad registrada ({edad}) compatible con la calculada a la fecha del accidente ({calculada}).",
                    evidencias_valor,
                    f"edad {edad}",
                )
            )
    return resultados


# =====================================================================
# R06: póliza
# =====================================================================


@verificacion("poliza")
def poliza(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    resultados = comparar_campos(ctx, regla.model_copy(update={"parametros": {"campos": ["administrativo.numero_poliza"]}}))

    accidente, motivo = _fecha_unica(ctx, "accidente.fecha")
    desde, motivo_d = _fecha_unica(ctx, "administrativo.vigencia_poliza_desde")
    hasta, motivo_h = _fecha_unica(ctx, "administrativo.vigencia_poliza_hasta")
    if not (accidente and desde and hasta):
        resultados.append(
            Resultado(
                catalogos.NO_EVALUABLE,
                f"No se puede verificar la vigencia documentada: {motivo or motivo_d or motivo_h}.",
                detalle="vigencia",
            )
        )
        return resultados

    evidencias = (
        _evidencias_campo(ctx, ctx.campo("accidente.fecha"))
        + _evidencias_campo(ctx, ctx.campo("administrativo.vigencia_poliza_desde"))
        + _evidencias_campo(ctx, ctx.campo("administrativo.vigencia_poliza_hasta"))
    )
    if desde <= accidente <= hasta:
        resultados.append(
            Resultado(
                catalogos.SIN_INCONSISTENCIA,
                f"La fecha del accidente ({accidente:%d/%m/%Y}) está dentro de la vigencia documentada "
                f"({desde:%d/%m/%Y} a {hasta:%d/%m/%Y}).",
                evidencias,
                "vigencia",
            )
        )
    else:
        resultados.append(
            Resultado(
                catalogos.POSIBLE_INCONSISTENCIA,
                f"La fecha del accidente ({accidente:%d/%m/%Y}) está fuera de la vigencia que aparece en los documentos "
                f"({desde:%d/%m/%Y} a {hasta:%d/%m/%Y}). La cobertura definitiva requiere validación.",
                evidencias,
                "vigencia",
            )
        )
    return resultados


# =====================================================================
# R09: pacientes distintos
# =====================================================================


@verificacion("pacientes_distintos")
def pacientes_distintos(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    estado = ctx.campo("paciente.nombre")
    datos = [d for v in estado.valores for d in v.datos]
    documentos = {d.documento_id for d in datos}
    if len(documentos) < 2 and len(estado.valores) < 2:
        return [Resultado(catalogos.NO_EVALUABLE, "El nombre del paciente no aparece en al menos dos soportes distintos.")]

    minimo = float(regla.parametros.get("similitud_minima", 0.5))
    base = estado.valores[0]
    distintos = [v for v in estado.valores[1:] if _similitud_nombres(base.mostrar, v.mostrar) < minimo]
    if not distintos:
        return [
            Resultado(
                catalogos.SIN_INCONSISTENCIA,
                f"Los nombres del paciente son compatibles entre {len(datos)} registros.",
                [ctx.evidencia_dato(d) for d in datos],
            )
        ]
    involucrados = [base] + distintos
    return [
        Resultado(
            catalogos.POSIBLE_INCONSISTENCIA,
            "Se encontraron nombres de paciente muy distintos: "
            + "; ".join(f"«{v.mostrar}»" for v in involucrados)
            + ". Verifique si hay documentos de otro paciente.",
            [ctx.evidencia_dato(d) for v in involucrados for d in v.datos],
        )
    ]


# =====================================================================
# R10: fechas de atención
# =====================================================================


@verificacion("fechas_atencion")
def fechas_atencion(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    accidente, motivo_a = _fecha_unica(ctx, "accidente.fecha")
    ingreso, motivo_i = _fecha_unica(ctx, "clinico.fecha_ingreso")
    egreso, _ = _fecha_unica(ctx, "clinico.fecha_egreso")
    resultados: list[Resultado] = []

    for campo_id in ("clinico.fecha_ingreso", "clinico.fecha_egreso"):
        estado = ctx.campo(campo_id)
        if len(estado.valores) > 1:
            resultados.append(
                Resultado(
                    catalogos.POSIBLE_INCONSISTENCIA,
                    f"«{estado.campo.etiqueta}» tiene valores distintos: {_valores_texto(estado)}.",
                    _evidencias_campo(ctx, estado),
                    estado.campo.etiqueta,
                )
            )

    def evidencias(*campos):
        return [e for c in campos for e in _evidencias_campo(ctx, ctx.campo(c))]

    if accidente and ingreso:
        dias = (ingreso - accidente).days
        if dias < 0:
            resultados.append(
                Resultado(
                    catalogos.POSIBLE_INCONSISTENCIA,
                    f"El ingreso ({ingreso:%d/%m/%Y}) es anterior al accidente ({accidente:%d/%m/%Y}).",
                    evidencias("accidente.fecha", "clinico.fecha_ingreso"),
                    "ingreso antes del accidente",
                )
            )
        elif dias > int(regla.parametros.get("dias_maximos_accidente_ingreso", 30)):
            resultados.append(
                Resultado(
                    catalogos.POSIBLE_INCONSISTENCIA,
                    f"Pasaron {dias} días entre el accidente ({accidente:%d/%m/%Y}) y el ingreso ({ingreso:%d/%m/%Y}). "
                    "Requiere aclaración (umbral provisional, pendiente de validación).",
                    evidencias("accidente.fecha", "clinico.fecha_ingreso"),
                    "tiempo accidente-ingreso",
                )
            )

    if ingreso and egreso and egreso < ingreso:
        resultados.append(
            Resultado(
                catalogos.POSIBLE_INCONSISTENCIA,
                f"El egreso ({egreso:%d/%m/%Y}) es anterior al ingreso ({ingreso:%d/%m/%Y}).",
                evidencias("clinico.fecha_ingreso", "clinico.fecha_egreso"),
                "egreso antes del ingreso",
            )
        )

    if accidente:
        for valor in ctx.campo("clinico.fecha_atencion").valores:
            fecha = leer_fecha(valor.mostrar)
            if fecha and fecha < accidente:
                resultados.append(
                    Resultado(
                        catalogos.POSIBLE_INCONSISTENCIA,
                        f"Hay una atención del {fecha:%d/%m/%Y}, anterior al accidente ({accidente:%d/%m/%Y}).",
                        [ctx.evidencia_dato(d) for d in valor.datos] + evidencias("accidente.fecha"),
                        f"atención {fecha:%d/%m/%Y}",
                    )
                )

    if resultados:
        return resultados
    if not accidente or not ingreso:
        return [Resultado(catalogos.NO_EVALUABLE, f"No se puede revisar la secuencia de fechas: {motivo_a or motivo_i}.")]
    return [
        Resultado(
            catalogos.SIN_INCONSISTENCIA,
            "La secuencia de fechas (accidente, ingreso, atenciones y egreso) es coherente.",
            evidencias("accidente.fecha", "clinico.fecha_ingreso", "clinico.fecha_egreso"),
        )
    ]


# =====================================================================
# R11: lateralidad
# =====================================================================

PATRON_LADO = r"(derech[oa]s?|izquierd[oa]s?|bilateral(?:es)?)"


@verificacion("lateralidad")
def lateralidad(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    regiones = [normalizar(r) for r in regla.parametros.get("regiones", [])]
    if not regiones:
        return [Resultado(catalogos.NO_EVALUABLE, "La regla no tiene regiones anatómicas configuradas.")]
    patron = re.compile(r"\b(" + "|".join(re.escape(r) for r in regiones) + r")s?\b(?:\s+\w+){0,3}?\s+" + PATRON_LADO + r"\b")

    lados: dict[str, dict[str, list[Evidencia]]] = defaultdict(lambda: defaultdict(list))
    for pagina in ctx.paginas_con_texto():
        texto = normalizar_conservando_longitud(pagina.texto)
        for m in patron.finditer(texto):
            lado = "bilateral" if m.group(2).startswith("bilateral") else ("derecho" if m.group(2).startswith("derech") else "izquierdo")
            lados[m.group(1)][lado].append(ctx.evidencia_pagina(pagina, m.start(), m.end()))

    if not lados:
        return [Resultado(catalogos.NO_EVALUABLE, "No se identificaron regiones anatómicas con lateralidad en el texto.")]

    resultados = []
    for region, por_lado in sorted(lados.items()):
        if "derecho" in por_lado and "izquierdo" in por_lado:
            nota = " También se menciona como bilateral." if "bilateral" in por_lado else ""
            resultados.append(
                Resultado(
                    catalogos.POSIBLE_INCONSISTENCIA,
                    f"La región «{region}» aparece como DERECHA en {len(por_lado['derecho'])} lugar(es) "
                    f"e IZQUIERDA en {len(por_lado['izquierdo'])}.{nota} Puede tratarse de lesiones bilaterales: verifique.",
                    por_lado["derecho"] + por_lado["izquierdo"],
                    region,
                )
            )
        else:
            lado = next(iter(por_lado))
            resultados.append(
                Resultado(
                    catalogos.SIN_INCONSISTENCIA,
                    f"La región «{region}» aparece siempre como {lado} ({len(por_lado[lado])} mención(es)).",
                    por_lado[lado][:3],
                    region,
                )
            )
    return resultados


# =====================================================================
# R12: ayudas diagnósticas
# =====================================================================


@verificacion("ayudas_diagnosticas")
def ayudas_diagnosticas(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    p = regla.parametros
    informes = ctx.paginas_de_tipo(p["tipos_informe"])
    if not informes:
        return [Resultado(catalogos.NO_APLICA, "No se identificaron informes de ayudas diagnósticas.")]
    soportes = ctx.paginas_de_tipo(p["tipos_justificacion"])

    resultados = []
    for estudio, palabras in p["estudios"].items():
        en_informes = ctx.buscar(informes, palabras)
        if not en_informes:
            continue
        pagina_inf, m = en_informes[0]
        evidencia_informe = ctx.evidencia_pagina(pagina_inf, m.start(), m.end())
        if not soportes:
            resultados.append(
                Resultado(
                    catalogos.FALTANTE,
                    f"Hay informe de {estudio}, pero no se identificaron páginas de historia clínica, urgencias, evolución u órdenes "
                    "para verificar su justificación. Esto no demuestra impertinencia.",
                    [evidencia_informe],
                    estudio,
                )
            )
            continue
        en_soportes = ctx.buscar(soportes, palabras)
        if en_soportes:
            pagina_sop, ms = en_soportes[0]
            resultados.append(
                Resultado(
                    catalogos.SIN_INCONSISTENCIA,
                    f"El estudio ({estudio}) se menciona en los soportes clínicos.",
                    [evidencia_informe, ctx.evidencia_pagina(pagina_sop, ms.start(), ms.end())],
                    estudio,
                )
            )
        else:
            resultados.append(
                Resultado(
                    catalogos.FALTANTE,
                    f"Hay informe de {estudio}, pero no se identificó su orden ni su mención en los soportes clínicos con texto. "
                    "Esto no demuestra que el estudio sea impertinente: verifique la justificación.",
                    [evidencia_informe],
                    estudio,
                )
            )
    return resultados or [
        Resultado(catalogos.NO_EVALUABLE, "Hay informes, pero no se reconoció el tipo de estudio con las palabras configuradas.")
    ]


# =====================================================================
# R13: estancia
# =====================================================================


@verificacion("estancia")
def estancia(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    ingreso, motivo_i = _fecha_unica(ctx, "clinico.fecha_ingreso")
    egreso, motivo_e = _fecha_unica(ctx, "clinico.fecha_egreso")
    if not ingreso or not egreso:
        return [Resultado(catalogos.NO_EVALUABLE, f"No se puede calcular la estancia: {motivo_i or motivo_e}.")]
    dias = (egreso - ingreso).days
    if dias < 0:
        return [Resultado(catalogos.NO_EVALUABLE, "El egreso es anterior al ingreso (ver regla R10).")]

    evidencias = _evidencias_campo(ctx, ctx.campo("clinico.fecha_ingreso")) + _evidencias_campo(ctx, ctx.campo("clinico.fecha_egreso"))
    notas = ctx.paginas_de_tipo(["Notas de evolución"])
    resultados = []
    if dias >= 1 and not notas:
        resultados.append(
            Resultado(
                catalogos.FALTANTE,
                f"Estancia de {dias} día(s) sin páginas identificadas como notas de evolución. "
                "Puede que estén sin texto o clasificadas con otro tipo: verifique.",
                evidencias,
                "notas de evolución",
            )
        )
    umbral = int(regla.parametros.get("umbral_dias_revision", 3))
    if dias > umbral:
        resultados.append(
            Resultado(
                catalogos.POSIBLE_INCONSISTENCIA,
                f"Estancia de {dias} días, mayor al umbral de revisión de {umbral} días (provisional, pendiente de validación). "
                f"Se identificaron {len(notas)} página(s) de notas de evolución. Verifique la justificación de la estancia.",
                evidencias + [ctx.evidencia_pagina(n) for n in notas[:3]],
                "duración",
            )
        )
    return resultados or [
        Resultado(
            catalogos.SIN_INCONSISTENCIA,
            f"Estancia de {dias} día(s) con {len(notas)} página(s) de notas de evolución identificadas.",
            evidencias,
        )
    ]


# =====================================================================
# R14: materiales de osteosíntesis
# =====================================================================


@verificacion("materiales_osteosintesis")
def materiales_osteosintesis(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    p = regla.parametros
    paginas_material = ctx.paginas_de_tipo(p["tipos_material"])
    if not paginas_material:
        return [Resultado(catalogos.NO_APLICA, "No se identificaron soportes de materiales de osteosíntesis.")]
    quirurgicas = ctx.paginas_de_tipo(p["tipos_quirurgicos"])
    if not quirurgicas:
        return [
            Resultado(
                catalogos.FALTANTE,
                "Hay soportes de materiales de osteosíntesis, pero no se identificó la descripción quirúrgica.",
                [ctx.evidencia_pagina(pg) for pg in paginas_material],
            )
        ]

    resultados = []
    for material in p["materiales"]:
        palabras = [material, material + "s", material + "es"]
        en_material = ctx.buscar(paginas_material, palabras)
        if not en_material:
            continue
        pagina_m, m = en_material[0]
        en_cirugia = ctx.buscar(quirurgicas, palabras)
        if en_cirugia:
            pagina_c, mc = en_cirugia[0]
            resultados.append(
                Resultado(
                    catalogos.SIN_INCONSISTENCIA,
                    f"El material «{material}» aparece en la descripción quirúrgica. Verifique cantidades.",
                    [ctx.evidencia_pagina(pagina_m, m.start(), m.end()), ctx.evidencia_pagina(pagina_c, mc.start(), mc.end())],
                    material,
                )
            )
        else:
            resultados.append(
                Resultado(
                    catalogos.POSIBLE_INCONSISTENCIA,
                    f"El material «{material}» aparece en los soportes de material, pero no se identificó en la descripción quirúrgica.",
                    [ctx.evidencia_pagina(pagina_m, m.start(), m.end())] + [ctx.evidencia_pagina(q) for q in quirurgicas[:2]],
                    material,
                )
            )
    return resultados or [
        Resultado(catalogos.NO_EVALUABLE, "No se reconocieron materiales con las palabras configuradas.")
    ]


# =====================================================================
# R15: medicamentos
# =====================================================================


@verificacion("medicamentos")
def medicamentos(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    formulas = ctx.paginas_de_tipo(regla.parametros["tipos_formula"])
    if not formulas:
        return [Resultado(catalogos.NO_APLICA, "No se identificaron fórmulas de medicamentos.")]
    ordenes = ctx.paginas_de_tipo(regla.parametros["tipos_orden"])
    if not ordenes:
        return [
            Resultado(
                catalogos.FALTANTE,
                "Hay fórmulas de medicamentos, pero no se identificaron órdenes médicas ni soportes clínicos para cotejarlas.",
                [ctx.evidencia_pagina(f) for f in formulas[:3]],
            )
        ]
    return [
        Resultado(
            catalogos.NO_EVALUABLE,
            "Hay fórmulas y soportes clínicos. El cotejo de cada medicamento facturado requiere el lector de XML/RIPS (Fase 5).",
            [ctx.evidencia_pagina(f) for f in formulas[:3]],
        )
    ]


# =====================================================================
# R16: ilegibles y sin texto
# =====================================================================


@verificacion("ilegibles")
def ilegibles(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    resultados = []
    marcadas = [p for p in ctx.paginas if p.legibilidad == catalogos.NO_LEGIBLE]
    for documento_id in sorted({p.documento_id for p in marcadas}):
        paginas = [p for p in marcadas if p.documento_id == documento_id]
        resultados.append(
            Resultado(
                catalogos.ILEGIBLE,
                f"El auditor marcó como ilegibles las páginas {', '.join(str(p.numero) for p in paginas)} de «{ctx.nombre_documento(documento_id)}».",
                [ctx.evidencia_pagina(p, texto="Página marcada como ilegible por el auditor.") for p in paginas],
                ctx.nombre_documento(documento_id),
            )
        )
    sin_texto = [p for p in ctx.paginas if p.requiere_analisis_visual and p.legibilidad != catalogos.NO_LEGIBLE]
    if sin_texto:
        resultados.append(
            Resultado(
                catalogos.NO_EVALUABLE,
                f"{len(sin_texto)} página(s) sin texto no fueron revisadas por las reglas automáticas: requieren OCR o revisión visual.",
                [ctx.evidencia_pagina(p, texto="Página sin texto (pendiente de análisis visual).") for p in sin_texto],
                "páginas sin texto",
            )
        )
    errores = [d for d in ctx.documentos if d.estado == catalogos.PROC_ERROR]
    for documento in errores:
        resultados.append(
            Resultado(
                catalogos.ILEGIBLE,
                f"El archivo «{documento.nombre_original}» no se pudo leer: {documento.mensaje}",
                [Evidencia(documento.nombre_original, documento.mensaje or "", documento.id, None)],
                documento.nombre_original,
            )
        )
    return resultados or [Resultado(catalogos.SIN_INCONSISTENCIA, "Todas las páginas tienen texto y ninguna fue marcada como ilegible.")]


# =====================================================================
# R17: información no encontrada
# =====================================================================


@verificacion("informacion_no_encontrada")
def informacion_no_encontrada(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    resultados = []
    sin_texto = sum(p.requiere_analisis_visual for p in ctx.paginas)
    nota = f" Hay {sin_texto} página(s) sin texto donde podría estar." if sin_texto else ""
    for estado in ctx.todos_los_campos():
        if estado.campo.revisar_si_falta and estado.sin_dato:
            resultados.append(
                Resultado(
                    catalogos.FALTANTE,
                    f"No se identificó «{estado.campo.etiqueta}» en los soportes revisados.{nota} "
                    "La ausencia no demuestra por sí sola un error.",
                    detalle=estado.campo.etiqueta,
                )
            )
    return resultados or [Resultado(catalogos.SIN_INCONSISTENCIA, "Se identificaron todos los datos clave de la ficha.")]


# =====================================================================
# R18: firmas
# =====================================================================


@verificacion("firmas")
def firmas(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    tipos = regla.parametros["tipos"]
    palabras = regla.parametros["palabras"]
    resultados = []
    for documento in ctx.documentos:
        paginas = [p for p in ctx.paginas if p.documento_id == documento.id]
        for seccion in agrupar_secciones(paginas):
            if seccion.tipo not in tipos:
                continue
            paginas_seccion = [p for p in paginas if p.numero in seccion.paginas]
            if ctx.buscar(paginas_seccion, palabras):
                continue
            rango = f"{seccion.pagina_inicio}-{seccion.pagina_fin}" if seccion.pagina_fin != seccion.pagina_inicio else str(seccion.pagina_inicio)
            resultados.append(
                Resultado(
                    catalogos.FALTANTE,
                    f"En «{seccion.tipo}» (páginas {rango} de «{documento.nombre_original}») no se identificó en el texto "
                    "firma ni registro del profesional. Las firmas en imagen no se detectan: verifique visualmente.",
                    [ctx.evidencia_pagina(paginas_seccion[0])],
                    f"{seccion.tipo} p. {rango} {documento.nombre_original}",
                )
            )
    return resultados or [Resultado(catalogos.SIN_INCONSISTENCIA, "Los documentos clínicos con texto tienen indicios de firma o registro profesional.")]


# =====================================================================
# R19: duplicados
# =====================================================================


@verificacion("duplicados")
def duplicados(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    minimo = int(regla.parametros.get("minimo_caracteres", 80))
    grupos = defaultdict(list)
    for pagina in ctx.paginas_con_texto():
        clave = normalizar(pagina.texto)
        if len(clave) >= minimo:
            grupos[clave].append(pagina)
    resultados = [
        Resultado(
            catalogos.POSIBLE_INCONSISTENCIA,
            "Páginas con texto idéntico: "
            + "; ".join(f"«{p.documento.nombre_original}» p. {p.numero}" for p in paginas)
            + ". Verifique si es un soporte duplicado.",
            [ctx.evidencia_pagina(p) for p in paginas],
            ", ".join(f"{p.documento_id}-{p.numero}" for p in paginas),
        )
        for paginas in grupos.values()
        if len(paginas) > 1
    ]
    return resultados or [Resultado(catalogos.SIN_INCONSISTENCIA, "No se encontraron páginas con texto idéntico.")]


# =====================================================================
# R20: correcciones del auditor
# =====================================================================


@verificacion("correcciones_auditor")
def correcciones_auditor(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    resultados = []
    for estado in ctx.todos_los_campos():
        for valor in estado.valores:
            for dato in valor.datos:
                if dato.valor_corregido is not None and dato.valor_corregido != dato.valor:
                    resultados.append(
                        Resultado(
                            catalogos.POSIBLE_INCONSISTENCIA,
                            f"«{estado.campo.etiqueta}»: el documento dice «{dato.valor}» y el auditor lo corrigió a «{dato.valor_corregido}». "
                            "Confirme que la corrección tiene soporte.",
                            [ctx.evidencia_dato(dato)],
                            f"dato {dato.id}",
                        )
                    )
    return resultados or [Resultado(catalogos.NO_APLICA, "No hay datos corregidos por el auditor.")]


# =====================================================================
# R21: servicios del XML/RIPS sin soporte
# =====================================================================


@verificacion("servicios_sin_soporte")
def servicios_sin_soporte(ctx: ContextoAuditoria, regla) -> list[Resultado]:
    estructurados = ctx.documentos_estructurados()
    if not estructurados:
        return [Resultado(catalogos.NO_EVALUABLE, "No se cargaron XML de factura ni RIPS.")]
    return [
        Resultado(
            catalogos.NO_EVALUABLE,
            f"Hay {len(estructurados)} archivo(s) XML/RIPS cargados, pero su lector está pendiente (Fase 5): "
            "los servicios facturados aún no se pueden cruzar con la historia clínica.",
            [Evidencia(d.nombre_original, "Archivo pendiente de lectura.", d.id, None) for d in estructurados],
        )
    ]
