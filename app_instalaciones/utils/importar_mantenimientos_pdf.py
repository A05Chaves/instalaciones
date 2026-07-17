import re
from datetime import datetime
from decimal import Decimal

from pypdf import PdfReader
from django.db import transaction

from app_instalaciones.models import Mantenimiento, Tecnico, CuadroInsta


SERVICIOS_MAP = {
    "MANTENIMIENTO CORRECTIVO": "MANTENIMIENTO CORRECTIVO",
    "MANTENIMIENTO PREVENTIVO": "MANTENIMIENTO PREVENTIVO",
    "INSTALACION": "INSTALACION",
    "INSTALACIÓN": "INSTALACION",
    "CCTV": "CCTV",
    "OTRO SERVICIO": "OTRO SERVICIO",
}


FALLAS_MAP = {
    "FALLO DE COMUNICACION": "F.COMUNICACION",
    "FALLO DE COMUNICACIÓN": "F.COMUNICACION",
    "FALLA COMUNICACION": "F.COMUNICACION",
    "FALLA COMUNICACIÓN": "F.COMUNICACION",

    "FALLO DE CORRIENTE": "F.CORRIENTE",
    "FALLA DE CORRIENTE": "F.CORRIENTE",

    "ACTIVACION": "ACTIVACION",
    "ACTIVACIÓN": "ACTIVACION",

    "PROGRAMACION": "PROGRAMACION",
    "PROGRAMACIÓN": "PROGRAMACION",

    "ACTUALIZACION DATOS": "ACT.DATOS",
    "ACTUALIZACIÓN DATOS": "ACT.DATOS",

    "FALLOS EQUIPOS": "FALLOS EQUIPOS",
    "CCTV": "CCTV",
    "OTRO SERVICIO": "OTRO SERVICIO",
    "INSTALACION": "INSTALACION",
    "INSTALACIÓN": "INSTALACION",
    "MANTO PREVENTIVO": "MANTO PREVENTIVO",
    "MANTENIMIENTO PREVENTIVO": "MANTO PREVENTIVO",
}


def limpiar_texto(valor):
    if not valor:
        return ""
    return re.sub(r"\s+", " ", valor).strip()


def buscar_regex(patron, texto, flags=re.IGNORECASE | re.DOTALL):
    match = re.search(patron, texto, flags)
    if not match:
        return ""
    return limpiar_texto(match.group(1))


# AGREGADO DESPUES

PATRON_TRABAJOS = (
    r"FALLA\s+(?:DE\s+)?COMUNICACI[ÓO]N"
    r"|FALLOS?\s+EQUIPOS?"
    r"|ACTIVACI[ÓO]N"
    r"|PROGRAMAC\s*I[ÓO]N"
    r"|ACTUALIZACI[ÓO]N\s+DATOS"
    r"|CCTV"
    r"|OTRO\s+SERVICIO"
    r"|MANTO\s+PREVENTIVO"
    r"|MANTENIMIENTO\s+PREVENTIVO"
    r"|INSTALACI[ÓO]N"
)


def extraer_trabajo_pdf(texto):
    """
    Obtiene el valor de la columna Trabajo del PDF:
    CCTV, ACTIVACION, FALLOS EQUIPOS, etc.
    """

    match = re.search(
        rf"\b({PATRON_TRABAJOS})\b"
        rf"\s+(?:ASIGNADO|FINALIZADA|FINALIZADO|PENDIENTE)",
        texto,
        re.IGNORECASE
    )

    if not match:
        return ""

    return limpiar_texto(match.group(1))


def extraer_descripcion_pdf(texto):
    """
    Obtiene únicamente la descripción reportada del servicio,
    sin incluir el encabezado del ticket.
    """

    match = re.search(
        r"Etapa\s+Tecnico\s+(.*?)"
        r"(?=\s+(?:DATOS\s+ACTA|Fecha\s+Inicio\s*:|Codigo\s+Acta\s*:|Creado\s+por:))",
        texto,
        re.IGNORECASE | re.DOTALL
    )

    if not match:
        return ""

    descripcion = limpiar_texto(match.group(1))

    # Quitar Trabajo + Estado cuando aparecen al final
    descripcion = re.sub(
        rf"\s+(?:{PATRON_TRABAJOS})"
        rf"\s+(?:ASIGNADO|FINALIZADA|FINALIZADO|PENDIENTE)\s*$",
        "",
        descripcion,
        flags=re.IGNORECASE
    )

    # Quitar textos repetidos del formato
    descripcion = re.sub(
        r"\s*Seguridad\s+del\s+sur\s+S\.?\s*A\.?\s*$",
        "",
        descripcion,
        flags=re.IGNORECASE
    )

    return limpiar_texto(descripcion)


def extraer_trabajo_y_descripcion(texto):
    """Extrae el tipo de trabajo y la descripción sin mezclar encabezados."""
    return extraer_trabajo_pdf(texto), extraer_descripcion_pdf(texto)


def normalizar_servicio(valor):
    valor = limpiar_texto(valor).upper()

    for clave, servicio in SERVICIOS_MAP.items():
        if clave in valor:
            return servicio

    return "OTRO SERVICIO"


def normalizar_falla(valor):
    valor = limpiar_texto(valor).upper()

    for clave, falla in FALLAS_MAP.items():
        if clave in valor:
            return falla

    if valor:
        return "OTRO"

    return ""


def convertir_fecha_hora(valor):
    valor = limpiar_texto(valor)

    if not valor:
        return None

    try:
        return datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def calcular_horas(fecha_inicio, fecha_fin):
    if not fecha_inicio or not fecha_fin:
        return None

    diferencia = fecha_fin - fecha_inicio

    if diferencia.total_seconds() <= 0:
        return None

    return Decimal(str(round(diferencia.total_seconds() / 3600, 2)))


def extraer_mantenimiento_desde_texto(texto):
    numero_ticket = buscar_regex(r"Orden Nro\.\s*(\d+)", texto)
    estado_ticket = buscar_regex(r"Estado:\s*([A-Za-zÁÉÍÓÚáéíóúñÑ ]+)", texto)

    codigo = buscar_regex(r"Codigo cliente:\s*(\d+)", texto)
    if not codigo:
        codigo = buscar_regex(r"Abonado:\s*(\d+)", texto)

    cliente = buscar_regex(
        r"Nombres cliente:\s*(.*?)\s+Direccion cliente:",
        texto
    )

    if not cliente:
        cliente = buscar_regex(
            r"Nombre:\s*(.*?)\s+Orden Nro\.",
            texto
        )

    direccion = buscar_regex(
        r"Direccion cliente:\s*(.*?)\s+INFORMACIÓN DEL PROBLEMA",
        texto
    )

    if not direccion:
        direccion = buscar_regex(
            r"Dirección:\s*(?:Teléfono.*?Celular:)?\s*(.*?)\s+Estado:",
            texto
        )

    tecnico_nombre = buscar_regex(
        r"Tecnico\s*:\s*(.*?)\s+(?:MOTIVO VISITA|DATOS COTIZACIÓN|Cotizacion:|Codigo Acta)",
        texto
    )

    tipo_servicio_pdf = buscar_regex(
        r"Motivo visita:\s*(.*?)\s+(?:Mantenimiento correctivo:|CCTV:|DATOS DEL CLIENTE)",
        texto
    )

    tipo_falla_pdf, observacion = extraer_trabajo_y_descripcion(texto)

    fecha_inicio_txt = buscar_regex(
        r"Fecha Inicio\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
        texto
    )

    fecha_fin_txt = buscar_regex(
        r"Fecha Fin\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
        texto
    )

    codigo_acta = buscar_regex(r"Codigo Acta\s*:\s*([A-Za-z0-9\-]+)", texto)

    problema_solucionado = buscar_regex(
        r"Problema solucionado:\s*(SI|NO)",
        texto
    )

    cotizacion = buscar_regex(
        r"Cotizacion:\s*(SI|NO)",
        texto
    )

    # observacion = extraer_descripcion_pdf(texto)

    pendiente = buscar_regex(
        r"Observaciones:\s*(.*?)(?:DATOS COTIZACIÓN|Cotizacion:|Trabajo realizado:|Creado por:)",
        texto
    )

    omt = buscar_regex(
        r"OMT:\s*(.*?)\s+(?:Georreferencia final|Fecha Fin|Creado por:)",
        texto
    )

    fecha_inicio = convertir_fecha_hora(fecha_inicio_txt)
    fecha_fin = convertir_fecha_hora(fecha_fin_txt)

    tipo_servicio = normalizar_servicio(tipo_servicio_pdf)
    tipo_falla = normalizar_falla(tipo_falla_pdf)

    horas = calcular_horas(fecha_inicio, fecha_fin)

    return {
        "numero_ticket": numero_ticket,
        "estado_ticket": limpiar_texto(estado_ticket).upper(),
        "codigo": codigo,
        "cliente": cliente,
        "direccion": direccion,
        "tecnico_nombre": tecnico_nombre,
        "tipo_servicio": tipo_servicio,
        "tipo_falla": tipo_falla,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "hora_entrada": fecha_inicio.time() if fecha_inicio else None,
        "hora_salida": fecha_fin.time() if fecha_fin else None,
        "horas": horas,
        "realizado": fecha_fin.date() if fecha_fin else None,
        "codigo_acta": codigo_acta,
        "problema_solucionado": problema_solucionado.upper() if problema_solucionado else "",
        "cotizacion": cotizacion.upper() if cotizacion else "",
        "observacion": observacion,
        "pendiente": pendiente,
        "omt": omt,
    }


def analizar_pdf_mantenimientos(archivo_pdf):
    reader = PdfReader(archivo_pdf)

    resultados = []

    for indice, page in enumerate(reader.pages, start=1):
        texto = page.extract_text() or ""
        data = extraer_mantenimiento_desde_texto(texto)

        advertencias = []

        if not data["numero_ticket"]:
            advertencias.append("No se encontró número de ticket.")

        if data["numero_ticket"] and Mantenimiento.objects.filter(
            numero_ticket=data["numero_ticket"]
        ).exists():
            advertencias.append("Ticket ya existe en la base de datos.")

        tecnico = None
        if data["tecnico_nombre"]:
            tecnico = Tecnico.objects.filter(
                nombre__icontains=data["tecnico_nombre"]
            ).first()

            if not tecnico:
                advertencias.append(
                    f"Técnico no encontrado: {data['tecnico_nombre']}"
                )
        else:
            advertencias.append("No se encontró técnico.")

        instalacion = None
        if data["codigo"]:
            instalacion = CuadroInsta.objects.filter(
                codigo__iexact=data["codigo"]
            ).first()

            if instalacion:
                if not data["cliente"]:
                    data["cliente"] = instalacion.cliente or ""

                if not data["direccion"]:
                    data["direccion"] = instalacion.direccion or ""

                data["ciudad"] = instalacion.ciudad or ""
            else:
                data["ciudad"] = ""
        else:
            data["ciudad"] = ""
            advertencias.append("No se encontró código.")

        data["tecnico_id"] = tecnico.id if tecnico else None

        resultados.append({
            "pagina": indice,
            "data": data,
            "advertencias": advertencias,
            "importable": bool(data["numero_ticket"]) and "Ticket ya existe en la base de datos." not in advertencias,
        })

    return resultados


@transaction.atomic
def importar_resultados_pdf(resultados, usuario):
    creados = 0
    repetidos = 0
    errores = 0

    for item in resultados:
        data = item["data"]

        if not data.get("numero_ticket"):
            errores += 1
            continue

        if Mantenimiento.objects.filter(
            numero_ticket=data["numero_ticket"]
        ).exists():
            repetidos += 1
            continue

        Mantenimiento.objects.create(
            numero_ticket=data["numero_ticket"],
            estado_ticket=data["estado_ticket"],
            codigo=data["codigo"],
            cliente=data["cliente"] or "SIN CLIENTE",
            ciudad=data.get("ciudad", ""),
            direccion=data["direccion"] or "",
            tipo_servicio=data["tipo_servicio"],
            tipo_falla=data["tipo_falla"] or None,
            tecnico_id=data["tecnico_id"],
            fecha_inicio=data["fecha_inicio"],
            fecha_fin=data["fecha_fin"],
            hora_entrada=data["hora_entrada"],
            hora_salida=data["hora_salida"],
            horas=data["horas"],
            orden="",
            realizado=data["realizado"],
            codigo_acta=data["codigo_acta"],
            problema_solucionado=data["problema_solucionado"],
            cotizacion=data["cotizacion"],
            observacion=data["observacion"],
            pendiente=data["pendiente"],
            omt=data["omt"],
            creado_por=usuario,
        )

        creados += 1

    return {
        "creados": creados,
        "repetidos": repetidos,
        "errores": errores,
    }


def preparar_resultados_para_session(resultados):
    for item in resultados:
        data = item["data"]

        for campo in ["fecha_inicio", "fecha_fin", "hora_entrada", "hora_salida", "realizado"]:
            valor = data.get(campo)
            if valor:
                data[campo] = valor.isoformat()

        if data.get("horas") is not None:
            data["horas"] = str(data["horas"])

    return resultados


def restaurar_resultados_desde_session(resultados):
    for item in resultados:
        data = item["data"]

        if data.get("fecha_inicio"):
            data["fecha_inicio"] = datetime.fromisoformat(data["fecha_inicio"])

        if data.get("fecha_fin"):
            data["fecha_fin"] = datetime.fromisoformat(data["fecha_fin"])

        if data.get("hora_entrada"):
            data["hora_entrada"] = datetime.fromisoformat(
                "2000-01-01T" + data["hora_entrada"]
            ).time()

        if data.get("hora_salida"):
            data["hora_salida"] = datetime.fromisoformat(
                "2000-01-01T" + data["hora_salida"]
            ).time()

        if data.get("realizado"):
            data["realizado"] = datetime.fromisoformat(
                data["realizado"]).date()

        if data.get("horas"):
            data["horas"] = Decimal(str(data["horas"]))

    return resultados
