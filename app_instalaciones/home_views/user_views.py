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
from django.contrib.auth.decorators import login_required
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta

from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from django.utils import timezone

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
    return render(request, "mantenimientos.html", context)

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
