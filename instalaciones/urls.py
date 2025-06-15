
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
    path('logout/', user_views.logout, name='logout'),
    path('lista_instalaciones/', views.lista_instalaciones,
         name='lista_instalaciones'),
    path('instalacion/editar/<int:id>/',
         views.editar_instalacion, name='editar_instalacion'),
    path('instalacion/eliminar/<int:id>/',
         views.eliminar_instalacion, name='eliminar_instalacion'),
    # path('importar/', views.importar_instalaciones,name = 'importar_instalaciones'),
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
]
