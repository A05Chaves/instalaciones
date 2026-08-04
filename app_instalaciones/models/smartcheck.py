from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from decimal import Decimal

from .cuadroInstalaciones import Ejecutivo, Tecnico


class ProyectoSmartCheck(models.Model):
    ESTADOS = [
        ("VISITA_PROGRAMADA", "Visita programada"),
        ("PROPUESTA_DISENO", "Propuesta de diseño"),
        ("ENVIADA", "Propuesta enviada"),
        ("APROBADA", "Aprobada"),
        ("RECHAZADA", "Rechazada"),
        ("CERRADA", "Cerrada"),
    ]
    SISTEMAS = [
        ("ALARMA", "Sistema de alarma"),
        ("CCTV", "Videovigilancia"),
        ("ACCESO", "Control de acceso"),
        ("INTELIGENTE", "Edificio inteligente"),
    ]

    numero = models.CharField(max_length=30, unique=True, null=True, blank=True)
    nombre = models.CharField(max_length=150)
    cliente = models.CharField(max_length=150)
    contacto = models.CharField(max_length=120, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    ciudad = models.CharField(max_length=80, blank=True)
    direccion = models.CharField(max_length=180, blank=True)
    georreferencia = models.CharField(max_length=120, blank=True)
    ejecutivo = models.ForeignKey(
        Ejecutivo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="proyectos_smartcheck",
    )
    tecnico = models.ForeignKey(
        Tecnico, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="proyectos_smartcheck",
    )
    fecha_visita = models.DateField(null=True, blank=True, db_index=True)
    estado = models.CharField(
        max_length=30, choices=ESTADOS, default="VISITA_PROGRAMADA", db_index=True
    )
    sistemas = models.JSONField(default=list, blank=True)
    descripcion_necesidad = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    datos_tecnicos = models.JSONField(default=dict, blank=True)
    creado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="proyectos_smartcheck_creados",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-actualizado", "-pk"]
        verbose_name = "Proyecto comercial"
        verbose_name_plural = "Proyectos comerciales"

    def __str__(self):
        return f"{self.numero or 'Proyecto comercial'} - {self.cliente}"

    def save(self, *args, **kwargs):
        for campo in ["nombre", "cliente", "contacto", "ciudad", "direccion", "georreferencia", "descripcion_necesidad", "observaciones"]:
            valor = getattr(self, campo, None)
            if isinstance(valor, str):
                setattr(self, campo, valor.upper())
        super().save(*args, **kwargs)
        if not self.numero:
            numero = f"SC-{timezone.localdate().year}-{self.pk:05d}"
            self.numero = numero
            super().save(update_fields=["numero"])

    @property
    def sistemas_display(self):
        etiquetas = dict(self.SISTEMAS)
        return ", ".join(etiquetas.get(valor, valor) for valor in self.sistemas)

    @property
    def avance(self):
        total = self.items_checklist.count()
        if not total:
            return 0
        revisados = self.items_checklist.exclude(estado="POR_REVISAR").count()
        return round((revisados / total) * 100)


class ItemChecklistSmartCheck(models.Model):
    ESTADOS = [
        ("POR_REVISAR", "Por revisar"),
        ("CUMPLE", "Cumple"),
        ("NO_CUMPLE", "No cumple"),
        ("NO_APLICA", "No aplica"),
        ("PENDIENTE", "Pendiente"),
    ]

    proyecto = models.ForeignKey(
        ProyectoSmartCheck,
        on_delete=models.CASCADE,
        related_name="items_checklist",
    )
    sistema = models.CharField(max_length=20, choices=ProyectoSmartCheck.SISTEMAS)
    etapa = models.CharField(max_length=80, default="Levantamiento técnico")
    item = models.CharField(max_length=220)
    estado = models.CharField(
        max_length=20, choices=ESTADOS, default="POR_REVISAR", db_index=True
    )
    cantidad = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    ubicacion = models.CharField(max_length=180, blank=True)
    observacion = models.TextField(blank=True)
    actualizado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sistema", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["proyecto", "sistema", "item"],
                name="smartcheck_item_unico_por_proyecto",
            )
        ]

    def __str__(self):
        return f"{self.get_sistema_display()}: {self.item}"


class ProductoProyectoComercial(models.Model):
    CATEGORIAS = [
        ("PANEL", "Panel de alarma"), ("SENSOR", "Sensor o dispositivo de zona"),
        ("MODULO", "Módulo"), ("EQUIPO", "Equipo adicional"),
        ("CABLE", "Cable"), ("ACCESORIO", "Accesorio"),
    ]
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, db_index=True)
    nombre = models.CharField(max_length=120)
    referencia = models.CharField(max_length=100, blank=True)
    marca = models.CharField(max_length=80, blank=True)
    precio = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unidad = models.CharField(max_length=30, default="Unidad")
    activo = models.BooleanField(default=True, db_index=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["categoria", "nombre", "referencia"]

    def __str__(self):
        return f"{self.nombre} - {self.referencia}" if self.referencia else self.nombre

    def save(self, *args, **kwargs):
        for campo in ["nombre", "referencia", "marca", "unidad"]:
            valor = getattr(self, campo, None)
            if isinstance(valor, str):
                setattr(self, campo, valor.upper())
        super().save(*args, **kwargs)


class KitProyectoComercial(models.Model):
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    porcentaje_descuento = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    @property
    def valor_equipos(self):
        return sum(item.subtotal for item in self.items.select_related("producto"))

    @property
    def valor_descuento(self):
        porcentaje = Decimal(str(self.porcentaje_descuento or 0))
        return self.valor_equipos * porcentaje / Decimal("100")

    @property
    def precio_total(self):
        return self.valor_equipos - self.valor_descuento

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").upper()
        self.descripcion = (self.descripcion or "").upper()
        super().save(*args, **kwargs)


class ItemKitProyectoComercial(models.Model):
    kit = models.ForeignKey(KitProyectoComercial, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(ProductoProyectoComercial, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kit", "producto"], name="producto_unico_por_kit_comercial")]

    @property
    def subtotal(self):
        return self.producto.precio * self.cantidad


class CotizacionProyectoComercial(models.Model):
    proyecto = models.OneToOneField(
        ProyectoSmartCheck, on_delete=models.CASCADE, related_name="cotizacion"
    )
    kit = models.ForeignKey(
        KitProyectoComercial, on_delete=models.SET_NULL, null=True, blank=True
    )
    nombre_propuesta = models.CharField(max_length=160, blank=True)
    mano_obra = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=19)
    observaciones = models.TextField(blank=True)
    actualizado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cotización de proyecto comercial"

    @property
    def subtotal_productos(self):
        return sum(item.valor_total for item in self.items.all())

    @property
    def subtotal(self):
        return max(self.subtotal_productos + self.mano_obra - self.descuento, 0)

    @property
    def valor_iva(self):
        return self.subtotal * self.porcentaje_iva / 100

    @property
    def total(self):
        return self.subtotal + self.valor_iva

    def save(self, *args, **kwargs):
        self.nombre_propuesta = (self.nombre_propuesta or "").upper()
        self.observaciones = (self.observaciones or "").upper()
        super().save(*args, **kwargs)


class ItemCotizacionProyectoComercial(models.Model):
    cotizacion = models.ForeignKey(
        CotizacionProyectoComercial, on_delete=models.CASCADE, related_name="items"
    )
    producto = models.ForeignKey(
        ProductoProyectoComercial, on_delete=models.SET_NULL, null=True, blank=True
    )
    referencia = models.CharField(max_length=100, blank=True)
    descripcion = models.CharField(max_length=300)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    valor_unitario = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    incluido_kit = models.BooleanField(default=False)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden", "pk"]

    @property
    def valor_total(self):
        if self.incluido_kit:
            return 0
        return self.cantidad * self.valor_unitario

    def save(self, *args, **kwargs):
        self.referencia = (self.referencia or "").upper()
        self.descripcion = (self.descripcion or "").upper()
        super().save(*args, **kwargs)
