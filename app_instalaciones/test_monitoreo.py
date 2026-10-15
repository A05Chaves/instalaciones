import json
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_instalaciones.models import Mantenimiento, Tecnico


class FlujoMonitoreoTests(TestCase):
    def setUp(self):
        self.grupo_monitoreo, _ = Group.objects.get_or_create(name="Monitoreo")
        self.grupo_admin_monitoreo, _ = Group.objects.get_or_create(name="Administrador Monitoreo")
        self.usuario_monitoreo = User.objects.create_user("operador_omt", password="Prueba-12345")
        self.usuario_monitoreo.groups.add(self.grupo_monitoreo)
        self.usuario_admin = User.objects.create_user("admin_omt", password="Prueba-12345")
        self.usuario_admin.groups.add(self.grupo_admin_monitoreo)
        self.usuario_tecnico = User.objects.create_user("tecnico_omt", password="Prueba-12345")
        self.tecnico = Tecnico.objects.create(nombre="Técnico OMT", usuario=self.usuario_tecnico)
        self.inicio = timezone.now() - timedelta(minutes=25)
        self.mantenimiento = Mantenimiento.objects.create(
            numero_ticket="REG-OMT-001",
            codigo="100",
            cliente="Cliente OMT",
            direccion="Calle 1",
            tecnico=self.tecnico,
            fecha_programada=timezone.localdate(),
            estado_operativo="EN_PROCESO",
            inicio_tecnico=self.inicio,
            hora_entrada=timezone.localtime(self.inicio).time().replace(microsecond=0),
        )

    def test_tecnico_finaliza_y_queda_pendiente_omt(self):
        self.client.force_login(self.usuario_tecnico)
        respuesta = self.client.post(
            reverse("api_servicios_tecnico"),
            data=json.dumps({
                "id": self.mantenimiento.pk,
                "estado": "FINALIZADO",
                "novedad": "Servicio terminado",
            }),
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.mantenimiento.refresh_from_db()
        self.assertEqual(self.mantenimiento.estado_operativo, "PENDIENTE_OMT")
        self.assertIsNotNone(self.mantenimiento.fin_tecnico)
        self.assertFalse(self.mantenimiento.orden)

    def test_monitoreo_solo_ve_mantenimientos_y_cierra_orden(self):
        self.mantenimiento.estado_operativo = "PENDIENTE_OMT"
        self.mantenimiento.fin_tecnico = timezone.now()
        self.mantenimiento.realizado = timezone.localdate()
        self.mantenimiento.save(permitir_estado_manual=True)
        self.client.force_login(self.usuario_monitoreo)

        inicio = self.client.get(reverse("home"))
        hoja = self.client.get(reverse("listar_mantenimientos"))
        self.assertNotContains(inicio, "Lista de Instalaciones")
        self.assertContains(inicio, "Hoja de Mantenimientos")
        self.assertContains(hoja, "Pendiente OMT")
        self.assertNotContains(hoja, "Nuevo mantenimiento")
        instalaciones = self.client.get(reverse("lista_instalaciones"))
        self.assertRedirects(
            instalaciones,
            f'{reverse("home")}?next={reverse("lista_instalaciones")}',
        )

        respuesta = self.client.post(
            reverse("registrar_orden_omt", args=[self.mantenimiento.pk]),
            {"orden": "OT-9001"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.mantenimiento.refresh_from_db()
        self.assertEqual(self.mantenimiento.orden, "OT-9001")
        self.assertEqual(self.mantenimiento.estado_operativo, "FINALIZADO")
        self.assertEqual(self.mantenimiento.orden_registrada_por, self.usuario_monitoreo)
        self.assertIsNotNone(self.mantenimiento.fecha_orden)
        self.assertTrue(self.mantenimiento.duracion_validacion_omt)

    def test_monitoreo_no_puede_editar_otros_campos(self):
        self.client.force_login(self.usuario_monitoreo)
        respuesta = self.client.post(
            reverse("mantenimiento_actualizar", args=[self.mantenimiento.pk]),
            {"cliente": "Cliente alterado"},
        )
        self.assertEqual(respuesta.status_code, 403)
        self.mantenimiento.refresh_from_db()
        self.assertEqual(self.mantenimiento.cliente, "Cliente OMT")

    def test_administrador_monitoreo_solo_crea_usuarios_monitoreo(self):
        self.client.force_login(self.usuario_admin)
        pagina = self.client.get(reverse("configuracion_usuarios"))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Sólo puedes asignar el perfil Monitoreo")
        self.assertNotContains(pagina, ">Administrador<")

        respuesta = self.client.post(reverse("configuracion_usuarios"), {
            "accion": "crear_usuario",
            "username": "nuevo_monitoreo",
            "password1": "Clave-Segura-2026",
            "password2": "Clave-Segura-2026",
            "grupo_ids": [str(self.grupo_monitoreo.pk)],
        })
        self.assertEqual(respuesta.status_code, 302)
        nuevo = User.objects.get(username="nuevo_monitoreo")
        self.assertTrue(nuevo.groups.filter(name="Monitoreo").exists())
        self.assertFalse(nuevo.is_staff)
        self.assertFalse(nuevo.is_superuser)
