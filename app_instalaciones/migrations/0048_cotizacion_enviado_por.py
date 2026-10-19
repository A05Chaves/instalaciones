from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0047_renombrar_visor_a_auditor"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cotizacionserviciotecnico",
            name="enviado_por",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cotizaciones_tecnicas_enviadas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
