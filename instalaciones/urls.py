
from django.contrib import admin
from django.urls import path
from app_instalaciones.home_views import views, user_views
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('registro_inst/', views.registro_inst, name='registro_inst'),
    path('login/', user_views.login, name='login'),
    path('registrate/', user_views.registrate, name='registrate'),
    path('lista_instalaciones/', views.lista_instalaciones,
         name='lista_instalaciones'),

    path('instalacion/editar/<int:id>/',
         views.editar_instalacion, name='editar_instalacion'),
    path('instalacion/eliminar/<int:id>/',
         views.eliminar_instalacion, name='eliminar_instalacion'),

    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='users/password_reset.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='users/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='users/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='users/password_reset_complete.html'), name='password_reset_complete'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('api/sesion/renovar/', user_views.renovar_sesion,
         name='renovar_sesion'),
    path('importar-excel/', views.importar_excel, name='importar_excel'),
    path('exportar_excel/', views.exportar_excel, name='exportar_excel'),

    path('mantenimientos/', user_views.listar_mantenimientos,
         name='listar_mantenimientos'),
    path('tecnico/servicios/', user_views.portal_tecnico, name='portal_tecnico'),
    path('api/tecnico/servicios/', user_views.api_servicios_tecnico, name='api_servicios_tecnico'),
    path('api/tecnico/notificaciones/leidas/', user_views.leer_notificaciones_tecnico, name='leer_notificaciones_tecnico'),
    path('manifest.webmanifest', user_views.manifiesto_tecnico, name='manifiesto_tecnico'),
    path('service-worker.js', user_views.service_worker_tecnico, name='service_worker_tecnico'),
    path('api/instalacion-por-codigo/', user_views.buscar_instalacion_por_codigo,
         name='buscar_instalacion_por_codigo'),

    # NUEVAS rutas para la columna Acción
    path('mantenimientos/<int:pk>/actualizar/',
         user_views.mantenimiento_actualizar,
         name='mantenimiento_actualizar'),
    path('mantenimientos/<int:pk>/eliminar/',
         user_views.mantenimiento_eliminar,
         name='mantenimiento_eliminar'),
    path('mantenimientos/<int:pk>/subir-archivo/',
         user_views.mantenimiento_subir_archivo,
         name='mantenimiento_subir_archivo'),
    path(
        'instalacion/<int:id>/facturar/',
        user_views.facturar_instalacion,
        name='facturar_instalacion'
    ),
    path('dashboard/', user_views.dashboard_instalaciones,
         name='dashboard_instalaciones'),
    path(
        'instalacion/<int:id>/alistar/',
        user_views.alistar_instalacion,
        name='alistar_instalacion'
    ),
    path(
        'configuracion/usuarios/',
        user_views.configuracion_usuarios,
        name='configuracion_usuarios'
    ),
    path(
        'mantenimientos/exportar/',
        user_views.exportar_mantenimientos,
        name='exportar_mantenimientos'
    ),

    # path(
    #   'mantenimientos/importar/',
    #   user_views.importar_mantenimientos,
    #   name='importar_mantenimientos'
    # ),

    path(
        'mantenimientos/importar-pdf/',
        user_views.importar_mantenimientos_pdf,
        name='importar_mantenimientos_pdf'
    ),

    path(
        'mantenimientos/importar-pdf/confirmar/',
        user_views.confirmar_importar_mantenimientos_pdf,
        name='confirmar_importar_mantenimientos_pdf'
    ),
]
