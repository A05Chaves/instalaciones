from django.db import models


class cuadroInst(models.Model):

    
    pvg= models.IntegerField(default=0)
    fecha =models.DateTimeField()
    codigo=models.IntegerField(default=0)
    cliente= models.CharField(max_length=100)
    ciudad=models.CharField(max_length=30)
    direccion=models.CharField(max_length=100)
    tecnicos=models.CharField(max_length=50)
    ejecutivo=models.CharField(max_length=20)
    finalizacion=models.DateTimeField()
    
    
    
    def __str__(self):
        return self.cliente
    
    
