from django.db import models
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

    BODEGA = [
        ("SI", "Sí"),
        ("NO", "No")
    ]

    pvg = models.IntegerField(default=0)
    fecha = models.DateTimeField()
    codigo = models.IntegerField(default=0)
    cliente = models.CharField(max_length=100)
    ciudad = models.CharField(null=True, max_length=30)
    direccion = models.CharField(null=True, max_length=100)
    instalacion = models.TextField(null=True, blank=True)
    dias_cotizados = models.IntegerField(null=True, blank=True)
    cantidad_tecnicos = models.IntegerField(null=True, blank=True)
    en_bodega = models.CharField(
        null=True, choices=BODEGA, max_length=2, default="NO")
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_terminacion = models.DateField(null=True, blank=True)
    finaliza = models.DateField(null=True, blank=True)
    orden = models.CharField(max_length=50, null=True, blank=True)
    tecnico1 = models.IntegerField(null=True,
                                   choices=TECNICOS, default=1)  # ✅ IntegerField
    tecnico2 = models.IntegerField(null=True,
                                   choices=TECNICOS, default=1)  # ✅ IntegerField
    estado = models.CharField(max_length=50, null=True, blank=True)
    observacion = models.TextField(null=True, blank=True)
    ejecutivo = models.IntegerField(null=True,
                                    choices=EJECUTIVOS, default=1)  # ✅ IntegerField
    # finalizacion = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    usuario = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"Instalación #{self.codigo} - {self.cliente}"

    # guarda los registros de importacion de archivos excel


class RegistroImportacion(models.Model):
    nombre_archivo = models.CharField(max_length=255, unique=True)
    fecha_importacion = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nombre_archivo} - {self.fecha_importacion.strftime('%Y-%m-%d %H:%M')}"  # pylint: disable=no-member
