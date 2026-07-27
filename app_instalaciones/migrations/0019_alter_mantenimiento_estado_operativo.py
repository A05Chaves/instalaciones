from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0018_mantenimiento_fecha_creacion_servicio"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mantenimiento",
            name="estado_operativo",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("EN_PROCESO", "En proceso"),
                    ("FINALIZADO", "Realizado"),
                ],
                db_index=True,
                default="PENDIENTE",
                max_length=20,
            ),
        ),
    ]
