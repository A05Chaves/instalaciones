
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from app_instalaciones.home_views import views,user_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('instalaciones', views.instalaciones_in, name ='instalaciones'),
    path('registro_inst', views.registro_inst, name ='registro_inst'),
    path('login', user_views.login, name='login'),
    path('registrate', user_views.registrate, name ='registrate'),
    path('logout', user_views.logout, name='logout'),
    path('checkservir', views.chequeo, name='chequeo'),
]
