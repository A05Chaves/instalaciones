from django.db import models
from django.contrib.auth.models import User


class Tecnico(models.Model):
    # ← bien: no se permite null
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return str(self.nombre or "Sin nombre")


class Ejecutivo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return str(self.nombre or "Ejecutivo sin nombre")


class CuadroInsta(models.Model):
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

    # Relaciones con técnicos (ahora como ForeignKey)
    tecnico1 = models.ForeignKey(
        'Tecnico', null=True, blank=True, on_delete=models.SET_NULL, related_name='cuadroinsta_tecnico1'
    )
    tecnico2 = models.ForeignKey(
        'Tecnico', null=True, blank=True, on_delete=models.SET_NULL, related_name='cuadroinsta_tecnico2'
    )

    estado = models.CharField(max_length=50, null=True, blank=True)
    observacion = models.TextField(null=True, blank=True)

    # Relación con Ejecutivo
    ejecutivo = models.ForeignKey(
        'Ejecutivo', null=True, blank=True, on_delete=models.SET_NULL
    )

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


# TABLA DE MANTENIMIENTOS AREA TECNICA

class Mantenimiento(models.Model):
    cliente = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=50)
    direccion = models.CharField(max_length=100)
    novedad = models.TextField(null=True, blank=True)
    observacion = models.TextField(null=True, blank=True)
    codigo = models.IntegerField()
    tecnico = models.CharField(max_length=50)
    pendiente = models.TextField(null=True, blank=True)
    horas = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True)
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida = models.TimeField(null=True, blank=True)
    orden = models.CharField(max_length=50, null=True, blank=True)

    # ← se ingresa manualmente
    realizado = models.DateField(null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)  # ← automático
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.fecha_registro.strftime('%Y-%m-%d %H:%M')} - {self.cliente}"  # pylint: disable=no-member
