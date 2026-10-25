"""Revisión de la cuenta según la lista del auditor.

Cada punto devuelve: Error, Falta, Revisar, Correcto o No aplica, con el folio donde está.
- "Error": los documentos se contradicen o algo no cumple.
- "Falta": no se encontró un documento o dato que debería estar.
- "Revisar": el programa no puede decidirlo solo (p. ej. firmas en imagen).
No se inventa nada: si un dato no se encontró se dice "Falta", no "Error".
"""

import re
from dataclasses import dataclass, field
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
    return re.compile(r"\b(?:" + "|".join(re.escape(normalizar(p)) for p in palabras) + r")\b")


def _buscar(folios: list[Folio], palabras) -> list[Folio]:
    patron = _patron_palabras(palabras)
    return [f for f in folios if patron.search(f.texto_normalizado)]


def _unicos(lista):
    return list(dict.fromkeys(lista))


def _lista_folios(cuenta: Cuenta, folios) -> list[str]:
    return _unicos(cuenta.ubicacion(f) for f in folios)


# =====================================================================
# Comparación de un dato entre grupos de folios (FURIPS, admisión, póliza, RUNT...)
# =====================================================================

NOMBRES_GRUPO = {
    "furips": "FURIPS",
    "admision": "hoja de admisión/urgencias",
    "factura": "factura",
    "poliza": "póliza",
    "runt": "RUNT",
    "documentos_vehiculo": "documentos del vehículo/identificaciones",
}


def _describir(cuenta: Cuenta, datos: list[Dato]) -> str:
    por_valor: dict[str, list[Dato]] = {}
    for d in datos:
        por_valor.setdefault(d.normalizado, []).append(d)
    return "; ".join(
        f"«{ds[0].valor}» ({', '.join(_lista_folios(cuenta, [d.folio for d in ds]))})" for ds in por_valor.values()
    )


def comparar(
    cuenta: Cuenta, seccion: str, nombre: str, campo: str, grupos: list[str], normalizar_dato=None, coincide_si_comparten=False
) -> Punto:
    """Compara un dato entre grupos de folios.

    - Ningún grupo lo tiene → Falta.  - Solo un grupo → Falta (no hay con qué comparar).
    - Valores iguales → Correcto.     - Valores distintos → Error.
    coincide_si_comparten: basta con que compartan un valor (p. ej. teléfonos).
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
            f"Solo aparece en {NOMBRES_GRUPO[grupo]}: {_describir(cuenta, datos)}. No se encontró en: {', '.join(faltantes)}.",
            folios,
        )

    conjuntos = {g: {clave(d) for d in ds} for g, ds in presentes.items()}
    if coincide_si_comparten:
        iguales = bool(set.intersection(*conjuntos.values()))
    else:
        iguales = len(set.union(*conjuntos.values())) == 1
    nota_faltantes = f" No se encontró en: {', '.join(faltantes)}." if faltantes else ""
    if iguales:
        return Punto(seccion, nombre, CORRECTO, f"Coincide: {_describir(cuenta, todos)}.{nota_faltantes}", folios)
    detalle = " | ".join(f"{NOMBRES_GRUPO[g].upper()}: {_describir(cuenta, ds)}" for g, ds in presentes.items())
    return Punto(seccion, nombre, ERROR, f"No coincide. {detalle}.{nota_faltantes}", folios)


def _clave_direccion(dato: Dato) -> str:
    """Direcciones: se comparan sus números (Cra 5 # 10-20 = Carrera 5 No. 10 20)."""
    numeros = re.findall(r"\d+", dato.valor)
    if numeros:
        return "-".join(numeros)
    vacias = {"de", "del", "la", "el", "vereda", "sector", "barrio", "km", "kilometro", "via"}
    return " ".join(p for p in normalizar(dato.valor).split() if p not in vacias)


def _clave_nombre(dato: Dato) -> str:
    """Nombres: mismas palabras en cualquier orden."""
    return " ".join(sorted(normalizar(dato.valor).split()))


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


# =====================================================================
# 1. FURIPS vs hoja de admisión
# =====================================================================

S_FURIPS = "FURIPS vs. hoja de admisión"


def _calidad(cuenta: Cuenta) -> Punto:
    furips = cuenta.datos_de("accidente.calidad_victima", _grupo("furips"))
    admision = cuenta.datos_de("accidente.calidad_victima", _grupo("admision"))
    folios_admision = cuenta.folios_de(_grupo("admision"))
    calidad_furips = {FAMILIAS_CALIDAD.get(d.normalizado.lower(), d.valor) for d in furips}
    if admision:
        calidad_admision = {FAMILIAS_CALIDAD.get(d.normalizado.lower(), d.valor) for d in admision}
        origen_admision = [d.folio for d in admision]
    else:  # Si la hoja no tiene el campo, se busca en su relato
        calidad_admision = set().union(*(_familias(f.texto, FAMILIAS_CALIDAD) for f in folios_admision)) if folios_admision else set()
        origen_admision = folios_admision
    folios = _lista_folios(cuenta, [d.folio for d in furips] + list(origen_admision))
    if not calidad_furips:
        return Punto(S_FURIPS, "Calidad del accidentado", FALTA, "No se encontró en el FURIPS.", folios)
    if not calidad_admision:
        return Punto(S_FURIPS, "Calidad del accidentado", FALTA, f"FURIPS: {', '.join(calidad_furips)}. No se encontró en la hoja de admisión/urgencias.", folios)
    if calidad_furips & calidad_admision:
        return Punto(S_FURIPS, "Calidad del accidentado", CORRECTO, f"Coincide: {', '.join(calidad_furips)}.", folios)
    return Punto(
        S_FURIPS, "Calidad del accidentado", ERROR,
        f"No coincide. FURIPS: {', '.join(calidad_furips)} | ADMISIÓN: {', '.join(calidad_admision)}.", folios,
    )


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
        return Punto(S_FURIPS, "Relato de los hechos", FALTA, "No se encontró relato o enfermedad actual en la hoja de admisión/urgencias.", folios)
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
        f"Sin contradicción en calidad de la víctima ni tipo de vehículo. FURIPS: «{texto_f[:150]}» | ADMISIÓN: «{texto_a[:150]}».",
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
            S_FURIPS, nombre, ERROR,
            f"Edad calculada: {esperada} años (nacimiento {nacimiento:%d/%m/%Y}, evento {evento:%d/%m/%Y}). "
            f"Folios con otra edad: {_describir(cuenta, distintas)}.",
            _lista_folios(cuenta, [d.folio for d in distintas]),
        )
    return Punto(S_FURIPS, nombre, CORRECTO, f"{esperada} años en todos los folios donde aparece.", folios)


def revisar_furips(cuenta: Cuenta) -> list[Punto]:
    g = ["furips", "admision"]
    return [
        comparar(cuenta, S_FURIPS, "Teléfono", "paciente.telefono", g, coincide_si_comparten=True),
        comparar(cuenta, S_FURIPS, "Fecha de nacimiento", "paciente.fecha_nacimiento", g),
        comparar(cuenta, S_FURIPS, "Fecha del evento", "accidente.fecha", g),
        comparar(cuenta, S_FURIPS, "Dirección del evento", "accidente.direccion", g, _clave_direccion),
        comparar(cuenta, S_FURIPS, "Zona (rural/urbana)", "accidente.zona", g),
        _edad(cuenta),
        _calidad(cuenta),
        _relato(cuenta),
    ]


# =====================================================================
# 2. Factura, urgencia y estancia
# =====================================================================

S_FACTURA = "Factura, urgencia y estancia"


def _urgencia(cuenta: Cuenta) -> Punto:
    p = parametros()
    facturas = cuenta.folios_de(_grupo("factura"))
    if not facturas:
        return Punto(S_FACTURA, "Cobro de urgencia", FALTA, "No se encontró la factura en los folios con texto.")
    cobro = _buscar(facturas, p["palabras_cobro_urgencia"])
    soporte = cuenta.folios_de(_grupo("urgencias")) or _buscar(cuenta.folios, p["palabras_soporte_urgencia"])
    folios = _lista_folios(cuenta, cobro + soporte)
    if cobro and soporte:
        return Punto(S_FACTURA, "Cobro de urgencia", CORRECTO, "Se cobra urgencia y hay soporte de atención de urgencias/triage.", folios)
    if cobro:
        return Punto(S_FACTURA, "Cobro de urgencia", ERROR, "Se cobra urgencia pero no se encontró la atención inicial de urgencias ni el triage.", folios)
    if soporte:
        return Punto(S_FACTURA, "Cobro de urgencia", REVISAR, "Hay atención de urgencias, pero no se identificó su cobro en el texto de la factura.", folios)
    return Punto(S_FACTURA, "Cobro de urgencia", NO_APLICA, "No se cobra urgencia ni hay atención de urgencias.")


PATRON_DIAS_FACTURA = re.compile(
    r"(\d{1,3})\s*dias?\s*(?:de\s*)?(?:estancia|hospitalizacion)|(?:estancia|hospitalizacion|habitacion)[^\n]{0,40}?(\d{1,3})\s*dias?"
)


def _estancia(cuenta: Cuenta) -> Punto:
    nombre = "Estancia"
    ingresos = {leer_fecha(d.valor) for d in cuenta.datos_de("clinico.fecha_ingreso")} - {None}
    egresos = {leer_fecha(d.valor) for d in cuenta.datos_de("clinico.fecha_egreso")} - {None}
    folios = _lista_folios(cuenta, [d.folio for d in cuenta.datos_de("clinico.fecha_ingreso") + cuenta.datos_de("clinico.fecha_egreso")])
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

    dias_factura = []
    for folio in cuenta.folios_de(_grupo("factura")):
        for m in PATRON_DIAS_FACTURA.finditer(folio.texto_normalizado):
            dias_factura.append((int(m.group(1) or m.group(2)), folio))
    notas = cuenta.folios_de(_grupo("evolucion"))
    resumen = f"Ingreso {ingreso:%d/%m/%Y}, egreso {egreso:%d/%m/%Y}: {dias} día(s); {len(notas)} folio(s) de notas de evolución."
    excesivos = [(n, f) for n, f in dias_factura if n > dias + 1]
    if excesivos:
        return Punto(
            S_FACTURA, nombre, ERROR,
            f"{resumen} La factura cobra {', '.join(str(n) for n, _ in excesivos)} día(s) de estancia.",
            folios + _lista_folios(cuenta, [f for _, f in excesivos]),
        )
    if dias >= 1 and not notas:
        return Punto(S_FACTURA, nombre, FALTA, f"{resumen} No se encontraron notas de evolución que soporten la estancia.", folios)
    return Punto(S_FACTURA, nombre, CORRECTO, resumen, folios + _lista_folios(cuenta, notas))


def revisar_factura(cuenta: Cuenta) -> list[Punto]:
    return [
        comparar(cuenta, S_FACTURA, "Número de factura (FURIPS vs. factura)", "administrativo.numero_factura", ["furips", "factura"]),
        _urgencia(cuenta),
        _estancia(cuenta),
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


def revisar_poliza(cuenta: Cuenta) -> list[Punto]:
    g = ["furips", "poliza", "runt"]
    gv = ["furips", "documentos_vehiculo"]
    return [
        comparar(cuenta, S_POLIZA, "Número de póliza (FURIPS, póliza y RUNT)", "administrativo.numero_poliza", g),
        comparar(cuenta, S_POLIZA, "Vigencia desde (FURIPS, póliza y RUNT)", "administrativo.vigencia_poliza_desde", g),
        comparar(cuenta, S_POLIZA, "Vigencia hasta (FURIPS, póliza y RUNT)", "administrativo.vigencia_poliza_hasta", g),
        _vigencia(cuenta),
        comparar(cuenta, S_POLIZA, "Placa (los documentos SOAT son del vehículo del evento)", "accidente.placa", g),
        comparar(cuenta, S_POLIZA, "Propietario: nombre", "administrativo.propietario_nombre", gv, _clave_nombre),
        comparar(cuenta, S_POLIZA, "Propietario: identificación", "administrativo.propietario_identificacion", gv),
        comparar(cuenta, S_POLIZA, "Conductor: nombre", "administrativo.conductor_nombre", gv, _clave_nombre),
        comparar(cuenta, S_POLIZA, "Conductor: identificación", "administrativo.conductor_identificacion", gv),
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
    distintos_id = {d.normalizado for d in ids}
    base = nombres[0].valor if nombres else ""
    nombres_raros = [d for d in nombres if _similitud(base, d.valor) < 0.5]
    folios = _lista_folios(cuenta, [d.folio for d in ids + nombres])
    if not ids and not nombres:
        puntos.append(Punto(S_PACIENTE, "Todos los folios son del mismo paciente", FALTA, "No se encontró nombre ni identificación del paciente."))
    elif len(distintos_id) > 1 or nombres_raros:
        detalle = []
        if len(distintos_id) > 1:
            detalle.append(f"identificaciones distintas: {_describir(cuenta, ids)}")
        if nombres_raros:
            detalle.append(f"nombres distintos: {_describir(cuenta, [nombres[0]] + nombres_raros)}")
        puntos.append(Punto(S_PACIENTE, "Todos los folios son del mismo paciente", ERROR, "; ".join(detalle) + ".", folios))
    else:
        valor = f"{nombres[0].valor} " if nombres else ""
        ident = f"identificación {ids[0].valor}" if ids else ""
        puntos.append(Punto(S_PACIENTE, "Todos los folios son del mismo paciente", CORRECTO, f"{valor}{ident} en todos los folios donde aparece.".strip(), folios))

    sexos = cuenta.datos_de("paciente.sexo")
    valores = {SEXO.get(normalizar(d.valor), d.valor) for d in sexos}
    folios_sexo = _lista_folios(cuenta, [d.folio for d in sexos])
    if not sexos:
        puntos.append(Punto(S_PACIENTE, "Sexo en todos los folios", FALTA, "No se encontró el sexo del paciente."))
    elif len(valores) > 1:
        puntos.append(Punto(S_PACIENTE, "Sexo en todos los folios", ERROR, f"No coincide: {_describir(cuenta, sexos)}.", folios_sexo))
    else:
        puntos.append(Punto(S_PACIENTE, "Sexo en todos los folios", CORRECTO, f"{'Masculino' if valores == {'M'} else 'Femenino' if valores == {'F'} else valores.pop()} en todos los folios donde aparece.", folios_sexo))
    return puntos


# =====================================================================
# 5. Pertinencia: exámenes, lateralidad, osteosíntesis, firmas, medicamentos
# =====================================================================

S_PERTINENCIA = "Pertinencia, ayudas diagnósticas y firmas"
PATRON_LADO = r"(derech[oa]s?|izquierd[oa]s?|bilateral(?:es)?)"


def _lateralidad(cuenta: Cuenta) -> Punto:
    regiones = [normalizar(r) for r in parametros()["regiones"]]
    patron = re.compile(r"\b(" + "|".join(re.escape(r) for r in _unicos(regiones)) + r")s?\b(?:\s+\w+){0,3}?\s+" + PATRON_LADO + r"\b")
    lados: dict[str, dict[str, list[Folio]]] = {}
    for folio in cuenta.folios:
        for m in patron.finditer(folio.texto_normalizado):
            lado = "bilateral" if m.group(2).startswith("bilateral") else ("DERECHA" if m.group(2).startswith("derech") else "IZQUIERDA")
            lados.setdefault(m.group(1), {}).setdefault(lado, []).append(folio)
    if not lados:
        return Punto(S_PERTINENCIA, "Lateralidad", FALTA, "No se encontraron regiones con lateralidad (derecha/izquierda).")
    conflictos = {r: l for r, l in lados.items() if "DERECHA" in l and "IZQUIERDA" in l and "bilateral" not in l}
    if conflictos:
        detalle = "; ".join(
            f"{region}: DERECHA en {', '.join(_lista_folios(cuenta, l['DERECHA']))} e IZQUIERDA en {', '.join(_lista_folios(cuenta, l['IZQUIERDA']))}"
            for region, l in conflictos.items()
        )
        folios = _lista_folios(cuenta, [f for l in conflictos.values() for fs in l.values() for f in fs])
        return Punto(S_PERTINENCIA, "Lateralidad", ERROR, f"Lateralidad distinta para la misma región: {detalle}.", folios)
    detalle = "; ".join(f"{r}: {', '.join(l)}" for r, l in lados.items())
    return Punto(S_PERTINENCIA, "Lateralidad", CORRECTO, f"Lateralidad consistente ({detalle}).")


def _examenes(cuenta: Cuenta) -> list[Punto]:
    p = parametros()
    informes = cuenta.folios_de(_grupo("informes"))
    ordenes = cuenta.folios_de(_grupo("ordenes"))
    puntos = []

    # Informe e interpretación de los exámenes radiológicos
    sin_interpretacion, con_informe = [], []
    for estudio, palabras in p["estudios_radiologicos"].items():
        en_informes = _buscar(informes, palabras)
        if en_informes:
            con_informe.append(estudio)
            for folio in en_informes:
                if not _buscar([folio], p["palabras_interpretacion"]):
                    sin_interpretacion.append((estudio, folio))
    ordenados_sin_informe = [e for e, palabras in p["estudios_radiologicos"].items() if e not in con_informe and _buscar(ordenes, palabras)]
    if not con_informe and not ordenados_sin_informe:
        puntos.append(Punto(S_PERTINENCIA, "Exámenes radiológicos: informe e interpretación", NO_APLICA, "No hay exámenes radiológicos en la cuenta."))
    elif sin_interpretacion or ordenados_sin_informe:
        detalle = []
        if ordenados_sin_informe:
            detalle.append(f"ordenados sin informe: {', '.join(ordenados_sin_informe)}")
        if sin_interpretacion:
            detalle.append("informe sin interpretación: " + ", ".join(f"{e} ({cuenta.ubicacion(f)})" for e, f in sin_interpretacion))
        resultado = FALTA if ordenados_sin_informe else REVISAR
        puntos.append(Punto(S_PERTINENCIA, "Exámenes radiológicos: informe e interpretación", resultado, "; ".join(detalle) + ".",
                            _lista_folios(cuenta, [f for _, f in sin_interpretacion])))
    else:
        puntos.append(Punto(S_PERTINENCIA, "Exámenes radiológicos: informe e interpretación", CORRECTO,
                            f"Con informe e interpretación: {', '.join(con_informe)}.", _lista_folios(cuenta, informes)))

    # Justificación de todas las ayudas diagnósticas
    todas = {**p["estudios_radiologicos"], **p["otras_ayudas"]}
    sin_justificar, justificadas = [], []
    for estudio, palabras in todas.items():
        en_informes = _buscar(informes, palabras)
        if not en_informes:
            continue
        if _buscar(ordenes, palabras):
            justificadas.append(estudio)
        else:
            sin_justificar.append((estudio, en_informes[0]))
    if not sin_justificar and not justificadas:
        puntos.append(Punto(S_PERTINENCIA, "Ayudas diagnósticas justificadas", NO_APLICA, "No hay informes de ayudas diagnósticas."))
    elif sin_justificar:
        puntos.append(Punto(
            S_PERTINENCIA, "Ayudas diagnósticas justificadas", FALTA,
            "No se encontró orden ni justificación en la historia/urgencias/órdenes para: "
            + ", ".join(f"{e} (informe en {cuenta.ubicacion(f)})" for e, f in sin_justificar) + ".",
            _lista_folios(cuenta, [f for _, f in sin_justificar]),
        ))
    else:
        puntos.append(Punto(S_PERTINENCIA, "Ayudas diagnósticas justificadas", CORRECTO, f"Con orden o justificación: {', '.join(justificadas)}."))
    return puntos


def _osteosintesis(cuenta: Cuenta) -> Punto:
    nombre = "Material de osteosíntesis descrito en el informe quirúrgico"
    materiales = parametros()["materiales"]
    soportes = cuenta.folios_de(_grupo("material")) + _buscar(cuenta.folios_de(_grupo("factura")), ["osteosintesis"])
    if not soportes:
        return Punto(S_PERTINENCIA, nombre, NO_APLICA, "No hay material de osteosíntesis en la cuenta.")
    quirurgicos = cuenta.folios_de(_grupo("quirurgico"))
    usados = [m for m in materiales if _buscar(soportes, [m, m + "s", m + "es"])]
    if not quirurgicos:
        return Punto(S_PERTINENCIA, nombre, FALTA, f"Hay material ({', '.join(usados) or 'sin detalle'}) pero no se encontró la descripción quirúrgica.", _lista_folios(cuenta, soportes))
    no_descritos = [m for m in usados if not _buscar(quirurgicos, [m, m + "s", m + "es"])]
    folios = _lista_folios(cuenta, soportes + quirurgicos)
    if no_descritos:
        return Punto(S_PERTINENCIA, nombre, ERROR, f"Material no descrito en la descripción quirúrgica: {', '.join(no_descritos)}.", folios)
    return Punto(S_PERTINENCIA, nombre, CORRECTO, f"Descrito en la cirugía: {', '.join(usados) or 'material sin detalle'}. Verifique cantidades.", folios)


def _firmas_medicos(cuenta: Cuenta) -> Punto:
    nombre = "Médicos de los informes con firma/registro"
    p = parametros()
    medico = re.compile("|".join(p["palabras_medico"]))
    firma = re.compile("|".join(p["palabras_firma"]))
    folios = cuenta.folios_de(_grupo("con_firma_medica"))
    if not folios:
        return Punto(S_PERTINENCIA, nombre, NO_APLICA, "No hay informes, descripciones quirúrgicas ni epicrisis con texto.")
    sin_medico = [f for f in folios if not medico.search(f.texto_normalizado)]
    sin_firma = [f for f in folios if f not in sin_medico and not firma.search(f.texto_normalizado)]
    if sin_medico:
        return Punto(S_PERTINENCIA, nombre, FALTA, f"No se identifica el médico en: {', '.join(_lista_folios(cuenta, sin_medico))}.", _lista_folios(cuenta, sin_medico + sin_firma))
    if sin_firma:
        return Punto(S_PERTINENCIA, nombre, REVISAR, f"Médico identificado pero sin firma ni registro en el texto (puede estar en imagen): {', '.join(_lista_folios(cuenta, sin_firma))}.", _lista_folios(cuenta, sin_firma))
    return Punto(S_PERTINENCIA, nombre, CORRECTO, "Todos los informes identifican al médico con firma o registro (en el texto).", _lista_folios(cuenta, folios))


def _orden_ambulatoria(cuenta: Cuenta) -> Punto:
    nombre = "Orden de medicamentos ambulatorios firmada por el paciente"
    p = parametros()
    ordenes = _buscar(cuenta.folios, p["palabras_orden_ambulatoria"])
    if not ordenes:
        return Punto(S_PERTINENCIA, nombre, FALTA, "No se encontró la orden de medicamentos ambulatorios.")
    con_espacio = _buscar(ordenes, p["palabras_firma_paciente"])
    if con_espacio:
        return Punto(S_PERTINENCIA, nombre, REVISAR, "Orden encontrada con espacio de firma del paciente: verifique visualmente que esté firmada.", _lista_folios(cuenta, con_espacio))
    return Punto(S_PERTINENCIA, nombre, REVISAR, "Orden encontrada, pero el texto no muestra firma del paciente: verifíquelo visualmente.", _lista_folios(cuenta, ordenes))


def revisar_pertinencia(cuenta: Cuenta) -> list[Punto]:
    return [_lateralidad(cuenta), *_examenes(cuenta), _osteosintesis(cuenta), _firmas_medicos(cuenta), _orden_ambulatoria(cuenta)]


def revisar_cuenta(cuenta: Cuenta) -> list[Punto]:
    """Todos los puntos de la lista del auditor, en orden."""
    return [*revisar_furips(cuenta), *revisar_factura(cuenta), *revisar_poliza(cuenta), *revisar_paciente(cuenta), *revisar_pertinencia(cuenta)]
