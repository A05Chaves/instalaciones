from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0049_limpiar_ordenes_none"),
    ]

    operations = [
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="numero_pedido",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
    ]
