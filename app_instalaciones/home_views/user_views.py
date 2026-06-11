import re
from django.shortcuts import render, redirect
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.contrib.auth import authenticate
from django.urls import reverse
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from app_instalaciones.models.cuadroInstalaciones import Mantenimiento, Tecnico

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta

from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from django.utils import timezone
from datetime import datetime
from django.contrib.auth.models import User, Group


# VISTAS PARA LA GESTIÓN DE USUARIOS

def pertenece_grupo(user, nombre_grupo):
    return user.groups.filter(name=nombre_grupo).exists()


def puede_programar(user):
    return (
        user.is_superuser
        or pertenece_grupo(user, 'Administrador')
        or pertenece_grupo(user, 'Programador')
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


def puede_ver(user):
    return user.is_authenticated

# MÉTODO PARA INGRESAR AL MÓDULO DE REGISTRO DE INSTALACIONES


def login(request):
    if request.user.is_authenticated:
        return redirect('home')  # ya está logueado

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
            return redirect('home')
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


def listar_mantenimientos(request):
    if request.method == "POST":
        # 1. Leer lo que viene del formulario
        codigo = (request.POST.get('codigo') or "").strip()
        cliente = (request.POST.get('cliente') or "").strip()
        ciudad = (request.POST.get('ciudad') or "").strip()
        direccion = (request.POST.get('direccion') or "").strip()
        tipo_falla = (request.POST.get('tipo_falla') or "").strip()
        tecnico_id = request.POST.get('tecnico') or None
        hora_entrada = request.POST.get('hora_entrada') or None
        hora_salida = request.POST.get('hora_salida') or None
        horas = request.POST.get('horas') or 0
        orden = (request.POST.get('orden') or "").strip()
        realizado = request.POST.get('realizado') or None

        # 2. Si hay código, intentar buscar la instalación SOLO para este registro
        inst = None
        if codigo:
            inst = CuadroInsta.objects.filter(codigo__iexact=codigo).first()

        # 3. Si encontramos instalación, solo sobrescribimos los campos VACÍOS
        if inst:
            if not cliente:
                cliente = inst.cliente or ""
            if not ciudad:
                ciudad = inst.ciudad or ""
            if not direccion:
                direccion = inst.direccion or ""

        # 4. Si hay orden y no viene fecha de realizado → usar hoy
        if orden and not realizado:
            realizado = timezone.now().date()

        # 5. Crear el mantenimiento con los datos resultantes
        Mantenimiento.objects.create(
            codigo=codigo,
            cliente=cliente,
            ciudad=ciudad,
            direccion=direccion,
            tipo_falla=tipo_falla,
            tecnico_id=tecnico_id,
            hora_entrada=hora_entrada or None,
            hora_salida=hora_salida or None,
            horas=horas or 0,
            orden=orden,
            realizado=realizado,
        )

        messages.success(request, "Mantenimiento registrado correctamente.")
        return redirect('listar_mantenimientos')

    # GET: listar
    mantenimientos = Mantenimiento.objects.all().order_by('-fecha_registro')
    tecnicos = Tecnico.objects.all().order_by('nombre')

    context = {
        "mantenimientos": mantenimientos,
        "tecnicos": tecnicos,
    }
    return render(request, "mantenimientos/listar_mantenimientos.html", context)

# JSON PARA BUSCAR CLIENTES Y AGREGAR AL CUADRO MANTENIMIENTOS


@login_required
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
@require_POST
def mantenimiento_actualizar(request, pk):
    """Actualiza un mantenimiento desde la fila (inline, vía AJAX)."""
    m = get_object_or_404(Mantenimiento, pk=pk)

    m.cliente = request.POST.get('cliente', m.cliente)
    m.ciudad = request.POST.get('ciudad', m.ciudad)
    m.direccion = request.POST.get('direccion', m.direccion)
    m.tipo_falla = request.POST.get('tipo_falla') or m.tipo_falla
    hora_entrada_post = request.POST.get('hora_entrada') or None
    hora_salida_post = request.POST.get('hora_salida') or None

    if hora_entrada_post and not m.hora_entrada:
        m.hora_entrada = hora_entrada_post

    if hora_salida_post and not m.hora_salida:
        m.hora_salida = hora_salida_post

    m.orden = request.POST.get('orden', m.orden)
    m.realizado = request.POST.get('realizado') or m.realizado

    tecnico_id = request.POST.get('tecnico')
    if tecnico_id:
        try:
            m.tecnico = Tecnico.objects.get(id=tecnico_id)
        except Tecnico.DoesNotExist:
            pass  # si no existe, no cambiamos el técnico

    m.save()

    orden_post = request.POST.get('orden') or m.orden
    m.orden = orden_post

    realizado_post = request.POST.get('realizado') or None
    if realizado_post:
        m.realizado = realizado_post
    else:
        # Si hay orden y sigue sin fecha, pon hoy
        if m.orden and not m.realizado:
            m.realizado = timezone.now().date()

    m.save()

    return JsonResponse({
        "ok": True,
        "cliente": m.cliente,
        "ciudad": m.ciudad,
        "direccion": m.direccion,
        "tipo_falla_display": m.get_tipo_falla_display() if hasattr(m, "get_tipo_falla_display") else m.tipo_falla,
        "tecnico": m.tecnico.nombre if m.tecnico else "",
        "orden": m.orden,
        "realizado": m.realizado.isoformat() if m.realizado else "",
    })


@login_required
@require_POST
def mantenimiento_eliminar(request, pk):
    """Elimina un mantenimiento desde el modal de confirmación."""
    m = get_object_or_404(Mantenimiento, pk=pk)
    m.delete()
    messages.success(request, "Mantenimiento eliminado correctamente.")
    return redirect('mantenimientos')


@login_required
@require_POST
def mantenimiento_subir_archivo(request, pk):
    """Sube o reemplaza el archivo (foto/PDF) de un mantenimiento."""
    m = get_object_or_404(Mantenimiento, pk=pk)
    archivo = request.FILES.get('archivo')

    if not archivo:
        messages.error(request, "No se recibió ningún archivo.")
        return redirect('mantenimientos')

    m.archivo = archivo
    m.save()
    messages.success(request, "Archivo cargado correctamente.")
    return redirect('mantenimientos')


# VISTA DE FACTURACIÓN

@login_required(login_url='login')
@user_passes_test(puede_facturar)
def facturar_instalacion(request, id):
    instalacion = get_object_or_404(CuadroInsta, id=id)

    if not instalacion.alistado:
        messages.error(
            request, "No se puede facturar una instalación que no ha sido alistada por almacén.")
        return redirect('lista_instalaciones')

    instalacion.facturado = True
    instalacion.save()

    messages.success(request, "Instalación marcada como facturada.")

    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)

    return redirect('lista_instalaciones')

# VISTA DE DASHBOARD


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_staff)
def dashboard_instalaciones(request):
    mes = request.GET.get('mes')
    ciudad = request.GET.get('ciudad')

    qs = CuadroInsta.objects.all()

    if mes:
        try:
            fecha_mes = datetime.strptime(mes, "%Y-%m")
            qs = qs.filter(
                fecha__year=fecha_mes.year,
                fecha__month=fecha_mes.month
            )
        except ValueError:
            pass

    if ciudad:
        qs = qs.filter(ciudad__iexact=ciudad)

    total_pvg = qs.count()

    # INSTALACIÓN
    registros_instalacion = qs.filter(
        fecha__isnull=False,
        fecha_inicio__isnull=False
    )

    total_instalacion = registros_instalacion.count()
    cumple_instalacion = 0
    suma_dias_instalacion = 0

    for item in registros_instalacion:
        dias = item.dias_instalacion

        if dias is not None:
            suma_dias_instalacion += dias

            if dias <= 8:
                cumple_instalacion += 1

    eficiencia_instalacion = 0
    promedio_instalacion = 0

    if total_instalacion > 0:
        eficiencia_instalacion = round(
            (cumple_instalacion / total_instalacion) * 100, 2
        )
        promedio_instalacion = round(
            suma_dias_instalacion / total_instalacion, 2
        )

    fuera_instalacion = total_instalacion - cumple_instalacion

    # ALMACÉN
    registros_almacen = qs.filter(
        finaliza__isnull=False,
        fecha_alistado__isnull=False
    )

    total_almacen = registros_almacen.count()
    cumple_almacen = 0
    suma_dias_almacen = 0

    for item in registros_almacen:
        dias = item.dias_para_alistar

        if dias is not None:
            suma_dias_almacen += dias

            if dias <= 2:
                cumple_almacen += 1

    eficiencia_almacen = 0
    promedio_almacen = 0

    if total_almacen > 0:
        eficiencia_almacen = round(
            (cumple_almacen / total_almacen) * 100, 2
        )
        promedio_almacen = round(
            suma_dias_almacen / total_almacen, 2
        )

    fuera_almacen = total_almacen - cumple_almacen

    # FACTURACIÓN
    registros_facturacion = qs.filter(
        fecha_alistado__isnull=False,
        fecha_facturacion__isnull=False
    )

    total_facturacion = registros_facturacion.count()
    cumple_facturacion = 0
    suma_dias_facturacion = 0

    for item in registros_facturacion:
        dias = item.dias_para_facturar

        if dias is not None:
            suma_dias_facturacion += dias

            if dias <= 2:
                cumple_facturacion += 1

    eficiencia_facturacion = 0
    promedio_facturacion = 0

    if total_facturacion > 0:
        eficiencia_facturacion = round(
            (cumple_facturacion / total_facturacion) * 100, 2
        )
        promedio_facturacion = round(
            suma_dias_facturacion / total_facturacion, 2
        )

    fuera_facturacion = total_facturacion - cumple_facturacion

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
        'ciudad': ciudad,
        'ciudades': ciudades,

        'total_pvg': total_pvg,

        'total_instalacion': total_instalacion,
        'cumple_instalacion': cumple_instalacion,
        'fuera_instalacion': fuera_instalacion,
        'eficiencia_instalacion': eficiencia_instalacion,
        'promedio_instalacion': promedio_instalacion,

        'total_almacen': total_almacen,
        'cumple_almacen': cumple_almacen,
        'fuera_almacen': fuera_almacen,
        'eficiencia_almacen': eficiencia_almacen,
        'promedio_almacen': promedio_almacen,

        'total_facturacion': total_facturacion,
        'cumple_facturacion': cumple_facturacion,
        'fuera_facturacion': fuera_facturacion,
        'eficiencia_facturacion': eficiencia_facturacion,
        'promedio_facturacion': promedio_facturacion,

        'total_cierre': total_cierre,
        'promedio_cierre_total': promedio_cierre_total,
    }

    return render(request, 'dashboard_instalaciones.html', contexto)


# VISTA PARA EL ALMACENISTA

@login_required(login_url='login')
@user_passes_test(puede_alistar)
def alistar_instalacion(request, id):
    instalacion = get_object_or_404(CuadroInsta, id=id)

    if instalacion.estado != "LEGALIZADO" or not instalacion.orden:
        messages.error(
            request, "No se puede alistar una instalación sin orden legalizada.")
        return redirect('lista_instalaciones')

    instalacion.alistado = True
    instalacion.save()

    messages.success(request, "Instalación marcada como alistada por almacén.")

    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)

    return redirect('lista_instalaciones')

# VISTA PARA BOTON DE CONFIGURACION


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser)
def configuracion_usuarios(request):
    grupos_base = [
        'Administrador',
        'Programador',
        'Almacen',
        'Facturacion',
        'Visor',
    ]

    for nombre in grupos_base:
        Group.objects.get_or_create(name=nombre)

    if request.method == 'POST':
        usuario_id = request.POST.get('usuario_id')
        grupo_id = request.POST.get('grupo_id')

        usuario = get_object_or_404(User, id=usuario_id)
        grupo = get_object_or_404(Group, id=grupo_id)

        usuario.groups.clear()
        usuario.groups.add(grupo)

        messages.success(
            request,
            f"Rol actualizado para el usuario {usuario.username}."
        )

        return redirect('configuracion_usuarios')

    usuarios = User.objects.all().order_by('username')
    grupos = Group.objects.filter(name__in=grupos_base).order_by('name')

    return render(request, 'configuracion_usuarios.html', {
        'usuarios': usuarios,
        'grupos': grupos,
    })
