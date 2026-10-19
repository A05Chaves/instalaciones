from django.db import migrations


def renombrar_visor(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    visor = Group.objects.filter(name="Visor").first()
    auditor, _ = Group.objects.get_or_create(name="Auditor")
    if visor:
        for usuario in visor.user_set.all():
            usuario.groups.add(auditor)
        visor.delete()


def revertir_a_visor(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    auditor = Group.objects.filter(name="Auditor").first()
    visor, _ = Group.objects.get_or_create(name="Visor")
    if auditor:
        for usuario in auditor.user_set.all():
            usuario.groups.add(visor)


class Migration(migrations.Migration):
    dependencies = [
        ("app_instalaciones", "0046_mantenimiento_en_proceso_requiere_tecnico"),
    ]

    operations = [
        migrations.RunPython(renombrar_visor, revertir_a_visor),
    ]
