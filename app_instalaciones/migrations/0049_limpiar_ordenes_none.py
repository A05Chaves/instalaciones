from django.db import migrations
from django.db.models import Q


def limpiar_ordenes_invalidas(apps, schema_editor):
    Mantenimiento = apps.get_model("app_instalaciones", "Mantenimiento")
    registros = Mantenimiento.objects.filter(
        Q(orden__iexact="none") | Q(orden__iexact="null")
    )
    for mantenimiento in registros.iterator():
        mantenimiento.orden = None
        mantenimiento.fecha_orden = None
        mantenimiento.orden_registrada_por_id = None
        if mantenimiento.estado_operativo == "FINALIZADO":
            mantenimiento.estado_operativo = (
                "PENDIENTE_OMT"
                if mantenimiento.fin_tecnico
                else "PENDIENTE"
            )
        mantenimiento.save(update_fields=[
            "orden",
            "fecha_orden",
            "orden_registrada_por",
            "estado_operativo",
        ])


class Migration(migrations.Migration):

    dependencies = [
        ("app_instalaciones", "0048_cotizacion_enviado_por"),
    ]

    operations = [
        migrations.RunPython(
            limpiar_ordenes_invalidas,
            migrations.RunPython.noop,
        ),
    ]
