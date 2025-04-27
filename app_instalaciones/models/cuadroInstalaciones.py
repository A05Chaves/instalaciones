from django.db import models
#from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


class CuadroInsta(models.Model):
    TECNICOS = [
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
        (11, "-----")
    ]

    EJECUTIVOS = [
        (1, "Francisco Silva"),
        (2, "Andrea Trujillo"),
        (3, "Yamile David"),
        (4, "-----")
    ]

    pvg = models.IntegerField(default=0)
    # Establecido como auto_now_add para que se registre automáticamente
    fecha = models.DateTimeField()
    codigo = models.IntegerField(default=0)
    cliente = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=30)
    direccion = models.CharField(max_length=100)
    tecnico1 = models.IntegerField(choices=TECNICOS, default=1)
    tecnico2 = models.IntegerField(choices=TECNICOS, default=1)
    ejecutivo = models.IntegerField(choices=EJECUTIVOS, default=1)
    finalizacion = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    usuario = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
  
    def __str__(self):
        return f"Instalación #{self.codigo} - {self.cliente}"
