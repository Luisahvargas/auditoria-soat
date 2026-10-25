"""Ficha maestra de la cuenta: datos con su origen, evidencia y validación del auditor.

Reglas:
- Si dos fuentes difieren se conservan ambos valores (nunca se sobrescribe en silencio).
- El auditor puede validar, corregir o descartar; se conserva el valor original.
- La edad se calcula con la fecha del accidente, nunca con la fecha actual.
- Ninguna fuente se asume correcta por sí sola (tampoco el FURIPS).
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.servicio import obtener_auditoria, verificar_abierta
from auditoria.db.modelos import DatoFicha, ahora
from auditoria.db.repositorios import RepositorioDocumentos, RepositorioFicha, RepositorioTrazabilidad
from auditoria.extraccion.extractor import CampoFicha, cargar_definicion, extraer_de_texto, normalizar_valor
from auditoria.texto import calcular_edad, leer_fecha

METODOS_AUTOMATICOS = ("Texto PDF", "OCR")
# XML y RIPS son la fuente principal para datos de facturación; luego lo manual y el texto.
PRIORIDAD_METODO = {"XML": 0, "RIPS": 1, "Manual": 2, "Texto PDF": 3, "OCR": 4, "IA": 5}


class ErrorFicha(ValueError):
    """Operación inválida sobre la ficha."""


@dataclass
class ValorCampo:
    """Un valor distinto de un campo, con todas las fuentes que lo respaldan."""

    normalizado: str
    mostrar: str
    datos: list[DatoFicha] = field(default_factory=list)


@dataclass
class EstadoCampo:
    campo: CampoFicha
    valores: list[ValorCampo] = field(default_factory=list)

    @property
    def sin_dato(self) -> bool:
        return not self.valores

    @property
    def discrepancia(self) -> bool:
        """Varios valores distintos en un campo que debería tener uno solo."""
        return not self.campo.multiple and len(self.valores) > 1


@dataclass
class EdadCalculada:
    valor: int | None
    explicacion: str


def extraer_auditoria(sesion: Session, auditoria_id: int, usuario_id: int) -> int:
    """Extrae los campos de todas las páginas con texto. Devuelve cuántos datos se registraron.

    Antes borra los datos automáticos aún no revisados; lo validado, corregido o
    agregado manualmente por el auditor se conserva.
    """
    verificar_abierta(obtener_auditoria(sesion, auditoria_id))
    repositorio = RepositorioFicha(sesion)
    repositorio.borrar_automaticos_sin_revisar(auditoria_id, METODOS_AUTOMATICOS, catalogos.VALIDACION_PENDIENTE)

    definicion = cargar_definicion()
    existentes = {
        (d.campo, d.documento_id, d.numero_pagina, normalizar_valor(definicion.campo(d.campo).tipo, d.valor))
        for d in repositorio.listar_por_auditoria(auditoria_id)
        if _campo_conocido(definicion, d.campo)
    }
    creados = 0
    for pagina in RepositorioDocumentos(sesion).listar_paginas_por_auditoria(auditoria_id):
        if not pagina.texto or pagina.requiere_analisis_visual:
            continue
        for coincidencia in extraer_de_texto(pagina.texto, definicion):
            tipo = definicion.campo(coincidencia.campo_id).tipo
            clave = (coincidencia.campo_id, pagina.documento_id, pagina.numero, normalizar_valor(tipo, coincidencia.valor))
            if clave in existentes:
                continue
            existentes.add(clave)
            repositorio.agregar(
                DatoFicha(
                    auditoria_id=auditoria_id,
                    campo=coincidencia.campo_id,
                    valor=coincidencia.valor,
                    documento_id=pagina.documento_id,
                    numero_pagina=pagina.numero,
                    evidencia=coincidencia.evidencia,
                    metodo=pagina.metodo_texto if pagina.metodo_texto in METODOS_AUTOMATICOS else "Texto PDF",
                    confianza="baja" if pagina.metodo_texto == "OCR" else "media",
                    usuario_creacion_id=usuario_id,
                )
            )
            creados += 1
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "ficha_extraida", f"datos={creados}", auditoria_id)
    return creados


def _campo_conocido(definicion, campo_id: str) -> bool:
    try:
        definicion.campo(campo_id)
        return True
    except KeyError:
        return False


def construir_ficha(sesion: Session, auditoria_id: int) -> dict[str, list[EstadoCampo]]:
    """Agrupa los datos por bloque y campo. Los datos descartados por el auditor no cuentan."""
    definicion = cargar_definicion()
    estados = {c.id: EstadoCampo(c) for c in definicion.campos}
    datos = [
        d
        for d in RepositorioFicha(sesion).listar_por_auditoria(auditoria_id)
        if d.estado_validacion != catalogos.VALIDACION_DESCARTADO and d.campo in estados
    ]
    datos.sort(key=lambda d: (PRIORIDAD_METODO.get(d.metodo, 9), d.id))
    for dato in datos:
        estado = estados[dato.campo]
        normalizado = normalizar_valor(estado.campo.tipo, dato.valor_efectivo)
        valor = next((v for v in estado.valores if v.normalizado == normalizado), None)
        if valor is None:
            valor = ValorCampo(normalizado, dato.valor_efectivo)
            estado.valores.append(valor)
        valor.datos.append(dato)

    ficha: dict[str, list[EstadoCampo]] = {bloque: [] for bloque in definicion.bloques}
    for campo in definicion.campos:
        ficha[campo.bloque].append(estados[campo.id])
    return ficha


def edad_al_accidente(ficha: dict[str, list[EstadoCampo]]) -> EdadCalculada:
    """Edad con la fecha del accidente y la de nacimiento. Si falta o hay discrepancia: no evaluable."""
    campos = {e.campo.id: e for estados in ficha.values() for e in estados}
    nacimiento, accidente = campos["paciente.fecha_nacimiento"], campos["accidente.fecha"]
    for estado, nombre in ((nacimiento, "fecha de nacimiento"), (accidente, "fecha del accidente")):
        if estado.sin_dato:
            return EdadCalculada(None, f"{catalogos.NO_EVALUABLE}: no se identificó la {nombre}.")
        if estado.discrepancia:
            return EdadCalculada(None, f"{catalogos.NO_EVALUABLE}: la {nombre} tiene valores distintos entre documentos.")
    fecha_nacimiento = leer_fecha(nacimiento.valores[0].mostrar)
    fecha_accidente = leer_fecha(accidente.valores[0].mostrar)
    edad = calcular_edad(fecha_nacimiento, fecha_accidente)
    if edad is None:
        return EdadCalculada(None, f"{catalogos.NO_EVALUABLE}: las fechas no se pudieron interpretar o son incompatibles.")
    return EdadCalculada(edad, f"{edad} años a la fecha del accidente ({fecha_accidente:%d/%m/%Y}).")


# ----------------------- Acciones del auditor -----------------------


def _dato_editable(sesion: Session, dato_id: int) -> DatoFicha:
    dato = RepositorioFicha(sesion).obtener(dato_id)
    if dato is None:
        raise ErrorFicha("El dato no existe.")
    verificar_abierta(obtener_auditoria(sesion, dato.auditoria_id))
    return dato


def _registrar_validacion(sesion, dato: DatoFicha, estado: str, usuario_id: int, accion: str) -> None:
    dato.estado_validacion = estado
    dato.usuario_validacion_id = usuario_id
    dato.fecha_validacion = ahora()
    RepositorioTrazabilidad(sesion).registrar(usuario_id, accion, f"dato_id={dato.id}; campo={dato.campo}", dato.auditoria_id)


def validar_dato(sesion: Session, dato_id: int, usuario_id: int) -> DatoFicha:
    dato = _dato_editable(sesion, dato_id)
    _registrar_validacion(sesion, dato, catalogos.VALIDACION_VALIDADO, usuario_id, "dato_validado")
    return dato


def corregir_dato(sesion: Session, dato_id: int, nuevo_valor: str, usuario_id: int) -> DatoFicha:
    """Guarda la corrección del auditor sin perder el valor original."""
    nuevo_valor = (nuevo_valor or "").strip()
    if not nuevo_valor:
        raise ErrorFicha("El valor corregido no puede estar vacío.")
    dato = _dato_editable(sesion, dato_id)
    dato.valor_corregido = nuevo_valor
    _registrar_validacion(sesion, dato, catalogos.VALIDACION_CORREGIDO, usuario_id, "dato_corregido")
    return dato


def descartar_dato(sesion: Session, dato_id: int, usuario_id: int) -> DatoFicha:
    dato = _dato_editable(sesion, dato_id)
    _registrar_validacion(sesion, dato, catalogos.VALIDACION_DESCARTADO, usuario_id, "dato_descartado")
    return dato


def agregar_dato_manual(
    sesion: Session,
    auditoria_id: int,
    campo_id: str,
    valor: str,
    usuario_id: int,
    documento_id: int | None = None,
    numero_pagina: int | None = None,
    evidencia: str | None = None,
) -> DatoFicha:
    """El auditor registra un dato que leyó él mismo (idealmente con archivo y página)."""
    verificar_abierta(obtener_auditoria(sesion, auditoria_id))
    try:
        cargar_definicion().campo(campo_id)
    except KeyError as error:
        raise ErrorFicha(f"Campo desconocido: {campo_id}") from error
    valor = (valor or "").strip()
    if not valor:
        raise ErrorFicha("El valor no puede estar vacío.")
    if documento_id is not None:
        documento = RepositorioDocumentos(sesion).obtener(documento_id)
        if documento is None or documento.auditoria_id != auditoria_id:
            raise ErrorFicha("El documento indicado no pertenece a esta auditoría.")
        if numero_pagina is not None and not (1 <= numero_pagina <= (documento.numero_paginas or 0)):
            raise ErrorFicha("La página indicada no existe en ese documento.")
    dato = RepositorioFicha(sesion).agregar(
        DatoFicha(
            auditoria_id=auditoria_id,
            campo=campo_id,
            valor=valor,
            documento_id=documento_id,
            numero_pagina=numero_pagina,
            evidencia=(evidencia or "").strip() or None,
            metodo="Manual",
            estado_validacion=catalogos.VALIDACION_VALIDADO,
            usuario_validacion_id=usuario_id,
            fecha_validacion=ahora(),
            usuario_creacion_id=usuario_id,
        )
    )
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "dato_manual_agregado", f"dato_id={dato.id}; campo={campo_id}", auditoria_id)
    return dato
