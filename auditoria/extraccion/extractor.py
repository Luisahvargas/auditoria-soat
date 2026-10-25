"""Extracción determinística de datos de la ficha maestra desde el texto de las páginas.

Los campos y patrones están en configuracion/ficha.yaml. Cada dato extraído guarda
archivo, página del archivo original, fragmento de evidencia y método.
El texto de los documentos es contenido no confiable: solo se buscan patrones.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from auditoria.config import RAIZ_PROYECTO
from auditoria.texto import fragmento, leer_fecha, normalizar, quitar_tildes, solo_alfanumerico

RUTA_FICHA = RAIZ_PROYECTO / "configuracion" / "ficha.yaml"

COMODINES = {
    "{FECHA}": r"(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2} de [a-z]+ del? \d{4})",
    "{NUM_ID}": r"(?:\d{1,3}(?:[.,]\d{3}){1,4}|\d{5,12})",
}
CORTE_NOMBRE = re.compile(
    r"\s{2,}|\b(?:identificacion|documento|c\.?c\b|t\.?i\b|edad|sexo|fecha|tipo|telefono|direccion|historia)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CampoFicha:
    id: str
    etiqueta: str
    bloque: str
    tipo: str
    multiple: bool
    revisar_si_falta: bool
    patrones: tuple[re.Pattern, ...]
    contexto_excluir: tuple[str, ...]


@dataclass(frozen=True)
class DefinicionFicha:
    version: str
    bloques: dict[str, str]
    campos: tuple[CampoFicha, ...]

    def campo(self, campo_id: str) -> CampoFicha:
        for campo in self.campos:
            if campo.id == campo_id:
                return campo
        raise KeyError(campo_id)


@dataclass(frozen=True)
class Coincidencia:
    campo_id: str
    valor: str
    evidencia: str


@lru_cache(maxsize=4)
def cargar_definicion(ruta: Path = RUTA_FICHA) -> DefinicionFicha:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    campos = []
    for c in datos["campos"]:
        patrones = []
        for patron in c.get("patrones", []):
            for comodin, expresion in COMODINES.items():
                patron = patron.replace(comodin, expresion)
            patrones.append(re.compile(patron, re.IGNORECASE))
        campos.append(
            CampoFicha(
                id=c["id"],
                etiqueta=c["etiqueta"],
                bloque=c["bloque"],
                tipo=c.get("tipo", "texto"),
                multiple=bool(c.get("multiple", False)),
                revisar_si_falta=bool(c.get("revisar_si_falta", False)),
                patrones=tuple(patrones),
                contexto_excluir=tuple(normalizar(p) for p in c.get("contexto_excluir", [])),
            )
        )
    return DefinicionFicha(version=str(datos.get("version", "")), bloques=dict(datos["bloques"]), campos=tuple(campos))


def limpiar_valor(campo: CampoFicha, valor: str) -> str:
    """Recorta ruido alrededor del valor capturado (sin cambiar su contenido)."""
    valor = valor.strip(" \t:-.;,")
    if campo.tipo in ("nombre", "texto"):
        corte = (CORTE_NOMBRE if campo.tipo == "nombre" else re.compile(r"\s{3,}")).search(valor)
        if corte and corte.start() > 0:
            valor = valor[: corte.start()]
        if campo.tipo == "nombre":
            valor = re.sub(r"\s+\w$", "", valor.strip())  # Letra suelta final (p. ej. la "C" de "C.C.")
    return " ".join(valor.split()).strip(" :-.;,")


def normalizar_valor(tipo: str, valor: str) -> str:
    """Forma comparable de un valor según su tipo (para detectar discrepancias)."""
    if tipo == "fecha":
        fecha = leer_fecha(valor)
        return fecha.isoformat() if fecha else normalizar(valor)
    if tipo == "identificacion":
        return re.sub(r"\D", "", valor)
    if tipo in ("placa", "codigo"):
        return solo_alfanumerico(valor)
    if tipo == "numero":
        return re.sub(r"\D", "", valor).lstrip("0") or "0"
    if tipo == "hora":
        return re.sub(r"\s", "", normalizar(valor)).replace(".", "")
    return normalizar(valor)


def extraer_de_texto(texto: str, definicion: DefinicionFicha | None = None) -> list[Coincidencia]:
    """Busca todos los campos en el texto de una página."""
    definicion = definicion or cargar_definicion()
    if not texto:
        return []
    # Se busca sobre el texto sin tildes; si la longitud se conserva, el valor se toma del original.
    sin_tildes = quitar_tildes(texto)
    misma_longitud = len(sin_tildes) == len(texto)
    resultados: list[Coincidencia] = []
    vistos: set[tuple[str, str]] = set()

    for campo in definicion.campos:
        for patron in campo.patrones:
            for coincidencia in patron.finditer(sin_tildes):
                inicio, fin = coincidencia.span("valor")
                # Contexto: lo que hay antes del dato en la MISMA línea (máx. 80 caracteres).
                desde = max(0, coincidencia.start() - 80, sin_tildes.rfind("\n", 0, coincidencia.start()) + 1)
                antes = normalizar(sin_tildes[desde : coincidencia.start()])
                if any(re.search(rf"\b{re.escape(palabra)}\b", antes) for palabra in campo.contexto_excluir):
                    continue
                original = texto[inicio:fin] if misma_longitud else coincidencia.group("valor")
                valor = limpiar_valor(campo, original)
                if not valor:
                    continue
                clave = (campo.id, normalizar_valor(campo.tipo, valor))
                if clave in vistos:
                    continue
                vistos.add(clave)
                resultados.append(Coincidencia(campo.id, valor, fragmento(texto, coincidencia.start(), fin)))
    return resultados
