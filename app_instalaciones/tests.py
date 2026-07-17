from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_instalaciones.models import CuadroInsta


class EstadoFacturacionTests(TestCase):
    def crear_instalacion_alistada(self):
        return CuadroInsta.objects.create(
            pvg=1001,
            ciudad="Bogotá",
            estado="LEGALIZADO",
            orden="ORD-1",
            alistado=True,
            fecha_alistado=timezone.now().date() - timedelta(days=3),
        )

    def test_retenido_cierra_el_mismo_indicador(self):
        instalacion = self.crear_instalacion_alistada()
        instalacion.estado_facturacion = "RETENIDO"
        instalacion.save()

        self.assertFalse(instalacion.facturado)
        self.assertEqual(instalacion.fecha_facturacion, timezone.now().date())
        self.assertEqual(instalacion.dias_para_facturar, 3)
        self.assertTrue(instalacion.cerrado_total)

    def test_vista_permite_marcar_como_facturado(self):
        grupo = Group.objects.create(name="Facturacion")
        usuario = User.objects.create_user("facturacion", password="prueba123")
        usuario.groups.add(grupo)
        instalacion = self.crear_instalacion_alistada()
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("facturar_instalacion", args=[instalacion.id]),
            {"estado_facturacion": "FACTURADO"},
        )

        self.assertEqual(response.status_code, 200)
        instalacion.refresh_from_db()
        self.assertEqual(instalacion.estado_facturacion, "FACTURADO")
        self.assertTrue(instalacion.facturado)
        self.assertEqual(instalacion.dias_para_facturar, 3)
