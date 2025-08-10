from django import forms
from datetime import timedelta
from django.utils.timezone import now
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta, Tecnico, Ejecutivo


class CuadroInstaForm(forms.ModelForm):
    # Entradas de fecha/fecha-hora
    fecha = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    fecha_inicio = forms.DateField(widget=forms.DateInput(
        attrs={'type': 'date'}), required=False)
    fecha_terminacion = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}), required=False)
    finaliza = forms.DateField(widget=forms.DateInput(
        attrs={'type': 'date'}), required=False)

    # Campos simples
    pvg = forms.IntegerField(label='PVG', initial=0)
    codigo = forms.IntegerField(label='Código', initial=0)
    cliente = forms.CharField(label='Cliente', max_length=100)
    ciudad = forms.CharField(label='Ciudad', max_length=30)
    direccion = forms.CharField(label='Dirección', max_length=100)
    instalacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False)
    dias_cotizados = forms.IntegerField(required=False)
    cantidad_tecnicos = forms.IntegerField(required=False)
    en_bodega = forms.ChoiceField(choices=CuadroInsta.BODEGA, required=False)
    estado = forms.CharField(max_length=50, required=False)
    observacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=False)

    # 🔑 Campos FK como ModelChoiceField
    tecnico1 = forms.ModelChoiceField(
        queryset=Tecnico.objects.none(), required=False)  # pylint: disable=no-member
    tecnico2 = forms.ModelChoiceField(
        queryset=Tecnico.objects.none(), required=False)  # pylint: disable=no-member
    ejecutivo = forms.ModelChoiceField(
        queryset=Ejecutivo.objects.none(), required=False)  # pylint: disable=no-member

    class Meta:
        model = CuadroInsta
        fields = [
            'pvg', 'fecha', 'codigo', 'cliente', 'ciudad', 'direccion',
            'instalacion', 'dias_cotizados', 'cantidad_tecnicos', 'en_bodega',
            'fecha_inicio', 'fecha_terminacion', 'finaliza', 'orden',
            'tecnico1', 'tecnico2', 'estado', 'observacion', 'ejecutivo'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Cargar opciones para FKs
        self.fields['tecnico1'].queryset = Tecnico.objects.all().order_by(  # pylint: disable=no-member
            'nombre')
        self.fields['tecnico2'].queryset = Tecnico.objects.all().order_by(  # pylint: disable=no-member
            'nombre')
        self.fields['ejecutivo'].queryset = Ejecutivo.objects.all().order_by(  # pylint: disable=no-member
            'nombre')

        self.fields['tecnico1'].label_from_instance = lambda obj: obj.nombre
        self.fields['tecnico2'].label_from_instance = lambda obj: obj.nombre
        self.fields['ejecutivo'].label_from_instance = lambda obj: obj.nombre

        # Deshabilitar en edición (⚠️ disabled no envía el valor en POST)
        # Lo compensamos restaurándolo desde instance en clean()
        if self.instance and self.instance.pk:
            readonly_fields = ['pvg', 'fecha', 'tecnico1', 'tecnico2']
            for field in readonly_fields:
                self.fields[field].disabled = True
                self.fields[field].widget.attrs.update(
                    {'class': 'form-control bg-light text-muted'})

        disabled_fields = ['fecha_terminacion', 'finaliza', 'estado']
        for field in disabled_fields:
            self.fields[field].disabled = True
            self.fields[field].widget.attrs.update(
                {'class': 'form-control bg-light text-muted'})

        self.fields['orden'].widget.attrs.update({
            'placeholder': 'Para anular escriba ANULADO',
            'class': 'form-control text-muted'
        })

    def clean(self):
        cleaned_data = super().clean()
        tecnico1 = cleaned_data.get('tecnico1')
        tecnico2 = cleaned_data.get('tecnico2')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        dias_cotizados = cleaned_data.get('dias_cotizados')
        orden = cleaned_data.get('orden')

        # 🛟 Restaurar valores de campos deshabilitados en edición
        if self.instance and self.instance.pk:
            if not cleaned_data.get('fecha') and self.instance.fecha:
                cleaned_data['fecha'] = self.instance.fecha
            if not tecnico1 and self.instance.tecnico1:
                cleaned_data['tecnico1'] = self.instance.tecnico1
            if not tecnico2 and self.instance.tecnico2:
                cleaned_data['tecnico2'] = self.instance.tecnico2
            if not cleaned_data.get('orden') and self.instance.orden:
                cleaned_data['orden'] = self.instance.orden

        # Validación: técnicos deben ser diferentes
        if tecnico1 and tecnico2 and tecnico1 == tecnico2:
            raise forms.ValidationError(
                "Los técnicos asignados deben ser diferentes.")

        # Calcular fecha_terminacion si hay fecha_inicio + días
        if fecha_inicio and dias_cotizados is not None:
            try:
                cleaned_data['fecha_terminacion'] = fecha_inicio + \
                    timedelta(days=dias_cotizados)
            except Exception as e:
                raise forms.ValidationError(
                    f"Error al calcular la fecha de terminación: {str(e)}")

        # Estados según 'orden' / fechas
        if orden and str(orden).strip().lower() == "anulado":
            cleaned_data['estado'] = "ANULADO"
            cleaned_data['finaliza'] = None
            return cleaned_data

        if orden:
            cleaned_data['estado'] = "LEGALIZADO"
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
        if CuadroInsta.objects.filter(pvg=pvg).exclude(id=instancia.id).exists():  # pylint: disable=no-member
            raise forms.ValidationError(
                "Ya existe una instalación con este PVG.")
        return pvg


# Subir información de instalaciones con Excel
class ExcelUploadForm(forms.Form):
    archivo_excel = forms.FileField(label="Selecciona un archivo Excel")
