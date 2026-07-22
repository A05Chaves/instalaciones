def permisos_usuario(request):

    user = request.user

    if not user.is_authenticated:
        return {}

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

        'es_visor': user.groups.filter(
            name='Visor'
        ).exists(),
    }
