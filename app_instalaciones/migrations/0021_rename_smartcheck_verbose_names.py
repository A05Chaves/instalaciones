from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0020_proyectos_smartcheck"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="proyectosmartcheck",
            options={
                "ordering": ["-actualizado", "-pk"],
                "verbose_name": "Proyecto comercial",
                "verbose_name_plural": "Proyectos comerciales",
            },
        ),
    ]
