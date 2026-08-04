from collections import OrderedDict
from decimal import Decimal, InvalidOperation
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from app_instalaciones.models.smartcheck import (
    CotizacionProyectoComercial,
    ItemChecklistSmartCheck,
    ItemCotizacionProyectoComercial,
    ItemKitProyectoComercial,
    KitProyectoComercial,
    ProductoProyectoComercial,
    ProyectoSmartCheck,
)
from app_instalaciones.models.smartcheck_forms import ProductoProyectoComercialForm, ProyectoSmartCheckForm


CHECKLISTS = {
    "CCTV": [
        "Definir tecnología IP, análoga o híbrida",
        "Confirmar ubicación y cobertura de cada cámara",
        "Validar condiciones de iluminación",
        "Definir días de almacenamiento requeridos",
        "Validar cuarto técnico, grabador y respaldo eléctrico",
        "Definir red, switches, cableado y canalización",
        "Confirmar acceso remoto y usuarios",
    ],
    # El levantamiento de alarma se registra como ficha técnica detallada.
    # Los estados Cumple/No cumple se reservarán para instalación y entrega.
    "ALARMA": [],
    "ACCESO": [
        "Identificar puertas y sentido de apertura",
        "Definir método de identificación",
        "Validar cerradura o electroimán",
        "Definir sensor, botón de salida y cierrapuertas",
        "Validar controladora y capacidad de usuarios",
        "Definir horarios y niveles de acceso",
        "Calcular energía, respaldo y cableado",
    ],
    "INTELIGENTE": [
        "Definir procesos que se van a automatizar",
        "Identificar iluminación y cargas controlables",
        "Validar medición y control de energía",
        "Definir citofonía e intercomunicación",
        "Validar integración con ascensores",
        "Definir protocolos e integraciones",
        "Confirmar plataforma central de administración",
    ],
}


def puede_gestionar_smartcheck(user):
    return (
        user.is_superuser
        or user.groups.filter(name__in=["Administrador", "Coordinador"]).exists()
    )


def sincronizar_checklist(proyecto):
    proyecto.items_checklist.exclude(sistema__in=proyecto.sistemas).delete()
    for sistema in proyecto.sistemas:
        items_sistema = CHECKLISTS.get(sistema, [])
        proyecto.items_checklist.filter(sistema=sistema).exclude(
            item__in=items_sistema
        ).delete()
        for item in items_sistema:
            ItemChecklistSmartCheck.objects.get_or_create(
                proyecto=proyecto,
                sistema=sistema,
                item=item,
            )


@login_required(login_url="login")
@user_passes_test(puede_gestionar_smartcheck, login_url="home")
def listar_proyectos(request):
    busqueda = (request.GET.get("busqueda") or "").strip()
    estado = (request.GET.get("estado") or "").strip()
    sistema = (request.GET.get("sistema") or "").strip()
    proyectos = ProyectoSmartCheck.objects.select_related(
        "ejecutivo", "tecnico"
    )
    if busqueda:
        proyectos = proyectos.filter(
            Q(numero__icontains=busqueda)
            | Q(nombre__icontains=busqueda)
            | Q(cliente__icontains=busqueda)
            | Q(ciudad__icontains=busqueda)
            | Q(direccion__icontains=busqueda)
        )
    if estado:
        proyectos = proyectos.filter(estado=estado)
    if sistema:
        proyectos = proyectos.filter(sistemas__icontains=sistema)
    return render(request, "smartcheck/listar.html", {
        "proyectos": proyectos,
        "busqueda": busqueda,
        "estado_filtro": estado,
        "sistema_filtro": sistema,
        "estados": ProyectoSmartCheck.ESTADOS,
        "sistemas": ProyectoSmartCheck.SISTEMAS,
    })


@login_required(login_url="login")
@user_passes_test(puede_gestionar_smartcheck, login_url="home")
@transaction.atomic
def crear_proyecto(request):
    form = ProyectoSmartCheckForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        proyecto = form.save(commit=False)
        proyecto.creado_por = request.user
        proyecto.save()
        sincronizar_checklist(proyecto)
        messages.success(request, "Proyecto comercial creado correctamente.")
        return redirect("smartcheck_listar")
    return render(request, "smartcheck/formulario.html", {
        "form": form,
        "titulo": "Nuevo proyecto comercial",
        "proyecto": None,
        "sensores_catalogo": list(ProductoProyectoComercial.objects.filter(categoria="SENSOR", activo=True).values("id", "nombre", "referencia")),
        "cables_catalogo": list(ProductoProyectoComercial.objects.filter(categoria="CABLE", activo=True).values("id", "nombre", "referencia", "precio", "unidad")),
        "equipos_catalogo": list(ProductoProyectoComercial.objects.filter(categoria__in=["MODULO", "EQUIPO", "ACCESORIO"], activo=True).values("id", "categoria", "nombre", "referencia", "precio", "unidad")),
    })


@login_required(login_url="login")
@user_passes_test(puede_gestionar_smartcheck, login_url="home")
@transaction.atomic
def editar_proyecto(request, pk):
    proyecto = get_object_or_404(ProyectoSmartCheck, pk=pk)
    form = ProyectoSmartCheckForm(request.POST or None, instance=proyecto)
    if request.method == "POST" and form.is_valid():
        proyecto = form.save()
        sincronizar_checklist(proyecto)
        messages.success(request, "Proyecto actualizado correctamente.")
        return redirect("smartcheck_listar")
    return render(request, "smartcheck/formulario.html", {
        "form": form,
        "titulo": f"Editar {proyecto.numero}",
        "proyecto": proyecto,
        "sensores_catalogo": list(ProductoProyectoComercial.objects.filter(categoria="SENSOR", activo=True).values("id", "nombre", "referencia")),
        "cables_catalogo": list(ProductoProyectoComercial.objects.filter(categoria="CABLE", activo=True).values("id", "nombre", "referencia", "precio", "unidad")),
        "equipos_catalogo": list(ProductoProyectoComercial.objects.filter(categoria__in=["MODULO", "EQUIPO", "ACCESORIO"], activo=True).values("id", "categoria", "nombre", "referencia", "precio", "unidad")),
    })


@login_required(login_url="login")
@user_passes_test(puede_gestionar_smartcheck, login_url="home")
def detalle_proyecto(request, pk):
    proyecto = get_object_or_404(
        ProyectoSmartCheck.objects.select_related("ejecutivo", "tecnico"),
        pk=pk,
    )
    grupos = OrderedDict()
    for item in proyecto.items_checklist.all():
        grupos.setdefault(item.get_sistema_display(), []).append(item)
    datos = proyecto.datos_tecnicos or {}
    etiquetas_dispositivo = {
        "MOVIMIENTO": "Sensor de movimiento",
        "MAGNETICO": "Contacto magnético",
        "PANICO": "Botón de pánico",
        "VIDRIO": "Detector de ruptura de vidrio",
        "HUMO": "Detector de humo",
        "INUNDACION": "Detector de inundación",
        "OTRO_ZONA": "Otro dispositivo de zona",
    }
    ids_catalogo = []
    for dispositivo in datos.get("dispositivos_alarma", []):
        tipo = str(dispositivo.get("tipo") or "")
        if tipo.startswith("CAT-") and tipo[4:].isdigit():
            ids_catalogo.append(int(tipo[4:]))
    for producto in ProductoProyectoComercial.objects.filter(pk__in=ids_catalogo):
        etiquetas_dispositivo[f"CAT-{producto.pk}"] = str(producto)
    areas_alarma = []
    for area in datos.get("areas_alarma", []):
        area = dict(area)
        try:
            area["area_m2"] = round(
                float(area.get("largo") or 0) * float(area.get("ancho") or 0),
                2,
            )
        except (TypeError, ValueError):
            area["area_m2"] = 0
        areas_alarma.append(area)
    dispositivos_alarma = []
    for dispositivo in datos.get("dispositivos_alarma", []):
        dispositivo = dict(dispositivo)
        dispositivo["tipo_display"] = etiquetas_dispositivo.get(
            dispositivo.get("tipo"), dispositivo.get("tipo") or "Dispositivo"
        )
        dispositivos_alarma.append(dispositivo)
    modulos_alarma = []
    for modulo in datos.get("modulos_alarma", []):
        modulo = dict(modulo)
        try:
            modulo["subtotal"] = float(Decimal(str(modulo.get("precio") or 0)) * Decimal(str(modulo.get("cantidad") or 0)))
        except (InvalidOperation, TypeError, ValueError):
            modulo["subtotal"] = 0
        modulos_alarma.append(modulo)
    return render(request, "smartcheck/detalle.html", {
        "proyecto": proyecto,
        "grupos_checklist": grupos.items(),
        "estados_item": ItemChecklistSmartCheck.ESTADOS,
        "datos_tecnicos": datos,
        "areas_alarma": areas_alarma,
        "dispositivos_alarma": dispositivos_alarma,
        "modulos_alarma": modulos_alarma,
        "cotizacion": CotizacionProyectoComercial.objects.filter(proyecto=proyecto).prefetch_related("items").first(),
    })


@login_required(login_url="login")
@user_passes_test(puede_gestionar_smartcheck, login_url="home")
@transaction.atomic
def propuesta_final(request, pk):
    proyecto = get_object_or_404(ProyectoSmartCheck, pk=pk)
    cotizacion, _ = CotizacionProyectoComercial.objects.get_or_create(
        proyecto=proyecto,
        defaults={"nombre_propuesta": proyecto.nombre},
    )
    if request.method == "POST":
        cotizacion.nombre_propuesta = (request.POST.get("nombre_propuesta") or proyecto.nombre).strip()[:160]
        cotizacion.kit = KitProyectoComercial.objects.filter(pk=request.POST.get("kit_id") or None, activo=True).first()
        for campo in ["mano_obra", "descuento", "porcentaje_iva"]:
            try:
                valor = Decimal(request.POST.get(campo) or 0)
            except InvalidOperation:
                valor = Decimal("0")
            setattr(cotizacion, campo, max(valor, Decimal("0")))
        cotizacion.observaciones = (request.POST.get("observaciones") or "").strip()
        cotizacion.actualizado_por = request.user
        cotizacion.save()
        try:
            items_recibidos = json.loads(request.POST.get("items_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            items_recibidos = []
        ids = {
            int(item.get("producto_id")) for item in items_recibidos
            if isinstance(item, dict) and str(item.get("producto_id") or "").isdigit()
        }
        productos = {p.pk: p for p in ProductoProyectoComercial.objects.filter(pk__in=ids, activo=True)}
        cotizacion.items.all().delete()
        nuevos = []
        for orden, item in enumerate(items_recibidos[:200], start=1):
            if not isinstance(item, dict) or not str(item.get("producto_id") or "").isdigit():
                continue
            producto = productos.get(int(item["producto_id"]))
            if not producto:
                continue
            try:
                cantidad = max(Decimal(str(item.get("cantidad") or 0)), Decimal("0"))
                precio = max(Decimal(str(item.get("valor_unitario") or producto.precio)), Decimal("0"))
            except InvalidOperation:
                continue
            nuevos.append(ItemCotizacionProyectoComercial(
                cotizacion=cotizacion, producto=producto,
                referencia=producto.referencia, descripcion=producto.nombre,
                cantidad=cantidad, valor_unitario=precio,
                incluido_kit=bool(item.get("incluido_kit")), orden=orden,
            ))
        for item_cotizacion in nuevos:
            item_cotizacion.save()
        proyecto.estado = "PROPUESTA_DISENO"
        proyecto.save(update_fields=["estado", "actualizado"])
        messages.success(request, "Propuesta final guardada correctamente.")
        return redirect("smartcheck_propuesta", pk=proyecto.pk)

    productos = list(ProductoProyectoComercial.objects.filter(activo=True).values(
        "id", "categoria", "nombre", "referencia", "marca", "precio", "unidad"
    ))
    kits = KitProyectoComercial.objects.filter(activo=True).prefetch_related("items__producto")
    kits_json = [{
        "id": kit.pk, "nombre": kit.nombre,
        "items": [{
            "producto_id": item.producto_id, "nombre": item.producto.nombre,
            "referencia": item.producto.referencia, "cantidad": item.cantidad,
            "precio": float(item.producto.precio),
        } for item in kit.items.all()],
    } for kit in kits]
    items_iniciales = [{
        "producto_id": item.producto_id, "descripcion": item.descripcion,
        "referencia": item.referencia, "cantidad": float(item.cantidad),
        "valor_unitario": float(item.valor_unitario), "incluido_kit": item.incluido_kit,
    } for item in cotizacion.items.all()]
    return render(request, "smartcheck/propuesta.html", {
        "proyecto": proyecto, "cotizacion": cotizacion,
        "productos_catalogo": productos, "kits": kits,
        "kits_json": kits_json, "items_iniciales": items_iniciales,
    })


@login_required(login_url="login")
@user_passes_test(puede_gestionar_smartcheck, login_url="home")
@require_POST
@transaction.atomic
def guardar_checklist(request, pk):
    proyecto = get_object_or_404(ProyectoSmartCheck, pk=pk)
    for item in proyecto.items_checklist.all():
        prefijo = f"item_{item.pk}_"
        estado = request.POST.get(f"{prefijo}estado", item.estado)
        if estado not in dict(ItemChecklistSmartCheck.ESTADOS):
            continue
        item.estado = estado
        cantidad = (request.POST.get(f"{prefijo}cantidad") or "").strip()
        try:
            item.cantidad = Decimal(cantidad) if cantidad else None
        except InvalidOperation:
            item.cantidad = None
        item.ubicacion = (
            request.POST.get(f"{prefijo}ubicacion") or ""
        ).strip()[:180]
        item.observacion = (
            request.POST.get(f"{prefijo}observacion") or ""
        ).strip()
        item.actualizado_por = request.user
        item.save()
    messages.success(request, "Lista de chequeo guardada.")
    return redirect("smartcheck_detalle", pk=proyecto.pk)


@login_required(login_url="login")
@user_passes_test(lambda u: u.is_superuser, login_url="home")
@transaction.atomic
def configuracion_catalogo(request):
    producto_editar_id = (request.GET.get("editar") or "").strip()
    producto_editar = (
        ProductoProyectoComercial.objects.filter(pk=producto_editar_id).first()
        if producto_editar_id.isdigit() else None
    )
    form = ProductoProyectoComercialForm(instance=producto_editar)
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "guardar_producto":
            producto_id = (request.POST.get("producto_id") or "").strip()
            producto = (
                ProductoProyectoComercial.objects.filter(pk=producto_id).first()
                if producto_id.isdigit() else None
            )
            form = ProductoProyectoComercialForm(request.POST, instance=producto)
            if form.is_valid():
                form.save()
                messages.success(request, "Producto guardado en el catálogo comercial.")
                return redirect("configuracion_catalogo_comercial")
        elif accion == "crear_kit":
            nombre = (request.POST.get("nombre_kit") or "").strip()
            if nombre:
                try:
                    descuento = min(max(Decimal(request.POST.get("porcentaje_descuento") or 0), 0), 100)
                except InvalidOperation:
                    descuento = Decimal("0")
                KitProyectoComercial.objects.create(
                    nombre=nombre,
                    descripcion=(request.POST.get("descripcion_kit") or "").strip(),
                    porcentaje_descuento=descuento,
                )
                messages.success(request, "Kit creado correctamente.")
                return redirect("configuracion_catalogo_comercial")
        elif accion == "actualizar_kit":
            kit = get_object_or_404(KitProyectoComercial, pk=request.POST.get("kit_id"))
            try:
                kit.porcentaje_descuento = min(max(Decimal(request.POST.get("porcentaje_descuento") or 0), 0), 100)
            except InvalidOperation:
                kit.porcentaje_descuento = Decimal("0")
            kit.save(update_fields=["porcentaje_descuento"])
            messages.success(request, "Descuento y valor del kit actualizados.")
            return redirect("configuracion_catalogo_comercial")
        elif accion == "quitar_item_kit":
            item = get_object_or_404(
                ItemKitProyectoComercial,
                pk=request.POST.get("item_id"),
                kit_id=request.POST.get("kit_id"),
            )
            item.delete()
            messages.success(request, "Equipo retirado del kit.")
            return redirect("configuracion_catalogo_comercial")
        elif accion == "agregar_item_kit":
            kit = get_object_or_404(KitProyectoComercial, pk=request.POST.get("kit_id"))
            producto = get_object_or_404(ProductoProyectoComercial, pk=request.POST.get("producto_id"))
            cantidad = max(1, int(request.POST.get("cantidad") or 1))
            item, creado = ItemKitProyectoComercial.objects.get_or_create(kit=kit, producto=producto, defaults={"cantidad": cantidad})
            if not creado:
                item.cantidad = cantidad
                item.save(update_fields=["cantidad"])
            messages.success(request, "Equipo agregado al kit.")
            return redirect("configuracion_catalogo_comercial")
        elif accion == "eliminar_producto":
            producto_id = (request.POST.get("producto_id") or "").strip()
            producto = get_object_or_404(
                ProductoProyectoComercial,
                pk=producto_id if producto_id.isdigit() else None,
            )
            nombre = str(producto)
            ItemKitProyectoComercial.objects.filter(producto=producto).delete()
            producto.delete()
            messages.success(request, f"Producto {nombre} eliminado del catálogo.")
            return redirect("configuracion_catalogo_comercial")
        elif accion == "eliminar_kit":
            kit_id = (request.POST.get("kit_id") or "").strip()
            kit = get_object_or_404(
                KitProyectoComercial,
                pk=kit_id if kit_id.isdigit() else None,
            )
            nombre = kit.nombre
            kit.delete()
            messages.success(request, f"Kit {nombre} eliminado correctamente.")
            return redirect("configuracion_catalogo_comercial")
    return render(request, "smartcheck/configuracion_catalogo.html", {
        "form": form,
        "producto_editar": producto_editar,
        "productos": ProductoProyectoComercial.objects.all(),
        "kits": KitProyectoComercial.objects.prefetch_related("items__producto"),
    })
