from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from app_instalaciones.models.forms import CuadroInstaForm, ExcelUploadForm
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta, RegistroImportacion
from django.shortcuts import get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
import openpyxl

# PAGINA INICIAL DEL PROYECTO
# VERSION 4 PARA EDICION SESUR 28 DE ABRIL 2025


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


# se utiliza para importar los archivos excel en la vista de carga de excel 2 de mayo 2025

@user_passes_test(lambda u: u.is_superuser)
def importar_excel(request):
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            archivo = request.FILES['archivo_excel']
            nombre = archivo.name

            # Verificar si el archivo ya fue importado
            if RegistroImportacion.objects.filter(nombre_archivo=nombre).exists():
                messages.warning(
                    request, f"⚠️ El archivo '{nombre}' ya fue cargado anteriormente.")
                return redirect('lista_instalaciones')

            wb = openpyxl.load_workbook(archivo)
            hoja = wb.active

            for fila in hoja.iter_rows(min_row=11, values_only=True):
                if fila[0] is None:
                    continue

                CuadroInsta.objects.create(
                    fecha_pvg=fila[0],
                    pvg=fila[1],
                    codigo=fila[2],
                    cliente=fila[3],
                    ciudad=fila[4],
                    instalacion=fila[5],
                    dias_cotizados=fila[6],
                    cantidad_tecnicos=fila[7],
                    en_bodega=fila[8],
                    fecha_inicio=fila[9],
                    fecha_terminacion=fila[10],
                    finaliza=fila[11],
                    orden=fila[12],
                    tecnico=fila[13],
                    estado=fila[14],
                    observacion=fila[15],
                    pendientes=fila[16],
                    qtecnicos=fila[17],
                    indicador=fila[18]
                )

            # Registrar la importación
            RegistroImportacion.objects.create(
                nombre_archivo=nombre,
                usuario=request.user
            )

            messages.success(
                request, f"✅ El archivo '{nombre}' fue importado exitosamente.")
            return redirect('lista_instalaciones')
    else:
        form = ExcelUploadForm()

    return render(request, 'importar_excel.html', {'form': form})
