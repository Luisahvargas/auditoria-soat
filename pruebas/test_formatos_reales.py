"""Pruebas con documentos FICTICIOS que imitan el formato de cuentas reales (FURIPS oficial,
SIRAS, SOAT en tabla, historia clínica con encabezado repetido). Ningún dato es real."""

from datetime import date

from auditoria.config import Configuracion
from auditoria.documentos.clasificador import clasificar_texto
from auditoria.revision import auditar
from auditoria.revision import formularios
from auditoria.texto import leer_fecha
from pruebas import generadores

FURIPS_TABLA = """Número de Reclamación:       111.111
                     FORMULARIO UNICO DE RECLAMACIONES DE LAS INSTITUCIONES PRESTADORAS DE SALUD
                                          PERSONAS JURIDICAS - FURIPS
 No. Radicado anterior:     0                                    Nro Factura FIC1001
                          I. DATOS DE LA INSTITUCION PRESTADORA DE SERVICIOS DE SALUD
 Departamento         CIUDAD FICTICIA          Cod 11       Telefono   6010000000
                          II. DATOS DE LA VICTIMA DEL EVENTO CATASTRÓFICO O ACCIDENTE DE TRANSITO
            PEREZ                        GOMEZ                       JUAN                     CARLOS
               1er. Apellido                         2do. Apellido                             1er. Nombre                         2do. Nombre
 Tipo de documento      CC                                          Nro. Documento   1111111111
 Fecha de Nacimiento       10-02-1990       Sexo  M
 Departamento         CIUDAD FICTICIA          Cod 11       Telefono   3000000001
 Condición del Accidentado         X  Conductor           Peatón           Ocupante             Ciclista
                          III. DATOS DEL SITIO DONDE OCURRIÓ EL EVENTO CATASTRÓFICO O EL ACCIDENTE DE TRANSITO
 Dirección de la Ocurrencia      CL10 CON CR20
 Fecha Evento/Accidente         05-03-2026      Hora   22:00
 Municipio                CIUDAD FICTICIA          Cod  001             Zona  U
 Descripción Breve del Evento Catastrófico o Accidente de Transito  (Enuncie las principales caracteristicas)
 PACIENTE EN CALIDAD DE CONDUCTOR DE MOTOCICLETA QUE CAE DE FORMA FICTICIA
                          IV. DATOS DEL VEHICULO DEL ACCIDENTE DE TRANSITO
 Marca  FICTICIA                                                   Placa   ABC12D
 Número de la Poliza           11112222                            Intervención de Autoridad
 Vigencia de la Poliza:         Desde   01-01-2026       Hasta   31-12-2026
                          V. DATOS DEL PROPIETARIO DEL VEHICULO
            RUIZ                     DIAZ                       ANA
                1er. Apellido                         2do. Apellido                             1er. Nombre                         2do. Nombre
 Tipo de documento      CC                                            Nro. Documento    2222222222
"""

SIRAS = """             SISTEMA DE INFORMACION DE REPORTES DE
           ATENCION EN SALUD A VICTIMAS DE ACCIDENTES
                    1. DATOS DE LA VÍCTIMA DEL ACCIDENTE DE TRÁNSITO
                   1er Apellido PEREZ                                    2o Apellido GOMEZ
                   1er Nombre JUAN                                   2o Nombre CARLOS
          Tipo de identificación: CC                          Número de identificación: 1111111111
         Fecha de nacimiento: 10/febrero/1990                 Sexo al momento de nacer: MASCULINO
        Condición de la víctima: CONDUCTOR
                        2. TIPO DE INGRESO A LOS SERVICIOS DE SALUD
                Fecha Hora: 04/marzo/2026 23:30            Víctima viene remitida: NO
                                     4. DATOS DEL ACCIDENTE
        Fecha Hora del evento: 04/marzo/2026 22:00
         Dirección del accidente: CL 10 # CON CR20 -
           Vehículo identificado: SI                                                     Placa: ABC12D
"""

SOAT_TABLA = """                                                    ASEGURADORA
                                mundial®SOAT
             FECHA DE EXPEDICIÓN     VIGENCIA
                                                MES  D     HA                       i MES  I DÍA
        2025   12  30    LAS 00  2026  1 1           S 23:59 2026  12  31
          No. DE PÓLIZA.               PLACA No.               CLASE DE VEHÍCULO
    11112222 -
                      ABC12D       MOTOCICLETA          PARTICULAR
"""

HISTORIA = """                                     CLINICA FICTICIA SAS
                                      INGRESO MEDICO
                                    DATOS DEL PACIENTE
Admisión:  1  Identificación:  CC 1111111111  Causa Externa:  ACCIDENTE DE TRANSITO      Ingreso:  2026-03-04 23:30  Egreso:  2026-03-06 10:00
Paciente: JUAN CARLOS PEREZ GOMEZ                  País de Nacionalidad:   COLOMBIA
Fecha de Nacimiento:   1990-02-10   Edad:  36 Años  Genero: MASCULINO
Teléfono:  3000000001   Dirección:  CALLE FICTICIA 1
Persona Resposable:   FAMILIAR FICTICIO          Parentezco:  MAMÁ          Teléfono:  3009999999
EXTREMIDADES: INFERIOR DERECHO: EUTROFICA, SIN EDEMA, NO LESIONES
TRAUMA CONTUNDENTE DE PIERNA IZQUIERDA CON FRACTURA FICTICIA
  Nombre: MEDICO FICTICIO          Entregado por:  AUXILIAR FICTICIO
        Cargo: AUX. ENFERMERIA
      Identificación: 3333333333
"""


def test_fechas_con_mes_en_letras():
    assert leer_fecha("23 JUN 1997") == date(1997, 6, 23)
    assert leer_fecha("30/septiembre/2026") == date(2026, 9, 30)
    assert leer_fecha("1 sept 2026") == date(2026, 9, 1)


def test_clasificacion_por_titulo_y_continuacion():
    assert clasificar_texto(HISTORIA) == "Historia clínica"
    assert clasificar_texto(SIRAS) == "SIRAS"
    # Una hoja sin título continúa el documento anterior.
    assert clasificar_texto("TEXTO DE CONTINUACION FICTICIO SIN TITULO ALGUNO", "Epicrisis") == "Epicrisis"
    # Una frase en medio de un párrafo no es un título.
    assert clasificar_texto("DIAGNOSTICO ANOTADO POR HISTORIA CLINICA. PACIENTE CON INMOVILIZACION DE MIEMBRO INFERIOR NO VALORABLE", "Notas de evolución") == "Notas de evolución"


def test_lector_furips_por_secciones():
    datos = {c: v for c, v, _ in formularios.leer_furips(FURIPS_TABLA)}
    assert datos["paciente.nombre"] == "JUAN CARLOS PEREZ GOMEZ"
    assert datos["paciente.numero_identificacion"] == "1111111111"
    assert datos["paciente.telefono"] == "3000000001"  # No el del prestador
    assert datos["accidente.calidad_victima"] == "conductor"
    assert datos["accidente.zona"] == "urbana"
    assert datos["accidente.fecha"] == "05-03-2026" and datos["accidente.hora"] == "22:00"
    assert datos["administrativo.numero_factura"] == "FIC1001"
    assert datos["administrativo.propietario_identificacion"] == "2222222222"
    assert datos["administrativo.propietario_nombre"] == "ANA RUIZ DIAZ"


def test_lector_soat_en_tabla():
    datos = {c: v for c, v, _ in formularios.leer_documentos_vehiculo(SOAT_TABLA)}
    assert datos["administrativo.numero_poliza"] == "11112222"
    assert datos["accidente.placa"] == "ABC12D"
    assert leer_fecha(datos["administrativo.vigencia_poliza_desde"]) == date(2026, 1, 1)
    assert leer_fecha(datos["administrativo.vigencia_poliza_hasta"]) == date(2026, 12, 31)


def _cuenta(*paginas):
    return auditar([("cuenta_ficticia.pdf", generadores.pdf_con_paginas(list(paginas)))], Configuracion())


def test_cuenta_con_formato_real_detecta_evento_despues_del_ingreso():
    cuenta, puntos, _ = _cuenta(FURIPS_TABLA, HISTORIA, SIRAS, SOAT_TABLA)
    resultados = {p.nombre: p for p in puntos}
    assert resultados["Fecha del evento"].resultado == "Error"  # FURIPS 05/03 vs SIRAS 04/03
    assert resultados["Fecha del evento anterior al ingreso"].resultado == "Error"
    assert "FURIPS dice 05/03/2026 22:00" in resultados["Fecha del evento anterior al ingreso"].detalle
    assert resultados["Calidad del accidentado"].resultado == "Correcto"
    assert resultados["Número de póliza (FURIPS, póliza y RUNT)"].resultado == "Correcto"


def test_cedula_del_personal_y_telefono_del_responsable_no_son_del_paciente():
    cuenta, puntos, _ = _cuenta(HISTORIA)
    ids = {d.normalizado for d in cuenta.datos_de("paciente.numero_identificacion")}
    assert ids == {"1111111111"}
    mismo = next(p for p in puntos if p.nombre == "Todos los folios son del mismo paciente")
    assert mismo.resultado == "Correcto"


def test_lateralidad_ignora_examen_normal_y_detecta_lado_cruzado():
    _, puntos, _ = _cuenta(HISTORIA)
    assert next(p for p in puntos if p.nombre == "Lateralidad").resultado == "Correcto"

    evolucion = "EVOLUCION MEDICA\nSE SOLICITA RADIOGRAFIA DE PIERNA DERECHA DE CONTROL\nMedico: Dr. Ficticio Registro medico 1"
    _, puntos, _ = _cuenta(HISTORIA, evolucion)
    lateralidad = next(p for p in puntos if p.nombre == "Lateralidad")
    assert lateralidad.resultado == "Error"
    assert "folio 2" in lateralidad.folios


RUNT_AUTOMOTORES = """Consulta Automotores
PLACA DEL VEHÍCULO: ABC12D
credit_card Póliza SOAT
Número de póliza Fecha expedición Fecha inicio de vigencia Fecha fin de vigencia Entidad expide SOAT Código tarifa Estado
ASEGURADORA FICTICIA S.A.
11112222 30/12/2025 01/01/2026 31/12/2026 120 VIGENTE
"""


def test_runt_consulta_automotores_con_vigencia_en_tabla():
    assert clasificar_texto(RUNT_AUTOMOTORES) == "Consulta RUNT"
    datos = {c: v for c, v, _ in formularios.leer_runt(RUNT_AUTOMOTORES)}
    assert datos["administrativo.numero_poliza"] == "11112222"
    assert datos["accidente.placa"] == "ABC12D"
    assert leer_fecha(datos["administrativo.vigencia_poliza_desde"]) == date(2026, 1, 1)
    assert leer_fecha(datos["administrativo.vigencia_poliza_hasta"]) == date(2026, 12, 31)


def test_hoja_en_blanco_no_es_folio_sin_leer():
    cuenta, _, texto = _cuenta(HISTORIA, None, generadores.SOLO_IMAGEN)
    assert [f.numero for f in cuenta.folios_en_blanco()] == [2]
    assert [f.numero for f in cuenta.folios_sin_texto()] == [3]  # La imagen sí es un escaneo sin leer
    assert "Folios en blanco (sin contenido): folio 2." in texto


def test_placa_con_confusion_en_la_ultima_letra_queda_para_revisar():
    soat = SOAT_TABLA.replace("ABC12D", "ABC120")  # Moto ABC12D leída como ABC120 (D/0 no es confusión)
    _, puntos, _ = _cuenta(FURIPS_TABLA, soat)
    assert next(p for p in puntos if p.nombre.startswith("Placa")).resultado == "Error"
    furips_moto = FURIPS_TABLA.replace("ABC12D", "EMA87I")
    soat_moto = SOAT_TABLA.replace("ABC12D", "EMA871")  # I final leída como 1
    _, puntos, _ = _cuenta(furips_moto, soat_moto)
    assert next(p for p in puntos if p.nombre.startswith("Placa")).resultado == "Revisar"


def test_placa_con_confusion_i_1_queda_para_revisar():
    soat = SOAT_TABLA.replace("ABC12D", "A8C12D")  # 8 por B: posible error de lectura
    _, puntos, _ = _cuenta(FURIPS_TABLA, soat)
    placa = next(p for p in puntos if p.nombre.startswith("Placa"))
    assert placa.resultado == "Revisar"
