"""Utilidades de texto: normalización y lectura de fechas.

El texto de los documentos es contenido NO confiable: aquí solo se compara y
transforma, nunca se interpreta como instrucción.
"""

import re
import unicodedata
from datetime import date

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def quitar_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin tildes y con espacios simples. Sirve para comparar."""
    if not texto:
        return ""
    return " ".join(quitar_tildes(texto).lower().split())


def solo_alfanumerico(texto: str | None) -> str:
    """Deja solo letras y números en mayúscula (para identificaciones, placas, facturas)."""
    return re.sub(r"[^0-9A-Z]", "", quitar_tildes(texto or "").upper())


def leer_fecha(texto: str | None) -> date | None:
    """Interpreta fechas comunes en documentos colombianos (día primero).

    Acepta: 05/03/2025, 5-3-2025, 2025-03-05, 5 de marzo de 2025.
    Devuelve None si no se puede interpretar con certeza.
    """
    if not texto:
        return None
    limpio = normalizar(texto)

    coincidencia = re.search(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b", limpio)
    if coincidencia:
        anio, mes, dia = map(int, coincidencia.groups())
        return _fecha_segura(anio, mes, dia)

    coincidencia = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", limpio)
    if coincidencia:
        dia, mes, anio = map(int, coincidencia.groups())
        return _fecha_segura(anio, mes, dia)

    coincidencia = re.search(r"\b(\d{1,2})\s+de\s+([a-z]+)\s+(?:de|del)\s+(\d{4})\b", limpio)
    if coincidencia and coincidencia.group(2) in MESES:
        return _fecha_segura(int(coincidencia.group(3)), MESES[coincidencia.group(2)], int(coincidencia.group(1)))

    # 23 JUN 1997, 23/junio/1997, 23-jun-1997
    coincidencia = re.search(r"\b(\d{1,2})[\s/-]+([a-z]{3,10})\.?[\s/-]+(\d{4})\b", limpio)
    if coincidencia:
        mes = _mes(coincidencia.group(2))
        if mes:
            return _fecha_segura(int(coincidencia.group(3)), mes, int(coincidencia.group(1)))

    return None


def _mes(texto: str) -> int | None:
    """Número de mes a partir del nombre completo o abreviado (ene, feb, ..., sept)."""
    if texto in MESES:
        return MESES[texto]
    for nombre, numero in MESES.items():
        if len(texto) >= 3 and nombre.startswith(texto[:3]) and (texto == nombre[: len(texto)]):
            return numero
    return None


def _fecha_segura(anio: int, mes: int, dia: int) -> date | None:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def calcular_edad(fecha_nacimiento: date | None, fecha_referencia: date | None) -> int | None:
    """Edad cumplida a la fecha de referencia (la del accidente, nunca la actual).

    Devuelve None si falta una fecha o si el nacimiento es posterior a la referencia.
    """
    if not fecha_nacimiento or not fecha_referencia or fecha_nacimiento > fecha_referencia:
        return None
    cumplio = (fecha_referencia.month, fecha_referencia.day) >= (fecha_nacimiento.month, fecha_nacimiento.day)
    return fecha_referencia.year - fecha_nacimiento.year - (0 if cumplio else 1)


def fragmento(texto: str, inicio: int, fin: int, margen: int = 60) -> str:
    """Recorta un fragmento alrededor de una coincidencia para usarlo como evidencia."""
    desde = max(0, inicio - margen)
    hasta = min(len(texto), fin + margen)
    recorte = " ".join(texto[desde:hasta].split())
    return ("…" if desde > 0 else "") + recorte + ("…" if hasta < len(texto) else "")
