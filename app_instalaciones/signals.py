from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.db import OperationalError, ProgrammingError
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from .auditoria_contexto import obtener_solicitud
from .models.auditoria import RegistroAuditoria


_CAMPOS_SENSIBLES = {"password"}


def _aplica(sender):
    return sender is not RegistroAuditoria and (
        sender._meta.app_label == "app_instalaciones" or sender in {User, Group}
    )


def _serializar(valor):
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if hasattr(valor, "name") and hasattr(valor, "storage"):
        return valor.name
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    if isinstance(valor, (list, dict)):
        return valor
    return str(valor)


def _datos(instance):
    resultado = {}
    for campo in instance._meta.concrete_fields:
        if campo.name in _CAMPOS_SENSIBLES:
            continue
        try:
            resultado[campo.name] = _serializar(campo.value_from_object(instance))
        except (ValueError, TypeError):
            resultado[campo.name] = "NO DISPONIBLE"
    return resultado


def _actor_y_peticion():
    request = obtener_solicitud()
    if not request:
        return None, "", "", None
    usuario = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    return usuario, request.path[:300], request.method[:10], ip


def _registrar(instance, accion, cambios):
    usuario, ruta, metodo, ip = _actor_y_peticion()
    try:
        RegistroAuditoria.objects.create(
            usuario=usuario, accion=accion,
            modulo=str(instance._meta.app_config.verbose_name or instance._meta.app_label)[:100],
            modelo=str(instance._meta.verbose_name).title()[:100],
            objeto_id=str(instance.pk or "")[:100], objeto=str(instance)[:300],
            cambios=cambios, ruta=ruta, metodo=metodo, ip=ip,
        )
    except (OperationalError, ProgrammingError):
        # Permite ejecutar migraciones antes de que exista la tabla de auditoría.
        pass


@receiver(pre_save)
def auditoria_pre_save(sender, instance, **kwargs):
    if not _aplica(sender) or not instance.pk:
        return
    anterior = sender._default_manager.filter(pk=instance.pk).first()
    if anterior:
        instance._auditoria_anterior = _datos(anterior)


@receiver(post_save)
def auditoria_post_save(sender, instance, created, **kwargs):
    if not _aplica(sender):
        return
    nuevos = _datos(instance)
    if created:
        cambios = {campo: {"anterior": None, "nuevo": valor} for campo, valor in nuevos.items() if campo != "id"}
        _registrar(instance, "CREAR", cambios)
        return
    anteriores = getattr(instance, "_auditoria_anterior", {})
    cambios = {
        campo: {"anterior": anteriores.get(campo), "nuevo": valor}
        for campo, valor in nuevos.items()
        if campo in anteriores and anteriores.get(campo) != valor
    }
    if cambios:
        _registrar(instance, "EDITAR", cambios)


@receiver(post_delete)
def auditoria_post_delete(sender, instance, **kwargs):
    if _aplica(sender):
        _registrar(instance, "ELIMINAR", {
            campo: {"anterior": valor, "nuevo": None}
            for campo, valor in _datos(instance).items() if campo != "id"
        })


@receiver(m2m_changed, sender=User.groups.through)
def auditoria_roles_usuario(sender, instance, action, pk_set, **kwargs):
    if action in {"pre_add", "pre_remove", "pre_clear"}:
        instance._auditoria_grupos_anteriores = list(instance.groups.values_list("name", flat=True))
        return
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    anteriores = getattr(instance, "_auditoria_grupos_anteriores", [])
    nuevos = list(instance.groups.values_list("name", flat=True))
    _registrar(instance, "EDITAR", {
        "roles": {"anterior": anteriores, "nuevo": nuevos}
    })
