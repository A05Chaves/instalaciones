from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0041_crear_rol_cotizaciones"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cotizacionserviciotecnico",
            name="registro",
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
