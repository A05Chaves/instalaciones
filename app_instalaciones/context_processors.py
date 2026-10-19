def permisos_usuario(request):

    user = request.user

    if not user.is_authenticated:
        return {}

    es_cotizaciones = user.groups.filter(name='Cotizaciones').exists()
    es_monitoreo = user.groups.filter(name='Monitoreo').exists()
    es_administrador_monitoreo = user.groups.filter(
        name='Administrador Monitoreo'
    ).exists()
    es_auditor = user.groups.filter(name__in=['Auditor', 'Visor']).exists()
    cotizaciones_nuevas = 0
    if user.is_superuser or es_cotizaciones:
        from app_instalaciones.models import CotizacionServicioTecnico

        cotizaciones_nuevas = CotizacionServicioTecnico.objects.filter(
            estado='REGISTRADA'
        ).count()

    return {
        'es_superusuario': user.is_superuser,

        'es_administrador': user.groups.filter(
            name='Administrador'
        ).exists(),

        'es_coordinador': user.groups.filter(
            name='Coordinador'
        ).exists(),

        'es_programador': user.groups.filter(
            name='Programador'
        ).exists(),

        'es_almacen': user.groups.filter(
            name='Almacen'
        ).exists(),

        'es_facturacion': user.groups.filter(
            name='Facturacion'
        ).exists(),

        'es_cotizaciones': es_cotizaciones,

        'es_monitoreo': es_monitoreo,

        'es_administrador_monitoreo': es_administrador_monitoreo,

        'cotizaciones_nuevas': cotizaciones_nuevas,

        'es_auditor': es_auditor,
        'es_visor': es_auditor,
    }
