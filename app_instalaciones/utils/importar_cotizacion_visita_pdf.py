import re
import unicodedata
from datetime import datetime

from django.utils import timezone
from pypdf import PdfReader


MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _limpiar(valor):
    return re.sub(r"\s+", " ", valor or "").strip()


def _buscar(texto, patron):
    coincidencia = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
    return _limpiar(coincidencia.group(1)) if coincidencia else ""


def _fecha_espanol(valor):
    normalizado = unicodedata.normalize("NFKD", valor or "")
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c)).lower()
    coincidencia = re.search(
        r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4}).*?"
        r"(\d{1,2}):(\d{2})\s*(a\.?\s*m\.?|p\.?\s*m\.?)?",
        normalizado,
    )
    if not coincidencia:
        return None
    dia, mes_texto, anio, hora, minuto, periodo = coincidencia.groups()
    mes = MESES.get(mes_texto)
    if not mes:
        return None
    hora = int(hora)
    if periodo and periodo.replace(" ", "").startswith("p") and hora < 12:
        hora += 12
    if periodo and periodo.replace(" ", "").startswith("a") and hora == 12:
        hora = 0
    fecha = datetime(int(anio), mes, int(dia), hora, int(minuto))
    return timezone.make_aware(fecha, timezone.get_current_timezone())


def analizar_visita_tecnica_cotizacion(archivo_pdf):
    archivo_pdf.seek(0)
    try:
        reader = PdfReader(archivo_pdf)
    except Exception as error:
        raise ValueError("El archivo no es un PDF válido.") from error
    texto = "\n".join(page.extract_text() or "" for page in reader.pages)
    archivo_pdf.seek(0)
    if not texto.strip():
        raise ValueError("El PDF no contiene texto extraíble.")

    cotizacion = _buscar(texto, r"\bCOTIZACION\s*:\s*(SI|NO)\b")
    if cotizacion.upper() != "SI":
        raise ValueError("La orden no está marcada como solicitud de cotización.")

    fecha_texto = _buscar(texto, r"Fecha\s+de\s+env[ií]o\s*:\s*([^\n]+)")
    datos = {
        "registro": _buscar(texto, r"\bRegistro\s*:\s*#?\s*([A-Za-z0-9-]+)"),
        "fecha_orden": _fecha_espanol(fecha_texto),
        "tecnico_nombre": _buscar(texto, r"\bTECNICO\s*:\s*([^\n]+)"),
        "codigo": _buscar(texto, r"CODIGO\s+CLIENTE\s*:\s*([^\n]+)"),
        "cliente": _buscar(texto, r"NOMBRES?\s+CLIENTE\s*:\s*([^\n]+)"),
        "direccion": _buscar(texto, r"DIRECCION\s+CLIENTE\s*:\s*([^\n]+)"),
        "descripcion": _buscar(
            texto,
            r"Observacion\s+Cotizacion\s*:\s*(.*?)\s*DESCRIPCION\s+ACTIVIDAD\s+REALIZADA\s*:",
        ),
        "actividad_realizada": _buscar(
            texto,
            r"DESCRIPCION\s+ACTIVIDAD\s+REALIZADA\s*:\s*(.*?)\s*[¿?]?EQUIPOS\s+INSTALADOS",
        ),
        "telefono": _buscar(texto, r"Telefono\s*:\s*([^\n]+)"),
        "contacto": _buscar(texto, r"NOMBRE\s+CLIENTE\s*:\s*([^\n]+)"),
        "omt": _buscar(texto, r"\bOMT\s*:\s*([^\n]+)"),
    }
    obligatorios = ["registro", "codigo", "cliente", "direccion", "descripcion"]
    faltantes = [campo for campo in obligatorios if not datos[campo]]
    if faltantes:
        raise ValueError("No se encontraron estos campos: " + ", ".join(faltantes))
    return datos
