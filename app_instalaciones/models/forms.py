from django import forms
from django.utils.timezone import now
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta
from django.core.exceptions import ValidationError
from datetime import timedelta


class CuadroInstaForm(forms.ModelForm):
    fecha = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )

    fecha_inicio = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False
    )
    fecha_terminacion = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False
    )

    finaliza = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False
    )

    pvg = forms.IntegerField(label='PVG', initial=0)
    codigo = forms.IntegerField(label='Código', initial=0)
    cliente = forms.CharField(label='Cliente', max_length=100)
    ciudad = forms.CharField(label='Ciudad', max_length=30)
    direccion = forms.CharField(label='Dirección', max_length=100)
    instalacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False
    )
    dias_cotizados = forms.IntegerField(required=False)
    cantidad_tecnicos = forms.IntegerField(required=False)
    en_bodega = forms.ChoiceField(choices=CuadroInsta.BODEGA, required=False)

    tecnico1 = forms.ChoiceField(choices=CuadroInsta.TECNICOS)
    tecnico2 = forms.ChoiceField(choices=CuadroInsta.TECNICOS)
    ejecutivo = forms.ChoiceField(choices=CuadroInsta.EJECUTIVOS)

    estado = forms.CharField(max_length=50, required=False)
    observacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['pvg'].disabled = True
            self.fields['pvg'].widget.attrs.update({
                'class': 'form-control bg-light text-muted'
            })

    class Meta:
        model = CuadroInsta
        fields = [
            'pvg', 'fecha', 'codigo', 'cliente', 'ciudad', 'direccion',
            'instalacion', 'dias_cotizados', 'cantidad_tecnicos', 'en_bodega',
            'fecha_inicio', 'fecha_terminacion', 'finaliza', 'orden',
            'tecnico1', 'tecnico2', 'estado', 'observacion', 'ejecutivo'
        ]

    def clean(self):
        cleaned_data = super().clean()
        tecnico1 = cleaned_data.get('tecnico1')
        tecnico2 = cleaned_data.get('tecnico2')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        dias_cotizados = cleaned_data.get('dias_cotizados')
        orden = cleaned_data.get('orden')
        estado = cleaned_data.get('estado')

        # Validación: Los técnicos no pueden ser iguales
        if tecnico1 and tecnico2 and str(tecnico1) == str(tecnico2):
            raise forms.ValidationError(
                "Los técnicos asignados deben ser diferentes.")

        # Calcular la fecha de terminación automáticamente
        if fecha_inicio and dias_cotizados is not None:
            try:
                fecha_terminacion = fecha_inicio + \
                    timedelta(days=dias_cotizados)
                cleaned_data['fecha_terminacion'] = fecha_terminacion
            except Exception as e:
                raise forms.ValidationError(
                    f"Error al calcular la fecha de terminación: {str(e)}")

        # Lógica del campo estado y fecha de finalización
        if orden:
            cleaned_data['estado'] = "LEGALIZADO"
            # Registrar la fecha de finalización si el estado cambia a "LEGALIZADO"
            if not cleaned_data.get('finaliza'):
                cleaned_data['finaliza'] = now().date()
        elif fecha_inicio:
            cleaned_data['estado'] = "PROGRAMADO"
        else:
            cleaned_data['estado'] = "PENDIENTE"

        return cleaned_data

    def clean_pvg(self):
        pvg = self.cleaned_data['pvg']
        instancia = self.instance
        if CuadroInsta.objects.filter(pvg=pvg).exclude(id=instancia.id).exists():
            raise forms.ValidationError(
                "⚠️ Ya existe una instalación con este PVG.")
        return pvg


# Subir información de instalaciones con Excel - 2 de mayo 2025
class ExcelUploadForm(forms.Form):
    archivo_excel = forms.FileField(label="Selecciona un archivo Excel")
