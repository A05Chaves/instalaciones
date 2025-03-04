from django.db import models
#from django.contrib.auth.models import User

class cuadroInst(models.Model):

    TECNICOS=[
        (1, "Ricardo"),
        (2, "Giovanny"),
        (3, "Juan"),
        (4, "Francisco"),
        (5, "German"),
        (6, "Willinthon"),
        (7, "Jhon"),
        (8, "Guido"),
        (9, "Esneyder"),
        (10, "Diego"),
        
    ]

    #cada que se guarde un registro actualiza la fecha de ingreso 
    #update_at=models.DateTimeField(auto_now=True)
    #se utiliza pra poner el nombre del usuario que ingreso el registro
    #usuario = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    pvg= models.IntegerField(default=0)
    fecha =models.DateTimeField()
    codigo=models.IntegerField(default=0)
    cliente= models.CharField(max_length=100)
    ciudad=models.CharField(max_length=30)
    direccion=models.CharField(max_length=100)
    tecnicos=models.CharField(max_length=50, choices=TECNICOS, default="Tecnicos")
    ejecutivo=models.CharField(max_length=20)
    finalizacion=models.DateTimeField()

    """
    def __str__(self):
        return self.cliente
    """
    
       
class listaCh(models.Model):

    fecha=models.DateField()
    edificio=models.CharField(max_length=150)
    codigo=models.IntegerField()
    orden=models.IntegerField()
    direccion1=models.CharField(max_length=150)
    visita=models.CharField(max_length=30)
    ciudad1=models.CharField(max_length=20)
    departamento1=models.CharField(max_length=20)
    
    """
    def __str__(self):
        return self.cliente
    """ 
    