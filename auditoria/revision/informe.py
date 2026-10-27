"""Informe en texto plano, listo para copiar y pegar en el sistema de destino."""

from datetime import datetime

from auditoria.revision.cuenta import Cuenta
from auditoria.revision.puntos import CORRECTO, ERROR, FALTA, NO_APLICA, REVISAR, Punto, _lineas_factura, parametros

TITULOS = {
    ERROR: "ERRORES ENCONTRADOS",
    FALTA: "DOCUMENTOS O DATOS QUE NO SE ENCONTRARON",
    REVISAR: "REVISAR MANUALMENTE",
    CORRECTO: "SIN ERRORES",
    NO_APLICA: "NO APLICA",
}


def _linea(punto: Punto) -> str:
    folios = f" [{', '.join(punto.folios)}]" if punto.folios and punto.resultado != CORRECTO else ""
    return f"- {punto.nombre}: {punto.detalle}{folios}"


def _rangos(numeros: list[int]) -> str:
    """[1,2,3,7] -> '1-3, 7'"""
    partes, inicio = [], None
    for i, n in enumerate(numeros):
        if inicio is None:
            inicio = n
        if i + 1 == len(numeros) or numeros[i + 1] != n + 1:
            partes.append(str(inicio) if inicio == n else f"{inicio}-{n}")
            inicio = None
    return ", ".join(partes)


def lectura_de_la_cuenta(cuenta: Cuenta) -> list[str]:
    """Qué documentos se reconocieron, cuáles no y qué folios no se pudieron leer.

    Sirve para distinguir un "Falta" real de un documento que la app no supo reconocer.
    """
    lineas = []
    archivos = sorted({f.archivo for f in cuenta.folios})
    tipos_presentes = {f.tipo for f in cuenta.folios if f.tipo}
    for archivo in archivos:
        del_archivo = [f for f in cuenta.folios if f.archivo == archivo]
        prefijo = f"{archivo}: " if len(archivos) > 1 else ""
        por_tipo: dict[str, list[int]] = {}
        for f in del_archivo:
            por_tipo.setdefault(f.tipo or ("En blanco" if f.en_blanco else "Sin texto (escaneado sin leer)"), []).append(f.numero)
        reconocidos = "; ".join(f"{t} ({_rangos(ns)})" for t, ns in por_tipo.items())
        lineas.append(f"- {prefijo}Documentos reconocidos: {reconocidos}.")

    for esperado in parametros().get("documentos_esperados", []):
        opciones = esperado.split("|")
        if not tipos_presentes & set(opciones):
            lineas.append(
                f"- No se reconoció {' / '.join(opciones)}. Si sí está en la cuenta, indique el folio para ajustar la lectura; "
                "los puntos que dependen de este documento salen como «no se encontró»."
            )
    otros = [f for f in cuenta.folios if f.tipo == "Otros"]
    if otros:
        lineas.append(f"- Folios sin tipo reconocido (no se usaron en las comparaciones por tipo): {', '.join(cuenta.ubicacion(f) for f in otros)}.")
    if "Factura" in tipos_presentes and not _lineas_factura(cuenta):
        lineas.append("- La factura se reconoció, pero no se pudieron leer sus líneas de cobro (cantidades): los chequeos de cobro no se aplicaron.")
    ocr = [f for f in cuenta.folios if f.metodo == "OCR"]
    if ocr:
        lineas.append(f"- Leídos con OCR (escaneados, la lectura puede tener errores): {', '.join(cuenta.ubicacion(f) for f in ocr)}.")
    return lineas


def generar_texto(cuenta: Cuenta, puntos: list[Punto], incluir_correctos: bool = True) -> str:
    archivos = sorted({f.archivo for f in cuenta.folios})
    errores = sum(p.resultado == ERROR for p in puntos)
    faltan = sum(p.resultado == FALTA for p in puntos)
    revisar = sum(p.resultado == REVISAR for p in puntos)

    lineas = [
        "AUDITORÍA DE CUENTA SOAT",
        f"Archivo(s): {', '.join(archivos) or '(ninguno)'} — {len(cuenta.folios)} folio(s)",
        f"Fecha de revisión: {datetime.now():%d/%m/%Y %H:%M}",
        f"Resultado: {errores} error(es), {faltan} faltante(s), {revisar} punto(s) para revisar manualmente.",
    ]
    sin_texto = cuenta.folios_sin_texto()
    if sin_texto:
        lineas.append(
            f"ATENCIÓN: {len(sin_texto)} folio(s) escaneados no se pudieron leer y no fueron revisados: "
            + ", ".join(cuenta.ubicacion(f) for f in sin_texto)
            + "."
        )
    en_blanco = cuenta.folios_en_blanco()
    if en_blanco:
        lineas.append(f"Folios en blanco (sin contenido): {', '.join(cuenta.ubicacion(f) for f in en_blanco)}.")
    for error in cuenta.errores_lectura:
        lineas.append(f"ATENCIÓN: no se pudo leer {error}")

    for resultado in (ERROR, FALTA, REVISAR, CORRECTO):
        if resultado == CORRECTO and not incluir_correctos:
            continue
        del_resultado = [p for p in puntos if p.resultado == resultado]
        if not del_resultado:
            continue
        lineas += ["", TITULOS[resultado]]
        lineas += [_linea(p) for p in del_resultado]

    lineas += ["", "LECTURA DE LA CUENTA"] + lectura_de_la_cuenta(cuenta)
    return "\n".join(lineas) + "\n"
