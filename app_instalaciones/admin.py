from django.contrib import admin
from app_instalaciones.models.cuadroInstalaciones import cuadroInst

"""
class cuadroInstalacionesInline(admin.TabularInline):
    model = cuadroInstalaciones


# Register your models here.
class cuadroInstalacionesAdmin(admin.ModelAdmin):
    list_display= ['pvg', 'cliente','fecha']
    
admin.site.register(cuadroInstalaciones, cuadroInstalacionesAdmin)
"""

#DE ESTA FORMA LA BASE QUE AGREGAMOS YA APARECE EN EL PANEL ADMINISTRATIVO
admin.site.register(cuadroInst)