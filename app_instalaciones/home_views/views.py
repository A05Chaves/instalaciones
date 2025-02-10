
from django.shortcuts import  redirect, render
from app_instalaciones.models.cuadroInstalaciones import cuadroInst


#PAGINA INICIAL DEL PROYECTO
def home (request):
    contexto = {}
    return render(request, "home.html", contexto)

#AQUI SE MUESTRAN LAS INSTALACIONES EN CURSO
def instalaciones_in(request):

    #se crea una variable para porder recibir los objetos en este caso instalaciones
    instalaciones = cuadroInst.objects.all()
   
    return render(request, "instalaciones.html", {"instalaciones":instalaciones})

#LISTA DE CHEQUEO SERVIR
def chequeo (request):
    contexto = {}
    return render(request, "chequeo.html", contexto)



#REGISTRO DE INSTALACIONES 
def registro_inst(request):
    
    contexto = {}
    
    #METODO PARA INGRESAR INSTALACIONES
     
    if request.method == "POST":
        Pvg= request.POST.get('pvg')
        Fecha=request.POST.get('fecha')
        Codigo=request.POST.get('codigo')
        Cliente=request.POST.get('cliente')
        Ciudad=request.POST.get('ciudad')
        Direccion=request.POST.get('direccion')
        Tecnico1=request.POST.get('tecnico1')
        Tecnico2=request.POST.get('tecnico2')
        Ejecutivo=request.POST.get('ejecutivo')
        Finalizacion='2024-03-23 20:44'
        
        tec1= Tecnico1
        tec2= Tecnico2
        
        Tecnicos= tec1 + '-' + tec2
        
        if tec1 == tec2:
            error = "El tecnico ya ha sido programado!!!!!"
            contexto['error']= error
            
        else:
           cuadro=cuadroInst.objects.create(pvg=Pvg, fecha=Fecha, codigo=Codigo, cliente=Cliente, ciudad=Ciudad, direccion=Direccion, tecnicos=Tecnicos, ejecutivo=Ejecutivo, finalizacion=Finalizacion)                   
           mensaje="Pedido ingresado a la programacion"
           contexto['mensaje']= mensaje
        
        
        return render(request, "registro_inst.html", contexto)

def finalizar (request):
    
    contexto={}
    
    

