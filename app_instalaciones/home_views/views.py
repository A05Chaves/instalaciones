from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from app_instalaciones.models.forms import CuadroInstaForm, ExcelUploadForm
from app_instalaciones.models.cuadroInstalaciones import CuadroInsta, RegistroImportacion
from django.shortcuts import get_object_or_404
import openpyxl
import csv
from django.http import HttpResponse
import pandas as pd

# PAGINA INICIAL DEL PROYECTO
# VERSION 4 PARA EDICION SESUR 28 DE ABRIL 2025


def home(request):
    if not request.user.is_authenticated:
        return redirect('login')  # 🔒 redirige al login si no está autenticado
    # ✅ muestra home si ya está autenticado
    return render(request, "home.html")


@login_required
def registro_inst(request):
    if request.user.groups.filter(name='Visor').exists():
        messages.warning(
            request, "⚠️ No tienes permisos para registrar instalaciones.")
        return redirect('home')

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
    # pylint: disable=no-member
    instalaciones = CuadroInsta.objects.all().order_by(
        '-id')  # pylint: disable=no-member
    return render(request, 'lista_instalaciones.html', {'instalaciones': instalaciones})

# AGREGADO 25 DE ABRIL


def is_editor_or_admin(user):
    """ Verifica si el usuario es administrador o pertenece al grupo de editores """
    return user.is_staff or user.groups.filter(name='editor').exists()


@login_required
@user_passes_test(lambda u: u.is_staff)  # Solo superusuarios
def editar_instalacion(request, id):
    instalacion = get_object_or_404(CuadroInsta, pk=id)

    # Bloquea si está anulada
    if instalacion.estado and instalacion.estado.strip().upper() == "ANULADO" and not request.user.is_superuser:
        messages.warning(  # pylint: disable=no-member
            request, "No puedes editar una instalación que ha sido anulada.")
        return redirect('lista_instalaciones')

    if request.method == 'POST':
        form = CuadroInstaForm(request.POST, instance=instalacion)

        if form.is_valid():
            nuevo_pvg = form.cleaned_data['pvg']

            # Verificar si ya existe otra instalación con ese PVG
            if CuadroInsta.objects.filter(pvg=nuevo_pvg).exclude(id=instalacion.id).exists():  # pylint: disable=no-member
                messages.error(
                    request, f"Ya existe una instalación con el PVG {nuevo_pvg}.")
            else:
                try:
                    form.save()
                    messages.success(
                        request, "Instalación actualizada correctamente.")
                    return redirect('lista_instalaciones')
                except Exception as e:
                    messages.error(request, f"Error al guardar: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Error en {field}: {error}")
    else:
        form = CuadroInstaForm(instance=instalacion)

    return render(request, 'editar_instalacion.html', {
        'form': form,
        'instalacion': instalacion
    })


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
            # pylint: disable=no-member
            if RegistroImportacion.objects.filter(nombre_archivo=nombre).exists():
                messages.warning(
                    request, f"⚠️ El archivo '{nombre}' ya fue cargado anteriormente.")
                return redirect('lista_instalaciones')

            wb = openpyxl.load_workbook(archivo)
            hoja = wb.active

            errores = []

            # Diccionarios de nombres a IDs
            tecnico_map = {
                "Ricardo": 1,
                "Giovanny": 2,
                "Juan": 3,
                "Francisco": 4,
                "German": 5,
                "Willinthon": 6,
                "Jhon": 7,
                "Guido": 8,
                "Esneyder": 9,
                "Diego": 10,
                "-----": 11
            }
            ejecutivo_map = {
                "Francisco Silva": 1,
                "Andrea Trujillo": 2,
                "Yamile David": 3,
                "-----": 4
            }

            for idx, fila in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
                if not any(fila):
                    continue

                try:
                    # Verificar si el PVG ya existe
                    if fila[0] and CuadroInsta.objects.filter(pvg=fila[0]).exists():
                        mensaje = f"Registro duplicado con PVG {fila[0]}"
                        errores.append((idx, fila, mensaje))
                        messages.warning(request, f"⚠️ Fila {idx}: {mensaje}")
                        continue

                    # Procesar técnicos
                    tecnico1 = None
                    tecnico2 = None
                    if fila[14]:
                        tecnicos = [t.strip() for t in str(
                            fila[14]).split(',') if t.strip()]
                        if len(tecnicos) > 0:
                            tecnico1 = tecnico_map.get(tecnicos[0], int(
                                tecnicos[0]) if tecnicos[0].isdigit() else None)
                        if len(tecnicos) > 1:
                            tecnico2 = tecnico_map.get(tecnicos[1], int(
                                tecnicos[1]) if tecnicos[1].isdigit() else None)

                    # Procesar ejecutivo
                    ejecutivo_val = fila[17]
                    if isinstance(ejecutivo_val, str):
                        ejecutivo = ejecutivo_map.get(
                            ejecutivo_val.strip(), None)
                    else:
                        ejecutivo = ejecutivo_val if ejecutivo_val else None

                    datos = {
                        "pvg": fila[0] if fila[0] not in [None, ""] else None,
                        "fecha": fila[1] if fila[1] not in [None, ""] else None,
                        "codigo": fila[2] if fila[2] not in [None, ""] else None,
                        "cliente": fila[3] if fila[3] not in [None, ""] else None,
                        "ciudad": fila[4] if fila[4] not in [None, ""] else None,
                        "direccion": fila[5] if fila[5] not in [None, ""] else None,
                        "instalacion": fila[6] if fila[6] not in [None, ""] else None,
                        "dias_cotizados": fila[7] if fila[7] not in [None, ""] else None,
                        "cantidad_tecnicos": fila[8] if fila[8] not in [None, ""] else None,
                        "en_bodega": fila[9] if fila[9] not in [None, ""] else None,
                        "fecha_inicio": fila[10] if fila[10] not in [None, ""] else None,
                        "fecha_terminacion": fila[11] if fila[11] not in [None, ""] else None,
                        "finaliza": fila[12] if fila[12] not in [None, ""] else None,
                        "orden": fila[13] if fila[13] not in [None, ""] else None,
                        "estado": fila[15] if fila[15] not in [None, ""] else None,
                        "observacion": fila[16] if fila[16] not in [None, ""] else None,
                        "ejecutivo": ejecutivo,
                        "finalizacion": fila[18] if fila[18] not in [None, ""] else None,
                        "tecnico1": tecnico1,
                        "tecnico2": tecnico2,
                        "usuario": request.user
                    }

                    CuadroInsta.objects.create(**datos)

                except Exception as e:
                    mensaje = str(e)
                    errores.append((idx, fila, mensaje))
                    messages.error(
                        request, f"❌ Error en fila {idx}: {mensaje}")

            RegistroImportacion.objects.create(
                nombre_archivo=nombre,
                usuario=request.user
            )

            if errores:
                response = HttpResponse(content_type='text/csv')
                response[
                    'Content-Disposition'] = f'attachment; filename=errores_importacion_{nombre}.csv'

                writer = csv.writer(response)
                writer.writerow(['Fila', 'Contenido', 'Error'])
                for fila_error in errores:
                    fila_num, contenido, mensaje_error = fila_error
                    writer.writerow([fila_num, contenido, mensaje_error])

                return response

            messages.success(
                request, f"El archivo '{nombre}' fue importado exitosamente.")
            return redirect('lista_instalaciones')
    else:
        form = ExcelUploadForm()

    return render(request, 'importar_excel.html', {'form': form})


def exportar_excel(request):
    instalaciones = CuadroInsta.objects.all().values(  # pylint: disable=no-member
        'pvg', 'fecha', 'codigo', 'cliente', 'ciudad', 'direccion',
        'instalacion', 'dias_cotizados', 'cantidad_tecnicos', 'en_bodega',
        'fecha_inicio', 'fecha_terminacion', 'finaliza', 'orden',
        'tecnico1', 'tecnico2', 'estado', 'observacion', 'ejecutivo'
    )

    df = pd.DataFrame(list(instalaciones))

   # Convertir columnas datetime a solo fecha (sin hora ni zona horaria)
    for col in ['fecha', 'fecha_inicio', 'fecha_terminacion', 'finaliza']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="instalaciones.xlsx"'
    df.to_excel(response, index=False)
    return response
