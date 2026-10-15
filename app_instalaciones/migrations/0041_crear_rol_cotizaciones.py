from django.db import migrations


def crear_rol_cotizaciones(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Cotizaciones")


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0040_seguimientocotizaciontecnica"),
    ]

    operations = [
        migrations.RunPython(crear_rol_cotizaciones, migrations.RunPython.noop),
    ]
