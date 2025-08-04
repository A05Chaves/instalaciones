import re
from django.shortcuts import render, redirect
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.contrib.auth import authenticate
from django.urls import reverse
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from app_instalaciones.models.cuadroInstalaciones import Mantenimiento, Tecnico

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


# VISTA DE LISTA DE MANTENIMIENTOS EN HTML

def listar_mantenimientos(request):
    if request.method == "POST":
        # Crear nuevo mantenimiento desde POST
        # pylint: disable=no-member

        Mantenimiento.objects.create(
            cliente=request.POST.get('cliente'),
            ciudad=request.POST.get('ciudad'),
            direccion=request.POST.get('direccion'),
            novedad=request.POST.get('novedad'),
            observacion=request.POST.get('observacion'),
            codigo=request.POST.get('codigo') or None,
            tecnico=Tecnico.objects.get(id=request.POST.get('tecnico')),
            pendiente=request.POST.get('pendiente'),
            horas=request.POST.get('horas') or 0,
            hora_entrada=request.POST.get('hora_entrada'),
            hora_salida=request.POST.get('hora_salida'),
            orden=request.POST.get('orden'),
            realizado=request.POST.get('realizado'),
        )

        # pyright: ignore[reportUndefinedVariable]
        messages.success(request, "Mantenimiento registrado exitosamente.")
        return redirect('listar_mantenimientos')

    # pylint: disable=no-member
    mantenimientos = Mantenimiento.objects.order_by('-fecha_creado')
    tecnicos = Tecnico.objects.all()  # pylint: disable=no-member
    return render(request, 'mantenimientos/listado_mantenimientos.html', {
        'mantenimientos': mantenimientos,
        'tecnicos': tecnicos
    })
