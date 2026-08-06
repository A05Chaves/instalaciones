import json
import re
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from django.forms.models import model_to_dict
from django.http import HttpResponse, JsonResponse
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
    DiaNoLaboralTecnico,
    Mantenimiento,
    JornadaLaboralTecnico,
    Tecnico,
    HistorialAsignacionMantenimiento,
    NotificacionTecnico,
    RotacionTecnicoDisponible,
)
from app_instalaciones.models.forms import MantenimientoForm
from app_instalaciones.models.auditoria import RegistroAuditoria

from app_instalaciones.utils.importar_mantenimientos_pdf import (
    analizar_pdf_mantenimientos,
    importar_resultados_pdf,
    preparar_resultados_para_session,
    restaurar_resultados_desde_session,
)
from app_instalaciones.utils.importar_mantenimientos_excel import analizar_excel_mantenimientos

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


def puede_gestionar_mantenimientos(user):
    return (
        user.is_superuser
        or pertenece_grupo(user, "Administrador")
        or pertenece_grupo(user, "Coordinador")
    )


def puede_eliminar_mantenimientos(user):
    return user.is_superuser or pertenece_grupo(user, "Administrador")


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
        return redirect('portal_tecnico' if _tecnico_del_usuario(request.user) else 'home')

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
            return redirect('portal_tecnico' if _tecnico_del_usuario(user) else 'home')
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
        finalizado = servicio.estado_operativo == "FINALIZADO"
        if finalizado:
            realizados_grupo += 1
        if finalizado and fila:
            fila["realizados"] += 1

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
            if timezone.is_naive(atendido):
                atendido = timezone.make_aware(atendido, timezone.get_current_timezone())
            horas_atencion = max(0, (atendido - inicio_medicion).total_seconds() / 3600)
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
            estado_operativo="FINALIZADO"
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
        estado_operativo="FINALIZADO",
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
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
def listar_mantenimientos(request):

    if request.method == "POST":
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
    fecha_filtro_txt = (request.GET.get("fecha") or "").strip()
    fecha_filtro = parse_date(fecha_filtro_txt)
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

    if fecha_filtro:
        mantenimientos = mantenimientos.filter(
            fecha_ordenamiento__date=fecha_filtro
        )

    if estado_filtro == "PENDIENTE":
        mantenimientos = mantenimientos.filter(
            estado_operativo="PENDIENTE", tecnico__isnull=True
        )
    elif estado_filtro == "ASIGNADO":
        mantenimientos = mantenimientos.filter(
            estado_operativo="PENDIENTE", tecnico__isnull=False
        )
    elif estado_filtro in {"EN_PROCESO", "FINALIZADO"}:
        mantenimientos = mantenimientos.filter(
            estado_operativo=estado_filtro
        )

    if alerta_filtro in {"prioritarios", "otros"}:
        mantenimientos = mantenimientos.exclude(estado_operativo="FINALIZADO").filter(
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
        "fecha_filtro": fecha_filtro_txt,
        "estado_filtro": estado_filtro,
        "alerta_filtro": alerta_filtro,
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
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
@require_POST
def mantenimiento_actualizar(request, pk):
    m = get_object_or_404(Mantenimiento, pk=pk)
    tecnico_anterior = m.tecnico
    novedad_anterior = m.novedad or ""

    if m.orden and not request.user.is_superuser:
        return JsonResponse(
            {"ok": False, "error": "El servicio está cerrado y no admite cambios."},
            status=409,
        )
    if m.estado_operativo == "FINALIZADO" and not request.user.is_superuser:
        orden = (request.POST.get("orden") or "").strip()
        if not orden:
            return JsonResponse(
                {"ok": False, "error": "Debe ingresar la orden para cerrar el servicio."},
                status=400,
            )
        m.orden = orden[:50]
        fecha_realizado = parse_date((request.POST.get("realizado") or "").strip())
        m.realizado = fecha_realizado or m.realizado or timezone.localdate()
        error_horas = _aplicar_horas_manuales(m, request.POST)
        if error_horas:
            return JsonResponse({"ok": False, "error": error_horas}, status=400)
        _aplicar_novedad_operador(
            m, request.POST, request.user, novedad_anterior
        )
        m.estado_operativo = "FINALIZADO"
        m.save()
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
            mantenimiento.fin_tecnico and mantenimiento.estado_operativo == "FINALIZADO"
        ) else "",
        "bloqueado": mantenimiento.estado_operativo == "FINALIZADO" or bool(mantenimiento.orden),
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
        ).exclude(estado_operativo="FINALIZADO").filter(
            Q(orden__isnull=True) | Q(orden="")
        )
        for mantenimiento in sin_programar:
            mantenimiento.fecha_programada = hoy
            mantenimiento.save(update_fields=["fecha_programada"])
        servicios = Mantenimiento.objects.filter(tecnico=tecnico).exclude(
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
    if mantenimiento.orden:
        return JsonResponse(
            {"ok": False, "error": "El servicio ya fue cerrado con una orden.", "retirar": True},
            status=409,
        )
    if mantenimiento.estado_operativo == "FINALIZADO":
        return JsonResponse(
            {"ok": False, "error": "El servicio ya fue finalizado.", "retirar": True},
            status=409,
        )
    estado = data.get("estado")
    if estado not in dict(Mantenimiento.ESTADO_OPERATIVO_CHOICES):
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
@user_passes_test(lambda u: u.is_superuser)
def configuracion_usuarios(request):
    grupos_base = [
        'Administrador',
        'Coordinador',
        'Programador',
        'Almacen',
        'Facturacion',
        'Visor',
        'Tecnico',
    ]

    for nombre in grupos_base:
        Group.objects.get_or_create(name=nombre)

    formulario_creacion = UserCreationForm()

    if request.method == 'POST':
        accion = request.POST.get('accion', 'actualizar_usuario')

        if accion == 'crear_usuario':
            formulario_creacion = UserCreationForm(request.POST)
            grupo_id = request.POST.get('grupo_id')
            tecnico_id = request.POST.get('tecnico_id')
            grupo = Group.objects.filter(id=grupo_id).first()
            tecnico = None

            if not grupo:
                formulario_creacion.add_error(None, "Debes seleccionar un rol.")

            if tecnico_id:
                tecnico = get_object_or_404(Tecnico, id=tecnico_id)
                if tecnico.usuario:
                    formulario_creacion.add_error(
                        None, "Ese técnico ya está vinculado a otro usuario."
                    )

            if grupo and grupo.name == 'Tecnico' and not tecnico:
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

                usuario.groups.add(grupo)

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
            usuario_id = request.POST.get('usuario_id')
            grupo_id = request.POST.get('grupo_id')
            tecnico_id = request.POST.get('tecnico_id')

            usuario = get_object_or_404(User, id=usuario_id)
            if grupo_id:
                grupo = get_object_or_404(Group, id=grupo_id)
                usuario.groups.clear()
                usuario.groups.add(grupo)

            tecnico = None
            if tecnico_id:
                tecnico = get_object_or_404(Tecnico, id=tecnico_id)
                if tecnico.usuario and tecnico.usuario != usuario:
                    messages.error(request, "Ese técnico ya está vinculado a otro usuario.")
                    return redirect('configuracion_usuarios')
            for tecnico_anterior in Tecnico.objects.filter(usuario=usuario).exclude(pk=getattr(tecnico, "pk", None)):
                tecnico_anterior.usuario = None
                tecnico_anterior.save(update_fields=["usuario"])
            if tecnico:
                tecnico.usuario = usuario
                tecnico.save(update_fields=["usuario"])

            messages.success(
                request,
                f"Rol actualizado para el usuario {usuario.username}."
            )

            return redirect('configuracion_usuarios')

    usuarios = User.objects.all().order_by('username')
    grupos = Group.objects.filter(name__in=grupos_base).order_by('name')
    for campo in formulario_creacion.fields.values():
        campo.widget.attrs['class'] = 'form-control'

    return render(request, 'configuracion_usuarios.html', {
        'usuarios': usuarios,
        'grupos': grupos,
        'tecnicos': Tecnico.objects.select_related("usuario").order_by("nombre"),
        'formulario_creacion': formulario_creacion,
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
