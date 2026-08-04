from contextvars import ContextVar


_solicitud_actual = ContextVar("solicitud_auditoria", default=None)


def establecer_solicitud(request):
    return _solicitud_actual.set(request)


def restablecer_solicitud(token):
    _solicitud_actual.reset(token)


def obtener_solicitud():
    return _solicitud_actual.get()
