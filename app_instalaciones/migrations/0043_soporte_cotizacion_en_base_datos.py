import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0042_cotizacion_registro_unico"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cotizacionserviciotecnico",
            name="soporte",
            field=models.FileField(
                blank=True,
                upload_to="cotizaciones_tecnicas/%Y/%m/",
                validators=[django.core.validators.FileExtensionValidator(["pdf"])],
            ),
        ),
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="soporte_contenido",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="soporte_nombre",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
