from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Tecnico(models.Model):
    # ← bien: no se permite null
    nombre = models.CharField(max_length=100, unique=True)
    usuario = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="perfil_tecnico",
        help_text="Usuario que ingresará al portal móvil.",
    )

    def __str__(self):
        return str(self.nombre or "Sin nombre")
    objects = models.Manager()  # ayuda a Pylint


class Ejecutivo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return str(self.nombre or "Ejecutivo sin nombre")


class CuadroInsta(models.Model):
    BODEGA = [
        ("SI", "Sí"),
        ("NO", "No"),
    ]

    ESTADO_FACTURACION_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("FACTURADO", "Facturado"),
        ("RETENIDO", "Retenido"),
    ]

    # Si PVG a veces viene vacío durante import, permite null/blank.
    # db_index acelera búsquedas/validaciones durante importaciones masivas.
    pvg = models.IntegerField(null=True, blank=True, db_index=True)

    # Fecha: si la fuente no trae fecha, usa un default
    fecha = models.DateTimeField(default=timezone.now)

    # codigo = models.IntegerField(null=True, blank=True, db_index=True)
    codigo = models.CharField(max_length=50, null=True,
                              blank=True, db_index=True)

    cliente = models.CharField(max_length=100, null=True, blank=True)
    ciudad = models.CharField(max_length=30, null=True,
                              blank=True, db_index=True)
    direccion = models.CharField(max_length=100, null=True, blank=True)

    instalacion = models.TextField(null=True, blank=True)
    dias_cotizados = models.IntegerField(null=True, blank=True)
    cantidad_tecnicos = models.IntegerField(null=True, blank=True)

    en_bodega = models.CharField(
        choices=BODEGA, max_length=2, default="NO", blank=True
    )

    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_terminacion = models.DateField(null=True, blank=True)
    finaliza = models.DateField(null=True, blank=True)

    # VARIABLES DE CALCULO DE INDICADOR

    alistado = models.BooleanField(default=False)
    fecha_alistado = models.DateField(null=True, blank=True)

    facturado = models.BooleanField(default=False)
    estado_facturacion = models.CharField(
        max_length=10,
        choices=ESTADO_FACTURACION_CHOICES,
        default="PENDIENTE",
        db_index=True,
    )
    fecha_facturacion = models.DateField(null=True, blank=True)

    # METODO PARA CALCULAR TIEMPO DE DEMORA EN EL INDICADOR DE FACTURACION

    def save(self, *args, **kwargs):
        # Si no está legalizado, no puede estar alistado ni facturado
        if self.estado != "LEGALIZADO":
            self.alistado = False
            self.fecha_alistado = None
            self.facturado = False
            self.estado_facturacion = "PENDIENTE"
            self.fecha_facturacion = None

        else:
            # Alistado
            if self.alistado and not self.fecha_alistado:
                self.fecha_alistado = timezone.now().date()

            if not self.alistado:
                self.fecha_alistado = None
                self.facturado = False
                self.estado_facturacion = "PENDIENTE"
                self.fecha_facturacion = None

            # Facturado solo si ya está alistado
            decision_facturacion = self.estado_facturacion in {
                "FACTURADO", "RETENIDO"
            }

            if decision_facturacion and self.alistado and not self.fecha_facturacion:
                self.fecha_facturacion = timezone.now().date()

            self.facturado = self.estado_facturacion == "FACTURADO"

            if not decision_facturacion:
                self.fecha_facturacion = None

        super().save(*args, **kwargs)

    @property
    def dias_instalacion(self):
        if self.fecha and self.fecha_inicio:
            return (self.fecha_inicio - self.fecha.date()).days
        return None

    @property
    def dias_para_alistar(self):
        if self.finaliza and self.fecha_alistado:
            return (self.fecha_alistado - self.finaliza).days
        return None

    @property
    def dias_para_facturar(self):
        if self.fecha_alistado and self.fecha_facturacion:
            return (self.fecha_facturacion - self.fecha_alistado).days
        return None

    @property
    def dias_cierre_total(self):
        if self.finaliza and self.fecha_facturacion:
            return (self.fecha_facturacion - self.finaliza).days
        return None

    orden = models.CharField(max_length=50, null=True, blank=True)

    # Relaciones con técnicos (pueden no existir al momento del import)
    tecnico1 = models.ForeignKey(
        'Tecnico', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cuadroinsta_tecnico1'
    )
    tecnico2 = models.ForeignKey(
        'Tecnico', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cuadroinsta_tecnico2'
    )

    estado = models.CharField(max_length=50, null=True, blank=True)
    observacion = models.TextField(null=True, blank=True)

    # Relación con Ejecutivo (igual: opcional durante import)
    ejecutivo = models.ForeignKey(
        'Ejecutivo', null=True, blank=True, on_delete=models.SET_NULL
    )

    updated_at = models.DateTimeField(auto_now=True)
    usuario = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL)

    @property
    def bloqueado_por_orden(self):
        return bool(self.orden) and self.estado == "LEGALIZADO"

    @property
    def cerrado_total(self):
        return (
            self.estado_facturacion in {"FACTURADO", "RETENIDO"}
            and self.fecha_facturacion is not None
        )

    def __str__(self):
        cod = self.codigo if self.codigo not in (None, "") else "-"
        cli = self.cliente if self.cliente not in (None, "") else "Sin cliente"
        return f"Instalación #{cod} - {cli}"

    class Meta:
        # Permite repetir PVG si la ciudad es distinta; bloquea solo (pvg, ciudad) iguales
        unique_together = (('pvg', 'ciudad'),)
        # Útil para listados recientes
        ordering = ['-fecha', '-updated_at']

# guarda los registros de importacion de archivos excel


class RegistroImportacion(models.Model):
    nombre_archivo = models.CharField(max_length=255, unique=True)
    fecha_importacion = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nombre_archivo} - {self.fecha_importacion.strftime('%Y-%m-%d %H:%M')}"  # pylint: disable=no-member


# TABLA DE MANTENIMIENTOS EDITADA

class Mantenimiento(models.Model):
    ESTADO_OPERATIVO_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("EN_PROCESO", "En proceso"),
        ("FINALIZADO", "Realizado"),
    ]
    # NUEVO: tipo de falla (para el select del template)
    TIPO_SERVICIO_CHOICES = [
        ("MANTENIMIENTO CORRECTIVO", "Mantenimiento correctivo"),
        ("MANTENIMIENTO PREVENTIVO", "Mantenimiento preventivo"),
        ("INSTALACION", "Instalación"),
        ("CCTV", "CCTV"),
        ("OTRO SERVICIO", "Otro servicio"),
    ]

    TIPO_FALLA_CHOICES = [
        ("F.COMUNICACION", "F. Comunicación"),
        ("F.CORRIENTE", "F. Corriente"),
        ("FALLOS EQUIPOS", "Fallos equipos"),
        ("ACTIVACION", "Activación"),
        ("PROGRAMACION", "Programación"),
        ("ACT.DATOS", "Actualización de datos"),
        ("CCTV", "CCTV"),
        ("INSTALACION", "Instalación"),
        ("MANTO PREVENTIVO", "Mantenimiento preventivo"),
        ("OTRO SERVICIO", "Otro servicio"),
        ("OTRO", "Otro"),
    ]

    cliente = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=50, null=True, blank=True)
    direccion = models.CharField(max_length=100)
    novedad = models.TextField(null=True, blank=True)
    observacion = models.TextField(null=True, blank=True)

    # Mejor que sea CharField como en CuadroInsta
    codigo = models.CharField(max_length=50, db_index=True)

    # NUEVO: tipo de falla

    tipo_servicio = models.CharField(
        max_length=30,
        choices=TIPO_SERVICIO_CHOICES,
        default="MANTENIMIENTO CORRECTIVO",
        db_index=True
    )

    tipo_falla = models.CharField(
        max_length=20, choices=TIPO_FALLA_CHOICES, null=True, blank=True
    )

    # CAMBIO: de CharField → ForeignKey
    tecnico = models.ForeignKey(
        "Tecnico", on_delete=models.SET_NULL, null=True, blank=True
    )
    fecha_programada = models.DateField(null=True, blank=True, db_index=True)
    estado_operativo = models.CharField(
        max_length=20,
        choices=ESTADO_OPERATIVO_CHOICES,
        default="PENDIENTE",
        db_index=True,
    )

    archivo = models.FileField(
        upload_to='mantenimientos/',
        null=True,
        blank=True
    )

    pendiente = models.TextField(null=True, blank=True)
    horas = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True)
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida = models.TimeField(null=True, blank=True)
    orden = models.CharField(max_length=50, null=True, blank=True)
    fecha_orden = models.DateTimeField(null=True, blank=True)
    realizado = models.DateField(null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_creacion_servicio = models.DateTimeField(null=True, blank=True, db_index=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    numero_ticket = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        verbose_name="Ticket"
    )

    estado_ticket = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        db_index=True
    )

    fecha_inicio = models.DateTimeField(
        null=True,
        blank=True
    )

    fecha_fin = models.DateTimeField(
        null=True,
        blank=True
    )

    inicio_tecnico = models.DateTimeField(null=True, blank=True)
    fin_tecnico = models.DateTimeField(null=True, blank=True)

    codigo_acta = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    problema_solucionado = models.CharField(
        max_length=10,
        null=True,
        blank=True
    )

    cotizacion = models.CharField(
        max_length=10,
        null=True,
        blank=True
    )

    omt = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    @property
    def duracion_servicio(self):
        """Devuelve la duración en formato HH:MM:SS sin cambiar el valor decimal."""
        segundos_totales = None

        if self.inicio_tecnico and self.fin_tecnico:
            segundos = (self.fin_tecnico - self.inicio_tecnico).total_seconds()
            if segundos > 0:
                segundos_totales = round(segundos)
        elif self.estado_operativo != "PENDIENTE":
            return ""
        elif self.fecha_inicio and self.fecha_fin:
            segundos = (self.fecha_fin - self.fecha_inicio).total_seconds()
            if segundos > 0:
                segundos_totales = round(segundos)
        elif self.hora_entrada and self.hora_salida:
            entrada = self.hora_entrada.hour * 60 + self.hora_entrada.minute
            salida = self.hora_salida.hour * 60 + self.hora_salida.minute
            if salida > entrada:
                segundos_totales = (salida - entrada) * 60
        elif self.horas is not None and self.horas > 0:
            segundos_totales = round(float(self.horas) * 3600)

        if segundos_totales is None:
            return ""

        horas, resto = divmod(segundos_totales, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    def __str__(self):
        return f"{self.fecha_registro.strftime('%Y-%m-%d %H:%M')} - {self.cliente}"

    @property
    def fecha_visible(self):
        return self.fecha_creacion_servicio or self.fecha_registro

    def save(self, *args, **kwargs):
        permitir_estado_manual = kwargs.pop("permitir_estado_manual", False)
        # El cierre manual solo es válido cuando el operador diligenció toda la
        # información. Asignar un técnico o indicar únicamente una fecha no debe
        # marcar el servicio como realizado.
        cierre_operador_completo = all([
            self.orden,
            self.realizado,
            self.hora_entrada,
            self.hora_salida,
            (self.novedad or "").strip(),
        ])
        if cierre_operador_completo and not permitir_estado_manual:
            self.estado_operativo = "FINALIZADO"
        if self.orden and not self.fecha_orden:
            self.fecha_orden = timezone.now()
        super().save(*args, **kwargs)


class HistorialAsignacionMantenimiento(models.Model):
    mantenimiento = models.ForeignKey(
        Mantenimiento, on_delete=models.CASCADE, related_name="historial_asignaciones"
    )
    tecnico_anterior = models.ForeignKey(
        Tecnico, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="asignaciones_retiradas",
    )
    tecnico_nuevo = models.ForeignKey(
        Tecnico, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="asignaciones_recibidas",
    )
    cambiado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]


class NotificacionTecnico(models.Model):
    TIPOS = [
        ("ASIGNACION", "Asignación"),
        ("REASIGNACION", "Reasignación"),
        ("RETIRADO", "Servicio retirado"),
    ]
    tecnico = models.ForeignKey(
        Tecnico, on_delete=models.CASCADE, related_name="notificaciones"
    )
    mantenimiento = models.ForeignKey(
        Mantenimiento, on_delete=models.CASCADE, related_name="notificaciones"
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    mensaje = models.CharField(max_length=250)
    leida = models.BooleanField(default=False, db_index=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]


# MODELO PARA CIUDADES

class Ciudad(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre
