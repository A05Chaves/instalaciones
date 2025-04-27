from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from app_instalaciones.models.forms import CuadroInstaForm
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta
from django.shortcuts import get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required

# PAGINA INICIAL DEL PROYECTO


def home(request):
    contexto = {}
    return render(request, "home.html", contexto)


@login_required
def registro_inst(request):
    if request.method == 'POST':
        form = CuadroInstaForm(request.POST)
        if form.is_valid():
            cuadro_insta = form.save(commit=False)
            cuadro_insta.usuario = request.user
            cuadro_insta.save()
            messages.success(request, 'Instalación registrada con éxito.')
            return redirect('registro_inst')
        else:
            messages.error(
                request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = CuadroInstaForm()
    return render(request, 'registro_inst.html', {'form': form})


def lista_instalaciones(request):
    # Obtener todas las instalaciones ordenadas por fecha
    instalaciones = CuadroInsta.objects.all().order_by(
        '-id')  # pylint: disable=no-member
    return render(request, 'lista_instalaciones.html', {'instalaciones': instalaciones})

# AGREGADO 25 DE ABRIL


@login_required
def editar_instalacion(request, id):
    if not request.user.is_staff:
        messages.error(
            request, "Acceso denegado: solo los administradores pueden editar instalaciones.")
        return redirect('lista_instalaciones')

    instalacion = get_object_or_404(CuadroInsta, id=id)
    if request.method == 'POST':
        form = CuadroInstaForm(request.POST, instance=instalacion)
        if form.is_valid():
            form.save()
            messages.success(request, "Instalación actualizada correctamente.")
            return redirect('lista_instalaciones')
    else:
        form = CuadroInstaForm(instance=instalacion)
    return render(request, 'editar_instalacion.html', {'form': form, 'instalacion': instalacion})


@login_required
def eliminar_instalacion(request, id):
    if not request.user.is_staff:
        messages.error(
            request, "Acceso denegado: solo los administradores pueden eliminar instalaciones.")
        return redirect('lista_instalaciones')

    instalacion = get_object_or_404(CuadroInsta, id=id)
    instalacion.delete()
    messages.success(request, "Instalación eliminada correctamente.")
    return redirect('lista_instalaciones')
