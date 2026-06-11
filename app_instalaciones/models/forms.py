from django import forms
from datetime import timedelta
from django.utils.timezone import now
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta, Tecnico, Ejecutivo, Ciudad


class CuadroInstaForm(forms.ModelForm):
    # Entradas de fecha/fecha-hora
    fecha = forms.DateTimeField(
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'type': 'datetime-local'}
        ),
        input_formats=['%Y-%m-%dT%H:%M'],
        required=False
    )

    fecha_inicio = forms.DateField(
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'type': 'date'}
        ),
        input_formats=['%Y-%m-%d'],
        required=False
    )

    fecha_terminacion = forms.DateField(
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'type': 'date'}
        ),
        input_formats=['%Y-%m-%d'],
        required=False
    )

    finaliza = forms.DateField(
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'type': 'date'}
        ),
        input_formats=['%Y-%m-%d'],
        required=False
    )

    # Campos simples
    pvg = forms.IntegerField(label='PVG', initial=0)
    codigo = forms.IntegerField(label='Código', initial=0)
    cliente = forms.CharField(label='Cliente', max_length=100)

    ciudad = forms.ModelChoiceField(
        queryset=Ciudad.objects.none(),
        required=True,
        label='Ciudad'
    )

    direccion = forms.CharField(label='Dirección', max_length=100)
    instalacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}), required=False)
    dias_cotizados = forms.IntegerField(required=False)
    en_bodega = forms.ChoiceField(choices=CuadroInsta.BODEGA, required=False)
    estado = forms.CharField(max_length=50, required=False)
    observacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=False)

    # Campos FK como ModelChoiceField
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
            'instalacion', 'dias_cotizados', 'en_bodega',
            'fecha_inicio', 'fecha_terminacion', 'finaliza', 'orden',
            'tecnico1', 'tecnico2', 'estado', 'observacion', 'ejecutivo'
        ]

    def __init__(self, *args, **kwargs):
        # Flag para distinguir importación vs uso manual
        self.modo_import = kwargs.pop('modo_import', False)
        super().__init__(*args, **kwargs)

        # VALOR POR DEFECTO EN BODEGA
        if not self.instance or not self.instance.pk:
            self.fields['en_bodega'].initial = "NO"

        # Cargar opciones para FKs
        self.fields['tecnico1'].queryset = Tecnico.objects.all().order_by(
            'nombre')  # pylint: disable=no-member
        self.fields['tecnico2'].queryset = Tecnico.objects.all().order_by(
            'nombre')  # pylint: disable=no-member
        self.fields['ejecutivo'].queryset = Ejecutivo.objects.all().order_by(  # pylint: disable=no-member
            'nombre')  # pylint: disable=no-member

        self.fields['tecnico1'].label_from_instance = lambda obj: obj.nombre
        self.fields['tecnico2'].label_from_instance = lambda obj: obj.nombre
        self.fields['ejecutivo'].label_from_instance = lambda obj: obj.nombre

        self.fields['ciudad'].queryset = Ciudad.objects.all().order_by(
            'nombre')
        self.fields['ciudad'].label_from_instance = lambda obj: obj.nombre

        if self.instance and self.instance.pk and self.instance.ciudad:
            ciudad_obj = Ciudad.objects.filter(
                nombre__iexact=self.instance.ciudad.strip()
            ).first()

            if ciudad_obj:
                self.initial['ciudad'] = ciudad_obj.pk

        # Deshabilitar en edición (disabled no envía el valor en POST)
        if self.instance and self.instance.pk:
            readonly_fields = ['pvg', 'codigo', 'cliente',
                               'fecha']
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

        # PVG totalmente cerrado
        if self.instance and self.instance.cerrado_total:

            for field in self.fields:
                self.fields[field].disabled = True

        # Legalizado o alistado: solo observación editable
        elif self.instance and (
            self.instance.bloqueado_por_orden or self.instance.alistado
        ):

            for field in self.fields:

                if field != 'observacion':
                    self.fields[field].disabled = True

    def clean(self):
        cleaned_data = super().clean()

        tecnico1 = cleaned_data.get('tecnico1')
        tecnico2 = cleaned_data.get('tecnico2')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        dias_cotizados = cleaned_data.get('dias_cotizados')
        orden = cleaned_data.get('orden')

        # Restaurar fecha original si viene vacía en edición
        if self.instance and self.instance.pk:
            if not cleaned_data.get('fecha') and self.instance.fecha:
                cleaned_data['fecha'] = self.instance.fecha
        else:
            if not cleaned_data.get('fecha'):
                if self.modo_import:
                    self.add_error(
                        'fecha',
                        "La columna 'Ingreso' (fecha y hora) es obligatoria en la importación."
                    )
                else:
                    cleaned_data['fecha'] = now()

        # Validación duplicado por PVG + Ciudad
        pvg = cleaned_data.get('pvg')
        ciudad_obj = cleaned_data.get('ciudad')
        ciudad = ciudad_obj.nombre if ciudad_obj else None
        cleaned_data['ciudad'] = ciudad

        if pvg is not None and ciudad:
            qs = CuadroInsta.objects.filter(
                pvg=pvg,
                ciudad__iexact=ciudad.strip()
            )

            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                self.add_error(
                    'pvg',
                    'Ya existe una instalación con este PVG en esta ciudad.'
                )

        # Restaurar orden solo si viene vacía y ya existía
        if self.instance and self.instance.pk:
            if not cleaned_data.get('orden') and self.instance.orden:
                cleaned_data['orden'] = self.instance.orden

        # Técnicos diferentes
        if tecnico1 and tecnico2 and tecnico1 == tecnico2:
            raise forms.ValidationError(
                "Los técnicos asignados deben ser diferentes."
            )

        # Calcular fecha de terminación
        if fecha_inicio and dias_cotizados is not None:
            cleaned_data['fecha_terminacion'] = fecha_inicio + \
                timedelta(days=dias_cotizados)

        # Calcular cantidad automática de técnicos
        cantidad = 0

        if tecnico1:
            cantidad += 1

        if tecnico2:
            cantidad += 1

        cleaned_data['cantidad_tecnicos'] = cantidad

        # Estados
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

    def save(self, commit=True):
        instancia = super().save(commit=False)

        ciudad = self.cleaned_data.get('ciudad')
        if ciudad:
            instancia.ciudad = ciudad

        cantidad = 0

        if instancia.tecnico1:
            cantidad += 1

        if instancia.tecnico2:
            cantidad += 1

        instancia.cantidad_tecnicos = cantidad

        if commit:
            instancia.save()

        return instancia

    def clean_pvg(self):
        # Aquí deja sólo reglas de formato/rango si quieres
        pvg = self.cleaned_data['pvg']
        # if pvg <= 0:
        #     raise forms.ValidationError("El PVG debe ser un número positivo.")
        return pvg


# Subir información de instalaciones con Excel


class ExcelUploadForm(forms.Form):
    archivo_excel = forms.FileField(label="Selecciona un archivo Excel")
