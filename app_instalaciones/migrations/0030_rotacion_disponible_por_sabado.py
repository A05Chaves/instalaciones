from datetime import timedelta

from django.db import migrations, models


def convertir_mes_en_primer_sabado(apps, schema_editor):
    Rotacion = apps.get_model("app_instalaciones", "RotacionTecnicoDisponible")
    for rotacion in Rotacion.objects.all():
        fecha = rotacion.mes
        dias_hasta_sabado = (5 - fecha.weekday()) % 7
        Rotacion.objects.filter(pk=rotacion.pk).update(
            fecha_sabado=fecha + timedelta(days=dias_hasta_sabado)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("app_instalaciones", "0029_dianolaboraltecnico_jornadalaboraltecnico_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="rotaciontecnicodisponible",
            name="fecha_sabado",
            field=models.DateField(null=True),
        ),
        migrations.RunPython(convertir_mes_en_primer_sabado, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="rotaciontecnicodisponible",
            name="mes",
        ),
        migrations.AlterField(
            model_name="rotaciontecnicodisponible",
            name="fecha_sabado",
            field=models.DateField(
                help_text="Sábado específico asignado al técnico disponible.", unique=True
            ),
        ),
        migrations.AlterModelOptions(
            name="rotaciontecnicodisponible",
            options={"ordering": ["-fecha_sabado"]},
        ),
    ]
