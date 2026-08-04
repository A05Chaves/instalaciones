from .auditoria_contexto import establecer_solicitud, restablecer_solicitud


class AuditoriaRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = establecer_solicitud(request)
        try:
            return self.get_response(request)
        finally:
            restablecer_solicitud(token)
