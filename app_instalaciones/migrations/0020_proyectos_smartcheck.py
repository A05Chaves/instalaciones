from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0019_alter_mantenimiento_estado_operativo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProyectoSmartCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(blank=True, max_length=30, null=True, unique=True)),
                ("nombre", models.CharField(max_length=150)),
                ("cliente", models.CharField(max_length=150)),
                ("contacto", models.CharField(blank=True, max_length=120)),
                ("telefono", models.CharField(blank=True, max_length=40)),
                ("ciudad", models.CharField(blank=True, max_length=80)),
                ("direccion", models.CharField(blank=True, max_length=180)),
                ("georreferencia", models.CharField(blank=True, max_length=120)),
                ("fecha_visita", models.DateField(blank=True, db_index=True, null=True)),
                ("estado", models.CharField(choices=[("BORRADOR", "Borrador"), ("VISITA_PROGRAMADA", "Visita programada"), ("LEVANTAMIENTO", "Levantamiento en proceso"), ("DISENO", "Pendiente de diseño"), ("PROPUESTA", "Propuesta en preparación"), ("ENVIADA", "Propuesta enviada"), ("REVISION_CLIENTE", "En revisión del cliente"), ("APROBADA", "Aprobada"), ("RECHAZADA", "Rechazada"), ("INSTALACION", "En instalación"), ("PRUEBAS", "En pruebas"), ("ENTREGA", "Pendiente de entrega"), ("ENTREGADA", "Entregada"), ("CERRADA", "Cerrada")], db_index=True, default="BORRADOR", max_length=30)),
                ("sistemas", models.JSONField(blank=True, default=list)),
                ("descripcion_necesidad", models.TextField(blank=True)),
                ("observaciones", models.TextField(blank=True)),
                ("datos_tecnicos", models.JSONField(blank=True, default=dict)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True, db_index=True)),
                ("creado_por", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="proyectos_smartcheck_creados", to=settings.AUTH_USER_MODEL)),
                ("ejecutivo", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="proyectos_smartcheck", to="app_instalaciones.ejecutivo")),
                ("tecnico", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="proyectos_smartcheck", to="app_instalaciones.tecnico")),
            ],
            options={"verbose_name": "Proyecto SmartCheck", "verbose_name_plural": "Proyectos SmartCheck", "ordering": ["-actualizado", "-pk"]},
        ),
        migrations.CreateModel(
            name="ItemChecklistSmartCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sistema", models.CharField(choices=[("ALARMA", "Sistema de alarma"), ("CCTV", "Videovigilancia"), ("ACCESO", "Control de acceso"), ("INTELIGENTE", "Edificio inteligente")], max_length=20)),
                ("etapa", models.CharField(default="Levantamiento técnico", max_length=80)),
                ("item", models.CharField(max_length=220)),
                ("estado", models.CharField(choices=[("POR_REVISAR", "Por revisar"), ("CUMPLE", "Cumple"), ("NO_CUMPLE", "No cumple"), ("NO_APLICA", "No aplica"), ("PENDIENTE", "Pendiente")], db_index=True, default="POR_REVISAR", max_length=20)),
                ("cantidad", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("ubicacion", models.CharField(blank=True, max_length=180)),
                ("observacion", models.TextField(blank=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("actualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("proyecto", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items_checklist", to="app_instalaciones.proyectosmartcheck")),
            ],
            options={"ordering": ["sistema", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="itemchecklistsmartcheck",
            constraint=models.UniqueConstraint(fields=("proyecto", "sistema", "item"), name="smartcheck_item_unico_por_proyecto"),
        ),
    ]
