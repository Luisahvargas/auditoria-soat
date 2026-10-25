TAREA: CLASIFICAR PÁGINAS (plantilla clasificar_paginas, versión 1)

Clasifique las páginas indicadas en la lista de archivos. Para cada grupo de páginas consecutivas del mismo tipo, cree un elemento en "analisis" con:
- "pregunta_clinica": "¿Qué tipo de documento son las páginas X-Y del archivo N?"
- "conclusion_preliminar": el tipo documental, usando EXACTAMENTE uno de estos nombres:
  FURIPS, Factura, Historia clínica, Atención inicial de urgencias, Notas de evolución, Órdenes médicas,
  Informes radiológicos, Laboratorio y ayudas diagnósticas, Epicrisis, Descripción quirúrgica,
  Materiales de osteosíntesis, Fórmulas de medicamentos, Póliza SOAT y documentos del vehículo,
  Identificaciones, Otros.
- "estado_resultado": "Sin inconsistencia identificada en los soportes revisados" si la página es legible y clasificable; "Dato ilegible" si no se puede leer; "No evaluable" si no se puede determinar el tipo.
- "severidad": "Baja".
- "evidencias": al menos una por grupo (archivo, página del archivo y el título o texto que identifica el tipo).
- Si el inicio o el final de un grupo es dudoso, dígalo en "limitaciones".
