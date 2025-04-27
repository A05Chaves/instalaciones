
from django.contrib import admin
from django.urls import path
from app_instalaciones.home_views import views, user_views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('registro_inst/', views.registro_inst, name='registro_inst'),
    path('login/', user_views.login, name='login'),
    path('registrate/', user_views.registrate, name='registrate'),
    path('logout/', user_views.logout, name='logout'),
    path('lista_instalaciones/', views.lista_instalaciones, name='lista_instalaciones'),
    path('instalacion/editar/<int:id>/', views.editar_instalacion, name='editar_instalacion'),
    path('instalacion/eliminar/<int:id>/', views.eliminar_instalacion, name='eliminar_instalacion'),

    
]
