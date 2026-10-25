"""Catálogos fijos del sistema (estados, severidades, orígenes).

Se definen en un solo lugar para que la interfaz, las reglas, la IA y las
exportaciones usen exactamente los mismos textos.
"""

# --- Estados de resultado de un hallazgo (CLAUDE.md, principio 3) ---
CONTRADICCION = "Contradicción documental"
POSIBLE_INCONSISTENCIA = "Posible inconsistencia"
FALTANTE = "Dato o documento faltante"
ILEGIBLE = "Dato ilegible"
NO_APLICA = "No aplica"
NO_EVALUABLE = "No evaluable"
SIN_INCONSISTENCIA = "Sin inconsistencia identificada en los soportes revisados"

ESTADOS_RESULTADO = (
    CONTRADICCION,
    POSIBLE_INCONSISTENCIA,
    FALTANTE,
    ILEGIBLE,
    NO_APLICA,
    NO_EVALUABLE,
    SIN_INCONSISTENCIA,
)

# Principio 12: por defecto solo se muestra al auditor lo que requiere su atención.
ESTADOS_QUE_REQUIEREN_ATENCION = (CONTRADICCION, POSIBLE_INCONSISTENCIA, FALTANTE, ILEGIBLE)

# --- Severidad ---
SEVERIDADES = ("Alta", "Media", "Baja")

# --- Origen del resultado (principio 10) ---
ORIGEN_REGLA = "Regla automática"
ORIGEN_IA = "Sugerencia de IA"
ORIGEN_AUDITOR = "Conclusión del auditor"
ORIGENES = (ORIGEN_REGLA, ORIGEN_IA, ORIGEN_AUDITOR)

# --- Revisión humana de un hallazgo ---
REVISION_PENDIENTE = "Pendiente de revisión humana"
REVISION_CONFIRMADO = "Confirmado por el auditor"
REVISION_DESCARTADO = "Descartado por el auditor"
REVISION_MODIFICADO = "Modificado por el auditor"
ESTADOS_REVISION = (REVISION_PENDIENTE, REVISION_CONFIRMADO, REVISION_DESCARTADO, REVISION_MODIFICADO)

# --- Procesamiento de documentos ---
PROC_PENDIENTE = "Pendiente"
PROC_EN_CURSO = "En procesamiento"
PROC_PROCESADO = "Procesado"
PROC_REQUIERE_REVISION = "Requiere revisión"
PROC_ERROR = "Error de procesamiento"
ESTADOS_PROCESAMIENTO = (PROC_PENDIENTE, PROC_EN_CURSO, PROC_PROCESADO, PROC_REQUIERE_REVISION, PROC_ERROR)

# --- Métodos de extracción de un dato ---
METODOS_EXTRACCION = ("XML", "RIPS", "Texto PDF", "OCR", "IA", "Manual")

# --- Estados de validación de un dato de la ficha ---
VALIDACION_PENDIENTE = "Pendiente de validación"
VALIDACION_VALIDADO = "Validado por el auditor"
VALIDACION_CORREGIDO = "Corregido por el auditor"
VALIDACION_DESCARTADO = "Descartado por el auditor"

# --- Legibilidad de una página ---
LEGIBILIDAD_SIN_EVALUAR = "Sin evaluar"
LEGIBLE = "Legible"
NO_LEGIBLE = "Ilegible"

# --- Estado de la auditoría ---
AUDITORIA_ABIERTA = "Abierta"
AUDITORIA_FINALIZADA = "Finalizada"

# Texto obligatorio cuando una regla depende de normas no verificadas (principio 7).
PENDIENTE_VALIDACION = "Pendiente de validación"
