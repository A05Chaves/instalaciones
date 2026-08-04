from django import forms
from decimal import Decimal
import json
import math

from .cuadroInstalaciones import Ejecutivo, Tecnico
from .smartcheck import ProductoProyectoComercial, ProyectoSmartCheck


class ProyectoSmartCheckForm(forms.ModelForm):
    sistemas = forms.MultipleChoiceField(
        choices=ProyectoSmartCheck.SISTEMAS,
        widget=forms.CheckboxSelectMultiple,
        label="Sistemas que se van a ofertar",
    )

    pisos = forms.IntegerField(min_value=1, required=False, initial=1)
    largo = forms.DecimalField(min_value=0, required=False, decimal_places=2)
    ancho = forms.DecimalField(min_value=0, required=False, decimal_places=2)
    altura_piso = forms.DecimalField(min_value=0, required=False, decimal_places=2)

    tipo_cctv = forms.ChoiceField(
        choices=[("", "Seleccione"), ("IP", "IP"), ("ANALOGO", "Análogo"), ("HIBRIDO", "Híbrido")],
        required=False,
    )
    camaras_internas = forms.IntegerField(min_value=0, required=False, initial=0)
    camaras_exteriores = forms.IntegerField(min_value=0, required=False, initial=0)
    camaras_parqueadero = forms.IntegerField(min_value=0, required=False, initial=0)
    dias_grabacion = forms.IntegerField(min_value=1, required=False, initial=30)

    panel_alarma = forms.CharField(
        required=False, initial="Panel de alarma", label="Panel propuesto"
    )
    capacidad_panel = forms.IntegerField(
        min_value=1, required=False, label="Capacidad del panel"
    )
    bateria_alarma = forms.CharField(
        required=False, initial="Batería 12 V / 7 Ah", label="Batería incluida"
    )
    transformador_alarma = forms.CharField(
        required=False, initial="Transformador para panel", label="Transformador incluido"
    )
    panel_piso = forms.IntegerField(min_value=1, required=False, initial=1, label="Piso donde se ubica el panel")
    panel_area = forms.CharField(required=False, label="Área central donde se ubica el panel")
    sirenas = forms.IntegerField(
        min_value=0, required=False, initial=1, label="Cantidad de sirenas"
    )
    comunicacion_alarma = forms.ChoiceField(
        choices=[("", "Seleccione"), ("IP", "IP"), ("CELULAR", "Celular"), ("IP_CELULAR", "IP + celular")],
        required=False,
        label="Tipo de comunicador",
    )
    conexion_monitoreo = forms.BooleanField(
        required=False, label="Conexión a central de monitoreo"
    )
    central_monitoreo = forms.CharField(
        required=False, label="Central de monitoreo"
    )
    reserva_cable = forms.DecimalField(
        min_value=0, max_value=100, required=False, initial=15,
        decimal_places=1, label="Reserva de cable (%)",
    )
    porcentaje_canaleta = forms.DecimalField(
        min_value=0, max_value=100, required=False, initial=60,
        decimal_places=1, label="Cable instalado en canaleta (%)",
    )
    areas_alarma_json = forms.CharField(
        required=False, widget=forms.HiddenInput, initial="[]"
    )
    dispositivos_alarma_json = forms.CharField(
        required=False, widget=forms.HiddenInput, initial="[]"
    )
    modulos_alarma_json = forms.CharField(
        required=False, widget=forms.HiddenInput, initial="[]"
    )

    puertas_controladas = forms.IntegerField(min_value=0, required=False, initial=0)
    puertas_dobles = forms.IntegerField(min_value=0, required=False, initial=0)
    lectores = forms.IntegerField(min_value=0, required=False, initial=0)
    tipo_credencial = forms.ChoiceField(
        choices=[("", "Seleccione"), ("TARJETA", "Tarjeta"), ("BIOMETRIA", "Biometría"), ("MOVIL", "Credencial móvil"), ("MIXTO", "Mixto")],
        required=False,
    )

    automatizacion_iluminacion = forms.BooleanField(required=False)
    control_energia = forms.BooleanField(required=False)
    citofonia = forms.BooleanField(required=False)
    integracion_ascensores = forms.BooleanField(required=False)
    plataforma_central = forms.BooleanField(required=False)

    CAMPOS_TECNICOS = [
        "pisos", "largo", "ancho", "altura_piso",
        "tipo_cctv", "camaras_internas", "camaras_exteriores",
        "camaras_parqueadero", "dias_grabacion",
        "panel_alarma", "capacidad_panel", "bateria_alarma",
        "transformador_alarma", "panel_piso", "panel_area", "sirenas", "comunicacion_alarma",
        "conexion_monitoreo", "central_monitoreo",
        "reserva_cable", "porcentaje_canaleta",
        "puertas_controladas", "puertas_dobles", "lectores", "tipo_credencial",
        "automatizacion_iluminacion", "control_energia", "citofonia",
        "integracion_ascensores", "plataforma_central",
    ]

    class Meta:
        model = ProyectoSmartCheck
        fields = [
            "nombre", "cliente", "contacto", "telefono", "ciudad", "direccion",
            "georreferencia", "ejecutivo", "tecnico", "fecha_visita", "estado",
            "sistemas", "descripcion_necesidad", "observaciones",
        ]
        widgets = {
            "fecha_visita": forms.DateInput(attrs={"type": "date"}),
            "descripcion_necesidad": forms.Textarea(attrs={"rows": 3}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        paneles = list(
            ProductoProyectoComercial.objects.filter(
                categoria="PANEL", activo=True
            ).order_by("nombre", "referencia")
        )
        opciones_panel = [("", "Seleccione un panel configurado")]
        opciones_panel.extend((str(panel), str(panel)) for panel in paneles)
        valor_actual = ""
        if self.instance and self.instance.pk:
            valor_actual = str(self.instance.datos_tecnicos.get("panel_alarma") or "")
        elif self.is_bound:
            valor_actual = str(self.data.get("panel_alarma") or "")
        if valor_actual and valor_actual not in {valor for valor, _ in opciones_panel} and not paneles:
            opciones_panel.append((valor_actual, valor_actual))
        self.fields["panel_alarma"] = forms.ChoiceField(
            choices=opciones_panel, required=False, label="Panel propuesto"
        )
        self.fields["ejecutivo"].queryset = Ejecutivo.objects.all().order_by("nombre")
        self.fields["tecnico"].queryset = Tecnico.objects.all().order_by("nombre")
        for nombre, campo in self.fields.items():
            if nombre == "sistemas":
                continue
            clase = "form-check-input" if isinstance(
                campo.widget, forms.CheckboxInput
            ) else "form-select" if isinstance(
                campo.widget, forms.Select
            ) else "form-control"
            campo.widget.attrs["class"] = clase

        if self.instance and self.instance.pk:
            self.initial["sistemas"] = self.instance.sistemas
            for campo in self.CAMPOS_TECNICOS:
                if campo in self.instance.datos_tecnicos:
                    self.initial[campo] = self.instance.datos_tecnicos[campo]
            self.initial["areas_alarma_json"] = json.dumps(
                self.instance.datos_tecnicos.get("areas_alarma", [])
            )
            self.initial["dispositivos_alarma_json"] = json.dumps(
                self.instance.datos_tecnicos.get("dispositivos_alarma", [])
            )
            self.initial["modulos_alarma_json"] = json.dumps(
                self.instance.datos_tecnicos.get("modulos_alarma", [])
            )

    @staticmethod
    def _leer_lista_json(valor, campos_permitidos):
        try:
            elementos = json.loads(valor or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(elementos, list):
            return []
        resultado = []
        for elemento in elementos[:200]:
            if not isinstance(elemento, dict):
                continue
            limpio = {
                campo: elemento.get(campo, "")
                for campo in campos_permitidos
            }
            if any(str(valor or "").strip() for valor in limpio.values()):
                resultado.append(limpio)
        return resultado

    def clean(self):
        cleaned = super().clean()
        sistemas = cleaned.get("sistemas") or []
        if not sistemas:
            self.add_error("sistemas", "Seleccione al menos un sistema.")
        if (
            "ACCESO" in sistemas
            and (cleaned.get("puertas_dobles") or 0)
            > (cleaned.get("puertas_controladas") or 0)
        ):
            self.add_error(
                "puertas_dobles",
                "Las puertas dobles no pueden superar las puertas controladas.",
            )
        areas = self._leer_lista_json(
            cleaned.get("areas_alarma_json"),
            ["nombre", "piso", "largo", "ancho", "alto", "nivel_riesgo", "descripcion"],
        )
        dispositivos = self._leer_lista_json(
            cleaned.get("dispositivos_alarma_json"),
            ["tipo", "area", "ubicacion", "conexion", "descripcion", "cable_producto", "cable_nombre"],
        )
        modulos = self._leer_lista_json(
            cleaned.get("modulos_alarma_json"),
            ["producto_id", "equipo", "referencia", "precio", "cantidad", "ubicacion", "descripcion"],
        )
        for lista in [areas, dispositivos, modulos]:
            for item in lista:
                for clave, valor in item.items():
                    if isinstance(valor, str) and clave not in {"producto_id", "cantidad", "precio", "largo", "ancho", "alto", "piso"}:
                        item[clave] = valor.upper()
        ids_equipos = {
            int(item["producto_id"]) for item in modulos
            if str(item.get("producto_id") or "").isdigit()
        }
        productos_equipos = {
            producto.pk: producto
            for producto in ProductoProyectoComercial.objects.filter(
                pk__in=ids_equipos,
                categoria__in=["MODULO", "EQUIPO", "ACCESORIO"], activo=True,
            )
        }
        for item in modulos:
            producto = productos_equipos.get(int(item["producto_id"])) if str(item.get("producto_id") or "").isdigit() else None
            if producto:
                item["equipo"] = producto.nombre
                item["referencia"] = producto.referencia
                item["precio"] = str(producto.precio)
        if ProductoProyectoComercial.objects.filter(categoria__in=["MODULO", "EQUIPO", "ACCESORIO"], activo=True).exists() and any(not item.get("equipo") for item in modulos):
            self.add_error("modulos_alarma_json", "Seleccione los equipos adicionales desde el catálogo configurado.")
        cleaned["areas_alarma"] = areas
        cleaned["dispositivos_alarma"] = dispositivos
        cleaned["modulos_alarma"] = modulos

        if "ALARMA" in sistemas and not areas:
            self.add_error(
                "areas_alarma_json",
                "Registre al menos un área o punto vulnerable.",
            )
        pisos_edificacion = int(cleaned.get("pisos") or 1)
        for area in areas:
            try:
                piso_area = int(area.get("piso") or 1)
            except (TypeError, ValueError):
                piso_area = 1
            if piso_area > pisos_edificacion:
                self.add_error("areas_alarma_json", f"El piso {piso_area} supera los {pisos_edificacion} pisos registrados para la edificación.")
                break
        if int(cleaned.get("panel_piso") or 1) > pisos_edificacion:
            self.add_error("panel_piso", "El piso del panel no puede superar la cantidad de pisos de la edificación.")
        nombres_areas = {str(area.get("nombre") or "").strip().lower() for area in areas}
        if any(str(dispositivo.get("area") or "").strip().lower() not in nombres_areas for dispositivo in dispositivos):
            self.add_error("dispositivos_alarma_json", "Cada sensor debe estar asociado con un área vulnerable registrada.")
        if ProductoProyectoComercial.objects.filter(categoria="CABLE", activo=True).exists() and any(
            dispositivo.get("conexion") == "CABLEADO" and not str(dispositivo.get("cable_producto") or "").isdigit()
            for dispositivo in dispositivos
        ):
            self.add_error("dispositivos_alarma_json", "Seleccione un producto de cable para cada sensor cableado.")

        tipos_zona = {
            "MOVIMIENTO", "MAGNETICO", "PANICO", "VIDRIO",
            "HUMO", "INUNDACION", "OTRO_ZONA",
        }
        zonas = sum(1 for dispositivo in dispositivos if dispositivo.get("tipo"))
        capacidades = [8, 16, 32, 64, 128, 256]
        recomendada = next(
            (capacidad for capacidad in capacidades if capacidad >= zonas),
            max(zonas, 256),
        )
        cleaned["zonas_calculadas"] = zonas
        cleaned["capacidad_recomendada"] = recomendada
        reserva = float(cleaned.get("reserva_cable") or 0) / 100
        porcentaje_canaleta = float(
            cleaned.get("porcentaje_canaleta") or 0
        ) / 100
        areas_por_nombre = {
            str(area.get("nombre") or "").strip().lower(): area
            for area in areas
        }
        panel_piso = int(cleaned.get("panel_piso") or 1)
        altura_edificacion = float(cleaned.get("altura_piso") or 0)

        def distancia_dispositivo(dispositivo):
            area = areas_por_nombre.get(
                str(dispositivo.get("area") or "").strip().lower(), {}
            )
            try:
                largo = float(area.get("largo") or 0)
                ancho = float(area.get("ancho") or 0)
                alto = float(area.get("alto") or 0)
            except (TypeError, ValueError):
                largo = ancho = alto = 0
            # Diagonal del área + recorrido vertical + reserva de llegada al panel.
            try:
                piso_area = int(area.get("piso") or 1)
            except (TypeError, ValueError):
                piso_area = 1
            altura_nivel = altura_edificacion or alto or 3
            recorrido_vertical = abs(piso_area - panel_piso) * altura_nivel
            return max(5, math.hypot(largo, ancho) + recorrido_vertical + 3)

        cable_2x22 = 0
        cable_4x22 = 0
        cables_por_producto = {}
        for dispositivo in dispositivos:
            if dispositivo.get("conexion") == "INALAMBRICO":
                continue
            distancia = distancia_dispositivo(dispositivo)
            cable_nombre = str(dispositivo.get("cable_nombre") or "").upper()
            cable_producto = str(dispositivo.get("cable_producto") or "")
            if cable_producto.isdigit():
                cables_por_producto[cable_producto] = cables_por_producto.get(cable_producto, 0) + distancia
            if "2X22" in cable_nombre or dispositivo.get("tipo") in {"MAGNETICO", "PANICO"}:
                cable_2x22 += distancia
            else:
                cable_4x22 += distancia

        sirenas = int(cleaned.get("sirenas") or 0)
        cable_sirena = sirenas * 10
        cable_utp = (
            10
            if cleaned.get("comunicacion_alarma") in {"IP", "IP_CELULAR"}
            else 0
        )
        factor_reserva = 1 + reserva
        cable_2x22 *= factor_reserva
        cable_4x22 *= factor_reserva
        cable_sirena *= factor_reserva
        cable_utp *= factor_reserva
        cable_total = cable_2x22 + cable_4x22 + cable_sirena + cable_utp
        productos_cable = {
            str(producto.pk): producto
            for producto in ProductoProyectoComercial.objects.filter(pk__in=cables_por_producto.keys(), categoria="CABLE")
        }
        detalle_cables = []
        for producto_id, metros in cables_por_producto.items():
            producto = productos_cable.get(producto_id)
            if not producto:
                continue
            metros_estimados = math.ceil(metros * factor_reserva)
            detalle_cables.append({
                "producto_id": producto.pk, "nombre": producto.nombre,
                "referencia": producto.referencia, "metros": metros_estimados,
                "precio_unitario": float(producto.precio),
                "subtotal": float(producto.precio * metros_estimados),
            })
        canaleta_metros = cable_total * porcentaje_canaleta
        tramos_canaleta = math.ceil(canaleta_metros / 2)
        cleaned["calculo_materiales_alarma"] = {
            "cable_2x22_m": math.ceil(cable_2x22),
            "cable_4x22_m": math.ceil(cable_4x22),
            "cable_sirena_m": math.ceil(cable_sirena),
            "cable_utp_m": math.ceil(cable_utp),
            "cable_total_m": math.ceil(cable_total),
            "canaleta_metros": math.ceil(canaleta_metros),
            "canaleta_tramos_2m": tramos_canaleta,
            "uniones": max(0, tramos_canaleta - 1),
            "curvas": math.ceil(tramos_canaleta / 5) if tramos_canaleta else 0,
            "terminales": max(0, len(dispositivos) + sirenas),
            "fijaciones": tramos_canaleta * 4,
            "cables_productos": detalle_cables,
        }
        if "ALARMA" in sistemas:
            capacidad_elegida = cleaned.get("capacidad_panel")
            if capacidad_elegida and capacidad_elegida < zonas:
                self.add_error(
                    "capacidad_panel",
                    f"El panel debe soportar por lo menos {zonas} zonas.",
                )
        return cleaned

    def save(self, commit=True):
        proyecto = super().save(commit=False)
        proyecto.sistemas = list(self.cleaned_data["sistemas"])
        def serializar(valor):
            if isinstance(valor, Decimal):
                return float(valor)
            if isinstance(valor, str):
                return valor.upper()
            return valor
        proyecto.datos_tecnicos = {
            campo: serializar(self.cleaned_data.get(campo))
            for campo in self.CAMPOS_TECNICOS
        }
        proyecto.datos_tecnicos.update({
            "areas_alarma": self.cleaned_data.get("areas_alarma", []),
            "dispositivos_alarma": self.cleaned_data.get(
                "dispositivos_alarma", []
            ),
            "modulos_alarma": self.cleaned_data.get("modulos_alarma", []),
            "zonas_calculadas": self.cleaned_data.get("zonas_calculadas", 0),
            "capacidad_recomendada": self.cleaned_data.get(
                "capacidad_recomendada", 8
            ),
            "calculo_materiales_alarma": self.cleaned_data.get(
                "calculo_materiales_alarma", {}
            ),
        })
        if commit:
            proyecto.save()
        return proyecto


class ProductoProyectoComercialForm(forms.ModelForm):
    class Meta:
        model = ProductoProyectoComercial
        fields = ["categoria", "nombre", "referencia", "marca", "precio", "unidad", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-check-input" if isinstance(campo.widget, forms.CheckboxInput) else "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
