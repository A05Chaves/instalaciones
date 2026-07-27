import re
import unicodedata
from datetime import datetime
from decimal import Decimal

from pypdf import PdfReader
from django.db import transaction
from django.utils import timezone

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
    "FALLA DE EQUIPO": "FALLOS EQUIPOS",
    "FALLA EQUIPO": "FALLOS EQUIPOS",
    "FALLO DE BATERIA": "FALLOS EQUIPOS",
    "FALLA DE BATERIA": "FALLOS EQUIPOS",
}


def limpiar_texto(valor):
    if not valor:
        return ""
    return re.sub(r"\s+", " ", valor).strip()


def normalizar_clave(valor):
    valor = limpiar_texto(valor).upper()
    return "".join(
        caracter for caracter in unicodedata.normalize("NFD", valor)
        if unicodedata.category(caracter) != "Mn"
    )


def buscar_regex(patron, texto, flags=re.IGNORECASE | re.DOTALL):
    match = re.search(patron, texto, flags)
    if not match:
        return ""
    return limpiar_texto(match.group(1))


# AGREGADO DESPUES

PATRON_TRABAJOS = (
    r"FALLA\s+(?:DE\s+)?COMUNICACI[ÓO]N"
    r"|FALL[AO]S?\s+(?:DE\s+)?EQUIPOS?"
    r"|FALL[AO]\s+DE\s+BATER[IÍ]A"
    r"|ACTIVACI[ÓO]N"
    r"|PROGRAMACI[ÓO]N"
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

    coincidencias = re.findall(
        rf"\b({PATRON_TRABAJOS})\b",
        texto,
        re.IGNORECASE,
    )

    if not coincidencias:
        return ""

    # El valor de la columna Trabajo suele ser la última coincidencia de la página.
    return limpiar_texto(coincidencias[-1])


def extraer_descripcion_pdf(texto):
    """
    Obtiene únicamente la descripción reportada del servicio,
    sin incluir el encabezado del ticket.
    """

    match = re.search(
        r"Etapa\s+Tecnico\s*(.*?)"
        rf"(?=\s+(?:(?:{PATRON_TRABAJOS})\s+)?(?:DATOS\s+ACTA|Creado\s+por:))",
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


def extraer_tecnico_pdf(texto):
    tecnico = buscar_regex(
        r"Tecnico\s*:\s*(.*?)(?=MOTIVO\s*VISITA)",
        texto,
    )
    if tecnico:
        return tecnico

    return ""


def normalizar_servicio(valor):
    valor = normalizar_clave(valor)

    for clave, servicio in SERVICIOS_MAP.items():
        if normalizar_clave(clave) in valor:
            return servicio

    trabajo = normalizar_clave(valor)
    if "PREVENTIVO" in trabajo:
        return "MANTENIMIENTO PREVENTIVO"
    if "INSTALACION" in trabajo:
        return "INSTALACION"
    if "CCTV" in trabajo:
        return "CCTV"
    if trabajo:
        return "MANTENIMIENTO CORRECTIVO"
    return "OTRO SERVICIO"


def normalizar_falla(valor):
    valor = normalizar_clave(valor)

    for clave, falla in FALLAS_MAP.items():
        if normalizar_clave(clave) in valor:
            return falla

    if valor:
        return "OTRO"

    return ""


def convertir_fecha_hora(valor):
    valor = limpiar_texto(valor)

    if not valor:
        return None

    valor = re.sub(
        r"(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2}:\d{2})",
        r"\1 \2",
        valor,
    )

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
    numero_ticket = buscar_regex(r"Orden\s+Nro\.?\s*:?[\s\r\n]*(\d+)", texto)
    estado_ticket = buscar_regex(
        r"\b(ASIGNADO|FINALIZADA|FINALIZADO|PENDIENTE|EN\s+SITIO)\s+Estado\s*:",
        texto,
    )
    estado_ticket = normalizar_clave(estado_ticket)

    codigo = buscar_regex(r"Codigo cliente:\s*(\d+)", texto)
    if not codigo:
        codigo = buscar_regex(r"Abonado:\s*(\d+)", texto)

    cliente = buscar_regex(
        r"Nombre\s*:\s*(.*?)\s+Orden\s+Nro\.?,?",
        texto,
    )

    direccion = buscar_regex(
        r"Celular\s*:\s*(.*?)\s+(?:Asignado|Finalizada|Finalizado|Pendiente)\s+Estado\s*:",
        texto,
    )

    tecnico_nombre = extraer_tecnico_pdf(texto)

    tipo_servicio_pdf = buscar_regex(
        r"Motivo\s+visita\s*:\s*(.*?)\s+(?:Mantenimiento\s+correctivo\s*:|CCTV\s*:|DATOS\s+DEL\s*CLIENTE)",
        texto
    )

    tipo_falla_pdf, descripcion = extraer_trabajo_y_descripcion(texto)

    trabajo_realizado = buscar_regex(
        rf"Trabajo\s+realizado\s*:\s*(.*?)(?=\s+(?:FIRMA\s+CLIENTE|M[ÁA]S\s+DETALLES|Georreferencia\s+final|Fecha\s+Fin|(?:{PATRON_TRABAJOS})\s+(?:FINALIZADA|FINALIZADO)|Creado\s+por:))",
        texto,
    )

    fecha_inicio_txt = buscar_regex(
        r"Fecha Inicio\s*:\s*(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2})",
        texto
    )

    fecha_fin_txt = buscar_regex(
        r"Fecha Fin\s*:\s*(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2})",
        texto
    )

    fecha_creado_txt = buscar_regex(
        r"\bCreado\s*:\s*(?:(?!Fecha\s+Visita|Materiales).){0,100}?"
        r"(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2})",
        texto
    )
    if not fecha_creado_txt:
        # En algunos PDF PyPDF ordena las columnas así:
        # "Creado por: ... 2026-07-06 18:06:11 Creado:".
        # La fecha sigue perteneciendo al campo Creado aunque la etiqueta quede
        # después de su valor en el texto extraído.
        fecha_creado_txt = buscar_regex(
            r"\bCreado\s+por\s*:"
            r"(?:(?!Fecha\s+Visita|Materiales).){0,300}?"
            r"(\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2})",
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
    fecha_creacion_servicio = convertir_fecha_hora(fecha_creado_txt)

    tipo_servicio = normalizar_servicio(tipo_servicio_pdf or tipo_falla_pdf)
    tipo_falla = normalizar_falla(tipo_falla_pdf)

    horas = calcular_horas(fecha_inicio, fecha_fin)

    return {
        "numero_ticket": numero_ticket,
        "estado_ticket": estado_ticket,
        "codigo": codigo,
        "cliente": cliente,
        "direccion": direccion,
        "tecnico_nombre": tecnico_nombre,
        "tipo_servicio": tipo_servicio,
        "tipo_falla": tipo_falla,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "fecha_creacion_servicio": fecha_creacion_servicio,
        "hora_entrada": fecha_inicio.time() if fecha_inicio else None,
        "hora_salida": fecha_fin.time() if fecha_fin else None,
        "horas": horas,
        "realizado": fecha_fin.date() if fecha_fin else None,
        "codigo_acta": codigo_acta,
        "problema_solucionado": problema_solucionado.upper() if problema_solucionado else "",
        "cotizacion": cotizacion.upper() if cotizacion else "",
        "observacion": trabajo_realizado or descripcion,
        "pendiente": pendiente or (
            descripcion
            if estado_ticket not in {"FINALIZADA", "FINALIZADO"}
            else ""
        ),
        "omt": omt,
    }


def analizar_pdf_mantenimientos(archivo_pdf, actualizar_existentes=False):
    reader = PdfReader(archivo_pdf)

    resultados = []
    tecnicos_por_clave = {
        normalizar_clave(tecnico.nombre).replace(" ", ""): tecnico
        for tecnico in Tecnico.objects.all()
    }

    for indice, page in enumerate(reader.pages, start=1):
        texto = page.extract_text() or ""
        data = extraer_mantenimiento_desde_texto(texto)

        # Algunos reportes ponen "Creado:" en una página de continuación
        # sin repetir el ticket. Esa fecha pertenece al último ticket leído.
        if not data["numero_ticket"]:
            fecha_continuacion = data.get("fecha_creacion_servicio")
            if fecha_continuacion:
                for resultado_anterior in reversed(resultados):
                    data_anterior = resultado_anterior["data"]
                    if data_anterior.get("numero_ticket"):
                        if not data_anterior.get("fecha_creacion_servicio"):
                            data_anterior["fecha_creacion_servicio"] = fecha_continuacion
                        break
            continue

        # El modo normal puede unir nombre y apellido cuando la columna es angosta.
        if data["tecnico_nombre"] and " " not in data["tecnico_nombre"]:
            texto_layout = page.extract_text(extraction_mode="layout") or ""
            tecnico_layout = extraer_tecnico_pdf(texto_layout)
            if tecnico_layout:
                data["tecnico_nombre"] = tecnico_layout

        advertencias = []

        if not data["numero_ticket"]:
            advertencias.append("No se encontró número de ticket.")

        ticket_existente = data["numero_ticket"] and Mantenimiento.objects.filter(
            numero_ticket=data["numero_ticket"]
        ).exists()
        if ticket_existente:
            if actualizar_existentes:
                advertencias.append(
                    "Ticket existente: se actualizará con los datos del PDF."
                )
            else:
                advertencias.append("Ticket ya existe en la base de datos.")

        tecnico = None
        if data["tecnico_nombre"]:
            clave_tecnico = normalizar_clave(
                data["tecnico_nombre"]
            ).replace(" ", "")
            tecnico = tecnicos_por_clave.get(clave_tecnico)

            if not tecnico:
                advertencias.append(
                    f"Se creará el técnico: {data['tecnico_nombre']}"
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
            "importable": bool(data["numero_ticket"]) and (
                actualizar_existentes or not ticket_existente
            ),
        })

    return resultados


@transaction.atomic
def importar_resultados_pdf(resultados, usuario, actualizar_existentes=False):
    creados = 0
    actualizados = 0
    repetidos = 0
    errores = 0

    for item in resultados:
        data = item["data"]

        if not data.get("numero_ticket"):
            errores += 1
            continue

        existente = Mantenimiento.objects.filter(
            numero_ticket=data["numero_ticket"]
        ).first()
        if existente and not actualizar_existentes:
            repetidos += 1
            continue
        if existente and existente.orden:
            repetidos += 1
            continue

        tecnico_id = data.get("tecnico_id")
        if not tecnico_id and data.get("tecnico_nombre"):
            nombre_tecnico = limpiar_texto(data["tecnico_nombre"])[:100]
            tecnico = Tecnico.objects.filter(
                nombre__iexact=nombre_tecnico
            ).first()
            if not tecnico:
                tecnico = Tecnico.objects.create(
                    nombre=nombre_tecnico
                )
            tecnico_id = tecnico.id

        fecha_creacion_servicio = (
            data.get("fecha_creacion_servicio") or timezone.now()
        )
        if timezone.is_naive(fecha_creacion_servicio):
            fecha_creacion_servicio = timezone.make_aware(
                fecha_creacion_servicio, timezone.get_current_timezone()
            )

        valores = {
            "estado_ticket": data["estado_ticket"],
            "codigo": data["codigo"],
            "cliente": data["cliente"] or "SIN CLIENTE",
            "ciudad": data.get("ciudad", ""),
            "direccion": data["direccion"] or "",
            "tipo_servicio": data["tipo_servicio"],
            "tipo_falla": data["tipo_falla"] or None,
            "tecnico_id": tecnico_id,
            "fecha_inicio": data["fecha_inicio"],
            "fecha_fin": data["fecha_fin"],
            "fecha_creacion_servicio": fecha_creacion_servicio,
            "hora_entrada": data["hora_entrada"],
            "hora_salida": data["hora_salida"],
            "horas": data["horas"],
            "realizado": data["realizado"],
            "codigo_acta": data["codigo_acta"],
            "problema_solucionado": data["problema_solucionado"],
            "cotizacion": data["cotizacion"],
            "observacion": data["observacion"],
            "pendiente": data["pendiente"],
            "omt": data["omt"],
        }

        # PostgreSQL aplica estrictamente max_length; algunos PDF contienen
        # columnas unidas o texto residual más largo que el campo del modelo.
        for campo, valor in valores.items():
            if isinstance(valor, str):
                nombre_campo = campo[:-3] if campo.endswith("_id") else campo
                max_length = Mantenimiento._meta.get_field(nombre_campo).max_length
                if max_length:
                    valores[campo] = valor[:max_length]

        if existente:
            for campo, valor in valores.items():
                setattr(existente, campo, valor)
            existente.save()
            actualizados += 1
        else:
            Mantenimiento.objects.create(
                numero_ticket=data["numero_ticket"],
                orden="",
                creado_por=usuario,
                **valores,
            )
            creados += 1

    return {
        "creados": creados,
        "actualizados": actualizados,
        "repetidos": repetidos,
        "errores": errores,
    }


def preparar_resultados_para_session(resultados):
    for item in resultados:
        data = item["data"]

        for campo in ["fecha_creacion_servicio", "fecha_inicio", "fecha_fin", "hora_entrada", "hora_salida", "realizado"]:
            valor = data.get(campo)
            if valor:
                data[campo] = valor.isoformat()

        if data.get("horas") is not None:
            data["horas"] = str(data["horas"])

    return resultados


def restaurar_resultados_desde_session(resultados):
    for item in resultados:
        data = item["data"]

        if data.get("fecha_creacion_servicio"):
            data["fecha_creacion_servicio"] = datetime.fromisoformat(
                data["fecha_creacion_servicio"]
            )
            if timezone.is_naive(data["fecha_creacion_servicio"]):
                data["fecha_creacion_servicio"] = timezone.make_aware(
                    data["fecha_creacion_servicio"], timezone.get_current_timezone()
                )

        if data.get("fecha_inicio"):
            data["fecha_inicio"] = datetime.fromisoformat(data["fecha_inicio"])
            if timezone.is_naive(data["fecha_inicio"]):
                data["fecha_inicio"] = timezone.make_aware(
                    data["fecha_inicio"], timezone.get_current_timezone()
                )

        if data.get("fecha_fin"):
            data["fecha_fin"] = datetime.fromisoformat(data["fecha_fin"])
            if timezone.is_naive(data["fecha_fin"]):
                data["fecha_fin"] = timezone.make_aware(
                    data["fecha_fin"], timezone.get_current_timezone()
                )

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
