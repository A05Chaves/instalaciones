from django.contrib.auth.models import User
from django.db import models


class RegistroAuditoria(models.Model):
    ACCIONES = [
        ("CREAR", "Agregó"),
        ("EDITAR", "Editó"),
        ("ELIMINAR", "Eliminó"),
    ]

    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movimientos_aplicacion",
    )
    accion = models.CharField(max_length=12, choices=ACCIONES, db_index=True)
    modulo = models.CharField(max_length=100, db_index=True)
    modelo = models.CharField(max_length=100, db_index=True)
    objeto_id = models.CharField(max_length=100, blank=True, db_index=True)
    objeto = models.CharField(max_length=300, blank=True)
    cambios = models.JSONField(default=dict, blank=True)
    ruta = models.CharField(max_length=300, blank=True)
    metodo = models.CharField(max_length=10, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "Registro de movimiento"
        verbose_name_plural = "Registro de movimientos"

    def __str__(self):
        usuario = self.usuario.username if self.usuario else "SISTEMA"
        return f"{usuario} {self.get_accion_display()} {self.modelo} {self.objeto_id}"
