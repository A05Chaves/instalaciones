from django.contrib import admin
from app_instalaciones.models.cuadroInstalaciones import cuadroInst

#DE ESTA FORMA LA BASE QUE AGREGAMOS YA APARECE EN EL PANEL ADMINISTRATIVO
admin.site.register(cuadroInst)