"""

from django.contrib import admin
from django import forms
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
from django import forms
from app_instalaciones.models.cuadroInstalaciones import (
    CotizacionServicioTecnico,
    CorteIndicadorCotizacion,
    CuadroInsta,
    Ejecutivo,
    Mantenimiento,
    RegistroImportacion,
    SeguimientoCotizacionTecnica,
    Tecnico,
)
from app_instalaciones.models.cuadroInstalaciones import Ciudad

admin.site.register(CuadroInsta)
admin.site.register(RegistroImportacion)
admin.site.register(Mantenimiento)
admin.site.register(Tecnico)
admin.site.register(Ejecutivo)
admin.site.register(Ciudad)
admin.site.register(CorteIndicadorCotizacion)


class SeguimientoCotizacionTecnicaInline(admin.TabularInline):
    model = SeguimientoCotizacionTecnica
    extra = 0
    readonly_fields = ("numero", "nota", "fecha", "usuario")
    can_delete = False


class CotizacionServicioTecnicoAdminForm(forms.ModelForm):
    mantenimiento = forms.ModelChoiceField(
        queryset=Mantenimiento.objects.all(),
        required=False,
        empty_label="Sin mantenimiento asociado",
    )

    class Meta:
        model = CotizacionServicioTecnico
        fields = "__all__"


@admin.register(CotizacionServicioTecnico)
class CotizacionServicioTecnicoAdmin(admin.ModelAdmin):
    form = CotizacionServicioTecnicoAdminForm
    inlines = (SeguimientoCotizacionTecnicaInline,)
    list_display = (
        "registro",
        "numero_cotizacion",
        "codigo",
        "cliente",
        "tecnico",
        "ejecutivo",
        "estado",
        "fecha_orden",
        "fecha_envio",
    )
    list_filter = ("estado", "medio_envio", "fecha_orden", "ejecutivo", "tecnico")
    search_fields = (
        "registro",
        "numero_cotizacion",
        "codigo",
        "cliente",
        "direccion",
        "descripcion",
        "contacto",
        "telefono",
        "tecnico__nombre",
        "ejecutivo__nombre",
    )
    readonly_fields = ("fecha_registro", "soporte", "soporte_nombre")
    date_hierarchy = "fecha_orden"
    ordering = ("-fecha_orden", "-pk")
