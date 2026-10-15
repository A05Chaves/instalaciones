from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0037_alter_cotizacionserviciotecnico_mantenimiento"),
    ]

    operations = [
        migrations.RenameField(
            model_name="cotizacionserviciotecnico",
            old_name="numero_ticket",
            new_name="registro",
        ),
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="fecha_orden",
            field=models.DateTimeField(
                db_index=True, default=django.utils.timezone.now
            ),
        ),
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="contacto",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="telefono",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="omt",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="actividad_realizada",
            field=models.TextField(blank=True),
        ),
    ]
