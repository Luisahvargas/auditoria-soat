"""Lectores de formularios con tablas: FURIPS, SIRAS, póliza SOAT / licencia de tránsito y RUNT.

En estos formularios la misma etiqueta aparece varias veces (p. ej. "Nro. Documento" de la
víctima, del propietario, del conductor y del médico), por eso se leen por secciones.
Cada lector devuelve (campo, valor, evidencia). Si no reconoce el formato devuelve [].
"""

import re

from auditoria.texto import normalizar, quitar_tildes

FECHA = r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/ -][a-z]{3,10}\.?[/ -]\d{4})"
PLACA = re.compile(r"\b([A-Z][A-Z0-9]{2}\s?-?\s?[0-9]{2}[A-Z0-9])\b")
OPCIONES_CALIDAD = ("conductor", "peaton", "ocupante", "ciclista")


def _lineas(texto: str) -> list[str]:
    """Líneas en minúsculas y sin tildes (conservan el contenido para recortar evidencia)."""
    return [quitar_tildes(l).lower() for l in (texto or "").splitlines()]


def _buscar(patron: str, lineas: list[str]) -> tuple[str, str] | None:
    """Primer valor del patrón en las líneas: (valor en mayúsculas, línea de evidencia)."""
    expresion = re.compile(patron)
    for linea in lineas:
        m = expresion.search(linea)
        if m:
            return m.group(1).strip().upper(), " ".join(linea.split())
    return None


def _nombre_sobre_etiquetas(lineas: list[str]) -> tuple[str, str] | None:
    """En el FURIPS el nombre va en la línea anterior a '1er. Apellido  2do. Apellido ...'."""
    for i, linea in enumerate(lineas):
        if "1er. apellido" in linea or "1er apellido" in linea:
            for j in range(i - 1, max(i - 4, -1), -1):
                partes = [p for p in re.split(r"\s{2,}", lineas[j].strip()) if p]
                if partes and all(re.fullmatch(r"[a-zñ ]+", p) for p in partes):
                    apellidos, nombres = partes[:2], partes[2:]
                    return " ".join(nombres + apellidos).upper(), " ".join(lineas[j].split())
            return None
    return None


def _secciones_furips(texto: str) -> dict[str, list[str]]:
    secciones: dict[str, list[str]] = {"encabezado": []}
    actual = "encabezado"
    for linea in _lineas(texto):
        m = re.match(r"\s*(i{1,3}|iv|v|vi{1,3}|ix|x|xi)\.\s+[a-z]", linea)
        if m:
            actual = m.group(1)
            secciones.setdefault(actual, [])
        secciones.setdefault(actual, []).append(linea)
    return secciones


def _calidad_marcada(linea: str) -> str | None:
    """'condicion del accidentado  x conductor  peaton ...' → la opción junto a la X.

    Si la X está entre dos opciones no se puede saber cuál es: se devuelve None.
    """
    resto = "accidentado " + linea.split("accidentado", 1)[1] if "accidentado" in linea else linea
    m = re.search(r"(\S+)\s+x\s+(\S+)", resto)
    if not m:
        return None
    antes, despues = m.group(1), m.group(2)
    antes_es, despues_es = antes in OPCIONES_CALIDAD, despues in OPCIONES_CALIDAD
    if antes_es and despues_es:
        return None
    return antes if antes_es else despues if despues_es else None


def leer_furips(texto: str) -> list[tuple[str, str, str]]:
    secciones = _secciones_furips(texto)
    if len(secciones) < 2:
        return []  # No es el formulario oficial con secciones
    datos = []

    def agregar(campo, patron, lineas):
        r = _buscar(patron, lineas)
        if r:
            datos.append((campo, r[0], r[1]))

    todas = [l for ls in secciones.values() for l in ls]
    agregar("administrativo.numero_factura", r"nro\.?\s*factura\s+([a-z0-9\-]+)", todas)

    victima = secciones.get("ii", [])
    if victima:
        nombre = _nombre_sobre_etiquetas(victima)
        if nombre:
            datos.append(("paciente.nombre", nombre[0], nombre[1]))
        agregar("paciente.numero_identificacion", r"nro\.?\s*documento\s+([\d.]{5,15})", victima)
        agregar("paciente.fecha_nacimiento", r"fecha de nacimiento\s+" + FECHA, victima)
        agregar("paciente.sexo", r"\bsexo\s+([mf])\b", victima)
        agregar("paciente.telefono", r"telefono\s+(\d{7,10})", victima)
        for linea in victima:
            if "condicion del accidentado" in linea:
                calidad = _calidad_marcada(linea)
                if calidad:
                    datos.append(("accidente.calidad_victima", calidad, " ".join(linea.split())))

    evento = secciones.get("iii", [])
    if evento:
        agregar("accidente.direccion", r"direccion de la ocurrencia\s+(.+?)(?:\s{2,}|$)", evento)
        agregar("accidente.fecha", r"fecha evento/accidente\s+" + FECHA, evento)
        agregar("accidente.hora", r"fecha evento/accidente\s+\S+\s+hora\s+(\d{1,2}:\d{2})", evento)
        zona = _buscar(r"\bzona\s+([ur])\b", evento)
        if zona:
            datos.append(("accidente.zona", "urbana" if zona[0].lower() == "u" else "rural", zona[1]))
        relato, leyendo = [], False
        for linea in evento:
            if "descripcion breve" in linea:
                leyendo = True
                continue
            if leyendo and linea.strip():
                relato.append(linea.strip())
        if relato:
            texto_relato = " ".join(" ".join(relato).split())
            datos.append(("accidente.relato", texto_relato, texto_relato[:200]))

    vehiculo = secciones.get("iv", [])
    if vehiculo:
        agregar("accidente.placa", r"\bplaca\s+([a-z0-9]{5,7})\b", vehiculo)
        agregar("administrativo.numero_poliza", r"numero de la poliza\s+(\d{5,15})", vehiculo)
        agregar("administrativo.vigencia_poliza_desde", r"desde\s+" + FECHA, vehiculo)
        agregar("administrativo.vigencia_poliza_hasta", r"hasta\s+" + FECHA, vehiculo)

    for seccion, prefijo in (("v", "administrativo.propietario"), ("vi", "administrativo.conductor")):
        lineas = secciones.get(seccion, [])
        if lineas:
            nombre = _nombre_sobre_etiquetas(lineas)
            if nombre:
                datos.append((f"{prefijo}_nombre", nombre[0], nombre[1]))
            agregar(f"{prefijo}_identificacion", r"nro\.?\s*documento\s+([\d.]{5,15})", lineas)

    atencion = secciones.get("ix", [])
    if atencion:
        agregar("clinico.fecha_ingreso", r"fecha de ingreso\s+" + FECHA, atencion)
        agregar("clinico.hora_ingreso", r"fecha de ingreso\s+\S+\s+a las\s+(\d{1,2}:\d{2})", atencion)
        agregar("clinico.fecha_egreso", r"fecha de egreso\s+" + FECHA, atencion)
    return datos


def leer_siras(texto: str) -> list[tuple[str, str, str]]:
    """Formulario SIRAS: secciones numeradas '1. DATOS DE LA VÍCTIMA', '4. DATOS DEL ACCIDENTE', '5. ... CONDUCTOR'."""
    secciones: dict[str, list[str]] = {}
    actual = "0"
    for linea in _lineas(texto):
        m = re.match(r"\s*(\d)\.\s+[a-z]", linea)
        if m:
            actual = m.group(1)
        secciones.setdefault(actual, []).append(linea)
    if len(secciones) < 2:
        return []
    datos = []

    def agregar(campo, patron, lineas):
        r = _buscar(patron, lineas)
        if r:
            datos.append((campo, r[0], r[1]))

    def nombre(lineas):
        ap = _buscar(r"1er apellido\s+([a-zñ]+)\s+2o apellido\s+([a-zñ]*)", lineas)
        no = _buscar(r"1er nombre\s+([a-zñ]+)\s+2o nombre\s+([a-zñ]*)", lineas)
        if not ap or not no:
            return None
        ap_m = re.search(r"1er apellido\s+([a-zñ]+)\s+2o apellido\s+([a-zñ]*)", ap[1])
        no_m = re.search(r"1er nombre\s+([a-zñ]+)\s+2o nombre\s+([a-zñ]*)", no[1])
        partes = [no_m.group(1), no_m.group(2), ap_m.group(1), ap_m.group(2)]
        return " ".join(p for p in partes if p).upper(), ap[1]

    victima = secciones.get("1", [])
    n = nombre(victima)
    if n:
        datos.append(("paciente.nombre", n[0], n[1]))
    agregar("paciente.numero_identificacion", r"numero de identificacion:\s*([\d.]{5,15})", victima)
    agregar("paciente.fecha_nacimiento", r"fecha de nacimiento:\s*" + FECHA, victima)
    agregar("paciente.sexo", r"sexo[a-z ]*:\s*(masculino|femenino|m|f)\b", victima)
    agregar("accidente.calidad_victima", r"condicion de la victima:\s*([a-z]+)", victima)

    ingreso = secciones.get("2", [])
    agregar("clinico.fecha_ingreso", r"fecha hora:\s*" + FECHA, ingreso)
    agregar("clinico.hora_ingreso", r"fecha hora:\s*\S+\s+(\d{1,2}:\d{2})", ingreso)

    accidente = secciones.get("4", [])
    agregar("accidente.fecha", r"fecha hora del evento:\s*" + FECHA, accidente)
    agregar("accidente.hora", r"fecha hora del evento:\s*\S+\s+(\d{1,2}:\d{2})", accidente)
    agregar("accidente.direccion", r"direccion del accidente:\s*(.+?)(?:\s{2,}|$)", accidente)
    agregar("accidente.placa", r"\bplaca:\s*([a-z0-9]{5,7})\b", accidente)

    conductor = secciones.get("5", [])
    n = nombre(conductor)
    if n:
        datos.append(("administrativo.conductor_nombre", n[0], n[1]))
    agregar("administrativo.conductor_identificacion", r"numero de identificacion:\s*([\d.]{5,15})", conductor)
    return datos


def leer_documentos_vehiculo(texto: str) -> list[tuple[str, str, str]]:
    """Póliza SOAT y licencia de tránsito (tablas con el valor debajo del encabezado)."""
    originales = (texto or "").splitlines()
    lineas = _lineas(texto)
    datos = []
    for i, linea in enumerate(lineas):
        ventana = range(i, min(i + 4, len(lineas)))
        if "placa" in linea and not any(d[0] == "accidente.placa" for d in datos):
            for j in ventana:
                # En el renglón del encabezado solo se mira lo que sigue a la palabra "placa".
                fragmento = originales[j].upper()
                if j == i:
                    fragmento = fragmento[linea.index("placa") + 5 :]
                m = PLACA.search(fragmento)
                if m:
                    datos.append(("accidente.placa", m.group(1).replace(" ", "").replace("-", ""), " ".join(originales[j].split())))
                    break
        if "poliza" in linea and ("no." in linea or "numero" in linea) and not any(d[0] == "administrativo.numero_poliza" for d in datos):
            for j in ventana:
                fragmento = lineas[j][linea.index("poliza") :] if j == i else lineas[j]
                m = re.search(r"\b(\d{6,15})\b", fragmento)
                if m:
                    datos.append(("administrativo.numero_poliza", m.group(1), " ".join(originales[j].split())))
                    break
        if "vigencia" in linea and not any(d[0] == "administrativo.vigencia_poliza_desde" for d in datos):
            bloque = " ".join(lineas[j] for j in ventana)
            triples = re.findall(r"\b(20\d{2})\s+(\d{1,2})\s+(\d{1,2})\b", bloque)
            if len(triples) >= 2:  # año mes día: el último par es desde / hasta
                (a1, m1, d1), (a2, m2, d2) = triples[-2], triples[-1]
                evidencia = " ".join(bloque.split())[:200]
                datos.append(("administrativo.vigencia_poliza_desde", f"{d1}/{m1}/{a1}", evidencia))
                datos.append(("administrativo.vigencia_poliza_hasta", f"{d2}/{m2}/{a2}", evidencia))
        if "propietario" in linea and not any(d[0] == "administrativo.propietario_identificacion" for d in datos):
            for j in ventana:
                m = re.search(r"([a-zñ][a-zñ ]{4,60}?)\s+c\.?\s?c\.?\s*([\d.]{5,15})", lineas[j][linea.index("propietario") + 11 :] if j == i else lineas[j])
                if m and "propietario" not in m.group(1):
                    datos.append(("administrativo.propietario_nombre", " ".join(m.group(1).split()).upper(), " ".join(originales[j].split())))
                    datos.append(("administrativo.propietario_identificacion", m.group(2), " ".join(originales[j].split())))
                    break
    return datos


def leer_runt(texto: str) -> list[tuple[str, str, str]]:
    lineas = _lineas(texto)
    datos = []
    r = _buscar(r"documento:\s*(?:c\.?c\.?\s*)?([\d.]{5,15})", lineas)
    if r:
        datos.append(("runt.documento", r[0], r[1]))
    r = _buscar(r"estado del conductor:\s*(.+?)(?:\s{2,}|$)", lineas)
    if r:
        datos.append(("runt.estado_conductor", r[0].upper(), r[1]))
    return datos + leer_documentos_vehiculo(texto)


LECTORES = {
    "FURIPS": leer_furips,
    "SIRAS": leer_siras,
    "Póliza SOAT y documentos del vehículo": leer_documentos_vehiculo,
    "Consulta RUNT": leer_runt,
}

# En estos tipos no se buscan datos del paciente con los patrones generales
# (sus números y nombres son del propietario, tomador o conductor).
SIN_DATOS_GENERALES_DEL_PACIENTE = ("Póliza SOAT y documentos del vehículo", "Consulta RUNT", "Consulta ADRES", "Identificaciones")


def normalizar_texto_evidencia(texto: str) -> str:
    return " ".join(normalizar(texto).split())
