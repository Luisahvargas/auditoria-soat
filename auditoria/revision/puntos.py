"""Revisión de la cuenta según la lista del auditor.

Cada punto devuelve: Error, Falta, Revisar, Correcto o No aplica, con el folio donde está.
- "Error": los documentos se contradicen o algo no cumple.
- "Falta": no se encontró un documento o dato que debería estar.
- "Revisar": el programa no puede decidirlo solo (p. ej. firmas en imagen).
No se inventa nada: si un dato no se encontró se dice "Falta", no "Error".
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

import yaml

from auditoria.config import RUTA_CONFIGURACION
from auditoria.revision.cuenta import Cuenta, Dato, Folio
from auditoria.texto import calcular_edad, leer_fecha, normalizar

ERROR = "Error"
FALTA = "Falta"
REVISAR = "Revisar"
CORRECTO = "Correcto"
NO_APLICA = "No aplica"
ORDEN_RESULTADOS = (ERROR, FALTA, REVISAR, CORRECTO, NO_APLICA)
MAXIMO_FOLIOS_EN_TEXTO = 10
NOTA_OCR = " La diferencia viene de un folio escaneado leído por OCR (puede ser un error de lectura): verifíquelo en el documento."


def _solo_ocr(datos) -> bool:
    """True si todos los datos vienen de folios escaneados leídos por OCR."""
    datos = list(datos)
    return bool(datos) and all(d.folio.metodo == "OCR" for d in datos)


@dataclass
class Punto:
    seccion: str
    nombre: str
    resultado: str
    detalle: str
    folios: list[str] = field(default_factory=list)


@lru_cache(maxsize=2)
def parametros() -> dict:
    return yaml.safe_load((RUTA_CONFIGURACION / "revision.yaml").read_text(encoding="utf-8"))


def _grupo(nombre: str) -> tuple[str, ...]:
    return tuple(parametros()["grupos"][nombre])


def _patron_palabras(palabras) -> re.Pattern:
    """Palabras o frases completas, tolerantes a espacios múltiples."""
    frases = [r"\s+".join(re.escape(p) for p in normalizar(f).split()) for f in palabras]
    return re.compile(r"\b(?:" + "|".join(frases) + r")\b")


def _buscar(folios: list[Folio], palabras) -> list[Folio]:
    patron = _patron_palabras(palabras)
    return [f for f in folios if patron.search(f.texto_normalizado)]


def _contiene(texto: str, palabras) -> bool:
    """Búsqueda por fragmento (sirve para raíces como 'quirurgic')."""
    normal = normalizar(texto)
    return any(normalizar(p) in normal for p in palabras)


def _unicos(lista):
    return list(dict.fromkeys(lista))


def _lista_folios(cuenta: Cuenta, folios) -> list[str]:
    return _unicos(cuenta.ubicacion(f) for f in folios)


def _resumir(ubicaciones: list[str]) -> str:
    if len(ubicaciones) <= MAXIMO_FOLIOS_EN_TEXTO:
        return ", ".join(ubicaciones)
    return ", ".join(ubicaciones[:MAXIMO_FOLIOS_EN_TEXTO]) + f" y {len(ubicaciones) - MAXIMO_FOLIOS_EN_TEXTO} más"


def _documentos(cuenta: Cuenta, tipos) -> list[list[Folio]]:
    """Folios consecutivos del mismo tipo forman un documento (los folios escaneados intermedios no lo cortan)."""
    sin_texto = {(f.archivo, f.numero) for f in cuenta.folios_sin_texto()}
    documentos: list[list[Folio]] = []
    for folio in cuenta.folios:
        if folio.tipo not in tipos:
            continue
        anterior = documentos[-1][-1] if documentos else None
        continua = anterior and all((folio.archivo, n) in sin_texto for n in range(anterior.numero + 1, folio.numero))
        if anterior and anterior.archivo == folio.archivo and anterior.tipo == folio.tipo and continua:
            documentos[-1].append(folio)
        else:
            documentos.append([folio])
    return documentos


# =====================================================================
# Comparación de un dato entre grupos de folios (FURIPS, admisión, SIRAS, póliza...)
# =====================================================================

NOMBRES_GRUPO = {
    "furips": "FURIPS",
    "admision": "hoja de admisión/historia",
    "siras": "SIRAS",
    "factura": "factura",
    "poliza": "póliza/licencia",
    "runt": "RUNT",
    "documentos_vehiculo": "póliza/licencia/RUNT",
}


def _mostrar(dato: Dato) -> str:
    """Valor para el informe: las fechas siempre como dd/mm/aaaa."""
    if "fecha" in dato.campo or "vigencia" in dato.campo:
        fecha = leer_fecha(dato.valor)
        if fecha:
            return f"{fecha:%d/%m/%Y}"
    return dato.valor


def _describir(cuenta: Cuenta, datos: list[Dato], clave=None) -> str:
    clave = clave or (lambda d: d.normalizado)
    por_valor: dict[str, list[Dato]] = {}
    for d in datos:
        por_valor.setdefault(clave(d), []).append(d)
    return "; ".join(
        f"«{_mostrar(ds[0])}» ({_resumir(_lista_folios(cuenta, [d.folio for d in ds]))})" for ds in por_valor.values()
    )


def comparar(
    cuenta: Cuenta, seccion: str, nombre: str, campo: str, grupos: list[str], normalizar_dato=None, coincide_si_comparten=False
) -> Punto:
    """Compara un dato entre grupos de folios.

    - Ningún grupo lo tiene → Falta.  - Solo un grupo → Falta (no hay con qué comparar).
    - Valores iguales → Correcto.     - Valores distintos → Error.
    """
    clave = normalizar_dato or (lambda d: d.normalizado)
    por_grupo = {g: cuenta.datos_de(campo, _grupo(g)) for g in grupos}
    presentes = {g: ds for g, ds in por_grupo.items() if ds}
    faltantes = [NOMBRES_GRUPO[g] for g in grupos if g not in presentes]
    todos = [d for ds in presentes.values() for d in ds]
    folios = _lista_folios(cuenta, [d.folio for d in todos])

    if not presentes:
        return Punto(seccion, nombre, FALTA, f"No se encontró en: {', '.join(faltantes)}.")
    if len(presentes) == 1:
        (grupo, datos), = presentes.items()
        return Punto(
            seccion, nombre, FALTA,
            f"Solo aparece en {NOMBRES_GRUPO[grupo]}: {_describir(cuenta, datos, clave)}. No se encontró en: {', '.join(faltantes)}.",
            folios,
        )

    def coinciden(grupos_datos: dict) -> bool:
        conjuntos = [{clave(d) for d in ds} for ds in grupos_datos.values() if ds]
        if len(conjuntos) < 2:
            return True
        return bool(set.intersection(*conjuntos)) if coincide_si_comparten else len(set.union(*conjuntos)) == 1

    nota = f" No se encontró en: {', '.join(faltantes)}." if faltantes else ""
    if coinciden(presentes):
        conjuntos = [{clave(d) for d in ds} for ds in presentes.values()]
        valor = next(iter(set.intersection(*conjuntos))) if coincide_si_comparten else None
        mostrar = [d for d in todos if valor is None or clave(d) == valor]
        return Punto(seccion, nombre, CORRECTO, f"Coincide: {_describir(cuenta, mostrar, clave)}.{nota}", folios)
    detalle = " | ".join(f"{NOMBRES_GRUPO[g].upper()}: {_describir(cuenta, ds, clave)}" for g, ds in presentes.items())
    # Si sin los datos leídos por OCR todo coincide, la diferencia puede ser un error de lectura.
    sin_ocr = {g: [d for d in ds if d.folio.metodo != "OCR"] for g, ds in presentes.items()}
    if coinciden(sin_ocr) and any(d.folio.metodo == "OCR" for d in todos):
        return Punto(seccion, nombre, REVISAR, f"No coincide. {detalle}.{nota}{NOTA_OCR}", folios)
    return Punto(seccion, nombre, ERROR, f"No coincide. {detalle}.{nota}", folios)


def _clave_direccion(dato: Dato) -> str:
    """Direcciones: se comparan sus números (CL80 CON CR120 = CL 80 # CON CR120)."""
    numeros = re.findall(r"\d+", dato.valor)
    if numeros:
        return "-".join(numeros)
    vacias = {"de", "del", "la", "el", "vereda", "sector", "barrio", "km", "kilometro", "via"}
    return " ".join(p for p in normalizar(dato.valor).split() if p not in vacias)


def _clave_nombre(dato: Dato) -> str:
    """Nombres: mismas palabras en cualquier orden."""
    return " ".join(sorted(normalizar(dato.valor).split()))


CONFUSIONES_LETRA = str.maketrans("01258", "OIZSB")
CONFUSIONES_NUMERO = str.maketrans("OIZSB", "01258")


def _clave_placa(dato: Dato) -> str:
    """Placa sin las confusiones típicas de lectura (I/1, O/0): 3 letras, 2 números, 1 carácter."""
    p = dato.normalizado
    if len(p) != 6:
        return p
    return p[:3].translate(CONFUSIONES_LETRA) + p[3:5].translate(CONFUSIONES_NUMERO) + p[5]


FAMILIAS_CALIDAD = {
    "peaton": "peatón",
    "conductor": "conductor",
    "motociclista": "conductor",
    "pasajero": "pasajero/ocupante",
    "ocupante": "pasajero/ocupante",
    "acompanante": "pasajero/ocupante",
    "parrillero": "pasajero/ocupante",
    "ciclista": "ciclista",
}
FAMILIAS_VEHICULO = {
    "moto": "motocicleta", "motocicleta": "motocicleta",
    "carro": "automóvil", "automovil": "automóvil", "campero": "automóvil", "camioneta": "automóvil",
    "bus": "bus/buseta", "buseta": "bus/buseta", "microbus": "bus/buseta",
    "camion": "camión", "tractocamion": "camión",
    "bicicleta": "bicicleta", "taxi": "taxi",
}


def _familias(texto: str, familias: dict) -> set[str]:
    normal = normalizar(texto)
    return {familia for palabra, familia in familias.items() if re.search(rf"\b{palabra}s?\b", normal)}


def _familia_calidad(dato: Dato) -> str:
    valor = normalizar(dato.valor)
    valor = parametros().get("codigos_calidad", {}).get(valor, valor)
    return FAMILIAS_CALIDAD.get(valor, valor)


# =====================================================================
# 1. FURIPS vs hoja de admisión (y SIRAS)
# =====================================================================

S_FURIPS = "FURIPS vs. hoja de admisión"
G_FURIPS = ["furips", "admision", "siras"]


def _relato(cuenta: Cuenta) -> Punto:
    furips = cuenta.datos_de("accidente.relato", _grupo("furips"))
    admision = [
        d for campo in ("accidente.relato", "clinico.enfermedad_actual", "clinico.motivo_consulta")
        for d in cuenta.datos_de(campo, _grupo("admision"))
    ]
    folios = _lista_folios(cuenta, [d.folio for d in furips + admision])
    if not furips:
        return Punto(S_FURIPS, "Relato de los hechos", FALTA, "No se encontró el relato en el FURIPS.", folios)
    if not admision:
        return Punto(S_FURIPS, "Relato de los hechos", FALTA, "No se encontró el relato en la hoja de admisión/historia.", folios)
    texto_f = " ".join(d.valor for d in furips)
    texto_a = " ".join(d.valor for d in admision)
    diferencias = []
    for nombre, familias in (("calidad de la víctima", FAMILIAS_CALIDAD), ("vehículo", FAMILIAS_VEHICULO)):
        en_f, en_a = _familias(texto_f, familias), _familias(texto_a, familias)
        if en_f and en_a and not (en_f & en_a):
            diferencias.append(f"{nombre}: FURIPS dice {', '.join(en_f)} y la admisión dice {', '.join(en_a)}")
    if diferencias:
        return Punto(S_FURIPS, "Relato de los hechos", ERROR, "Los relatos se contradicen en " + "; ".join(diferencias) + ".", folios)
    return Punto(
        S_FURIPS, "Relato de los hechos", CORRECTO,
        f"Sin contradicción en calidad de la víctima ni tipo de vehículo. FURIPS: «{texto_f[:120]}» | ADMISIÓN: «{texto_a[:120]}».",
        folios,
    )


def _fecha_evento(cuenta: Cuenta):
    fechas = {leer_fecha(d.valor) for d in cuenta.datos_de("accidente.fecha", _grupo("furips"))} - {None}
    if not fechas:
        fechas = {leer_fecha(d.valor) for d in cuenta.datos_de("accidente.fecha")} - {None}
    return fechas.pop() if len(fechas) == 1 else None


def _edad(cuenta: Cuenta) -> Punto:
    nombre = "Edad (calculada a la fecha del evento)"
    nacimientos = {leer_fecha(d.valor) for d in cuenta.datos_de("paciente.fecha_nacimiento")} - {None}
    evento = _fecha_evento(cuenta)
    edades = cuenta.datos_de("paciente.edad")
    folios = _lista_folios(cuenta, [d.folio for d in edades])
    if len(nacimientos) != 1 or not evento:
        motivo = "la fecha de nacimiento no coincide entre folios" if len(nacimientos) > 1 else "falta la fecha de nacimiento o la del evento"
        if len({d.normalizado for d in edades}) > 1:
            return Punto(S_FURIPS, nombre, ERROR, f"La edad no coincide entre folios: {_describir(cuenta, edades)}.", folios)
        return Punto(S_FURIPS, nombre, FALTA, f"No se puede calcular la edad: {motivo}.", folios)
    nacimiento = nacimientos.pop()
    esperada = calcular_edad(nacimiento, evento)
    if esperada is None:
        return Punto(S_FURIPS, nombre, ERROR, f"La fecha de nacimiento ({nacimiento:%d/%m/%Y}) es posterior al evento ({evento:%d/%m/%Y}).", folios)
    if not edades:
        return Punto(S_FURIPS, nombre, FALTA, f"Edad calculada: {esperada} años. No se encontró la edad registrada en los folios.")
    distintas = [d for d in edades if d.normalizado != str(esperada)]
    if distintas:
        return Punto(
            S_FURIPS, nombre, REVISAR if _solo_ocr(distintas) else ERROR,
            f"Edad calculada: {esperada} años (nacimiento {nacimiento:%d/%m/%Y}, evento {evento:%d/%m/%Y}). "
            f"Folios con otra edad: {_describir(cuenta, distintas)}." + (NOTA_OCR if _solo_ocr(distintas) else ""),
            _lista_folios(cuenta, [d.folio for d in distintas]),
        )
    return Punto(S_FURIPS, nombre, CORRECTO, f"{esperada} años en todos los folios donde aparece.", folios)


def _momento(fechas: list[Dato], horas: list[Dato]):
    """Fecha y hora (si es única) de un conjunto de datos."""
    valores = {leer_fecha(d.valor) for d in fechas} - {None}
    if len(valores) != 1:
        return None
    fecha = valores.pop()
    horas_validas = {d.normalizado for d in horas if re.fullmatch(r"\d{1,2}:\d{2}", d.normalizado)}
    if len(horas_validas) == 1:
        h, m = map(int, horas_validas.pop().split(":"))
        return datetime(fecha.year, fecha.month, fecha.day, h, m)
    return datetime(fecha.year, fecha.month, fecha.day)


def _evento_antes_de_ingreso(cuenta: Cuenta) -> Punto:
    nombre = "Fecha del evento anterior al ingreso"
    ingreso = _momento(cuenta.datos_de("clinico.fecha_ingreso"), cuenta.datos_de("clinico.hora_ingreso"))
    if ingreso is None:
        return Punto(S_FURIPS, nombre, FALTA, "No se encontró una fecha de ingreso única.")
    problemas = []
    for grupo in G_FURIPS:
        fechas = cuenta.datos_de("accidente.fecha", _grupo(grupo))
        evento = _momento(fechas, cuenta.datos_de("accidente.hora", _grupo(grupo)))
        if evento and evento > ingreso:
            problemas.append((grupo, evento, fechas))
    folios = _lista_folios(cuenta, [d.folio for _, _, ds in problemas for d in ds])
    if problemas:
        detalle = "; ".join(f"{NOMBRES_GRUPO[g]} dice {e:%d/%m/%Y %H:%M}" for g, e, _ in problemas)
        return Punto(
            S_FURIPS, nombre, ERROR,
            f"El evento queda DESPUÉS del ingreso ({ingreso:%d/%m/%Y %H:%M}): {detalle}.",
            folios,
        )
    return Punto(S_FURIPS, nombre, CORRECTO, f"El evento es anterior al ingreso ({ingreso:%d/%m/%Y %H:%M}).")


def revisar_furips(cuenta: Cuenta) -> list[Punto]:
    g = G_FURIPS
    return [
        comparar(cuenta, S_FURIPS, "Teléfono", "paciente.telefono", g, coincide_si_comparten=True),
        comparar(cuenta, S_FURIPS, "Fecha de nacimiento", "paciente.fecha_nacimiento", g),
        comparar(cuenta, S_FURIPS, "Fecha del evento", "accidente.fecha", g),
        _evento_antes_de_ingreso(cuenta),
        comparar(cuenta, S_FURIPS, "Dirección del evento", "accidente.direccion", g, _clave_direccion),
        comparar(cuenta, S_FURIPS, "Zona (rural/urbana)", "accidente.zona", g),
        _edad(cuenta),
        comparar(cuenta, S_FURIPS, "Calidad del accidentado", "accidente.calidad_victima", g, _familia_calidad),
        _relato(cuenta),
    ]


# =====================================================================
# 2. Factura, urgencia, estancia y radiología
# =====================================================================

S_FACTURA = "Factura, urgencia, estancia y radiología"
LINEA_COBRO = re.compile(r"^\s*\S+\s+\S+\s+(?P<descripcion>.+?)\s+(?P<cantidad>\d{1,5})\s+\$")


def _lineas_factura(cuenta: Cuenta) -> list[tuple[str, int, str, Folio]]:
    """(sección de la factura, cantidad, descripción, folio) de cada línea de cobro."""
    lineas, seccion = [], ""
    for folio in cuenta.folios_de(_grupo("factura")):
        for linea in folio.texto_normalizado.splitlines():
            m = LINEA_COBRO.match(linea)
            if m:
                lineas.append((seccion, int(m.group("cantidad")), m.group("descripcion"), folio))
            elif linea.strip() and len(linea.split()) <= 6 and not re.search(r"\d", linea):
                seccion = linea.strip()
    return lineas


def _urgencia(cuenta: Cuenta) -> Punto:
    p = parametros()
    facturas = cuenta.folios_de(_grupo("factura"))
    if not facturas:
        return Punto(S_FACTURA, "Cobro de urgencia", FALTA, "No se encontró la factura en los folios con texto.")
    cobro = _buscar(facturas, p["palabras_cobro_urgencia"])
    soporte = cuenta.folios_de(_grupo("urgencias")) or _buscar(cuenta.folios, p["palabras_soporte_urgencia"])
    soporte = soporte or _buscar(cuenta.folios_de(_grupo("admision")), p["palabras_soporte_urgencia"])
    folios = _lista_folios(cuenta, cobro + soporte)
    if cobro and soporte:
        return Punto(S_FACTURA, "Cobro de urgencia", CORRECTO, "Se cobra urgencia y hay soporte de atención de urgencias/triage.", folios)
    if cobro:
        return Punto(S_FACTURA, "Cobro de urgencia", ERROR, "Se cobra urgencia pero no se encontró la atención de urgencias ni el triage.", folios)
    if soporte:
        return Punto(S_FACTURA, "Cobro de urgencia", REVISAR, "Hay atención de urgencias, pero no se identificó su cobro en el texto de la factura.", folios)
    return Punto(S_FACTURA, "Cobro de urgencia", NO_APLICA, "No se cobra urgencia ni hay atención de urgencias.")


PATRON_DIAS_FACTURA = re.compile(
    r"(\d{1,3})\s*dias?\s*(?:de\s*)?(?:estancia|hospitalizacion)|(?:estancia|hospitalizacion|habitacion)[^\n]{0,40}?(\d{1,3})\s*dias?"
)


def _dias_cobrados(cuenta: Cuenta) -> tuple[int, list[Folio]]:
    """Días de estancia cobrados: líneas de la sección ESTANCIAS o 'N días de estancia'."""
    total, folios = 0, []
    for seccion, cantidad, descripcion, folio in _lineas_factura(cuenta):
        if "estancia" in seccion or re.search(r"habitacion|estancia|cama hospitalaria", descripcion):
            total += cantidad
            folios.append(folio)
    if not folios:
        for folio in cuenta.folios_de(_grupo("factura")):
            for m in PATRON_DIAS_FACTURA.finditer(folio.texto_normalizado):
                total += int(m.group(1) or m.group(2))
                folios.append(folio)
    return total, folios


def _estancia(cuenta: Cuenta) -> Punto:
    nombre = "Estancia"
    ingresos = {leer_fecha(d.valor) for d in cuenta.datos_de("clinico.fecha_ingreso")} - {None}
    egresos = {leer_fecha(d.valor) for d in cuenta.datos_de("clinico.fecha_egreso")} - {None}
    folios = _lista_folios(cuenta, [d.folio for d in cuenta.datos_de("clinico.fecha_ingreso") + cuenta.datos_de("clinico.fecha_egreso")][:4])
    if len(ingresos) > 1 or len(egresos) > 1:
        detalle = []
        if len(ingresos) > 1:
            detalle.append(f"ingreso: {_describir(cuenta, cuenta.datos_de('clinico.fecha_ingreso'))}")
        if len(egresos) > 1:
            detalle.append(f"egreso: {_describir(cuenta, cuenta.datos_de('clinico.fecha_egreso'))}")
        return Punto(S_FACTURA, nombre, ERROR, "Las fechas no coinciden entre folios: " + " | ".join(detalle) + ".", folios)
    if not ingresos or not egresos:
        return Punto(S_FACTURA, nombre, FALTA, "No se encontró la fecha de ingreso o de egreso.", folios)
    ingreso, egreso = ingresos.pop(), egresos.pop()
    dias = (egreso - ingreso).days
    if dias < 0:
        return Punto(S_FACTURA, nombre, ERROR, f"El egreso ({egreso:%d/%m/%Y}) es anterior al ingreso ({ingreso:%d/%m/%Y}).", folios)

    cobrados, folios_cobro = _dias_cobrados(cuenta)
    notas = cuenta.folios_de(_grupo("evolucion"))
    resumen = (
        f"Ingreso {ingreso:%d/%m/%Y}, egreso {egreso:%d/%m/%Y}: {dias} día(s). "
        f"Factura: {cobrados} día(s) de estancia cobrados. {len(notas)} folio(s) de notas de evolución."
    )
    if cobrados > dias + 1:
        return Punto(S_FACTURA, nombre, ERROR, f"{resumen} Se cobran más días de los que estuvo hospitalizado.",
                     folios + _lista_folios(cuenta, folios_cobro))
    if dias >= 1 and not notas:
        return Punto(S_FACTURA, nombre, FALTA, f"{resumen} No se encontraron notas de evolución que soporten la estancia.", folios)
    return Punto(S_FACTURA, nombre, CORRECTO, resumen, _lista_folios(cuenta, folios_cobro))


def _radiologia_facturada(cuenta: Cuenta) -> Punto:
    nombre = "Exámenes radiológicos cobrados vs. informes"
    cobradas = [
        (cantidad, folio) for _, cantidad, descripcion, folio in _lineas_factura(cuenta)
        if re.search(r"\b(rx|radiografia|tomografia|tac|resonancia|ecografia)\b", descripcion) and "portatil" not in descripcion
    ]
    informes = cuenta.folios_de(_grupo("radiologia"))
    total = sum(c for c, _ in cobradas)
    if not cobradas and not informes:
        return Punto(S_FACTURA, nombre, NO_APLICA, "No se cobran exámenes radiológicos ni hay informes.")
    folios = _lista_folios(cuenta, [f for _, f in cobradas] + informes)
    if total > len(informes):
        return Punto(S_FACTURA, nombre, ERROR, f"Se cobran {total} estudio(s) radiológico(s) y hay {len(informes)} informe(s).", folios)
    return Punto(S_FACTURA, nombre, CORRECTO, f"Se cobran {total} estudio(s) radiológico(s) y hay {len(informes)} informe(s).", folios)


def revisar_factura(cuenta: Cuenta) -> list[Punto]:
    return [
        comparar(cuenta, S_FACTURA, "Número de factura (FURIPS vs. factura)", "administrativo.numero_factura", ["furips", "factura"]),
        _urgencia(cuenta),
        _estancia(cuenta),
        _radiologia_facturada(cuenta),
    ]


# =====================================================================
# 3. Póliza, vehículo, propietario y conductor
# =====================================================================

S_POLIZA = "Póliza, vehículo, propietario y conductor"


def _vigencia(cuenta: Cuenta) -> Punto:
    nombre = "Fecha del evento dentro de la vigencia"
    evento = _fecha_evento(cuenta)
    desde = {leer_fecha(d.valor) for d in cuenta.datos_de("administrativo.vigencia_poliza_desde")} - {None}
    hasta = {leer_fecha(d.valor) for d in cuenta.datos_de("administrativo.vigencia_poliza_hasta")} - {None}
    folios = _lista_folios(
        cuenta, [d.folio for c in ("administrativo.vigencia_poliza_desde", "administrativo.vigencia_poliza_hasta") for d in cuenta.datos_de(c)]
    )
    if not evento or len(desde) != 1 or len(hasta) != 1:
        return Punto(S_POLIZA, nombre, FALTA, "Falta la fecha del evento o una vigencia única de la póliza para comprobarlo.", folios)
    d, h = desde.pop(), hasta.pop()
    if d <= evento <= h:
        return Punto(S_POLIZA, nombre, CORRECTO, f"Evento {evento:%d/%m/%Y} dentro de la vigencia {d:%d/%m/%Y} a {h:%d/%m/%Y}.", folios)
    return Punto(S_POLIZA, nombre, ERROR, f"Evento {evento:%d/%m/%Y} FUERA de la vigencia {d:%d/%m/%Y} a {h:%d/%m/%Y}.", folios)


def _placa(cuenta: Cuenta) -> Punto:
    grupos = ["furips", "siras", "poliza", "runt"]
    punto = comparar(cuenta, S_POLIZA, "Placa (los documentos SOAT son del vehículo del evento)", "accidente.placa", grupos)
    if punto.resultado != ERROR:
        return punto
    tolerante = comparar(cuenta, S_POLIZA, punto.nombre, "accidente.placa", grupos, _clave_placa)
    if tolerante.resultado == CORRECTO:
        punto.resultado = REVISAR
        punto.detalle = (
            f"{punto.detalle} La diferencia es solo de caracteres parecidos (I/1, O/0): "
            "puede ser un error de lectura del escaneo; verifique la placa en el documento."
        )
    return punto


def _licencia_conductor(cuenta: Cuenta) -> Punto:
    nombre = "Conductor: licencia de conducción (RUNT)"
    estados = cuenta.datos_de("runt.estado_conductor")
    if not estados:
        return Punto(S_POLIZA, nombre, FALTA, "No se encontró consulta RUNT del conductor.")
    documentos = {d.normalizado for d in cuenta.datos_de("runt.documento")}
    conductores = {d.normalizado for d in cuenta.datos_de("administrativo.conductor_identificacion")}
    quien = f"C.C. {', '.join(documentos)}" if documentos else "consultado"
    nota = "" if not conductores or documentos & conductores else " OJO: el documento consultado no es el del conductor del FURIPS."
    folios = _lista_folios(cuenta, [d.folio for d in estados])
    estado = estados[0].valor
    if re.search(r"no tiene|sin licencia|cancelad|suspendid|vencid", normalizar(estado)):
        return Punto(S_POLIZA, nombre, REVISAR, f"El RUNT indica para el conductor ({quien}): {estado}.{nota}", folios)
    return Punto(S_POLIZA, nombre, CORRECTO if not nota else REVISAR, f"RUNT del conductor ({quien}): {estado}.{nota}", folios)


def revisar_poliza(cuenta: Cuenta) -> list[Punto]:
    g = ["furips", "poliza", "runt"]
    gv = ["furips", "siras", "documentos_vehiculo"]
    return [
        comparar(cuenta, S_POLIZA, "Número de póliza (FURIPS, póliza y RUNT)", "administrativo.numero_poliza", g),
        comparar(cuenta, S_POLIZA, "Vigencia desde (FURIPS, póliza y RUNT)", "administrativo.vigencia_poliza_desde", g),
        comparar(cuenta, S_POLIZA, "Vigencia hasta (FURIPS, póliza y RUNT)", "administrativo.vigencia_poliza_hasta", g),
        _vigencia(cuenta),
        _placa(cuenta),
        comparar(cuenta, S_POLIZA, "Propietario: nombre", "administrativo.propietario_nombre", gv, _clave_nombre),
        comparar(cuenta, S_POLIZA, "Propietario: identificación", "administrativo.propietario_identificacion", gv),
        comparar(cuenta, S_POLIZA, "Conductor: nombre", "administrativo.conductor_nombre", gv, _clave_nombre),
        comparar(cuenta, S_POLIZA, "Conductor: identificación", "administrativo.conductor_identificacion", gv),
        _licencia_conductor(cuenta),
    ]


# =====================================================================
# 4. Paciente en todos los folios
# =====================================================================

S_PACIENTE = "Paciente en todos los folios"
SEXO = {"m": "M", "masculino": "M", "hombre": "M", "f": "F", "femenino": "F", "mujer": "F"}


def _similitud(a: str, b: str) -> float:
    pa = {p for p in normalizar(a).split() if len(p) > 1}
    pb = {p for p in normalizar(b).split() if len(p) > 1}
    if not pa or not pb:
        return 0.0
    if pa <= pb or pb <= pa:
        return 1.0
    return len(pa & pb) / len(pa | pb)


def revisar_paciente(cuenta: Cuenta) -> list[Punto]:
    puntos = []
    ids = cuenta.datos_de("paciente.numero_identificacion")
    nombres = cuenta.datos_de("paciente.nombre")
    # El valor más frecuente se toma como el del paciente; los demás se listan como diferentes.
    id_principal = max({d.normalizado for d in ids}, key=lambda v: sum(d.normalizado == v for d in ids), default=None)
    ids_distintos = [d for d in ids if d.normalizado != id_principal]
    base = max(nombres, key=lambda n: sum(_similitud(n.valor, o.valor) == 1.0 for o in nombres)).valor if nombres else ""
    nombres_raros = [d for d in nombres if _similitud(base, d.valor) < 0.5]
    folios = _lista_folios(cuenta, [d.folio for d in ids_distintos + nombres_raros])
    nombre_punto = "Todos los folios son del mismo paciente"
    if not ids and not nombres:
        puntos.append(Punto(S_PACIENTE, nombre_punto, FALTA, "No se encontró nombre ni identificación del paciente."))
    elif ids_distintos or nombres_raros:
        detalle = [f"paciente: {base} identificación {id_principal}"]
        if ids_distintos:
            detalle.append(f"otras identificaciones: {_describir(cuenta, ids_distintos)}")
        if nombres_raros:
            detalle.append(f"otros nombres: {_describir(cuenta, nombres_raros)}")
        solo_ocr = _solo_ocr(ids_distintos + nombres_raros)
        puntos.append(Punto(S_PACIENTE, nombre_punto, REVISAR if solo_ocr else ERROR,
                            "; ".join(detalle) + "." + (NOTA_OCR if solo_ocr else ""), folios))
    else:
        total = len({d.folio.numero for d in ids + nombres})
        puntos.append(Punto(S_PACIENTE, nombre_punto, CORRECTO, f"{base} identificación {id_principal} en los {total} folios donde aparece."))

    sexos = cuenta.datos_de("paciente.sexo")
    valores = {SEXO.get(normalizar(d.valor), d.valor) for d in sexos}
    if not sexos:
        puntos.append(Punto(S_PACIENTE, "Sexo en todos los folios", FALTA, "No se encontró el sexo del paciente."))
    elif len(valores) > 1:
        sin_ocr = {SEXO.get(normalizar(d.valor), d.valor) for d in sexos if d.folio.metodo != "OCR"}
        solo_ocr = len(sin_ocr) <= 1
        puntos.append(Punto(S_PACIENTE, "Sexo en todos los folios", REVISAR if solo_ocr else ERROR,
                            f"No coincide: {_describir(cuenta, sexos)}." + (NOTA_OCR if solo_ocr else ""),
                            _lista_folios(cuenta, [d.folio for d in sexos])))
    else:
        texto = {"M": "Masculino", "F": "Femenino"}.get(next(iter(valores)), next(iter(valores)))
        puntos.append(Punto(S_PACIENTE, "Sexo en todos los folios", CORRECTO, f"{texto} en los {len({d.folio.numero for d in sexos})} folios donde aparece."))
    return puntos


# =====================================================================
# 5. Pertinencia: lateralidad, exámenes, osteosíntesis, firmas, medicamentos
# =====================================================================

S_PERTINENCIA = "Pertinencia, ayudas diagnósticas y firmas"
PATRON_LADO = r"(derech[oa]s?|izquierd[oa]s?|bilateral(?:es)?)"


def _lateralidad(cuenta: Cuenta) -> Punto:
    p = parametros()
    regiones = _unicos(normalizar(r) for r in p["regiones"])
    patron = re.compile(
        r"\b(" + "|".join(r"\s+".join(map(re.escape, r.split())) for r in regiones) + r")s?\b(?:\s+\w+){0,3}?\s+" + PATRON_LADO + r"\b"
    )
    # (región, lado, folio, texto de la línea) de cada mención de la lesión, imagen o procedimiento
    menciones = []
    for folio in cuenta.folios:
        for linea in folio.texto_normalizado.splitlines():
            if not _contiene(linea, p["palabras_lesion"]) or _contiene(linea, p["palabras_no_lesion"]):
                continue
            for m in patron.finditer(linea):
                lado = "BILATERAL" if m.group(2).startswith("bilateral") else ("DERECHA" if m.group(2).startswith("derech") else "IZQUIERDA")
                menciones.append((" ".join(m.group(1).split()), lado, folio, " ".join(linea.split())))
    if not menciones:
        return Punto(S_PERTINENCIA, "Lateralidad", FALTA, "No se encontraron lesiones o estudios con lateralidad (derecha/izquierda).")

    regiones_con_ambos = {
        r for r in {m[0] for m in menciones}
        if {"DERECHA", "IZQUIERDA"} <= {m[1] for m in menciones if m[0] == r} and "BILATERAL" not in {m[1] for m in menciones if m[0] == r}
    }
    if not regiones_con_ambos:
        detalle = "; ".join(f"{r}: {', '.join(sorted({m[1] for m in menciones if m[0] == r}))}" for r in _unicos(m[0] for m in menciones))
        return Punto(S_PERTINENCIA, "Lateralidad", CORRECTO, f"Lateralidad consistente ({detalle}).")

    # El lado de referencia es el de los informes de imagen y quirúrgicos; si no hay, el más mencionado.
    referencia_tipos = _grupo("radiologia") + _grupo("quirurgico")
    en_referencia = [m for m in menciones if m[2].tipo in referencia_tipos and m[1] != "BILATERAL"]
    base = en_referencia or [m for m in menciones if m[1] != "BILATERAL"]
    conteo = {l: sum(m[1] == l for m in base) for l in ("DERECHA", "IZQUIERDA")}
    if conteo["DERECHA"] == conteo["IZQUIERDA"]:
        # No hay forma de saber cuál es el lado correcto: se muestran ambos.
        conflicto = [m for m in menciones if m[0] in regiones_con_ambos]
        partes = [
            f"{lado} en {_resumir(_lista_folios(cuenta, [m[2] for m in conflicto if m[1] == lado]))}"
            for lado in ("DERECHA", "IZQUIERDA")
        ]
        return Punto(S_PERTINENCIA, "Lateralidad", ERROR,
                     f"La misma región aparece con los dos lados ({', '.join(sorted(regiones_con_ambos))}): " + " / ".join(partes) + ".",
                     _lista_folios(cuenta, [m[2] for m in conflicto]))
    lado_correcto = max(conteo, key=conteo.get)
    fuente = (
        f"informes de imagen y quirúrgicos ({_resumir(_lista_folios(cuenta, [m[2] for m in en_referencia]))})"
        if en_referencia else "la mayoría de los folios"
    )
    contrarias = [m for m in menciones if m[0] in regiones_con_ambos and m[1] not in (lado_correcto, "BILATERAL")]
    por_tipo: dict[str, list] = {}
    for m in contrarias:
        por_tipo.setdefault(m[2].tipo or "Otros", []).append(m)
    partes = [
        f"{tipo} ({_resumir(_lista_folios(cuenta, [m[2] for m in ms]))}), p. ej. «{ms[0][3][:90]}»"
        for tipo, ms in por_tipo.items()
    ]
    otro_lado = "DERECHA" if lado_correcto == "IZQUIERDA" else "IZQUIERDA"
    solo_ocr = all(m[2].metodo == "OCR" for m in contrarias)
    return Punto(
        S_PERTINENCIA, "Lateralidad", REVISAR if solo_ocr else ERROR,
        f"La lesión es {lado_correcto} según {fuente}, pero dicen {otro_lado}: " + " | ".join(partes) + "."
        + (NOTA_OCR if solo_ocr else ""),
        _lista_folios(cuenta, [m[2] for m in contrarias]),
    )


PATRON_ESTUDIO = re.compile(r"\b(radiografia|tomografia|resonancia|ecografia)\s+(?:de\s+)?([a-z]+)")


def _examenes(cuenta: Cuenta) -> list[Punto]:
    p = parametros()
    informes = cuenta.folios_de(_grupo("informes"))
    radiologia = cuenta.folios_de(_grupo("radiologia"))
    ordenes = cuenta.folios_de(_grupo("ordenes"))
    texto_ordenes = "\n".join(f.texto_normalizado for f in ordenes)
    puntos = []

    # Interpretación de cada informe radiológico
    sin_interpretacion = [f for f in radiologia if not _buscar([f], p["palabras_interpretacion"])]
    if not radiologia:
        ordenados = [e for e, palabras in p["estudios_radiologicos"].items() if _buscar(ordenes, palabras)]
        if ordenados:
            puntos.append(Punto(S_PERTINENCIA, "Exámenes radiológicos: informe e interpretación", FALTA,
                                f"Se ordenaron ({', '.join(ordenados)}) pero no se encontraron informes radiológicos."))
        else:
            puntos.append(Punto(S_PERTINENCIA, "Exámenes radiológicos: informe e interpretación", NO_APLICA, "No hay exámenes radiológicos en la cuenta."))
    elif sin_interpretacion:
        puntos.append(Punto(S_PERTINENCIA, "Exámenes radiológicos: informe e interpretación", REVISAR,
                            f"Informe sin interpretación identificable en: {_resumir(_lista_folios(cuenta, sin_interpretacion))}.",
                            _lista_folios(cuenta, sin_interpretacion)))
    else:
        estudios = _unicos(" ".join(m.groups()) for f in radiologia for m in PATRON_ESTUDIO.finditer(f.texto_normalizado))
        puntos.append(Punto(S_PERTINENCIA, "Exámenes radiológicos: informe e interpretación", CORRECTO,
                            f"{len(radiologia)} informe(s) con interpretación ({', '.join(estudios)}).", _lista_folios(cuenta, radiologia)))

    # Justificación: cada estudio informado debe estar ordenado o mencionado en la historia
    sin_justificar, justificados = [], []
    for folio in radiologia:
        for m in PATRON_ESTUDIO.finditer(folio.texto_normalizado):
            estudio, region = m.groups()
            claves = p["estudios_radiologicos"].get(estudio, [estudio])
            ordenado = any(
                re.search(rf"\b{re.escape(c)}\b[^\n]{{0,40}}\b{re.escape(region)}", texto_ordenes) for c in claves
            )
            (justificados if ordenado else sin_justificar).append((f"{estudio} de {region}", folio))
    for estudio, palabras in p["otras_ayudas"].items():
        en_informes = _buscar(informes, palabras)
        if en_informes:
            (justificados if _buscar(ordenes, palabras) else sin_justificar).append((estudio, en_informes[0]))
    if not sin_justificar and not justificados:
        puntos.append(Punto(S_PERTINENCIA, "Ayudas diagnósticas justificadas", NO_APLICA, "No hay informes de ayudas diagnósticas."))
    elif sin_justificar:
        detalle = ", ".join(_unicos(f"{e} (informe en {cuenta.ubicacion(f)})" for e, f in sin_justificar))
        puntos.append(Punto(S_PERTINENCIA, "Ayudas diagnósticas justificadas", FALTA,
                            f"No se encontró orden ni justificación en la historia/órdenes para: {detalle}.",
                            _lista_folios(cuenta, [f for _, f in sin_justificar])))
    else:
        puntos.append(Punto(S_PERTINENCIA, "Ayudas diagnósticas justificadas", CORRECTO,
                            f"Con orden o justificación: {', '.join(_unicos(e for e, _ in justificados))}."))
    return puntos


LINEA_MATERIAL = re.compile(r"^\s*\S+\s+(?P<descripcion>.+?)\s+(?P<cantidad>\d{1,4})\s+\$")
CANTIDAD_EN_CIRUGIA = re.compile(r"([^():,;]{5,120}?)\s*(?:cantidad\s*:?\s*|#\s*)(\d{1,3})\b")


def _firma_material(descripcion: str) -> tuple[str, ...]:
    """Medidas del material (3.5 x 14, 9 x 320...): identifican la pieza aunque cambie la redacción."""
    numeros = re.findall(r"\d+/\d+|\d+(?:[.,]\d+)?", descripcion.replace("(ortopedia)", ""))
    return tuple(sorted(str(float(n.replace(",", "."))) if "/" not in n else n for n in numeros))


def _materiales_cobrados(cuenta: Cuenta) -> list[tuple[str, int, Folio]]:
    """Líneas de la sección de material quirúrgico de la factura: (descripción, cantidad, folio)."""
    materiales, en_material = [], False
    for folio in cuenta.folios_de(_grupo("factura")):
        for linea in folio.texto_normalizado.splitlines():
            if "material qx" in linea or "material especial" in linea or "osteosintesis" in linea and "$" not in linea:
                en_material = True
                continue
            if en_material and linea.strip() and len(linea.split()) <= 6 and "$" not in linea and "subtotal" not in linea:
                en_material = False  # Empieza otra sección (p. ej. LABORATORIO)
            m = LINEA_MATERIAL.match(linea) if en_material else None
            if m and "subtotal" not in linea:
                materiales.append((" ".join(m.group("descripcion").split()), int(m.group("cantidad")), folio))
    return materiales


def _cantidades_cirugia(texto: str) -> dict[tuple[str, ...], int]:
    cantidades: dict[tuple[str, ...], int] = {}
    for m in CANTIDAD_EN_CIRUGIA.finditer(texto):
        firma = _firma_material(m.group(1))
        if firma:
            cantidades[firma] = cantidades.get(firma, 0) + int(m.group(2))
    return cantidades


def _material_cantidades(cuenta: Cuenta) -> Punto:
    nombre = "Material de osteosíntesis: cantidades cobradas vs. informe quirúrgico"
    cobrados = _materiales_cobrados(cuenta)
    if not cobrados:
        return Punto(S_PERTINENCIA, nombre, NO_APLICA, "La factura no tiene una sección de material quirúrgico con cantidades.")
    quirurgicos = cuenta.folios_de(_grupo("quirurgico"))
    if not quirurgicos:
        return Punto(S_PERTINENCIA, nombre, FALTA, "Hay material cobrado pero no se encontró el informe quirúrgico.",
                     _lista_folios(cuenta, [f for _, _, f in cobrados]))
    texto = "\n".join(f.texto_normalizado for f in quirurgicos)
    corte = re.search(r"\n\s*material\s*\n|material autorizado|material adicional", texto)
    narrativa = _cantidades_cirugia(texto[: corte.start()] if corte else texto)
    lista = _cantidades_cirugia(texto[corte.start():]) if corte else {}

    problemas, correctos = [], 0
    for descripcion, cantidad, folio in cobrados:
        firma = _firma_material(descripcion)
        en_lista, en_relato = lista.get(firma), narrativa.get(firma)
        if en_lista is None and en_relato is None:
            problemas.append(f"«{descripcion}»: se cobran {cantidad} y no aparece en el informe quirúrgico ({cuenta.ubicacion(folio)})")
        elif en_lista is not None and cantidad > en_lista:
            relato = f"; el relato de la cirugía menciona {en_relato}" if en_relato is not None else ""
            problemas.append(f"«{descripcion}»: se cobran {cantidad} y la lista de material del informe registra {en_lista}{relato} ({cuenta.ubicacion(folio)})")
        elif en_lista is None and cantidad > en_relato:
            problemas.append(f"«{descripcion}»: se cobran {cantidad} y el informe quirúrgico describe {en_relato} ({cuenta.ubicacion(folio)})")
        else:
            correctos += 1
    folios = _lista_folios(cuenta, [f for _, _, f in cobrados] + quirurgicos)
    if problemas:
        return Punto(S_PERTINENCIA, nombre, ERROR, "; ".join(problemas) + f". ({correctos} material(es) más coinciden.)", folios)
    return Punto(S_PERTINENCIA, nombre, CORRECTO, f"Los {correctos} materiales cobrados coinciden en cantidad con el informe quirúrgico.", folios)


LINEA_MEDICAMENTO_SALIDA = re.compile(r"^\s*([a-z][a-z]+).*?\s(\d{1,4})\s+[a-z]+\s*$")


def _ambulatorios_cobrados_vs_orden(cuenta: Cuenta) -> Punto:
    nombre = "Medicamentos ambulatorios cobrados vs. orden de salida"
    cobrados = [(d, c, f) for _, c, d, f in _lineas_factura(cuenta) if "ambulatorio" in d]
    if not cobrados:
        return Punto(S_PERTINENCIA, nombre, NO_APLICA, "La factura no cobra medicamentos ambulatorios.")
    ordenados: dict[str, int] = {}
    folios_orden = []
    for folio in _buscar(cuenta.folios, parametros()["palabras_orden_ambulatoria"]):
        texto = re.split(r"salida|ambulatori", folio.texto_normalizado, maxsplit=1)[-1]
        for linea in texto.splitlines():
            m = LINEA_MEDICAMENTO_SALIDA.match(linea)
            if m and re.search(r"\b(tableta|capsula|inyectable|solucion|suspension|jarabe|ampolla|sobre)\b", linea):
                ordenados[m.group(1)] = ordenados.get(m.group(1), 0) + int(m.group(2))
                folios_orden.append(folio)
    if not ordenados:
        return Punto(S_PERTINENCIA, nombre, FALTA, "Se cobran medicamentos ambulatorios pero no se encontró la orden de salida con cantidades.",
                     _lista_folios(cuenta, [f for _, _, f in cobrados]))
    problemas = []
    for descripcion, cantidad, folio in cobrados:
        medicamento = re.match(r"[a-z]+", descripcion).group(0)
        orden = ordenados.get(medicamento)
        if orden is None:
            problemas.append(f"«{descripcion}»: se cobran {cantidad} y no está en la orden de salida")
        elif cantidad > orden:
            problemas.append(f"«{descripcion}»: se cobran {cantidad} y la orden de salida dice {orden}")
    folios = _lista_folios(cuenta, [f for _, _, f in cobrados] + folios_orden)
    if problemas:
        return Punto(S_PERTINENCIA, nombre, ERROR, "; ".join(problemas) + ".", folios)
    return Punto(S_PERTINENCIA, nombre, CORRECTO,
                 "Coinciden con la orden de salida: " + ", ".join(f"{d.split(' (')[0]} x{c}" for d, c, _ in cobrados) + ".", folios)


def _osteosintesis(cuenta: Cuenta) -> Punto:
    nombre = "Material de osteosíntesis descrito en el informe quirúrgico"
    materiales = parametros()["materiales"]
    factura_material = [
        (descripcion, folio) for seccion, _, descripcion, folio in _lineas_factura(cuenta)
        if "material" in seccion or "osteosintesis" in descripcion or "(ortopedia)" in descripcion
    ]
    soportes = cuenta.folios_de(_grupo("material")) + [f for _, f in factura_material]
    texto_soportes = "\n".join(d for d, _ in factura_material) + "\n" + "\n".join(f.texto_normalizado for f in cuenta.folios_de(_grupo("material")))
    usados = [m for m in materiales if re.search(rf"\b{m}(?:s|es)?\b", texto_soportes)]
    if not usados:
        return Punto(S_PERTINENCIA, nombre, NO_APLICA, "No hay material de osteosíntesis cobrado ni remitido.")
    quirurgicos = cuenta.folios_de(_grupo("quirurgico"))
    if not quirurgicos:
        return Punto(S_PERTINENCIA, nombre, FALTA, f"Hay material ({', '.join(usados)}) pero no se encontró la descripción quirúrgica.",
                     _lista_folios(cuenta, soportes))
    texto_cirugia = "\n".join(f.texto_normalizado for f in quirurgicos)
    no_descritos = [m for m in usados if not re.search(rf"\b{m}(?:s|es)?\b", texto_cirugia)]
    folios = _lista_folios(cuenta, soportes + quirurgicos)
    if no_descritos:
        return Punto(S_PERTINENCIA, nombre, ERROR, f"Material cobrado/remitido que no se describe en la cirugía: {', '.join(no_descritos)}.", folios)
    return Punto(S_PERTINENCIA, nombre, CORRECTO, f"Descrito en la cirugía: {', '.join(usados)}. Verifique cantidades.", folios)


def _firmas_medicos(cuenta: Cuenta) -> Punto:
    nombre = "Médicos de los informes con firma/registro"
    p = parametros()
    medico = re.compile("|".join(p["palabras_medico"]))
    firma = re.compile("|".join(p["palabras_firma"]))
    documentos = _documentos(cuenta, _grupo("con_firma_medica"))
    if not documentos:
        return Punto(S_PERTINENCIA, nombre, NO_APLICA, "No hay informes, descripciones quirúrgicas ni epicrisis con texto.")

    def rango(doc):
        return cuenta.ubicacion(doc[0]) + (f"-{doc[-1].numero}" if len(doc) > 1 else "")

    sin_medico, sin_firma = [], []
    for doc in documentos:
        texto = "\n".join(f.texto_normalizado for f in doc)
        if not medico.search(texto):
            sin_medico.append(doc)
        elif not firma.search(texto):
            sin_firma.append(doc)
    if sin_medico:
        return Punto(S_PERTINENCIA, nombre, FALTA,
                     f"No se identifica el médico en: {', '.join(f'{d[0].tipo} ({rango(d)})' for d in sin_medico)}.",
                     _lista_folios(cuenta, [f for d in sin_medico + sin_firma for f in d]))
    if sin_firma:
        return Punto(S_PERTINENCIA, nombre, REVISAR,
                     "Médico identificado pero sin firma ni registro en el texto (puede estar en imagen): "
                     + ", ".join(f"{d[0].tipo} ({rango(d)})" for d in sin_firma) + ".",
                     _lista_folios(cuenta, [f for d in sin_firma for f in d]))
    return Punto(S_PERTINENCIA, nombre, CORRECTO,
                 f"Los {len(documentos)} informes identifican al médico con firma o registro (en el texto). La firma manuscrita se verifica visualmente.")


def _orden_ambulatoria(cuenta: Cuenta) -> Punto:
    nombre = "Orden de medicamentos ambulatorios firmada por el paciente"
    p = parametros()
    ordenes = _buscar(cuenta.folios_de(("Fórmulas de medicamentos",)), p["palabras_orden_ambulatoria"]) or _buscar(
        cuenta.folios, p["palabras_orden_ambulatoria"]
    )
    if not ordenes:
        return Punto(S_PERTINENCIA, nombre, FALTA, "No se encontró la orden de medicamentos ambulatorios.")
    con_espacio = _buscar(ordenes, p["palabras_firma_paciente"])
    if con_espacio:
        return Punto(S_PERTINENCIA, nombre, REVISAR, "Orden encontrada con espacio de firma del paciente: verifique visualmente que esté firmada.",
                     _lista_folios(cuenta, con_espacio))
    return Punto(S_PERTINENCIA, nombre, REVISAR, "Orden encontrada, pero en el texto no aparece la firma del paciente: verifíquelo visualmente.",
                 _lista_folios(cuenta, ordenes))


def revisar_pertinencia(cuenta: Cuenta) -> list[Punto]:
    return [
        _lateralidad(cuenta),
        *_examenes(cuenta),
        _osteosintesis(cuenta),
        _material_cantidades(cuenta),
        _firmas_medicos(cuenta),
        _orden_ambulatoria(cuenta),
        _ambulatorios_cobrados_vs_orden(cuenta),
    ]


def revisar_cuenta(cuenta: Cuenta) -> list[Punto]:
    """Todos los puntos de la lista del auditor, en orden."""
    return [*revisar_furips(cuenta), *revisar_factura(cuenta), *revisar_poliza(cuenta), *revisar_paciente(cuenta), *revisar_pertinencia(cuenta)]
