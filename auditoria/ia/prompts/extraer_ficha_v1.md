TAREA: EXTRAER DATOS DE LA FICHA MAESTRA DESDE PÁGINAS ESCANEADAS (plantilla extraer_ficha, versión 1)

Lea las páginas indicadas (no tienen texto seleccionable) y extraiga, solo si aparecen, estos datos:
- Paciente: nombres, tipo y número de identificación, fecha de nacimiento, edad registrada, sexo, teléfono.
- Accidente: fecha y hora, dirección, municipio, departamento, zona, relato, calidad del accidentado, placa y tipo de vehículo.
- Administrativos: número de FURIPS o radicado, número y fecha de factura, número y vigencia de póliza, aseguradora, propietario y conductor (nombre e identificación), prestador y NIT.
- Clínicos: motivo de consulta, hallazgos, diagnósticos (con código CIE-10 si aparece), procedimientos, exámenes, medicamentos, fechas de atención, ingreso y egreso.

Cree un elemento en "analisis" por cada dato encontrado:
- "pregunta_clinica": el nombre del dato (por ejemplo "Fecha de nacimiento del paciente").
- "conclusion_preliminar": el valor exactamente como aparece en el documento.
- "estado_resultado": "Sin inconsistencia identificada en los soportes revisados" si se lee con claridad; "Dato ilegible" si se ve pero no se lee con certeza.
- Si el mismo dato aparece con valores distintos en páginas distintas, cree un elemento con "Posible inconsistencia" que cite ambas páginas y liste los valores en "informacion_contradictoria".
- "severidad": "Baja" salvo inconsistencias (use "Media" o "Alta" según su efecto sobre la reclamación).
- No adivine ni complete datos parcialmente legibles.
