"""

from django.contrib import admin
from app_instalaciones.models.cuadroInstalaciones import (
    CuadroInsta, HistorialAsignacionMantenimiento, Mantenimiento,
    NotificacionTecnico, Tecnico,
)


# DE ESTA FORMA LA BASE QUE AGREGAMOS YA APARECE EN EL PANEL ADMINISTRATIVO
admin.site.register(CuadroInsta)
admin.site.register(Mantenimiento)
admin.site.register(Tecnico)
admin.site.register(HistorialAsignacionMantenimiento)
admin.site.register(NotificacionTecnico)

"""
from django.contrib import admin
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta, RegistroImportacion, Mantenimiento, Tecnico, Ejecutivo
from app_instalaciones.models.cuadroInstalaciones import Ciudad

admin.site.register(CuadroInsta)
admin.site.register(RegistroImportacion)
admin.site.register(Mantenimiento)
admin.site.register(Tecnico)
admin.site.register(Ejecutivo)
admin.site.register(Ciudad)
