import json
import re
from datetime import datetime

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
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from openpyxl import Workbook

from app_instalaciones.models.cuadroInstalaciones import (
    CuadroInsta,
    Mantenimiento,
    Tecnico,
    HistorialAsignacionMantenimiento,
    NotificacionTecnico,
)
from app_instalaciones.models.forms import MantenimientoForm

from app_instalaciones.utils.importar_mantenimientos_pdf import (
    analizar_pdf_mantenimientos,
    importar_resultados_pdf,
    preparar_resultados_para_session,
    restaurar_resultados_desde_session,
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
        Mantenimiento.objects.filter(pk=mantenimiento.pk).update(
            fecha_programada=mantenimiento.fecha_programada
        )
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

# NUEVO ARREGLO LISTA DE MANTENIMIENTOS


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

    mantenimientos = (
        Mantenimiento.objects
        .select_related("tecnico")
        .order_by("-fecha_registro")
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

    tecnicos = Tecnico.objects.all().order_by("nombre")

    context = {
        "form": form,
        "mantenimientos": mantenimientos,
        "tecnicos": tecnicos,
        "busqueda": busqueda,
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


@login_required
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
@require_POST
def mantenimiento_actualizar(request, pk):
    m = get_object_or_404(Mantenimiento, pk=pk)
    tecnico_anterior = m.tecnico

    if m.orden:
        return JsonResponse(
            {"ok": False, "error": "El servicio está cerrado y no admite cambios."},
            status=409,
        )
    if m.estado_operativo == "FINALIZADO":
        orden = (request.POST.get("orden") or "").strip()
        if not orden:
            return JsonResponse(
                {"ok": False, "error": "Debe ingresar la orden para cerrar el servicio."},
                status=400,
            )
        m.orden = orden[:50]
        m.realizado = m.realizado or timezone.localdate()
        m.save()
        return JsonResponse({
            "ok": True,
            "orden": m.orden,
            "realizado": m.realizado.isoformat(),
            "fecha_orden": timezone.localtime(m.fecha_orden).isoformat(),
        })

    campos_editables = {
        "cliente", "ciudad", "direccion", "tipo_servicio",
        "tipo_falla", "tecnico", "fecha_programada", "orden", "realizado",
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
    if m.orden and not m.realizado:
        m.realizado = timezone.now().date()
    m.save()
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
        "estado": mantenimiento.estado_operativo,
        "novedad": mantenimiento.novedad or "",
        "observacion": mantenimiento.observacion or "",
        "pendiente": mantenimiento.pendiente or "",
        "inicio": mantenimiento.fecha_inicio.isoformat() if mantenimiento.fecha_inicio else "",
        "fin": mantenimiento.fecha_fin.isoformat() if mantenimiento.fecha_fin else "",
        "bloqueado": mantenimiento.estado_operativo == "FINALIZADO" or bool(mantenimiento.orden),
    }


@login_required(login_url="login")
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
        Mantenimiento.objects.filter(
            tecnico=tecnico,
            fecha_programada__isnull=True,
        ).update(fecha_programada=hoy)
        servicios = Mantenimiento.objects.filter(tecnico=tecnico).filter(
            Q(fecha_programada=hoy) | ~Q(estado_operativo="FINALIZADO")
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
            {"ok": False, "error": "El servicio ya fue cerrado con una orden."},
            status=409,
        )
    if mantenimiento.estado_operativo == "FINALIZADO":
        return JsonResponse(
            {"ok": False, "error": "El servicio finalizado solo admite la orden del operador."},
            status=409,
        )
    estado = data.get("estado")
    if estado not in dict(Mantenimiento.ESTADO_OPERATIVO_CHOICES):
        return JsonResponse({"ok": False, "error": "Estado inválido."}, status=400)

    ahora = timezone.now()
    fecha_evento = parse_datetime(str(data.get("fecha_evento") or ""))
    if fecha_evento:
        if timezone.is_naive(fecha_evento):
            fecha_evento = timezone.make_aware(
                fecha_evento, timezone.get_current_timezone()
            )
    else:
        fecha_evento = ahora
    fecha_evento_local = timezone.localtime(fecha_evento)
    novedad_anterior = mantenimiento.novedad or ""
    novedad_nueva = str(data.get("novedad", novedad_anterior)).strip()[:5000]
    if estado == "FINALIZADO" and mantenimiento.estado_operativo != "EN_PROCESO":
        return JsonResponse(
            {"ok": False, "error": "Debes iniciar el servicio antes de finalizarlo."},
            status=409,
        )
    if estado == "FINALIZADO" and not novedad_nueva:
        return JsonResponse(
            {"ok": False, "error": "Debes registrar la novedad antes de finalizar."},
            status=400,
        )
    if estado == "EN_PROCESO" and Mantenimiento.objects.filter(
        tecnico=tecnico,
        estado_operativo="EN_PROCESO",
    ).exclude(pk=mantenimiento.pk).exists():
        return JsonResponse(
            {"ok": False, "error": "Debes finalizar el servicio en ejecución antes de iniciar otro."},
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
    if estado == "EN_PROCESO" and not mantenimiento.fecha_inicio:
        mantenimiento.fecha_inicio = fecha_evento
        mantenimiento.hora_entrada = fecha_evento_local.time().replace(
            second=0, microsecond=0
        )
    if estado == "FINALIZADO":
        mantenimiento.realizado = mantenimiento.realizado or fecha_evento_local.date()
        if not mantenimiento.fecha_fin:
            mantenimiento.fecha_fin = fecha_evento
            mantenimiento.hora_salida = fecha_evento_local.time().replace(
                second=0, microsecond=0
            )
        if mantenimiento.fecha_inicio and mantenimiento.fecha_fin:
            mantenimiento.horas = round(
                (mantenimiento.fecha_fin - mantenimiento.fecha_inicio).total_seconds() / 3600, 2
            )
    mantenimiento.save()
    return JsonResponse({"ok": True, "servicio": _serializar_servicio_tecnico(mantenimiento)})


@login_required(login_url="login")
@require_POST
def leer_notificaciones_tecnico(request):
    tecnico = _tecnico_del_usuario(request.user)
    if not tecnico:
        return JsonResponse({"ok": False}, status=403)
    tecnico.notificaciones.filter(leida=False).update(leida=True)
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

    ciudades = (
        CuadroInsta.objects
        .exclude(ciudad__isnull=True)
        .exclude(ciudad="")
        .values_list('ciudad', flat=True)
        .distinct()
        .order_by('ciudad')
    )

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
    }

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
            Tecnico.objects.filter(usuario=usuario).exclude(pk=getattr(tecnico, "pk", None)).update(usuario=None)
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


# VISTA DE EXPORTAR MANTENIMIENTOS

@login_required(login_url='login')
@user_passes_test(puede_gestionar_mantenimientos, login_url='home')
def exportar_mantenimientos(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Mantenimientos"

    encabezados = [
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
            m.fecha_registro.strftime(
                "%Y-%m-%d %H:%M") if m.fecha_registro else "",
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
        archivo_pdf = request.FILES.get("archivo_pdf")

        if not archivo_pdf:
            messages.error(request, "Debe seleccionar un archivo PDF.")
            return redirect("importar_mantenimientos_pdf")

        actualizar_existentes = (
            request.POST.get("actualizar_existentes") == "1"
        )
        resultados = analizar_pdf_mantenimientos(
            archivo_pdf,
            actualizar_existentes=actualizar_existentes,
        )

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
