from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.urls import reverse
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import  redirect, render


#METODO PARA INGRESAR AL MODULO DE REGISTRO DE INSTALACIONES
def login(request):
    contexto = {}
    #este condicional funciona valildando la informacion que viene del registro de usuario
    if request.method == "GET":
        greetings =  request.GET.get('greetings')
        print("greetins: {}".format('greetings'))
        if greetings == "true":
            contexto['mensaje'] = "!!!!!!!!Cuenta creada correctamente, autenticate"
    #esta condicion funciona para validar si el usuario ya existe y no puede ingresar
    else:
        username = request.POST.get('username')
        password = request.POST.get('password')
        #con esta sentencia se busca el usuario en la base de datos para validar y entrar.
        user = authenticate(request, username=username, password=password)
        #este condicional valida si el usurio existe y si en este caso es true, lo lleva a la pagina de registro de instalaciones
      
        if user is not None:
            auth_login(request, user)
            return render(request, "registro_inst.html")
            #return redirect(reverse('registro_inst'))
        else:
            contexto['error'] = "Valide su clave y contraseña"
       
    return render(request, "users/login.html", contexto)

#METODO PARA REGISTRAR USUARIOS A LA BASE DE DATOS
def registrate(request):
    
    contexto = {}
    
    if request.method =="POST":
        print("post")
        nombre = request.POST.get('nombre')
        apellido = request.POST.get('apellido')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        #vamos a verificar que el usuario no este duplicado
        user_exist = User.objects.filter(username = username).exists()
        if user_exist:
            error = "El usuario ingresado ya existe"
            contexto['error'] = error
            #de esta forma el fomulario no pierde la informacion al mostrarse el error
            contexto['nombre'] = nombre
            contexto['apellido'] = apellido
            contexto['username'] = username
            contexto['email'] = email
        else:
            #este metodo lo utilizamos solo para ver si se imprime en pantalla lo ingresado 
            print("Crear usuario")
            #ahora vamos a crear el usuario
            User.objects.create_user(username, email, password, first_name = nombre, last_name = apellido)
            #esta parte se crea para que se muestre un mensaje cuando se crea la cuenta correctamente
            url = "{}?greetings=true".format(reverse('login'))
            return redirect(url)
            
    else:
        print("get")
    
    
    return render(request, "users/registrate.html", contexto)

#METODO PARA SALIR COMO USUARIO REGISTRADO
def logout(request):
    auth_logout(request)
    return redirect(reverse('home'))