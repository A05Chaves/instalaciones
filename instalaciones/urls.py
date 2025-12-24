
from django.contrib import admin  # type: ignore
from django.urls import path  # type: ignore
from app_instalaciones.home_views import views, user_views
from django.contrib.auth import views as auth_views  # type: ignore
from django.contrib.auth.views import LogoutView  # type: ignore


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('registro_inst/', views.registro_inst, name='registro_inst'),
    path('login/', user_views.login, name='login'),
    path('registrate/', user_views.registrate, name='registrate'),
    path('logout/', user_views.logout, name='logout'),
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
    path('importar-excel/', views.importar_excel, name='importar_excel'),
    path('exportar_excel/', views.exportar_excel, name='exportar_excel'),

    path('mantenimientos/', user_views.listar_mantenimientos,
         name='listar_mantenimientos'),
    path('api/instalacion-por-codigo/', user_views.buscar_instalacion_por_codigo,
         name='buscar_instalacion_por_codigo'),

    path('mantenimientos/', user_views.listar_mantenimientos, name='mantenimientos'),

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

    path('api/instalacion-por-codigo/', user_views.buscar_instalacion_por_codigo,
         name='buscar_instalacion_por_codigo'),
]
