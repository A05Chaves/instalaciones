from django.db import migrations


def _mayusculas(valor):
    if isinstance(valor, str):
        return valor.upper()
    if isinstance(valor, list):
        return [_mayusculas(item) for item in valor]
    if isinstance(valor, dict):
        return {clave: _mayusculas(item) for clave, item in valor.items()}
    return valor


def normalizar_textos(apps, schema_editor):
    Proyecto = apps.get_model("app_instalaciones", "ProyectoSmartCheck")
    Producto = apps.get_model("app_instalaciones", "ProductoProyectoComercial")
    Kit = apps.get_model("app_instalaciones", "KitProyectoComercial")
    Cotizacion = apps.get_model("app_instalaciones", "CotizacionProyectoComercial")
    ItemCotizacion = apps.get_model("app_instalaciones", "ItemCotizacionProyectoComercial")

    for producto in Producto.objects.all().iterator():
        Producto.objects.filter(pk=producto.pk).update(
            nombre=(producto.nombre or "").upper(),
            referencia=(producto.referencia or "").upper(),
            marca=(producto.marca or "").upper(),
            unidad=(producto.unidad or "").upper(),
        )
    for kit in Kit.objects.all().iterator():
        Kit.objects.filter(pk=kit.pk).update(
            nombre=(kit.nombre or "").upper(),
            descripcion=(kit.descripcion or "").upper(),
        )
    for proyecto in Proyecto.objects.all().iterator():
        Proyecto.objects.filter(pk=proyecto.pk).update(
            nombre=(proyecto.nombre or "").upper(), cliente=(proyecto.cliente or "").upper(),
            contacto=(proyecto.contacto or "").upper(), ciudad=(proyecto.ciudad or "").upper(),
            direccion=(proyecto.direccion or "").upper(), georreferencia=(proyecto.georreferencia or "").upper(),
            descripcion_necesidad=(proyecto.descripcion_necesidad or "").upper(),
            observaciones=(proyecto.observaciones or "").upper(),
            datos_tecnicos=_mayusculas(proyecto.datos_tecnicos or {}),
        )
    for cotizacion in Cotizacion.objects.all().iterator():
        Cotizacion.objects.filter(pk=cotizacion.pk).update(
            nombre_propuesta=(cotizacion.nombre_propuesta or "").upper(),
            observaciones=(cotizacion.observaciones or "").upper(),
        )
    for item in ItemCotizacion.objects.all().iterator():
        ItemCotizacion.objects.filter(pk=item.pk).update(
            referencia=(item.referencia or "").upper(),
            descripcion=(item.descripcion or "").upper(),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("app_instalaciones", "0026_kitproyectocomercial_porcentaje_descuento"),
    ]

    operations = [
        migrations.RunPython(normalizar_textos, migrations.RunPython.noop),
    ]
