from django import forms
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta
from django.core.exceptions import ValidationError


class CuadroInstaForm(forms.ModelForm):
    fecha = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    finalizacion = forms.DateTimeField(
        label='Fecha de Finalización (opcional)',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False
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

    tecnico1 = forms.ChoiceField(choices=CuadroInsta.TECNICOS)  # ✅ AÑADIDO
    tecnico2 = forms.ChoiceField(choices=CuadroInsta.TECNICOS)  # ✅ AÑADIDO
    ejecutivo = forms.ChoiceField(choices=CuadroInsta.EJECUTIVOS)  # ✅ AÑADIDO

    estado = forms.CharField(max_length=50, required=False)
    observacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=False
    )

    class Meta:
        model = CuadroInsta
        fields = [
            'pvg', 'fecha', 'codigo', 'cliente', 'ciudad', 'direccion',
            'instalacion', 'dias_cotizados', 'cantidad_tecnicos', 'en_bodega',
            'fecha_inicio', 'fecha_terminacion', 'finaliza', 'orden',
            'tecnico1', 'tecnico2', 'estado', 'observacion',
            'ejecutivo', 'finalizacion'
        ]

    def clean(self):
        cleaned_data = super().clean()
        tecnico1 = cleaned_data.get('tecnico1')
        tecnico2 = cleaned_data.get('tecnico2')

        if tecnico1 and tecnico2 and str(tecnico1) == str(tecnico2):
            raise forms.ValidationError(
                "Los técnicos asignados deben ser diferentes.")
        return cleaned_data

    def clean_pvg(self):
        pvg = self.cleaned_data['pvg']
        instancia = self.instance

        if CuadroInsta.objects.filter(pvg=pvg).exclude(id=instancia.id).exists():
            raise forms.ValidationError(
                "⚠️ Ya existe una instalación con este PVG.")
        return pvg


# subir informacion de instalacinoes con excel 2 de mayo 2025


class ExcelUploadForm(forms.Form):
    archivo_excel = forms.FileField(label="Selecciona un archivo Excel")
