from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def crear_roles_monitoreo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Monitoreo")
    Group.objects.get_or_create(name="Administrador Monitoreo")


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0043_soporte_cotizacion_en_base_datos"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="mantenimiento",
            name="estado_operativo",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("EN_PROCESO", "En proceso"),
                    ("PENDIENTE_OMT", "Pendiente OMT"),
                    ("FINALIZADO", "Realizado"),
                ],
                db_index=True,
                default="PENDIENTE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="mantenimiento",
            name="orden_registrada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ordenes_mantenimiento_registradas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(crear_roles_monitoreo, migrations.RunPython.noop),
    ]
