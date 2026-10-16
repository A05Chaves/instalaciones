import json
import re
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from django.forms.models import model_to_dict
from django.http import FileResponse, HttpResponse, JsonResponse
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from openpyxl import Workbook

from app_instalaciones.models.cuadroInstalaciones import (
    CuadroInsta,
    Ciudad,
    CorteIndicadorCotizacion,
    CotizacionServicioTecnico,
    DiaNoLaboralTecnico,
    Ejecutivo,
    Mantenimiento,
    JornadaLaboralTecnico,
    Tecnico,
    HistorialAsignacionMantenimiento,
    NotificacionTecnico,
    RotacionTecnicoDisponible,
    SeguimientoCotizacionTecnica,
)
from app_instalaciones.models.forms import MantenimientoForm
from app_instalaciones.models.auditoria import RegistroAuditoria

from app_instalaciones.utils.importar_mantenimientos_pdf import (
    analizar_pdf_mantenimientos,
    importar_resultados_pdf,
    normalizar_clave,
    preparar_resultados_para_session,
    restaurar_resultados_desde_session,
)
from app_instalaciones.utils.importar_mantenimientos_excel import analizar_excel_mantenimientos
from app_instalaciones.utils.importar_cotizacion_visita_pdf import (
    analizar_visita_tecnica_cotizacion,
)

# VISTAS PARA LA GESTIÓN DE USUARIOS


def pertenece_grupo(user, nombre_grupo):
    return user.groups.filter(name=nombre_grupo).exists()


def puede_editar_instalacion(user):
    return (
        user.is_superuser
        or pertenece_grupo(user, 'Administrador')
        or pertenece_grupo(user, 'Coordinador')
        or pertenece_grupo(user, 'Programador')
        or pertenece_grupo(user, 'Almacen')
        or pertenece_grupo(user, 'Facturacion')
    )


def puede_programar(user):
    return (
        user.is_superuser
        or user.groups.filter(name='Administrador').exists()
        or user.groups.filter(name='Coordinador').exists()
        or user.groups.filter(name='Programador').exists()
    )


def puede_alistar(user):
    return (
        user.is_superuser
        or pertenece_grupo(user, 'Administrador')
        or pertenece_grupo(user, 'Almacen')
    )


def puede_facturar(user):
    return (
        user.is_superuser
        or pertenece_grupo(user, 'Administrador')
        or pertenece_grupo(user, 'Facturacion')
    )


def puede_ver_dashboard(user):
    return (
        user.is_staff
        or puede_editar_instalacion(user)
    )


def puede_ver(user):
    return user.is_authenticated


def puede_ver_instalaciones(user):
    return (
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name__in={
            "Administrador", "Coordinador", "Programador", "Almacen",
            "Facturacion", "Visor",
        }).exists()
    )


def puede_gestionar_mantenimientos(user):
    return (
        user.is_superuser
        or pertenece_grupo(user, "Administrador")
        or pertenece_grupo(user, "Coordinador")
    )


def puede_ver_mantenimientos(user):
    return (
        puede_gestionar_mantenimientos(user)
        or pertenece_grupo(user, "Monitoreo")
        or pertenece_grupo(user, "Administrador Monitoreo")
    )


def puede_registrar_orden_omt(user):
    return (
        user.is_superuser
        or pertenece_grupo(user, "Administrador")
        or pertenece_grupo(user, "Coordinador")
        or pertenece_grupo(user, "Monitoreo")
        or pertenece_grupo(user, "Administrador Monitoreo")
    )


def puede_configurar_usuarios(user):
    return user.is_superuser or pertenece_grupo(user, "Administrador Monitoreo")


def puede_gestionar_cotizaciones(user):
    return user.is_superuser or pertenece_grupo(user, "Cotizaciones")


def puede_eliminar_mantenimientos(user):
    return user.is_superuser or pertenece_grupo(user, "Administrador")


def es_usuario_solo_tecnico(user):
    """Indica si el portal móvil debe ser el inicio principal del usuario."""
    if not _tecnico_del_usuario(user):
        return False
    if user.is_superuser:
        return False
    roles_administrativos = {
        "Administrador", "Coordinador", "Programador", "Almacen",
        "Facturacion", "Visor", "Cotizaciones", "Monitoreo",
        "Administrador Monitoreo",
    }
    return not user.groups.filter(name__in=roles_administrativos).exists()


def registrar_cambio_tecnico(mantenimiento, anterior, nuevo, usuario):
    if anterior == nuevo:
        return
    HistorialAsignacionMantenimiento.objects.create(
        mantenimiento=mantenimiento,
        tecnico_anterior=anterior,
        tecnico_nuevo=nuevo,
        cambiado_por=usuario,
    )
    if nuevo and not mantenimiento.fecha_programada:
        mantenimiento.fecha_programada = timezone.localdate()
        mantenimiento.save(update_fields=["fecha_programada"])
    referencia = mantenimiento.numero_ticket or mantenimiento.codigo
    if anterior:
        NotificacionTecnico.objects.create(
            tecnico=anterior,
            mantenimiento=mantenimiento,
            tipo="RETIRADO",
            mensaje=f"El servicio {referencia} fue reasignado a otro técnico.",
        )
    if nuevo:
        tipo = "REASIGNACION" if anterior else "ASIGNACION"
        NotificacionTecnico.objects.create(
            tecnico=nuevo,
            mantenimiento=mantenimiento,
            tipo=tipo,
            mensaje=f"Tienes un servicio asignado: {referencia} - {mantenimiento.cliente}.",
        )

# MÉTODO PARA INGRESAR AL MÓDULO DE REGISTRO DE INSTALACIONES


def login(request):
    if request.user.is_authenticated:
        return redirect('portal_tecnico' if es_usuario_solo_tecnico(request.user) else 'home')

    contexto = {}

    if request.method == "GET":
        greetings = request.GET.get('greetings')
        print("greetings: {}".format(greetings))
        if greetings == "true":
            contexto['mensaje'] = "¡Cuenta creada correctamente! Autentícate para continuar."
    else:
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('portal_tecnico' if es_usuario_solo_tecnico(user) else 'home')
        else:
            contexto['error'] = "Usuario o contraseña incorrectos. Intenta nuevamente."

    return render(request, "users/login.html", contexto)

# METODO PARA REGISTRAR USUARIOS A LA BASE DE DATOS


def registrate(request):
    contexto = {}

    if request.method == "POST":
        nombre = request.POST.get('nombre')
        apellido = request.POST.get('apellido')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        # Verificación: contraseñas coinciden
        if password != confirm_password:
            contexto['error'] = "Las contraseñas no coinciden."
            contexto.update({'nombre': nombre, 'apellido': apellido,
                            'username': username, 'email': email})
            return render(request, "users/registrate.html", contexto)

        # Verificación: seguridad de la contraseña
        if len(password) < 8:
            contexto['error'] = "La contraseña debe tener al menos 8 caracteres."
        elif not re.search(r"[A-Za-z]", password):
            contexto['error'] = "La contraseña debe incluir al menos una letra."
        elif not re.search(r"\d", password):
            contexto['error'] = "La contraseña debe incluir al menos un número."
        # elif not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        #     contexto['error'] = "La contraseña debe incluir al menos un carácter especial."  # opcional

        if 'error' in contexto:
            contexto.update({'nombre': nombre, 'apellido': apellido,
                            'username': username, 'email': email})
            return render(request, "users/registrate.html", contexto)

        # Verificación: usuario duplicado
        if User.objects.filter(username=username).exists():
            contexto['error'] = "El usuario ingresado ya existe."
            contexto.update({'nombre': nombre, 'apellido': apellido,
                            'username': username, 'email': email})
            return render(request, "users/registrate.html", contexto)

        # Crear usuario
        user = User.objects.create_user(
            username, email, password, first_name=nombre, last_name=apellido)

        grupo_visores, _ = Group.objects.get_or_create(name='Visor')
        user.groups.add(grupo_visores)

        return redirect(f"{reverse('login')}?greetings=true")

    return render(request, "users/registrate.html", contexto)

# METODO PARA SALIR COMO USUARIO REGISTRADO


def logout(request):
    auth_logout(request)
    return redirect(reverse('home'))


@login_required(login_url="login")
@require_POST
def renovar_sesion(request):
    """Renueva la sesión únicamente después de actividad real del usuario."""
    request.session.modified = True
    return JsonResponse({
        "ok": True,
        "vence_en_segundos": request.session.get_expiry_age(),
    })


# NUEVO ARREGLO LISTA DE MANTENIMIENTOS

FALLAS_PRIORITARIAS_MANTENIMIENTO = {"F.COMUNICACION", "F.CORRIENTE", "ACTIVACION"}


def indicadores_atencion_mantenimientos(fecha_desde=None, fecha_hasta=None, ciudades=None):
    """Calcula una única fuente para alertas, promedios y efectividad."""
    hoy = timezone.localdate()
    ahora = timezone.now()
    consulta_servicios = Mantenimiento.objects.select_related("tecnico").filter(
        fecha_programada__isnull=False
    )
    if fecha_desde and fecha_hasta:
        consulta_servicios = consulta_servicios.filter(
            fecha_programada__range=(fecha_desde, fecha_hasta)
        )
    if ciudades:
        consulta_servicios = consulta_servicios.filter(ciudad__in=ciudades)
    servicios = list(consulta_servicios)
    resumen_tecnicos = {}
    tiempos_grupo = []
    cumplidos_grupo = 0
    realizados_grupo = 0
    programados_prioritarios = programados_otros = 0
    cumplidos_prioritarios = cumplidos_otros = 0
    pendientes_prioritarios = pendientes_otros = 0
    vencidos_prioritarios = vencidos_otros = 0
    detalle_prioritarios = []
    detalle_otros = []
    detalle_pendientes = []
    detalle_realizados = []

    def fecha_programacion(servicio):
        return timezone.make_aware(
            datetime.combine(servicio.fecha_programada, datetime.min.time()),
            timezone.get_current_timezone(),
        )

    def fecha_atencion(servicio):
        if servicio.inicio_tecnico:
            return servicio.inicio_tecnico
        if servicio.realizado and servicio.hora_entrada:
            return timezone.make_aware(
                datetime.combine(servicio.realizado, servicio.hora_entrada),
                timezone.get_current_timezone(),
            )
        if servicio.fecha_inicio:
            return servicio.fecha_inicio
        if servicio.realizado:
            return timezone.make_aware(
                datetime.combine(servicio.realizado, datetime.min.time()),
                timezone.get_current_timezone(),
            )
        return None

    for servicio in servicios:
        prioritario = servicio.tipo_falla in FALLAS_PRIORITARIAS_MANTENIMIENTO
        if prioritario:
            programados_prioritarios += 1
        else:
            programados_otros += 1
        meta_horas = 24 if prioritario else 48
        tecnico_habilitado = bool(
            servicio.tecnico and servicio.tecnico.incluir_indicadores
        )
        tecnico_nombre = servicio.tecnico.nombre if servicio.tecnico else "SIN ASIGNAR"
        fila = None
        if tecnico_habilitado:
            fila = resumen_tecnicos.setdefault(tecnico_nombre, {
                "tecnico": tecnico_nombre, "prioritarios_pendientes": 0,
                "otros_pendientes": 0, "tiempos": [], "cumplidos": 0,
                "asignados": 0, "realizados": 0,
            })
            fila["asignados"] += 1
        inicio_medicion = fecha_programacion(servicio)
        atendido = fecha_atencion(servicio)
        # El estado operativo es la fuente de verdad. Una fecha ``realizado``
        # aislada no debe sacar un servicio pendiente de las alertas.
        finalizado = servicio.estado_operativo in {"PENDIENTE_OMT", "FINALIZADO"}
        if finalizado:
            realizados_grupo += 1
        if finalizado and fila:
            fila["realizados"] += 1

        horas_atencion = None
        if atendido:
            if timezone.is_naive(atendido):
                atendido = timezone.make_aware(atendido, timezone.get_current_timezone())
            horas_atencion = max(0, (atendido - inicio_medicion).total_seconds() / 3600)

        detalle = {
            "servicio": servicio,
            "prioritario": prioritario,
            "meta_horas": meta_horas,
            "atendido": atendido,
            "horas_atencion": round(horas_atencion, 1) if horas_atencion is not None else None,
            "cumple": bool(finalizado and horas_atencion is not None and horas_atencion <= meta_horas),
            "finalizado": finalizado,
        }
        (detalle_prioritarios if prioritario else detalle_otros).append(detalle)
        if finalizado:
            detalle_realizados.append(detalle)
        elif servicio.fecha_programada <= hoy:
            detalle_pendientes.append(detalle)

        if not finalizado and servicio.fecha_programada <= hoy:
            horas_pendiente = max(0, (ahora - inicio_medicion).total_seconds() / 3600)
            if prioritario:
                pendientes_prioritarios += 1
                if fila:
                    fila["prioritarios_pendientes"] += 1
                vencidos_prioritarios += int(horas_pendiente > meta_horas)
            else:
                pendientes_otros += 1
                if fila:
                    fila["otros_pendientes"] += 1
                vencidos_otros += int(horas_pendiente > meta_horas)
        elif finalizado and atendido:
            tiempos_grupo.append(horas_atencion)
            if fila:
                fila["tiempos"].append(horas_atencion)
            if horas_atencion <= meta_horas:
                cumplidos_grupo += 1
                if fila:
                    fila["cumplidos"] += 1
                if prioritario:
                    cumplidos_prioritarios += 1
                else:
                    cumplidos_otros += 1

    indicadores_por_tecnico = []
    for fila in resumen_tecnicos.values():
        tiempos = fila.pop("tiempos")
        total_atendidos = len(tiempos)
        fila["promedio_horas"] = round(sum(tiempos) / total_atendidos, 1) if tiempos else None
        fila["atendidos"] = total_atendidos
        fila["pendientes"] = fila["prioritarios_pendientes"] + fila["otros_pendientes"]
        fila["efectividad"] = round(
            fila["realizados"] * 100 / fila["asignados"], 1
        ) if fila["asignados"] else None
        if total_atendidos or fila["prioritarios_pendientes"] or fila["otros_pendientes"]:
            indicadores_por_tecnico.append(fila)
    indicadores_por_tecnico.sort(key=lambda item: item["tecnico"])

    return {
        "pendientes_fecha": pendientes_prioritarios + pendientes_otros,
        "pendientes_prioritarios": pendientes_prioritarios,
        "pendientes_otros": pendientes_otros,
        "vencidos_prioritarios": vencidos_prioritarios,
        "vencidos_otros": vencidos_otros,
        "pendientes_sin_programar": Mantenimiento.objects.exclude(
            estado_operativo__in={"PENDIENTE_OMT", "FINALIZADO"}
        ).filter(fecha_programada__isnull=True).count(),
        "promedio_grupo_horas": round(sum(tiempos_grupo) / len(tiempos_grupo), 1) if tiempos_grupo else None,
        "servicios_programados": len(servicios),
        "servicios_realizados": realizados_grupo,
        "efectividad_grupo": round(realizados_grupo * 100 / len(servicios), 1) if servicios else None,
        "programados_prioritarios": programados_prioritarios,
        "cumplidos_prioritarios": cumplidos_prioritarios,
        "cumplimiento_prioritarios": round(
            cumplidos_prioritarios * 100 / programados_prioritarios, 1
        ) if programados_prioritarios else None,
        "programados_otros": programados_otros,
        "cumplidos_otros": cumplidos_otros,
        "cumplimiento_otros": round(
            cumplidos_otros * 100 / programados_otros, 1
        ) if programados_otros else None,
        "indicadores_por_tecnico": indicadores_por_tecnico,
        "detalle_prioritarios": detalle_prioritarios,
        "detalle_otros": detalle_otros,
        "detalle_pendientes": detalle_pendientes,
        "detalle_realizados": detalle_realizados,
    }


HORARIOS_TECNICOS_PREDETERMINADOS = {
    ("BASE", 0): (time(7, 15), time(12), time(14, 15), time(18)),
    ("BASE", 1): (time(7, 15), time(12), time(14, 15), time(18)),
    ("BASE", 2): (time(7, 15), time(12), time(14, 15), time(18)),
    ("BASE", 3): (time(7, 15), time(12), time(14, 15), time(18)),
    ("BASE", 4): (time(8), time(12), None, None),
    ("BASE", 5): (time(9), time(13), None, None),
    ("DISPONIBLE", 5): (time(14, 30), time(18, 30), None, None),
}


def asegurar_horarios_tecnicos():
    for (tipo, dia), horas in HORARIOS_TECNICOS_PREDETERMINADOS.items():
        JornadaLaboralTecnico.objects.get_or_create(
            tipo=tipo, dia_semana=dia,
            defaults={
                "entrada_1": horas[0], "salida_1": horas[1],
                "entrada_2": horas[2], "salida_2": horas[3], "activo": True,
            },
        )


def indicadores_ocupacion_tecnicos(fecha_desde=None, fecha_hasta=None):
    asegurar_horarios_tecnicos()
    hoy = timezone.localdate()
    if isinstance(fecha_desde, datetime):
        fecha_desde = fecha_desde.date()
    if isinstance(fecha_hasta, datetime):
        fecha_hasta = fecha_hasta.date()
    if fecha_desde is None:
        fecha_desde = hoy.replace(day=1)
    if fecha_hasta is None:
        fecha_hasta = hoy
    if fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde
    jornadas = {(j.tipo, j.dia_semana): j for j in JornadaLaboralTecnico.objects.filter(activo=True)}
    festivos = set(DiaNoLaboralTecnico.objects.filter(
        fecha__range=(fecha_desde, fecha_hasta)
    ).values_list("fecha", flat=True))
    rotaciones = {
        rotacion.fecha_sabado: rotacion
        for rotacion in RotacionTecnicoDisponible.objects.filter(
            fecha_sabado__range=(fecha_desde, fecha_hasta)
        ).select_related("tecnico")
    }

    horas_esperadas = {}
    tecnicos = list(Tecnico.objects.filter(
        incluir_indicadores=True
    ).order_by("nombre"))
    for tecnico in tecnicos:
        total = 0
        fecha = fecha_desde
        while fecha <= fecha_hasta:
            if fecha in festivos:
                fecha += timedelta(days=1)
                continue
            rotacion_dia = rotaciones.get(fecha)
            tipo = "DISPONIBLE" if (
                rotacion_dia and rotacion_dia.tecnico_id == tecnico.id
            ) else "BASE"
            jornada = jornadas.get((tipo, fecha.weekday()))
            if jornada:
                total += jornada.horas_dia
            fecha += timedelta(days=1)
        horas_esperadas[tecnico.id] = round(total, 2)

    horas_reales = {tecnico.id: 0 for tecnico in tecnicos}
    servicios_medidos = {tecnico.id: 0 for tecnico in tecnicos}
    servicios = Mantenimiento.objects.select_related("tecnico").filter(
        tecnico__in=tecnicos,
        estado_operativo__in={"PENDIENTE_OMT", "FINALIZADO"},
    )
    for servicio in servicios:
        inicio = servicio.inicio_tecnico or servicio.fecha_inicio
        fin = servicio.fin_tecnico or servicio.fecha_fin
        if not inicio or not fin:
            continue
        if timezone.is_naive(inicio):
            inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
        if timezone.is_naive(fin):
            fin = timezone.make_aware(fin, timezone.get_current_timezone())
        inicio_local = timezone.localtime(inicio)
        if not (fecha_desde <= inicio_local.date() <= fecha_hasta):
            continue
        duracion = (fin - inicio).total_seconds() / 3600
        if duracion <= 0:
            continue
        horas_reales[servicio.tecnico_id] = horas_reales.get(servicio.tecnico_id, 0) + duracion
        servicios_medidos[servicio.tecnico_id] = servicios_medidos.get(servicio.tecnico_id, 0) + 1

    filas = []
    for tecnico in tecnicos:
        reales = round(horas_reales.get(tecnico.id, 0), 2)
        esperadas = horas_esperadas.get(tecnico.id, 0)
        sabados_disponible = sorted(
            fecha for fecha, rotacion in rotaciones.items()
            if rotacion.tecnico_id == tecnico.id
        )
        filas.append({
            "tecnico": tecnico.nombre,
            "es_disponible": bool(sabados_disponible),
            "sabados_disponible": sabados_disponible,
            "servicios": servicios_medidos.get(tecnico.id, 0),
            "horas_reales": reales,
            "horas_esperadas": esperadas,
            "diferencia": round(reales - esperadas, 2),
            "ocupacion": round(reales * 100 / esperadas, 1) if esperadas else None,
        })

    total_reales = round(sum(horas_reales.values()), 2)
    total_esperadas = round(sum(horas_esperadas.values()), 2)
    return {
        "ocupacion_desde": fecha_desde.isoformat(),
        "ocupacion_hasta": fecha_hasta.isoformat(),
        "ocupacion_periodo": f"{fecha_desde.isoformat()} a {fecha_hasta.isoformat()}",
        "ocupacion_tecnicos": filas,
        "ocupacion_total_horas": total_reales,
        "ocupacion_total_esperadas": total_esperadas,
        "ocupacion_total_porcentaje": round(total_reales * 100 / total_esperadas, 1) if total_esperadas else None,
        "ocupacion_festivos_mes": len(festivos),
        "ocupacion_rotaciones_mes": len(rotaciones),
        "ocupacion_tecnicos_disponibles": ", ".join(
            f"{fecha.strftime('%d/%m')}: {rotacion.tecnico.nombre}"
            for fecha, rotacion in sorted(rotaciones.items())
        ) or "Sin asignar",
    }


@login_required(login_url='login')
@user_passes_test(puede_ver_mantenimientos, login_url='home')
def listar_mantenimientos(request):

    if request.method == "POST":
        if not puede_gestionar_mantenimientos(request.user):
            messages.error(request, "Tu perfil sólo permite consultar y registrar órdenes OMT.")
            return redirect("listar_mantenimientos")
        # form = MantenimientoForm(request.POST, request.FILES)
        post_data = request.POST.copy()

        codigo = (post_data.get("codigo") or "").strip()

        if codigo:
            inst = CuadroInsta.objects.filter(codigo__iexact=codigo).first()

            if inst:
                if not post_data.get("cliente"):
                    post_data["cliente"] = inst.cliente or ""

                if not post_data.get("ciudad"):
                    post_data["ciudad"] = inst.ciudad or ""

                if not post_data.get("direccion"):
                    post_data["direccion"] = inst.direccion or ""

        form = MantenimientoForm(post_data, request.FILES)

        if form.is_valid():
            mantenimiento = form.save(commit=False)
            mantenimiento.creado_por = request.user
            mantenimiento.save()
            registrar_cambio_tecnico(
                mantenimiento, None, mantenimiento.tecnico, request.user
            )

            messages.success(
                request, "Mantenimiento registrado correctamente.")
            return redirect("listar_mantenimientos")

        messages.error(request, form.errors)

    else:
        form = MantenimientoForm()

    busqueda = (request.GET.get("busqueda") or "").strip()
    # Conserva compatibilidad con enlaces anteriores que enviaban una sola
    # fecha y permite consultar intervalos abiertos o cerrados.
    fecha_legacy_txt = (request.GET.get("fecha") or "").strip()
    fecha_desde_txt = (request.GET.get("fecha_desde") or fecha_legacy_txt).strip()
    fecha_hasta_txt = (request.GET.get("fecha_hasta") or fecha_legacy_txt).strip()
    fecha_desde = parse_date(fecha_desde_txt)
    fecha_hasta = parse_date(fecha_hasta_txt)
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde
        fecha_desde_txt = fecha_desde.isoformat()
        fecha_hasta_txt = fecha_hasta.isoformat()
    estado_filtro = (request.GET.get("estado_movil") or "").strip().upper()
    alerta_filtro = (request.GET.get("alerta") or "").strip().lower()

    hoy = timezone.localdate()
    indicadores_mantenimiento = indicadores_atencion_mantenimientos()

    mantenimientos = (
        Mantenimiento.objects
        .select_related("tecnico")
        .annotate(fecha_ordenamiento=Coalesce(
            "fecha_creacion_servicio", "fecha_registro"
        ))
        .order_by("-fecha_ordenamiento", "-pk")
    )

    if busqueda:
        mantenimientos = mantenimientos.filter(
            Q(numero_ticket__icontains=busqueda)
            | Q(codigo__icontains=busqueda)
            | Q(cliente__icontains=busqueda)
            | Q(ciudad__icontains=busqueda)
            | Q(direccion__icontains=busqueda)
            | Q(tipo_servicio__icontains=busqueda)
            | Q(tipo_falla__icontains=busqueda)
            | Q(tecnico__nombre__icontains=busqueda)
            | Q(orden__icontains=busqueda)
            | Q(observacion__icontains=busqueda)
            | Q(novedad__icontains=busqueda)
            | Q(pendiente__icontains=busqueda)
        ).distinct()

    if fecha_desde:
        mantenimientos = mantenimientos.filter(
            fecha_ordenamiento__date__gte=fecha_desde
        )
    if fecha_hasta:
        mantenimientos = mantenimientos.filter(
            fecha_ordenamiento__date__lte=fecha_hasta
        )

    if estado_filtro == "PENDIENTE":
        mantenimientos = mantenimientos.filter(
            estado_operativo="PENDIENTE", tecnico__isnull=True
        )
    elif estado_filtro == "ASIGNADO":
        mantenimientos = mantenimientos.filter(
            estado_operativo="PENDIENTE", tecnico__isnull=False
        )
    elif estado_filtro in {"EN_PROCESO", "PENDIENTE_OMT", "FINALIZADO"}:
        mantenimientos = mantenimientos.filter(
            estado_operativo=estado_filtro
        )

    if alerta_filtro in {"prioritarios", "otros"}:
        mantenimientos = mantenimientos.exclude(
            estado_operativo__in={"FINALIZADO", "PENDIENTE_OMT"}
        ).filter(
            fecha_programada__lte=hoy
        )
        if alerta_filtro == "prioritarios":
            mantenimientos = mantenimientos.filter(
                tipo_falla__in=FALLAS_PRIORITARIAS_MANTENIMIENTO
            )
        else:
            mantenimientos = mantenimientos.exclude(
                tipo_falla__in=FALLAS_PRIORITARIAS_MANTENIMIENTO
            )

    tecnicos = Tecnico.objects.all().order_by("nombre")
    ciudades_mantenimiento = Ciudad.objects.all().order_by("nombre")

    context = {
        "form": form,
        "mantenimientos": mantenimientos,
        "tecnicos": tecnicos,
        "ciudades_mantenimiento": ciudades_mantenimiento,
        "busqueda": busqueda,
        "fecha_desde_filtro": fecha_desde_txt,
        "fecha_hasta_filtro": fecha_hasta_txt,
        "estado_filtro": estado_filtro,
        "alerta_filtro": alerta_filtro,
        "puede_gestionar_mantenimientos": puede_gestionar_mantenimientos(request.user),
        "puede_registrar_orden_omt": puede_registrar_orden_omt(request.user),
        **indicadores_mantenimiento,
    }

    return render(
        request,
        "mantenimientos/listar_mantenimientos.html",
        context
    )
# JSON PARA BUSCAR CLIENTES Y AGREGAR AL CUADRO MANTENIMIENTOS


@login_required
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
def buscar_instalacion_por_codigo(request):
    codigo = (request.GET.get('codigo') or "").strip()

    if not codigo:
        return JsonResponse(
            {"ok": False, "error": "Sin código"},
            status=400
        )

    # Buscamos de forma segura (case-insensitive) y tomamos la primera coincidencia
    qs = CuadroInsta.objects.filter(codigo__iexact=codigo)

    if not qs.exists():
        return JsonResponse(
            {"ok": False, "error": "Instalación no encontrada"},
            status=404
        )

    inst = qs.first()

    return JsonResponse({
        "ok": True,
        "cliente": inst.cliente or "",
        "ciudad": inst.ciudad or "",
        "direccion": inst.direccion or "",
    })

# vistas para edicion y subir archivos de mantenimientos


def _aplicar_horas_manuales(mantenimiento, datos):
    entrada_txt = (datos.get("hora_entrada") or "").strip()
    salida_txt = (datos.get("hora_salida") or "").strip()
    if not entrada_txt and not salida_txt:
        return None
    if not entrada_txt or not salida_txt:
        return "Debe ingresar tanto la hora de entrada como la hora de salida."

    entrada = parse_time(entrada_txt)
    salida = parse_time(salida_txt)
    fecha = parse_date((datos.get("realizado") or "").strip())
    fecha = fecha or mantenimiento.realizado or timezone.localdate()
    if not entrada or not salida:
        return "Las horas de entrada y salida no tienen un formato válido."

    inicio = timezone.make_aware(
        datetime.combine(fecha, entrada), timezone.get_current_timezone()
    )
    fin = timezone.make_aware(
        datetime.combine(fecha, salida), timezone.get_current_timezone()
    )
    if fin <= inicio:
        return "La hora de salida debe ser posterior a la hora de entrada."

    mantenimiento.realizado = fecha
    mantenimiento.hora_entrada = entrada
    mantenimiento.hora_salida = salida
    mantenimiento.inicio_tecnico = inicio
    mantenimiento.fin_tecnico = fin
    mantenimiento.horas = round((fin - inicio).total_seconds() / 3600, 2)
    return None


def _aplicar_novedad_operador(mantenimiento, datos, usuario, novedad_anterior):
    if "novedad" not in datos:
        return
    novedad = (datos.get("novedad") or "").strip()[:5000]
    mantenimiento.novedad = novedad
    if not novedad or novedad == novedad_anterior:
        return

    fecha_nota = timezone.localtime().strftime("%Y-%m-%d %H:%M")
    nota = f"[NOTA OPERADOR - {usuario.username} - {fecha_nota}] {novedad}"
    observacion_actual = (mantenimiento.observacion or "").strip()
    mantenimiento.observacion = (
        f"{nota}\n{observacion_actual}" if observacion_actual else nota
    )


@login_required
@user_passes_test(puede_ver_mantenimientos, login_url='home')
@require_POST
def mantenimiento_actualizar(request, pk):
    m = get_object_or_404(Mantenimiento, pk=pk)
    if (
        not puede_gestionar_mantenimientos(request.user)
        and (
            pertenece_grupo(request.user, "Monitoreo")
            or pertenece_grupo(request.user, "Administrador Monitoreo")
        )
    ):
        return JsonResponse(
            {"ok": False, "error": "Tu perfil sólo puede registrar la orden OMT."},
            status=403,
        )
    tecnico_anterior = m.tecnico
    orden_anterior = m.orden
    novedad_anterior = m.novedad or ""

    if m.orden and not request.user.is_superuser:
        return JsonResponse(
            {"ok": False, "error": "El servicio está cerrado y no admite cambios."},
            status=409,
        )
    if m.estado_operativo in {"FINALIZADO", "PENDIENTE_OMT"} and not request.user.is_superuser:
        if not puede_registrar_orden_omt(request.user):
            return JsonResponse({"ok": False, "error": "No tienes permiso para registrar la orden."}, status=403)
        orden = (request.POST.get("orden") or "").strip()
        if not orden:
            return JsonResponse(
                {"ok": False, "error": "Debe ingresar la orden para cerrar el servicio."},
                status=400,
            )
        m.orden = orden[:50]
        m.fecha_orden = timezone.now()
        m.orden_registrada_por = request.user
        fecha_realizado = parse_date((request.POST.get("realizado") or "").strip())
        m.realizado = fecha_realizado or m.realizado or timezone.localdate()
        error_horas = _aplicar_horas_manuales(m, request.POST)
        if error_horas:
            return JsonResponse({"ok": False, "error": error_horas}, status=400)
        _aplicar_novedad_operador(
            m, request.POST, request.user, novedad_anterior
        )
        m.estado_operativo = "FINALIZADO"
        m.save(update_fields=[
            "orden", "fecha_orden", "orden_registrada_por", "realizado",
            "hora_entrada", "hora_salida", "inicio_tecnico", "fin_tecnico",
            "horas", "novedad", "observacion", "estado_operativo",
        ])
        return JsonResponse({
            "ok": True,
            "orden": m.orden,
            "realizado": m.realizado.isoformat(),
            "fecha_orden": timezone.localtime(m.fecha_orden).isoformat(),
        })

    campos_editables = {
        "codigo", "cliente", "ciudad", "direccion", "tipo_servicio",
        "tipo_falla", "tecnico", "fecha_programada", "orden", "realizado",
        "hora_entrada", "hora_salida", "novedad", "observacion",
    }
    datos = model_to_dict(
        m,
        fields=[
            campo for campo in MantenimientoForm.Meta.fields
            if campo != "archivo"
        ],
    )

    for campo in campos_editables:
        if campo in request.POST:
            datos[campo] = request.POST.get(campo, "")

    form = MantenimientoForm(datos, instance=m)
    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": form.errors.get_json_data()},
            status=400,
        )

    m = form.save(commit=False)
    error_horas = _aplicar_horas_manuales(m, request.POST)
    if error_horas:
        return JsonResponse({"ok": False, "error": error_horas}, status=400)
    _aplicar_novedad_operador(
        m, request.POST, request.user, novedad_anterior
    )
    if request.user.is_superuser:
        estado_manual = (request.POST.get("estado_operativo") or "").strip()
        if estado_manual:
            if estado_manual not in dict(Mantenimiento.ESTADO_OPERATIVO_CHOICES):
                return JsonResponse(
                    {"ok": False, "error": "Estado móvil inválido."},
                    status=400,
                )
            m.estado_operativo = estado_manual
    elif m.orden:
        campos_faltantes = []
        if not m.realizado:
            campos_faltantes.append("fecha de realización")
        if not m.hora_entrada:
            campos_faltantes.append("hora de entrada")
        if not m.hora_salida:
            campos_faltantes.append("hora de salida")
        if not (m.novedad or "").strip():
            campos_faltantes.append("novedad técnico")
        if campos_faltantes:
            return JsonResponse({
                "ok": False,
                "error": (
                    "Para cerrar el servicio debe completar: "
                    + ", ".join(campos_faltantes) + "."
                ),
            }, status=400)
        m.estado_operativo = "FINALIZADO"
        if not m.fecha_orden:
            m.fecha_orden = timezone.now()
        if not m.orden_registrada_por:
            m.orden_registrada_por = request.user
    if m.orden and not orden_anterior:
        m.fecha_orden = timezone.now()
        m.orden_registrada_por = request.user
        if m.estado_operativo == "PENDIENTE_OMT":
            m.estado_operativo = "FINALIZADO"
    m.save(permitir_estado_manual=request.user.is_superuser)
    registrar_cambio_tecnico(m, tecnico_anterior, m.tecnico, request.user)

    return JsonResponse({
        "ok": True,
        "cliente": m.cliente,
        "ciudad": m.ciudad,
        "direccion": m.direccion,
        "tipo_servicio_display": m.get_tipo_servicio_display(),
        "tipo_falla_display": m.get_tipo_falla_display() if m.tipo_falla else "Sin registrar",
        "tecnico": m.tecnico.nombre if m.tecnico else "",
        "orden": m.orden,
        "realizado": m.realizado.isoformat() if m.realizado else "",
    })


@login_required(login_url="login")
@user_passes_test(puede_registrar_orden_omt, login_url="home")
@require_POST
def registrar_orden_omt(request, pk):
    mantenimiento = get_object_or_404(Mantenimiento, pk=pk)
    if mantenimiento.orden:
        messages.error(request, "Este servicio ya tiene un número de orden registrado.")
        return redirect(f'{reverse("listar_mantenimientos")}#mantenimiento-{pk}')
    if mantenimiento.estado_operativo != "PENDIENTE_OMT":
        messages.error(request, "La orden sólo puede registrarse cuando el servicio está pendiente de OMT.")
        return redirect(f'{reverse("listar_mantenimientos")}#mantenimiento-{pk}')
    orden = (request.POST.get("orden") or "").strip()
    if not orden:
        messages.error(request, "Debes ingresar el número de orden.")
        return redirect(f'{reverse("listar_mantenimientos")}#mantenimiento-{pk}')

    mantenimiento.orden = orden[:50]
    mantenimiento.fecha_orden = timezone.now()
    mantenimiento.orden_registrada_por = request.user
    mantenimiento.estado_operativo = "FINALIZADO"
    mantenimiento.save(update_fields=[
        "orden", "fecha_orden", "orden_registrada_por", "estado_operativo"
    ])
    messages.success(request, "Orden OMT registrada y servicio cerrado correctamente.")
    return redirect(f'{reverse("listar_mantenimientos")}#mantenimiento-{pk}')


@login_required
@user_passes_test(puede_eliminar_mantenimientos, login_url='home')
@require_POST
def mantenimiento_eliminar(request, pk):
    """Elimina un mantenimiento desde el modal de confirmación."""
    m = get_object_or_404(Mantenimiento, pk=pk)
    if m.estado_operativo == "FINALIZADO" or m.orden:
        messages.error(request, "El servicio finalizado no se puede eliminar.")
        return redirect('listar_mantenimientos')
    m.delete()
    messages.success(request, "Mantenimiento eliminado correctamente.")
    return redirect('listar_mantenimientos')


@login_required
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
@require_POST
def mantenimiento_subir_archivo(request, pk):
    """Sube o reemplaza el archivo (foto/PDF) de un mantenimiento."""
    m = get_object_or_404(Mantenimiento, pk=pk)
    if m.estado_operativo == "FINALIZADO" or m.orden:
        messages.error(request, "El servicio finalizado solo permite registrar la orden.")
        return redirect('listar_mantenimientos')
    archivo = request.FILES.get('archivo')

    if not archivo:
        messages.error(request, "No se recibió ningún archivo.")
        return redirect('listar_mantenimientos')

    m.archivo = archivo
    m.save()
    messages.success(request, "Archivo cargado correctamente.")
    return redirect('listar_mantenimientos')


# VISTA DE FACTURACIÓN

@login_required(login_url='login')
@user_passes_test(puede_facturar)
def facturar_instalacion(request, id):
    instalacion = get_object_or_404(CuadroInsta, id=id)

    if request.method != "POST":
        return JsonResponse({
            "ok": False,
            "mensaje": "Método no permitido."
        }, status=405)

    if not instalacion.alistado:
        return JsonResponse({
            "ok": False,
            "mensaje": "No se puede facturar una instalación que no ha sido alistada por almacén."
        }, status=400)

    estado_facturacion = request.POST.get("estado_facturacion", "").upper()
    if estado_facturacion not in {"FACTURADO", "RETENIDO"}:
        return JsonResponse({
            "ok": False,
            "mensaje": "Seleccione Facturado o Retenido."
        }, status=400)

    instalacion.estado_facturacion = estado_facturacion
    instalacion.save()

    etiqueta = instalacion.get_estado_facturacion_display()

    return JsonResponse({
        "ok": True,
        "mensaje": f"Instalación marcada como {etiqueta.lower()}.",
        "estado": instalacion.estado_facturacion,
        "etiqueta": etiqueta,
        "fecha": instalacion.fecha_facturacion.strftime("%Y-%m-%d"),
        "dias": instalacion.dias_para_facturar,
    })


def _tecnico_del_usuario(user):
    try:
        return user.perfil_tecnico
    except Tecnico.DoesNotExist:
        return None


def _serializar_servicio_tecnico(mantenimiento):
    try:
        cotizacion_registrada = bool(mantenimiento.cotizacion_tecnica)
    except CotizacionServicioTecnico.DoesNotExist:
        cotizacion_registrada = False
    return {
        "id": mantenimiento.pk,
        "ticket": mantenimiento.numero_ticket or "",
        "codigo": mantenimiento.codigo,
        "cliente": mantenimiento.cliente,
        "ciudad": mantenimiento.ciudad or "",
        "direccion": mantenimiento.direccion,
        "tipo_servicio": mantenimiento.get_tipo_servicio_display(),
        "tipo_falla": mantenimiento.get_tipo_falla_display() if mantenimiento.tipo_falla else "",
        "fecha_programada": mantenimiento.fecha_programada.isoformat() if mantenimiento.fecha_programada else "",
        "realizado": mantenimiento.realizado.isoformat() if mantenimiento.realizado else "",
        "estado": mantenimiento.estado_operativo,
        "estado_label": (
            "REALIZADO"
            if mantenimiento.estado_operativo == "FINALIZADO"
            else "PENDIENTE OMT"
            if mantenimiento.estado_operativo == "PENDIENTE_OMT"
            else "EN PROCESO"
            if mantenimiento.estado_operativo == "EN_PROCESO"
            else "ASIGNADO"
        ),
        "novedad": mantenimiento.novedad or "",
        "observacion": mantenimiento.observacion or "",
        "pendiente": mantenimiento.pendiente or "",
        "inicio": mantenimiento.inicio_tecnico.isoformat() if (
            mantenimiento.inicio_tecnico and mantenimiento.estado_operativo != "PENDIENTE"
        ) else "",
        "fin": mantenimiento.fin_tecnico.isoformat() if (
            mantenimiento.fin_tecnico
            and mantenimiento.estado_operativo in {"PENDIENTE_OMT", "FINALIZADO"}
        ) else "",
        "bloqueado": mantenimiento.estado_operativo in {"PENDIENTE_OMT", "FINALIZADO"} or bool(mantenimiento.orden),
        "cotizacion_registrada": cotizacion_registrada,
    }


@login_required(login_url="login")
@never_cache
def portal_tecnico(request):
    tecnico = _tecnico_del_usuario(request.user)
    if not tecnico:
        messages.error(request, "Tu usuario todavía no está vinculado a un técnico.")
        return redirect("home")
    return render(request, "mantenimientos/portal_tecnico.html", {"tecnico": tecnico})


@login_required(login_url="login")
@never_cache
def api_servicios_tecnico(request):
    tecnico = _tecnico_del_usuario(request.user)
    if not tecnico:
        return JsonResponse({"ok": False, "error": "Usuario sin técnico vinculado."}, status=403)

    if request.method == "GET":
        hoy = timezone.localdate()
        sin_programar = Mantenimiento.objects.filter(
            tecnico=tecnico,
            fecha_programada__isnull=True,
            realizado__isnull=True,
        ).exclude(estado_operativo="FINALIZADO").filter(
            Q(orden__isnull=True) | Q(orden="")
        )
        for mantenimiento in sin_programar:
            mantenimiento.fecha_programada = hoy
            mantenimiento.save(update_fields=["fecha_programada"])
        servicios = Mantenimiento.objects.select_related("cotizacion_tecnica").filter(
            tecnico=tecnico,
            realizado__isnull=True,
        ).exclude(
            estado_operativo="FINALIZADO"
        ).filter(
            Q(orden__isnull=True) | Q(orden="")
        ).order_by("fecha_programada", "cliente")
        notificaciones = tecnico.notificaciones.filter(leida=False)[:30]
        return JsonResponse({
            "ok": True,
            "servidor": timezone.now().isoformat(),
            "servicios": [_serializar_servicio_tecnico(m) for m in servicios],
            "notificaciones": [{
                "id": n.pk,
                "tipo": n.tipo,
                "mensaje": n.mensaje,
                "fecha": n.fecha.isoformat(),
                "servicio_id": n.mantenimiento_id,
            } for n in notificaciones],
        })

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido."}, status=405)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Datos inválidos."}, status=400)

    mantenimiento = get_object_or_404(
        Mantenimiento, pk=data.get("id"), tecnico=tecnico
    )
    if mantenimiento.orden or mantenimiento.realizado:
        return JsonResponse(
            {"ok": False, "error": "El servicio ya fue realizado o cerrado con una orden.", "retirar": True},
            status=409,
        )
    if mantenimiento.estado_operativo in {"FINALIZADO", "PENDIENTE_OMT"}:
        return JsonResponse(
            {"ok": False, "error": "El servicio ya fue finalizado.", "retirar": True},
            status=409,
        )
    estado = data.get("estado")
    if estado not in {"PENDIENTE", "EN_PROCESO", "FINALIZADO"}:
        return JsonResponse({"ok": False, "error": "Estado inválido."}, status=400)

    ahora = timezone.now()
    fecha_evento = ahora
    if data.get("registrado_offline"):
        fecha_offline = parse_datetime(str(data.get("fecha_evento") or ""))
        if fecha_offline:
            if timezone.is_naive(fecha_offline):
                fecha_offline = timezone.make_aware(
                    fecha_offline, timezone.get_current_timezone()
                )
            fecha_evento = fecha_offline
    fecha_evento_local = timezone.localtime(fecha_evento)
    estado_anterior = mantenimiento.estado_operativo
    novedad_anterior = mantenimiento.novedad or ""
    novedad_nueva = str(data.get("novedad", novedad_anterior)).strip()[:5000]
    if estado == "FINALIZADO" and estado_anterior != "EN_PROCESO":
        return JsonResponse(
            {"ok": False, "error": "Debes iniciar el servicio antes de finalizarlo."},
            status=409,
        )
    if estado == "FINALIZADO" and not novedad_nueva:
        return JsonResponse(
            {"ok": False, "error": "Debes registrar la novedad antes de finalizar."},
            status=400,
        )
    if estado == "PENDIENTE" and estado_anterior != "EN_PROCESO":
        return JsonResponse(
            {"ok": False, "error": "Solo se puede soltar un servicio que esté en ejecución."},
            status=409,
        )
    servicio_abierto = None
    if estado == "EN_PROCESO":
        servicio_abierto = Mantenimiento.objects.filter(
            tecnico=tecnico,
            estado_operativo="EN_PROCESO",
        ).exclude(pk=mantenimiento.pk).filter(
            Q(orden__isnull=True) | Q(orden="")
        ).first()
    if servicio_abierto:
        referencia_abierta = (
            servicio_abierto.numero_ticket
            or servicio_abierto.codigo
            or str(servicio_abierto.pk)
        )
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    f"Tienes otro servicio abierto ({referencia_abierta}). "
                    "Debes finalizarlo o soltarlo antes de iniciar otro."
                ),
                "servicio_abierto_id": servicio_abierto.pk,
            },
            status=409,
        )
    mantenimiento.estado_operativo = estado
    mantenimiento.novedad = novedad_nueva
    if novedad_nueva and novedad_nueva != novedad_anterior:
        fecha_nota = fecha_evento_local.strftime("%Y-%m-%d %H:%M")
        nota = f"[NOTA TÉCNICO - {tecnico.nombre} - {fecha_nota}] {novedad_nueva}"
        observacion_actual = (mantenimiento.observacion or "").strip()
        mantenimiento.observacion = (
            f"{observacion_actual}\n{nota}" if observacion_actual else nota
        )
    if estado == "EN_PROCESO" and estado_anterior != "EN_PROCESO":
        mantenimiento.inicio_tecnico = fecha_evento
        mantenimiento.hora_entrada = fecha_evento_local.time().replace(
            microsecond=0
        )
        mantenimiento.fin_tecnico = None
        mantenimiento.hora_salida = None
        mantenimiento.horas = None
        mantenimiento.realizado = None
    if estado == "PENDIENTE":
        mantenimiento.inicio_tecnico = None
        mantenimiento.fin_tecnico = None
        mantenimiento.hora_entrada = None
        mantenimiento.hora_salida = None
        mantenimiento.horas = None
        mantenimiento.realizado = None
    if estado == "FINALIZADO":
        mantenimiento.estado_operativo = "PENDIENTE_OMT"
        mantenimiento.realizado = fecha_evento_local.date()
        mantenimiento.fin_tecnico = fecha_evento
        mantenimiento.hora_salida = fecha_evento_local.time().replace(
            microsecond=0
        )
        if mantenimiento.inicio_tecnico and mantenimiento.fin_tecnico:
            mantenimiento.horas = round(
                (mantenimiento.fin_tecnico - mantenimiento.inicio_tecnico).total_seconds() / 3600, 2
            )
    mantenimiento.save()
    return JsonResponse({"ok": True, "servicio": _serializar_servicio_tecnico(mantenimiento)})


@login_required(login_url="login")
@require_POST
def registrar_cotizacion_tecnico(request, pk):
    tecnico = _tecnico_del_usuario(request.user)
    if not tecnico:
        return JsonResponse({"ok": False, "error": "Usuario sin técnico vinculado."}, status=403)

    mantenimiento = get_object_or_404(Mantenimiento, pk=pk, tecnico=tecnico)
    if hasattr(mantenimiento, "cotizacion_tecnica"):
        return JsonResponse(
            {"ok": False, "error": "Este servicio ya tiene una cotización registrada."},
            status=409,
        )

    registro = (mantenimiento.numero_ticket or "").strip()
    if not registro:
        return JsonResponse(
            {"ok": False, "error": "El servicio no tiene número de registro."},
            status=400,
        )
    if CotizacionServicioTecnico.objects.filter(registro=registro).exists():
        return JsonResponse(
            {"ok": False, "error": f"El registro {registro} ya tiene una cotización."},
            status=409,
        )

    descripcion = (request.POST.get("descripcion") or "").strip()
    if not descripcion:
        return JsonResponse(
            {"ok": False, "error": "Debes escribir la descripción de la cotización."},
            status=400,
        )

    cotizacion = CotizacionServicioTecnico.objects.create(
        mantenimiento=mantenimiento,
        tecnico=tecnico,
        codigo=(mantenimiento.codigo or "0")[:50],
        registro=registro[:50],
        cliente=mantenimiento.cliente,
        direccion=mantenimiento.direccion,
        descripcion=descripcion[:5000],
        creado_por=request.user,
    )
    return JsonResponse({
        "ok": True,
        "cotizacion": {
            "id": cotizacion.pk,
            "codigo": cotizacion.codigo,
            "registro": cotizacion.registro,
            "cliente": cotizacion.cliente,
        },
    }, status=201)


@login_required(login_url="login")
@user_passes_test(puede_gestionar_cotizaciones, login_url="home")
def listar_cotizaciones_tecnicas(request):
    busqueda = (request.GET.get("busqueda") or "").strip()
    filtro_estado = (request.GET.get("estado") or "").upper()
    cotizaciones_base = CotizacionServicioTecnico.objects.select_related(
        "tecnico", "mantenimiento", "creado_por", "ejecutivo"
    ).prefetch_related("seguimientos")
    if busqueda:
        cotizaciones_base = cotizaciones_base.filter(
            Q(codigo__icontains=busqueda)
            | Q(registro__icontains=busqueda)
            | Q(cliente__icontains=busqueda)
            | Q(direccion__icontains=busqueda)
            | Q(descripcion__icontains=busqueda)
            | Q(numero_cotizacion__icontains=busqueda)
            | Q(tecnico__nombre__icontains=busqueda)
        ).distinct()
    contadores = {
        "enviadas": cotizaciones_base.filter(fecha_envio__isnull=False).count(),
        "aprobadas": cotizaciones_base.filter(estado="APROBADA").count(),
        "pendientes": cotizaciones_base.filter(estado="PENDIENTE").count(),
    }
    cotizaciones = cotizaciones_base
    if filtro_estado == "ENVIADAS":
        cotizaciones = cotizaciones.filter(fecha_envio__isnull=False)
    elif filtro_estado in {"APROBADA", "PENDIENTE"}:
        cotizaciones = cotizaciones.filter(estado=filtro_estado)
    cotizaciones = list(cotizaciones)
    limite = timezone.localdate() - timedelta(days=8)
    for cotizacion in cotizaciones:
        cotizacion.total_seguimientos = len(cotizacion.seguimientos.all())
        # El plazo comercial comienza cuando la cotización fue enviada. Después
        # de cada seguimiento, el siguiente plazo se cuenta desde esa gestión.
        ultima_gestion = cotizacion.fecha_seguimiento or cotizacion.fecha_envio
        fecha_ultima_gestion = (
            timezone.localtime(ultima_gestion).date() if ultima_gestion else None
        )
        cotizacion.fecha_proximo_seguimiento = (
            fecha_ultima_gestion + timedelta(days=8)
            if fecha_ultima_gestion else None
        )
        cotizacion.seguimiento_vencido = bool(
            cotizacion.estado == "PENDIENTE"
            and fecha_ultima_gestion
            and fecha_ultima_gestion <= limite
        )
        cotizacion.siguiente_seguimiento = cotizacion.total_seguimientos + 1
    cotizaciones_vencidas = list(
        CotizacionServicioTecnico.objects.filter(estado="PENDIENTE")
        .filter(
            Q(fecha_seguimiento__date__lte=limite)
            | Q(
                fecha_seguimiento__isnull=True,
                fecha_envio__date__lte=limite,
            )
        )
        .select_related("ejecutivo")
    )
    return render(request, "mantenimientos/listar_cotizaciones.html", {
        "cotizaciones": cotizaciones,
        "busqueda": busqueda,
        "ejecutivos": Ejecutivo.objects.all().order_by("nombre"),
        "cotizaciones_vencidas": cotizaciones_vencidas,
        "filtro_estado": filtro_estado,
        "contadores": contadores,
    })


def _duracion_legible(segundos):
    if segundos is None:
        return "---"
    minutos = max(0, round(segundos / 60))
    dias, minutos = divmod(minutos, 1440)
    horas, minutos = divmod(minutos, 60)
    partes = []
    if dias:
        partes.append(f"{dias} d")
    if horas:
        partes.append(f"{horas} h")
    partes.append(f"{minutos} min")
    return " ".join(partes)


@login_required(login_url="login")
@user_passes_test(lambda user: user.is_superuser, login_url="home")
def indicadores_cotizaciones(request):
    fecha_desde = parse_date(request.GET.get("desde") or "")
    fecha_hasta = parse_date(request.GET.get("hasta") or "")
    cotizaciones = CotizacionServicioTecnico.objects.select_related(
        "creado_por", "tecnico"
    ).order_by("-fecha_registro", "-pk")
    if fecha_desde:
        cotizaciones = cotizaciones.filter(fecha_registro__date__gte=fecha_desde)
    if fecha_hasta:
        cotizaciones = cotizaciones.filter(fecha_registro__date__lte=fecha_hasta)

    detalle = []
    por_responsable = {}
    tiempos_carga = []
    tiempos_envio = []
    pendientes_envio = 0
    for cotizacion in cotizaciones:
        responsable = cotizacion.creado_por
        nombre_responsable = (
            responsable.get_full_name().strip() or responsable.username
            if responsable else "Sin identificar"
        )
        carga = None
        if cotizacion.fecha_orden and cotizacion.fecha_registro:
            diferencia = (
                cotizacion.fecha_registro - cotizacion.fecha_orden
            ).total_seconds()
            if diferencia >= 0:
                carga = diferencia
                tiempos_carga.append(diferencia)
        envio = None
        if cotizacion.fecha_envio and cotizacion.fecha_registro:
            diferencia = (
                cotizacion.fecha_envio - cotizacion.fecha_registro
            ).total_seconds()
            if diferencia >= 0:
                envio = diferencia
                tiempos_envio.append(diferencia)
        else:
            pendientes_envio += 1

        resumen = por_responsable.setdefault(nombre_responsable, {
            "nombre": nombre_responsable,
            "cargadas": 0,
            "enviadas": 0,
            "pendientes": 0,
            "tiempos_carga": [],
            "tiempos_envio": [],
        })
        resumen["cargadas"] += 1
        if carga is not None:
            resumen["tiempos_carga"].append(carga)
        if cotizacion.fecha_envio:
            resumen["enviadas"] += 1
        else:
            resumen["pendientes"] += 1
        if envio is not None:
            resumen["tiempos_envio"].append(envio)
        detalle.append({
            "cotizacion": cotizacion,
            "responsable": nombre_responsable,
            "tiempo_carga": _duracion_legible(carga),
            "tiempo_envio": _duracion_legible(envio),
        })

    responsables = []
    for resumen in por_responsable.values():
        cargas = resumen.pop("tiempos_carga")
        envios = resumen.pop("tiempos_envio")
        resumen["promedio_carga"] = _duracion_legible(
            sum(cargas) / len(cargas) if cargas else None
        )
        resumen["promedio_envio"] = _duracion_legible(
            sum(envios) / len(envios) if envios else None
        )
        responsables.append(resumen)
    responsables.sort(key=lambda item: item["nombre"].casefold())

    cortes = CorteIndicadorCotizacion.objects.select_related("cerrado_por")
    corte_id = request.GET.get("corte")
    corte_seleccionado = cortes.filter(pk=corte_id).first() if corte_id else None
    return render(request, "mantenimientos/indicadores_cotizaciones.html", {
        "detalle": detalle,
        "responsables": responsables,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "total": len(detalle),
        "total_enviadas": sum(1 for item in detalle if item["cotizacion"].fecha_envio),
        "pendientes_envio": pendientes_envio,
        "promedio_carga": _duracion_legible(
            sum(tiempos_carga) / len(tiempos_carga) if tiempos_carga else None
        ),
        "promedio_envio": _duracion_legible(
            sum(tiempos_envio) / len(tiempos_envio) if tiempos_envio else None
        ),
        "cortes": cortes,
        "corte_seleccionado": corte_seleccionado,
        "hoy": timezone.localdate(),
    })


def _snapshot_corte_cotizaciones(cotizaciones):
    detalles = []
    cargas = []
    envios = []
    enviadas = 0
    pendientes = 0
    for cotizacion in cotizaciones:
        responsable = cotizacion.creado_por
        nombre = (
            responsable.get_full_name().strip() or responsable.username
            if responsable else "Sin identificar"
        )
        carga = None
        if cotizacion.fecha_orden and cotizacion.fecha_registro:
            valor = (cotizacion.fecha_registro - cotizacion.fecha_orden).total_seconds()
            if valor >= 0:
                carga = valor
                cargas.append(valor)
        envio = None
        if cotizacion.fecha_envio and cotizacion.fecha_registro:
            valor = (cotizacion.fecha_envio - cotizacion.fecha_registro).total_seconds()
            if valor >= 0:
                envio = valor
                envios.append(valor)
            enviadas += 1
        else:
            pendientes += 1
        detalles.append({
            "registro": cotizacion.registro or "---",
            "cliente": cotizacion.cliente,
            "responsable": nombre,
            "fecha_orden": timezone.localtime(cotizacion.fecha_orden).strftime("%Y-%m-%d %H:%M") if cotizacion.fecha_orden else "---",
            "fecha_carga": timezone.localtime(cotizacion.fecha_registro).strftime("%Y-%m-%d %H:%M"),
            "tiempo_carga": _duracion_legible(carga),
            "fecha_envio": timezone.localtime(cotizacion.fecha_envio).strftime("%Y-%m-%d %H:%M") if cotizacion.fecha_envio else "Pendiente",
            "tiempo_envio": _duracion_legible(envio),
        })
    return {
        "resumen": {
            "total": len(detalles),
            "enviadas": enviadas,
            "pendientes": pendientes,
            "promedio_carga": _duracion_legible(
                sum(cargas) / len(cargas) if cargas else None
            ),
            "promedio_envio": _duracion_legible(
                sum(envios) / len(envios) if envios else None
            ),
        },
        "detalle": detalles,
    }


@login_required(login_url="login")
@user_passes_test(lambda user: user.is_superuser, login_url="home")
@require_POST
def finalizar_corte_cotizaciones(request):
    fecha_hasta = parse_date(request.POST.get("fecha_hasta") or "")
    if not fecha_hasta or fecha_hasta > timezone.localdate():
        messages.error(request, "Selecciona una fecha de corte válida que no sea futura.")
        return redirect("indicadores_cotizaciones")
    if CorteIndicadorCotizacion.objects.filter(fecha_hasta=fecha_hasta).exists():
        messages.error(request, "Ya existe un corte finalizado para esa fecha.")
        return redirect("indicadores_cotizaciones")

    corte_anterior = CorteIndicadorCotizacion.objects.order_by("-fecha_hasta").first()
    if corte_anterior:
        fecha_desde = corte_anterior.fecha_hasta + timedelta(days=1)
    else:
        primera = CotizacionServicioTecnico.objects.order_by("fecha_registro").first()
        fecha_desde = (
            timezone.localtime(primera.fecha_registro).date()
            if primera else fecha_hasta
        )
    if fecha_hasta < fecha_desde:
        messages.error(
            request,
            f"El nuevo corte debe ser posterior al último cierre ({corte_anterior.fecha_hasta:%Y-%m-%d}).",
        )
        return redirect("indicadores_cotizaciones")

    cotizaciones = list(
        CotizacionServicioTecnico.objects.select_related("creado_por")
        .filter(
            fecha_registro__date__gte=fecha_desde,
            fecha_registro__date__lte=fecha_hasta,
        )
        .order_by("-fecha_registro", "-pk")
    )
    snapshot = _snapshot_corte_cotizaciones(cotizaciones)
    corte = CorteIndicadorCotizacion.objects.create(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        cerrado_por=request.user,
        resumen=snapshot["resumen"],
        detalle=snapshot["detalle"],
    )
    messages.success(
        request,
        f"Corte de comisiones finalizado hasta {fecha_hasta:%Y-%m-%d}.",
    )
    return redirect(f'{reverse("indicadores_cotizaciones")}?corte={corte.pk}')


@login_required(login_url="login")
@user_passes_test(puede_gestionar_cotizaciones, login_url="home")
@require_POST
def crear_cotizacion_tecnica_manual(request):
    codigo = (request.POST.get("codigo") or "").strip() or "0"
    registro = (request.POST.get("registro") or "").strip()
    cliente = (request.POST.get("cliente") or "").strip()
    direccion = (request.POST.get("direccion") or "").strip()
    descripcion = (request.POST.get("descripcion") or "").strip()
    contacto = (request.POST.get("contacto") or "").strip()
    telefono = (request.POST.get("telefono") or "").strip()
    fecha_orden = parse_datetime(request.POST.get("fecha_orden") or "")
    if fecha_orden and timezone.is_naive(fecha_orden):
        fecha_orden = timezone.make_aware(fecha_orden, timezone.get_current_timezone())
    soporte = request.FILES.get("soporte")
    if not all([codigo, registro, cliente, direccion, descripcion, soporte]):
        messages.error(request, "Completa los campos obligatorios y adjunta el PDF.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=manual')
    if CotizacionServicioTecnico.objects.filter(registro=registro[:50]).exists():
        messages.error(request, f"El registro {registro[:50]} ya tiene una cotización.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=manual')
    if soporte.size > 10 * 1024 * 1024:
        messages.error(request, "El PDF no puede superar 10 MB.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=manual')
    encabezado = soporte.read(5)
    soporte.seek(0)
    if not soporte.name.lower().endswith(".pdf") or encabezado != b"%PDF-":
        messages.error(request, "El soporte debe ser un archivo PDF válido.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=manual')
    soporte_contenido = soporte.read()
    soporte.seek(0)
    CotizacionServicioTecnico.objects.create(
        codigo=codigo[:50],
        registro=registro[:50],
        cliente=cliente[:100],
        direccion=direccion[:100],
        descripcion=descripcion[:5000],
        fecha_orden=fecha_orden or timezone.now(),
        contacto=contacto[:150],
        dirigida_a=contacto[:150],
        telefono=telefono[:50],
        soporte=soporte.name,
        soporte_contenido=soporte_contenido,
        soporte_nombre=soporte.name[:255],
        creado_por=request.user,
    )
    messages.success(request, "Cotización manual creada correctamente.")
    return redirect("listar_cotizaciones_tecnicas")


@login_required(login_url="login")
@user_passes_test(puede_gestionar_cotizaciones, login_url="home")
def buscar_cliente_mantenimiento(request):
    codigo = (request.GET.get("codigo") or "").strip()
    if not codigo:
        return JsonResponse({"encontrado": False})
    mantenimiento = (
        Mantenimiento.objects.filter(codigo__iexact=codigo)
        .exclude(cliente__isnull=True)
        .exclude(cliente="")
        .order_by("-fecha_creacion_servicio", "-fecha_registro", "-pk")
        .first()
    )
    if not mantenimiento:
        return JsonResponse({"encontrado": False})
    return JsonResponse({
        "encontrado": True,
        "cliente": mantenimiento.cliente or "",
        "direccion": mantenimiento.direccion or "",
    })


@login_required(login_url="login")
@user_passes_test(puede_gestionar_cotizaciones, login_url="home")
@require_POST
def importar_cotizacion_visita_pdf(request):
    soporte = request.FILES.get("soporte")
    if not soporte or not soporte.name.lower().endswith(".pdf"):
        messages.error(request, "Selecciona una orden de visita en formato PDF.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=importar')
    if soporte.size > 10 * 1024 * 1024:
        messages.error(request, "El PDF no puede superar 10 MB.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=importar')
    try:
        datos = analizar_visita_tecnica_cotizacion(soporte)
    except (ValueError, OSError) as error:
        messages.error(request, f"No fue posible importar la orden: {error}")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=importar')
    registro = (datos.get("registro") or "").strip()[:50]
    if not registro:
        messages.error(request, "La orden no contiene un número de registro válido.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=importar')
    if CotizacionServicioTecnico.objects.filter(registro=registro).exists():
        messages.error(request, f"El registro {registro} ya fue importado.")
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}?error=importar')

    clave_tecnico = normalizar_clave(datos["tecnico_nombre"]).replace(" ", "")
    tecnico = next(
        (
            item for item in Tecnico.objects.all()
            if normalizar_clave(item.nombre).replace(" ", "") == clave_tecnico
        ),
        None,
    )
    soporte.seek(0)
    soporte_contenido = soporte.read()
    soporte.seek(0)
    CotizacionServicioTecnico.objects.create(
        registro=registro,
        codigo=(datos.get("codigo") or "0")[:50],
        cliente=datos["cliente"][:100],
        direccion=datos["direccion"][:100],
        descripcion=datos["descripcion"][:5000],
        fecha_orden=datos["fecha_orden"] or timezone.now(),
        contacto=datos["contacto"][:150],
        dirigida_a=datos["contacto"][:150],
        telefono=datos["telefono"][:50],
        omt=datos["omt"][:150],
        actividad_realizada=datos["actividad_realizada"][:5000],
        tecnico=tecnico,
        soporte=soporte.name,
        soporte_contenido=soporte_contenido,
        soporte_nombre=soporte.name[:255],
        creado_por=request.user,
    )
    messages.success(
        request,
        f"Orden {datos['registro']} importada y guardada con su soporte PDF.",
    )
    return redirect("listar_cotizaciones_tecnicas")


@login_required(login_url="login")
@user_passes_test(puede_gestionar_cotizaciones, login_url="home")
@require_POST
def gestionar_cotizacion_tecnica(request, pk):
    cotizacion = get_object_or_404(CotizacionServicioTecnico, pk=pk)
    accion = (request.POST.get("accion") or "").upper()
    ahora = timezone.now()

    if accion == "ENVIAR":
        ejecutivo_id = request.POST.get("ejecutivo")
        medio = (request.POST.get("medio_envio") or "").upper()
        dirigida_a = (request.POST.get("dirigida_a") or "").strip()
        numero_cotizacion = (request.POST.get("numero_cotizacion") or "").strip()
        ejecutivo = Ejecutivo.objects.filter(pk=ejecutivo_id).first()
        if (
            not ejecutivo
            or medio not in {"CELULAR", "CORREO"}
            or not dirigida_a
            or not numero_cotizacion
        ):
            messages.error(
                request,
                "Selecciona el ejecutivo, el medio, el destinatario y el número de cotización.",
            )
        elif cotizacion.estado != "REGISTRADA":
            messages.error(request, "Esta cotización ya fue enviada.")
        else:
            cotizacion.ejecutivo = ejecutivo
            cotizacion.medio_envio = medio
            cotizacion.dirigida_a = dirigida_a[:150]
            cotizacion.numero_cotizacion = numero_cotizacion[:80]
            cotizacion.estado = "PENDIENTE"
            cotizacion.fecha_envio = ahora
            cotizacion.save(update_fields=[
                "ejecutivo", "medio_envio", "dirigida_a", "numero_cotizacion",
                "estado", "fecha_envio"
            ])
            messages.success(request, "Cotización marcada como enviada y pendiente.")
    elif accion in {"APROBAR", "RECHAZAR"}:
        if cotizacion.estado != "PENDIENTE":
            messages.error(request, "Solo se puede gestionar una cotización pendiente.")
        else:
            nota = (request.POST.get("nota_rechazo") or "").strip()
            if accion == "RECHAZAR" and not nota:
                messages.error(request, "Escribe el motivo del rechazo.")
            else:
                cotizacion.estado = "APROBADA" if accion == "APROBAR" else "RECHAZADA"
                cotizacion.nota_rechazo = nota[:5000] if accion == "RECHAZAR" else ""
                cotizacion.fecha_gestion = ahora
                cotizacion.save(update_fields=["estado", "nota_rechazo", "fecha_gestion"])
                messages.success(request, f"Cotización {cotizacion.get_estado_display().lower()}.")
    elif accion in {"SEGUIMIENTO", "GESTIONADA"}:
        if cotizacion.estado != "PENDIENTE":
            messages.error(request, "La cotización ya no está pendiente.")
        else:
            nota = (request.POST.get("nota_seguimiento") or "").strip()[:5000]
            if not nota:
                messages.error(request, "Escribe una nota sobre el seguimiento realizado.")
            else:
                numero = cotizacion.seguimientos.count() + 1
                SeguimientoCotizacionTecnica.objects.create(
                    cotizacion=cotizacion,
                    numero=numero,
                    nota=nota,
                    fecha=ahora,
                    usuario=request.user,
                )
                cotizacion.accion_seguimiento = "GESTIONADA"
                cotizacion.nota_seguimiento = nota
                cotizacion.fecha_seguimiento = ahora
                cotizacion.save(update_fields=[
                    "accion_seguimiento", "nota_seguimiento", "fecha_seguimiento"
                ])
                messages.success(request, "Seguimiento registrado; la cotización continúa pendiente.")
    else:
        messages.error(request, "Acción de cotización no válida.")

    destino = reverse("listar_cotizaciones_tecnicas")
    busqueda = (request.POST.get("busqueda") or "").strip()
    if busqueda:
        destino += "?" + urlencode({"busqueda": busqueda})
    return redirect(f"{destino}#cotizacion-{cotizacion.pk}")


@login_required(login_url="login")
@user_passes_test(puede_gestionar_cotizaciones, login_url="home")
def descargar_soporte_cotizacion(request, pk):
    cotizacion = get_object_or_404(CotizacionServicioTecnico, pk=pk)
    nombre = (
        cotizacion.soporte_nombre
        or (cotizacion.soporte.name.rsplit("/", 1)[-1] if cotizacion.soporte else "")
        or f"soporte-{cotizacion.registro}.pdf"
    )
    if cotizacion.soporte_contenido:
        return FileResponse(
            BytesIO(bytes(cotizacion.soporte_contenido)),
            content_type="application/pdf",
            as_attachment=False,
            filename=nombre,
        )
    contenido = None
    try:
        with cotizacion.soporte.open("rb") as archivo:
            contenido = archivo.read()
    except (FileNotFoundError, OSError, ValueError):
        pass

    # Algunas filas antiguas guardaron únicamente el nombre (o una ruta que
    # cambió entre despliegues). Se permite recuperar el original del árbol de
    # medios solo cuando los archivos coincidentes tienen contenido idéntico.
    if contenido is None:
        directorio = Path(settings.MEDIA_ROOT) / "cotizaciones_tecnicas"
        nombre_guardado = Path(cotizacion.soporte.name or "").name.casefold()
        registro = re.sub(r"\W+", "", cotizacion.registro or "").casefold()
        candidatos = []
        if directorio.exists():
            for ruta in directorio.rglob("*.pdf"):
                nombre_ruta = ruta.name.casefold()
                nombre_normalizado = re.sub(r"\W+", "", ruta.stem).casefold()
                if (
                    (nombre_guardado and nombre_ruta == nombre_guardado)
                    or (registro and registro in nombre_normalizado)
                ):
                    candidatos.append(ruta)
        contenidos = []
        for ruta in candidatos:
            try:
                datos = ruta.read_bytes()
            except OSError:
                continue
            if datos and datos not in contenidos:
                contenidos.append(datos)
        if len(contenidos) == 1:
            contenido = contenidos[0]

    if contenido is None:
        messages.error(
            request,
            "El soporte PDF original no está disponible en el almacenamiento. "
            "El soporte de una cotización no se puede reemplazar.",
        )
        return redirect(f'{reverse("listar_cotizaciones_tecnicas")}#cotizacion-{cotizacion.pk}')
    # Los soportes creados antes de almacenarlos en PostgreSQL conservaban solo
    # la ruta del archivo. Al abrirlos por primera vez se guarda exactamente el
    # mismo PDF en la base de datos para que sobreviva a futuros despliegues.
    cotizacion.soporte_contenido = contenido
    cotizacion.soporte_nombre = nombre[:255]
    cotizacion.save(update_fields=["soporte_contenido", "soporte_nombre"])
    return FileResponse(
        BytesIO(contenido),
        content_type="application/pdf",
        as_attachment=False,
        filename=nombre,
    )


@login_required(login_url="login")
@user_passes_test(puede_gestionar_cotizaciones, login_url="home")
def exportar_cotizaciones_excel(request):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Cotizaciones"
    hoja.append([
        "Fecha de la orden", "Código", "Registro / solicitante", "Fecha de carga",
        "Horas orden a carga", "Cliente", "Dirección", "Descripción", "Técnico",
        "Ejecutivo", "Medio de envío", "Dirigida a", "Teléfono",
        "Número de cotización", "Estado", "Fecha de envío",
        "Horas carga a envío", "Fecha de gestión", "Último seguimiento",
    ])
    cotizaciones = CotizacionServicioTecnico.objects.select_related(
        "tecnico", "ejecutivo"
    ).order_by("-fecha_orden", "-pk")
    for cotizacion in cotizaciones:
        def fecha_local(valor):
            return timezone.localtime(valor).strftime("%Y-%m-%d %H:%M") if valor else ""

        hoja.append([
            fecha_local(cotizacion.fecha_orden),
            cotizacion.codigo,
            cotizacion.registro,
            fecha_local(cotizacion.fecha_registro),
            round(
                (cotizacion.fecha_registro - cotizacion.fecha_orden).total_seconds() / 3600,
                2,
            ) if cotizacion.fecha_registro and cotizacion.fecha_orden else "",
            cotizacion.cliente,
            cotizacion.direccion,
            cotizacion.descripcion,
            cotizacion.tecnico.nombre if cotizacion.tecnico else "",
            cotizacion.ejecutivo.nombre if cotizacion.ejecutivo else "",
            cotizacion.get_medio_envio_display() if cotizacion.medio_envio else "",
            cotizacion.dirigida_a,
            cotizacion.telefono,
            cotizacion.numero_cotizacion,
            cotizacion.get_estado_display(),
            fecha_local(cotizacion.fecha_envio),
            round(
                (cotizacion.fecha_envio - cotizacion.fecha_registro).total_seconds() / 3600,
                2,
            ) if cotizacion.fecha_envio and cotizacion.fecha_registro else "",
            fecha_local(cotizacion.fecha_gestion),
            fecha_local(cotizacion.fecha_seguimiento),
        ])
    for columna in hoja.columns:
        letra = columna[0].column_letter
        hoja.column_dimensions[letra].width = min(
            max(len(str(celda.value or "")) for celda in columna) + 2,
            45,
        )
    salida = BytesIO()
    libro.save(salida)
    salida.seek(0)
    respuesta = HttpResponse(
        salida.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    respuesta["Content-Disposition"] = (
        f'attachment; filename="cotizaciones-{timezone.localdate():%Y-%m-%d}.xlsx"'
    )
    return respuesta


@login_required(login_url="login")
@require_POST
def leer_notificaciones_tecnico(request):
    tecnico = _tecnico_del_usuario(request.user)
    if not tecnico:
        return JsonResponse({"ok": False}, status=403)
    for notificacion in tecnico.notificaciones.filter(leida=False):
        notificacion.leida = True
        notificacion.save(update_fields=["leida"])
    return JsonResponse({"ok": True})


def manifiesto_tecnico(request):
    return JsonResponse({
        "name": "Servicios técnicos SESUR",
        "short_name": "SESUR Técnico",
        "start_url": reverse("portal_tecnico"),
        "display": "standalone",
        "background_color": "#f1f5f9",
        "theme_color": "#0d6efd",
        "icons": [{
            "src": "/static/sesur/img/logosesur.png",
            "sizes": "192x192",
            "type": "image/png",
        }],
    }, content_type="application/manifest+json")


@never_cache
def service_worker_tecnico(request):
    contenido = render(request, "mantenimientos/service-worker.js", content_type="application/javascript")
    contenido["Service-Worker-Allowed"] = "/"
    return contenido

# VISTA DE DASHBOARD


@login_required(login_url='login')
@user_passes_test(puede_ver_dashboard)
def dashboard_instalaciones(request):
    seccion = (request.GET.get("seccion") or "resumen").strip().lower()
    secciones_validas = {"resumen", "instalaciones", "mantenimientos", "almacen", "facturacion"}
    if seccion not in secciones_validas:
        seccion = "resumen"
    mes = request.GET.get('mes')
    ciudades_seleccionadas = request.GET.getlist('ciudad')
    fecha_corte = timezone.localdate()
    indicador_desde = parse_date(request.GET.get("indicador_desde") or "")
    indicador_hasta = parse_date(request.GET.get("indicador_hasta") or "")
    if not indicador_desde:
        indicador_desde = fecha_corte.replace(day=1)
    if not indicador_hasta:
        indicador_hasta = fecha_corte
    if indicador_desde > indicador_hasta:
        indicador_desde, indicador_hasta = indicador_hasta, indicador_desde
    fecha_mes = None

    qs = CuadroInsta.objects.all()

    if mes:
        try:
            fecha_mes = datetime.strptime(mes, "%Y-%m")
            qs = qs.filter(
                fecha__year=fecha_mes.year,
                fecha__month=fecha_mes.month
            )
        except ValueError:
            mes = ""

    if ciudades_seleccionadas:
        qs = qs.filter(ciudad__in=ciudades_seleccionadas)

    total_pvg = qs.count()

    # INSTALACIÓN / EFICIENCIA PVG

    anulados_instalacion = qs.filter(
        estado__iexact="ANULADO"
    ).count()

    registros_instalacion = qs.exclude(
        estado__iexact="ANULADO"
    )

    total_instalacion = 0

    cumple_instalacion = 0
    fuera_instalacion = 0
    pendiente_instalacion = 0
    suma_dias_instalacion = 0
    total_con_dias = 0
    inconsistencias_instalacion = 0

    for item in registros_instalacion:

        if not item.fecha_inicio:
            pendiente_instalacion += 1
            continue

        if item.fecha_inicio > fecha_corte:
            pendiente_instalacion += 1
            continue

        dias = item.dias_instalacion

        if dias is not None:
            if dias < 0:
                inconsistencias_instalacion += 1
                continue

            suma_dias_instalacion += dias
            total_con_dias += 1
            total_instalacion += 1

            if dias <= 8:
                cumple_instalacion += 1
            else:
                fuera_instalacion += 1
        else:
            pendiente_instalacion += 1

    eficiencia_instalacion = 0
    promedio_instalacion = 0

    if total_con_dias > 0:
        eficiencia_instalacion = round(
            (cumple_instalacion / total_con_dias) * 100, 2
        )

    if total_con_dias > 0:
        promedio_instalacion = round(
            suma_dias_instalacion / total_con_dias, 2
        )

        # PVG INGRESADOS Y EJECUTADOS EN EL MISMO RANGO

    pvg_ingresados_rango = 0
    pvg_ejecutados_rango = 0
    eficiencia_ejecucion_rango = 0

    if fecha_mes:
        pvg_ingresados_rango = qs.exclude(
            estado__iexact="ANULADO"
        ).count()

        pvg_ejecutados_rango = qs.exclude(
            estado__iexact="ANULADO"
        ).filter(
            fecha_inicio__isnull=False,
            fecha_inicio__year=fecha_mes.year,
            fecha_inicio__month=fecha_mes.month
        ).count()

    if pvg_ingresados_rango > 0:
        eficiencia_ejecucion_rango = round(
            (pvg_ejecutados_rango / pvg_ingresados_rango) * 100, 2
        )

    pendientes_ejecucion_rango = (
        pvg_ingresados_rango - pvg_ejecutados_rango
    )

    # ALMACÉN
    registros_almacen = qs.exclude(
        estado__iexact="ANULADO"
    ).filter(finaliza__isnull=False)

    total_almacen = 0
    cumple_almacen = 0
    suma_dias_almacen = 0
    total_almacen_completados = 0
    pendientes_almacen = 0
    vencidos_almacen = 0
    inconsistencias_almacen = 0

    for item in registros_almacen:
        if not item.fecha_alistado:
            pendientes_almacen += 1
            if (fecha_corte - item.finaliza).days > 2:
                vencidos_almacen += 1
                total_almacen += 1
            continue

        dias = item.dias_para_alistar

        if dias is not None:
            if dias < 0:
                inconsistencias_almacen += 1
                continue

            suma_dias_almacen += dias
            total_almacen += 1
            total_almacen_completados += 1

            if dias <= 2:
                cumple_almacen += 1

    eficiencia_almacen = 0
    promedio_almacen = 0

    if total_almacen > 0:
        eficiencia_almacen = round(
            (cumple_almacen / total_almacen) * 100, 2
        )
    if total_almacen_completados > 0:
        promedio_almacen = round(
            suma_dias_almacen / total_almacen_completados, 2
        )

    fuera_almacen = total_almacen - cumple_almacen

    # FACTURACIÓN
    registros_facturacion = qs.exclude(
        estado__iexact="ANULADO"
    ).filter(fecha_alistado__isnull=False)

    total_facturacion = 0
    cumple_facturacion = 0
    suma_dias_facturacion = 0
    total_facturacion_completados = 0
    pendientes_facturacion = 0
    vencidos_facturacion = 0
    inconsistencias_facturacion = 0

    for item in registros_facturacion:
        if not item.fecha_facturacion:
            pendientes_facturacion += 1
            if (fecha_corte - item.fecha_alistado).days > 2:
                vencidos_facturacion += 1
                total_facturacion += 1
            continue

        dias = item.dias_para_facturar

        if dias is not None:
            if dias < 0:
                inconsistencias_facturacion += 1
                continue

            suma_dias_facturacion += dias
            total_facturacion += 1
            total_facturacion_completados += 1

            if dias <= 2:
                cumple_facturacion += 1

    eficiencia_facturacion = 0
    promedio_facturacion = 0

    if total_facturacion > 0:
        eficiencia_facturacion = round(
            (cumple_facturacion / total_facturacion) * 100, 2
        )
    if total_facturacion_completados > 0:
        promedio_facturacion = round(
            suma_dias_facturacion / total_facturacion_completados, 2
        )

    fuera_facturacion = total_facturacion - cumple_facturacion

    facturados = registros_facturacion.filter(
        estado_facturacion="FACTURADO"
    ).count()
    retenidos = registros_facturacion.filter(
        estado_facturacion="RETENIDO"
    ).count()

    # CIERRE TOTAL
    registros_cierre = qs.filter(
        finaliza__isnull=False,
        fecha_facturacion__isnull=False
    )

    total_cierre = registros_cierre.count()
    suma_cierre = 0

    for item in registros_cierre:
        dias = item.dias_cierre_total

        if dias is not None:
            suma_cierre += dias

    promedio_cierre_total = 0

    if total_cierre > 0:
        promedio_cierre_total = round(suma_cierre / total_cierre, 2)

    ciudades_instalaciones = (
        CuadroInsta.objects
        .exclude(ciudad__isnull=True)
        .exclude(ciudad="")
        .values_list('ciudad', flat=True)
        .distinct()
        .order_by('ciudad')
    )
    ciudades_mantenimientos = (
        Mantenimiento.objects.exclude(ciudad__isnull=True).exclude(ciudad="")
        .values_list("ciudad", flat=True).distinct()
    )
    ciudades = sorted(set(ciudades_instalaciones) | set(ciudades_mantenimientos))

    contexto = {
        'seccion': seccion,
        'mes': mes,
        'ciudades_seleccionadas': ciudades_seleccionadas,
        'ciudades': ciudades,

        'total_pvg': total_pvg,

        'total_instalacion': total_instalacion,
        'cumple_instalacion': cumple_instalacion,
        'fuera_instalacion': fuera_instalacion,
        'pendiente_instalacion': pendiente_instalacion,
        'anulados_instalacion': anulados_instalacion,
        'eficiencia_instalacion': eficiencia_instalacion,
        'promedio_instalacion': promedio_instalacion,
        'inconsistencias_instalacion': inconsistencias_instalacion,

        'total_almacen': total_almacen,
        'cumple_almacen': cumple_almacen,
        'fuera_almacen': fuera_almacen,
        'eficiencia_almacen': eficiencia_almacen,
        'promedio_almacen': promedio_almacen,
        'pendientes_almacen': pendientes_almacen,
        'vencidos_almacen': vencidos_almacen,
        'inconsistencias_almacen': inconsistencias_almacen,

        'total_facturacion': total_facturacion,
        'cumple_facturacion': cumple_facturacion,
        'fuera_facturacion': fuera_facturacion,
        'eficiencia_facturacion': eficiencia_facturacion,
        'promedio_facturacion': promedio_facturacion,
        'pendientes_facturacion': pendientes_facturacion,
        'vencidos_facturacion': vencidos_facturacion,
        'inconsistencias_facturacion': inconsistencias_facturacion,
        'facturados': facturados,
        'retenidos': retenidos,

        'total_cierre': total_cierre,
        'promedio_cierre_total': promedio_cierre_total,
        'pvg_ingresados_rango': pvg_ingresados_rango,
        'pvg_ejecutados_rango': pvg_ejecutados_rango,
        'pendientes_ejecucion_rango': pendientes_ejecucion_rango,
        'eficiencia_ejecucion_rango': eficiencia_ejecucion_rango,
        'puede_ver_indicadores_mantenimiento': puede_gestionar_mantenimientos(request.user),
        'detalle_instalaciones': qs.order_by('-fecha', '-pk')[:500],
        'detalle_almacen': registros_almacen.order_by('-finaliza', '-pk')[:500],
        'detalle_facturacion': registros_facturacion.order_by('-fecha_alistado', '-pk')[:500],
    }

    if contexto['puede_ver_indicadores_mantenimiento']:
        contexto.update(indicadores_atencion_mantenimientos(
            indicador_desde, indicador_hasta, ciudades_seleccionadas
        ))
        contexto.update(indicadores_ocupacion_tecnicos(
            indicador_desde, indicador_hasta
        ))

    return render(request, 'dashboard_instalaciones.html', contexto)


# VISTA PARA EL ALMACENISTA

@login_required(login_url='login')
@user_passes_test(puede_alistar)
def alistar_instalacion(request, id):
    instalacion = get_object_or_404(CuadroInsta, id=id)

    if request.method != "POST":
        return JsonResponse({
            "ok": False,
            "mensaje": "Método no permitido."
        }, status=405)

    if instalacion.estado != "LEGALIZADO" or not instalacion.orden:
        return JsonResponse({
            "ok": False,
            "mensaje": "No se puede alistar una instalación sin orden legalizada."
        }, status=400)

    instalacion.alistado = True
    instalacion.save()

    return JsonResponse({
        "ok": True,
        "fecha": instalacion.fecha_alistado.strftime("%Y-%m-%d"),
        "dias": instalacion.dias_para_alistar,
        "id": instalacion.id,
        "url_facturar": reverse(
            "facturar_instalacion",
            args=[instalacion.id]
        )
    })

# VISTA PARA BOTON DE CONFIGURACION


@login_required(login_url='login')
@user_passes_test(puede_configurar_usuarios, login_url='home')
def configuracion_usuarios(request):
    grupos_base = [
        'Administrador',
        'Coordinador',
        'Programador',
        'Almacen',
        'Facturacion',
        'Visor',
        'Tecnico',
        'Cotizaciones',
        'Monitoreo',
        'Administrador Monitoreo',
    ]

    for nombre in grupos_base:
        Group.objects.get_or_create(name=nombre)

    configuracion_monitoreo_limitada = (
        not request.user.is_superuser
        and pertenece_grupo(request.user, 'Administrador Monitoreo')
    )
    grupos_permitidos = ['Monitoreo'] if configuracion_monitoreo_limitada else grupos_base

    formulario_creacion = UserCreationForm()
    grupos_creacion_seleccionados = request.POST.getlist('grupo_ids')
    if not grupos_creacion_seleccionados and request.POST.get('grupo_id'):
        grupos_creacion_seleccionados = [request.POST.get('grupo_id')]

    if request.method == 'POST':
        accion = request.POST.get('accion', 'actualizar_usuario')

        if accion == 'crear_usuario':
            formulario_creacion = UserCreationForm(request.POST)
            tecnico_id = request.POST.get('tecnico_id')
            grupos_seleccionados = Group.objects.filter(
                id__in=grupos_creacion_seleccionados,
                name__in=grupos_permitidos,
            )
            tecnico = None

            if not grupos_seleccionados.exists():
                formulario_creacion.add_error(None, "Debes seleccionar al menos un rol.")

            if tecnico_id:
                tecnico = get_object_or_404(Tecnico, id=tecnico_id)
                if tecnico.usuario:
                    formulario_creacion.add_error(
                        None, "Ese técnico ya está vinculado a otro usuario."
                    )

            if grupos_seleccionados.filter(name='Tecnico').exists() and not tecnico:
                formulario_creacion.add_error(
                    None, "El rol Técnico debe estar vinculado a un técnico."
                )

            if formulario_creacion.is_valid():
                usuario = formulario_creacion.save(commit=False)
                usuario.first_name = (request.POST.get('first_name') or '').strip()
                usuario.last_name = (request.POST.get('last_name') or '').strip()
                usuario.email = (request.POST.get('email') or '').strip()
                usuario.is_staff = False
                usuario.is_superuser = False
                usuario.save()

                usuario.groups.set(grupos_seleccionados)

                if tecnico:
                    tecnico.usuario = usuario
                    tecnico.save(update_fields=['usuario'])

                messages.success(
                    request, f"Usuario {usuario.username} creado correctamente."
                )
                return redirect('configuracion_usuarios')

            messages.error(
                request, "No se pudo crear el usuario. Revisa los campos indicados."
            )

        else:
            if configuracion_monitoreo_limitada:
                messages.error(request, "Este perfil sólo puede crear usuarios de Monitoreo.")
                return redirect('configuracion_usuarios')
            usuario_id = request.POST.get('usuario_id')
            grupo_ids = request.POST.getlist('grupo_ids')
            if not grupo_ids and request.POST.get('grupo_id'):
                grupo_ids = [request.POST.get('grupo_id')]
            tecnico_id = request.POST.get('tecnico_id')

            usuario = get_object_or_404(User, id=usuario_id)
            grupos_seleccionados = Group.objects.filter(
                id__in=grupo_ids,
                name__in=grupos_base,
            )
            if not grupos_seleccionados.exists():
                messages.error(request, "Debes seleccionar al menos un rol.")
                return redirect('configuracion_usuarios')

            tecnico = None
            if tecnico_id:
                tecnico = get_object_or_404(Tecnico, id=tecnico_id)
                if tecnico.usuario and tecnico.usuario != usuario:
                    messages.error(request, "Ese técnico ya está vinculado a otro usuario.")
                    return redirect('configuracion_usuarios')
            if grupos_seleccionados.filter(name='Tecnico').exists() and not tecnico:
                messages.error(request, "El rol Técnico debe estar vinculado a un técnico.")
                return redirect('configuracion_usuarios')
            usuario.groups.set(grupos_seleccionados)
            for tecnico_anterior in Tecnico.objects.filter(usuario=usuario).exclude(pk=getattr(tecnico, "pk", None)):
                tecnico_anterior.usuario = None
                tecnico_anterior.save(update_fields=["usuario"])
            if tecnico:
                tecnico.usuario = usuario
                tecnico.save(update_fields=["usuario"])

            messages.success(
                request,
                f"Roles actualizados para el usuario {usuario.username}."
            )

            return redirect('configuracion_usuarios')

    usuarios = User.objects.all().order_by('username')
    if configuracion_monitoreo_limitada:
        usuarios = usuarios.filter(groups__name='Monitoreo').distinct()
    grupos = Group.objects.filter(name__in=grupos_permitidos).order_by('name')
    for campo in formulario_creacion.fields.values():
        campo.widget.attrs['class'] = 'form-control'

    return render(request, 'configuracion_usuarios.html', {
        'usuarios': usuarios,
        'grupos': grupos,
        'tecnicos': Tecnico.objects.select_related("usuario").order_by("nombre"),
        'formulario_creacion': formulario_creacion,
        'grupos_creacion_seleccionados': grupos_creacion_seleccionados,
        'configuracion_monitoreo_limitada': configuracion_monitoreo_limitada,
    })


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser, login_url='home')
def configuracion_horarios_tecnicos(request):
    asegurar_horarios_tecnicos()
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "guardar_horarios":
            for jornada in JornadaLaboralTecnico.objects.all():
                prefijo = f"{jornada.tipo}_{jornada.dia_semana}"
                jornada.entrada_1 = parse_time(request.POST.get(f"{prefijo}_entrada_1") or "")
                jornada.salida_1 = parse_time(request.POST.get(f"{prefijo}_salida_1") or "")
                jornada.entrada_2 = parse_time(request.POST.get(f"{prefijo}_entrada_2") or "")
                jornada.salida_2 = parse_time(request.POST.get(f"{prefijo}_salida_2") or "")
                jornada.activo = request.POST.get(f"{prefijo}_activo") == "1"
                jornada.save()
            messages.success(request, "Horarios técnicos actualizados.")
        elif accion == "agregar_festivo":
            fecha = parse_date(request.POST.get("fecha") or "")
            nombre = (request.POST.get("nombre") or "DÍA NO LABORAL").strip().upper()
            if fecha:
                DiaNoLaboralTecnico.objects.update_or_create(
                    fecha=fecha, defaults={"nombre": nombre}
                )
                messages.success(request, "Día no laboral guardado.")
            else:
                messages.error(request, "Indique una fecha válida.")
        elif accion == "eliminar_festivo":
            DiaNoLaboralTecnico.objects.filter(pk=request.POST.get("festivo_id")).delete()
            messages.success(request, "Día no laboral eliminado.")
        elif accion == "guardar_rotacion":
            fecha_sabado = parse_date(request.POST.get("fecha_sabado") or "")
            tecnico_id = request.POST.get("tecnico")
            if fecha_sabado and fecha_sabado.weekday() != 5:
                messages.error(request, "La fecha de rotación debe ser un sábado.")
            elif fecha_sabado and tecnico_id:
                RotacionTecnicoDisponible.objects.update_or_create(
                    fecha_sabado=fecha_sabado, defaults={"tecnico_id": tecnico_id}
                )
                messages.success(request, "Rotación del sábado guardada.")
            else:
                messages.error(request, "Seleccione un sábado y el técnico disponible.")
        elif accion == "eliminar_rotacion":
            RotacionTecnicoDisponible.objects.filter(pk=request.POST.get("rotacion_id")).delete()
            messages.success(request, "Rotación eliminada.")
        elif accion == "guardar_tecnicos_indicadores":
            seleccionados = {
                int(valor) for valor in request.POST.getlist("tecnicos_indicadores")
                if valor.isdigit()
            }
            for tecnico in Tecnico.objects.all():
                habilitado = tecnico.pk in seleccionados
                if tecnico.incluir_indicadores != habilitado:
                    tecnico.incluir_indicadores = habilitado
                    tecnico.save(update_fields=["incluir_indicadores"])
            messages.success(request, "Técnicos de los indicadores actualizados.")
        return redirect("configuracion_horarios_tecnicos")

    return render(request, "configuracion_horarios_tecnicos.html", {
        "jornadas_base": JornadaLaboralTecnico.objects.filter(tipo="BASE"),
        "jornadas_disponible": JornadaLaboralTecnico.objects.filter(tipo="DISPONIBLE"),
        "festivos": DiaNoLaboralTecnico.objects.all()[:30],
        "rotaciones": RotacionTecnicoDisponible.objects.select_related("tecnico")[:24],
        "tecnicos": Tecnico.objects.all().order_by("nombre"),
        "fecha_actual": timezone.localdate().isoformat(),
    })


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser, login_url='home')
def registro_movimientos(request):
    registros = RegistroAuditoria.objects.select_related('usuario')
    usuario_id = (request.GET.get('usuario') or '').strip()
    accion = (request.GET.get('accion') or '').strip()
    modulo = (request.GET.get('modulo') or '').strip()
    busqueda = (request.GET.get('busqueda') or '').strip()
    fecha_desde = parse_date(request.GET.get('desde') or '')
    fecha_hasta = parse_date(request.GET.get('hasta') or '')

    if usuario_id.isdigit():
        registros = registros.filter(usuario_id=usuario_id)
    if accion in dict(RegistroAuditoria.ACCIONES):
        registros = registros.filter(accion=accion)
    if modulo:
        registros = registros.filter(modulo=modulo)
    if busqueda:
        registros = registros.filter(
            Q(objeto__icontains=busqueda)
            | Q(objeto_id__icontains=busqueda)
            | Q(modelo__icontains=busqueda)
            | Q(ruta__icontains=busqueda)
            | Q(usuario__username__icontains=busqueda)
        )
    if fecha_desde:
        registros = registros.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        registros = registros.filter(fecha__date__lte=fecha_hasta)

    pagina = Paginator(registros, 50).get_page(request.GET.get('pagina'))
    parametros = request.GET.copy()
    parametros.pop('pagina', None)
    return render(request, 'registro_movimientos.html', {
        'pagina': pagina,
        'usuarios_auditoria': User.objects.filter(
            movimientos_aplicacion__isnull=False
        ).distinct().order_by('username'),
        'modulos_auditoria': RegistroAuditoria.objects.order_by().values_list(
            'modulo', flat=True
        ).distinct(),
        'acciones_auditoria': RegistroAuditoria.ACCIONES,
        'filtros': request.GET,
        'querystring': parametros.urlencode(),
    })


# VISTA DE EXPORTAR MANTENIMIENTOS

@login_required(login_url='login')
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
def exportar_mantenimientos(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Mantenimientos"

    encabezados = [
        "Número ticket",
        "Estado ticket",
        "Fecha registro",
        "Código",
        "Cliente",
        "Ciudad",
        "Dirección",
        "Tipo servicio",
        "Tipo falla",
        "Técnico",
        "Hora entrada",
        "Hora salida",
        "Duración",
        "Orden",
        "Realizado",
        "Novedad",
        "Observación",
        "Pendiente",
    ]

    ws.append(encabezados)

    mantenimientos = (
        Mantenimiento.objects
        .select_related("tecnico")
        .order_by("-fecha_registro")
    )

    for m in mantenimientos:
        ws.append([
            m.numero_ticket or "",
            m.estado_ticket or "",
            timezone.localtime(m.fecha_visible).strftime(
                "%Y-%m-%d %H:%M") if m.fecha_visible else "",
            m.codigo or "",
            m.cliente or "",
            m.ciudad or "",
            m.direccion or "",
            m.get_tipo_servicio_display() if m.tipo_servicio else "",
            m.get_tipo_falla_display() if m.tipo_falla else "",
            m.tecnico.nombre if m.tecnico else "",
            m.hora_entrada.strftime("%H:%M") if m.hora_entrada else "",
            m.hora_salida.strftime("%H:%M") if m.hora_salida else "",
            m.duracion_servicio or "---",
            m.orden or "",
            m.realizado.strftime("%Y-%m-%d") if m.realizado else "",
            m.novedad or "",
            m.observacion or "",
            m.pendiente or "",
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="mantenimientos.xlsx"'

    wb.save(response)
    return response


# VISTA DE IMPORTACION DE MANTENIMIENTOS
@login_required(login_url='login')
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
def importar_mantenimientos_pdf(request):

    if request.method == "POST":
        archivo = (
            request.FILES.get("archivo_pdf")
            or request.FILES.get("archivo")
            or next(iter(request.FILES.values()), None)
        )

        if not archivo:
            messages.error(request, "Debe seleccionar un archivo PDF o Excel.")
            return redirect("importar_mantenimientos_pdf")

        extension = archivo.name.lower().rsplit(".", 1)[-1] if "." in archivo.name else ""
        if extension not in {"pdf", "xlsx"}:
            messages.error(request, "Formato no permitido. Seleccione un archivo PDF o Excel (.xlsx).")
            return redirect("importar_mantenimientos_pdf")

        actualizar_existentes = (
            request.POST.get("actualizar_existentes") == "1"
        )
        try:
            analizador = analizar_pdf_mantenimientos if extension == "pdf" else analizar_excel_mantenimientos
            resultados = analizador(archivo, actualizar_existentes=actualizar_existentes)
        except (ValueError, OSError) as error:
            messages.error(request, f"No fue posible leer el archivo: {error}")
            return redirect("importar_mantenimientos_pdf")

        request.session["preview_mantenimientos_pdf"] = preparar_resultados_para_session(
            resultados)
        request.session["actualizar_mantenimientos_pdf"] = actualizar_existentes

        total = len(resultados)
        importables = sum(1 for r in resultados if r["importable"])
        advertencias = sum(1 for r in resultados if r["advertencias"])

        return render(
            request,
            "mantenimientos/preview_importar_pdf.html",
            {
                "resultados": resultados,
                "total": total,
                "importables": importables,
                "advertencias": advertencias,
                "formato_origen": extension.upper(),
            }
        )

    return render(
        request,
        "mantenimientos/importar_pdf.html"
    )


@login_required(login_url='login')
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
def confirmar_importar_mantenimientos_pdf(request):

    if request.method != "POST":
        return redirect("importar_mantenimientos_pdf")

    resultados = restaurar_resultados_desde_session(
        request.session.get("preview_mantenimientos_pdf")
    )

    if not resultados:
        messages.error(request, "No hay datos para importar.")
        return redirect("importar_mantenimientos_pdf")

    actualizar_existentes = request.session.get(
        "actualizar_mantenimientos_pdf", False
    )
    resumen = importar_resultados_pdf(
        resultados,
        request.user,
        actualizar_existentes=actualizar_existentes,
    )

    messages.success(
        request,
        f"Importación finalizada. "
        f"Creados: {resumen['creados']}. "
        f"Actualizados: {resumen['actualizados']}. "
        f"Repetidos: {resumen['repetidos']}. "
        f"Errores: {resumen['errores']}."
    )

    request.session.pop("preview_mantenimientos_pdf", None)
    request.session.pop("actualizar_mantenimientos_pdf", None)

    return redirect("listar_mantenimientos")
