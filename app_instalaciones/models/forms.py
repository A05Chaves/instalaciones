from django import forms
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta
from django.core.exceptions import ValidationError


class CuadroInstaForm(forms.ModelForm):
    fecha = forms.DateTimeField()
    finalizacion = forms.DateTimeField(
        label='Fecha de Finalización (opcional)',
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False,
    )
    pvg = forms.IntegerField(label='PVG', initial=0)
    codigo = forms.IntegerField(label='Código', initial=0)
    cliente = forms.CharField(label='Cliente', max_length=100)
    ciudad = forms.CharField(label='Ciudad', max_length=30)
    direccion = forms.CharField(label='Dirección', max_length=100)
    tecnico1 = forms.ChoiceField(
        label='Técnico 1', choices=CuadroInsta.TECNICOS, initial=1)
    tecnico2 = forms.ChoiceField(
        label='Técnico 2', choices=CuadroInsta.TECNICOS, initial=1)
    ejecutivo = forms.ChoiceField(
        label='Ejecutivo', choices=CuadroInsta.EJECUTIVOS, initial=1)

    class Meta:
        model = CuadroInsta
        fields = [
            'pvg', 'fecha', 'codigo', 'cliente', 'ciudad', 'direccion',
            'tecnico1', 'tecnico2', 'ejecutivo', 'finalizacion'
        ]

    def clean(self):
        cleaned_data = super().clean()
        tecnico1 = cleaned_data.get('tecnico1')
        tecnico2 = cleaned_data.get('tecnico2')

        if tecnico1 and tecnico2 and str(tecnico1) == str(tecnico2):
            raise forms.ValidationError(
                "Los técnicos asignados deben ser diferentes.")
        return cleaned_data
    
#valida si un pvg ya fue creado en la base de datos
    def clean_pvg(self):
        pvg = self.cleaned_data.get('pvg')
        if CuadroInsta.objects.filter(pvg=pvg).exists(): # pylint: disable=no-member
            raise ValidationError("El PVG ingresado ya está registrado.")
        return pvg