from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_instalaciones.models import (
    Ciudad, CuadroInsta, HistorialAsignacionMantenimiento, Mantenimiento,
    NotificacionTecnico, Tecnico,
)
from app_instalaciones.home_views.user_views import registrar_cambio_tecnico
from app_instalaciones.utils.importar_mantenimientos_pdf import (
    analizar_pdf_mantenimientos,
    extraer_mantenimiento_desde_texto,
    importar_resultados_pdf,
    preparar_resultados_para_session,
    restaurar_resultados_desde_session,
)


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

        self.assertEqual(response.status_code, 200, response.content)
        instalacion.refresh_from_db()
        self.assertEqual(instalacion.estado_facturacion, "FACTURADO")
        self.assertTrue(instalacion.facturado)
        self.assertEqual(instalacion.dias_para_facturar, 3)


class DashboardInstalacionesTests(TestCase):
    def setUp(self):
        grupo = Group.objects.create(name="Administrador")
        self.usuario = User.objects.create_user("administrador", password="prueba123")
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)

    def test_grupo_operativo_puede_ver_dashboard_y_mes_invalido_no_falla(self):
        response = self.client.get(reverse("dashboard_instalaciones"), {"mes": "invalido"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["mes"], "")

    def test_excluye_fechas_negativas_e_incluye_pendientes_vencidos(self):
        hoy = timezone.localdate()
        fecha_ingreso = timezone.make_aware(
            datetime.combine(hoy, time.min)
        )

        CuadroInsta.objects.create(
            pvg=2001,
            ciudad="Pasto",
            estado="LEGALIZADO",
            fecha=fecha_ingreso,
            fecha_inicio=hoy - timedelta(days=1),
        )
        CuadroInsta.objects.create(
            pvg=2002,
            ciudad="Pasto",
            estado="LEGALIZADO",
            fecha=fecha_ingreso - timedelta(days=5),
            fecha_inicio=hoy,
        )
        CuadroInsta.objects.create(
            pvg=2003,
            ciudad="Pasto",
            estado="LEGALIZADO",
            finaliza=hoy - timedelta(days=3),
        )
        CuadroInsta.objects.create(
            pvg=2004,
            ciudad="Pasto",
            estado="LEGALIZADO",
            alistado=True,
            fecha_alistado=hoy - timedelta(days=3),
        )

        response = self.client.get(reverse("dashboard_instalaciones"))

        self.assertEqual(response.context["inconsistencias_instalacion"], 1)
        self.assertEqual(response.context["total_instalacion"], 1)
        self.assertEqual(response.context["promedio_instalacion"], 5)
        self.assertEqual(response.context["vencidos_almacen"], 1)
        self.assertEqual(response.context["vencidos_facturacion"], 1)


class ListaMantenimientosTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("operador", password="prueba123")
        administradores, _ = Group.objects.get_or_create(name="Administrador")
        self.usuario.groups.add(administradores)
        self.client.force_login(self.usuario)
        Mantenimiento.objects.create(
            codigo="COD-001",
            cliente="Cliente Pasto",
            ciudad="Pasto",
            direccion="Calle 1",
        )
        Mantenimiento.objects.create(
            codigo="COD-002",
            cliente="Cliente Cali",
            ciudad="Cali",
            direccion="Calle 2",
        )

    def test_formulario_nuevo_esta_cerrado_por_defecto(self):
        response = self.client.get(reverse("listar_mantenimientos"))

        self.assertContains(response, 'id="panel-nuevo-mantenimiento" class="collapse"')

    def test_filtra_mantenimientos_por_texto(self):
        response = self.client.get(
            reverse("listar_mantenimientos"),
            {"busqueda": "Pasto"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["mantenimientos"]), 1)
        self.assertContains(response, "Cliente Pasto")
        self.assertNotContains(response, "Cliente Cali")

    def test_ordena_por_fecha_del_servicio_del_mas_nuevo_al_mas_antiguo(self):
        zona = timezone.get_current_timezone()
        Mantenimiento.objects.filter(codigo="COD-001").update(
            fecha_creacion_servicio=timezone.make_aware(
                datetime(2026, 7, 6, 8, 0), zona
            )
        )
        Mantenimiento.objects.filter(codigo="COD-002").update(
            fecha_creacion_servicio=timezone.make_aware(
                datetime(2026, 7, 20, 8, 0), zona
            )
        )

        response = self.client.get(reverse("listar_mantenimientos"))
        codigos = list(response.context["mantenimientos"].values_list(
            "codigo", flat=True
        ))

        self.assertEqual(codigos, ["COD-002", "COD-001"])

    def test_filtra_por_fecha_efectiva_del_mantenimiento(self):
        zona = timezone.get_current_timezone()
        Mantenimiento.objects.filter(codigo="COD-001").update(
            fecha_creacion_servicio=timezone.make_aware(
                datetime(2026, 7, 6, 8, 0), zona
            )
        )
        Mantenimiento.objects.filter(codigo="COD-002").update(
            fecha_creacion_servicio=timezone.make_aware(
                datetime(2026, 7, 20, 8, 0), zona
            )
        )

        response = self.client.get(
            reverse("listar_mantenimientos"), {"fecha": "2026-07-20"}
        )

        codigos = list(response.context["mantenimientos"].values_list(
            "codigo", flat=True
        ))
        self.assertEqual(codigos, ["COD-002"])

    def test_filtra_por_estado_movil_asignado(self):
        tecnico = Tecnico.objects.create(nombre="Técnico filtro")
        Mantenimiento.objects.filter(codigo="COD-002").update(tecnico=tecnico)

        response = self.client.get(
            reverse("listar_mantenimientos"), {"estado_movil": "ASIGNADO"}
        )

        codigos = list(response.context["mantenimientos"].values_list(
            "codigo", flat=True
        ))
        self.assertEqual(codigos, ["COD-002"])

    def test_orden_registrada_por_operador_marca_el_servicio_realizado(self):
        mantenimiento = Mantenimiento.objects.get(codigo="COD-001")
        mantenimiento.orden = "OT-123"
        mantenimiento.realizado = timezone.localdate()
        mantenimiento.hora_entrada = time(8, 0)
        mantenimiento.hora_salida = time(9, 0)
        mantenimiento.novedad = "Servicio realizado desde plataforma"
        mantenimiento.save()
        mantenimiento.refresh_from_db()

        self.assertEqual(mantenimiento.estado_operativo, "FINALIZADO")
        self.assertEqual(mantenimiento.get_estado_operativo_display(), "Realizado")

    def test_asignar_tecnico_no_cierra_el_servicio(self):
        mantenimiento = Mantenimiento.objects.get(codigo="COD-001")
        tecnico = Tecnico.objects.create(nombre="Técnico asignado")
        mantenimiento.tecnico = tecnico
        mantenimiento.realizado = timezone.localdate()
        mantenimiento.save()
        mantenimiento.refresh_from_db()

        self.assertEqual(mantenimiento.estado_operativo, "PENDIENTE")

        response = self.client.get(reverse("listar_mantenimientos"))
        self.assertContains(response, "Asignado")

    def test_superadministrador_puede_editar_completo_un_servicio_cerrado(self):
        Ciudad.objects.get_or_create(nombre="Pasto")
        mantenimiento = Mantenimiento.objects.get(codigo="COD-001")
        mantenimiento.orden = "OT-CERRADA"
        mantenimiento.realizado = timezone.localdate()
        mantenimiento.hora_entrada = time(8, 0)
        mantenimiento.hora_salida = time(9, 0)
        mantenimiento.novedad = "Trabajo terminado"
        mantenimiento.save()

        superusuario = User.objects.create_superuser(
            "super_mantenimiento", "super@example.com", "Clave-12345"
        )
        self.client.force_login(superusuario)
        response = self.client.post(
            reverse("mantenimiento_actualizar", args=[mantenimiento.pk]),
            {
                "codigo": "COD-SUPER",
                "cliente": "Cliente corregido",
                "tipo_falla": "OTRO",
                "estado_operativo": "PENDIENTE",
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        mantenimiento.refresh_from_db()
        self.assertEqual(mantenimiento.codigo, "COD-SUPER")
        self.assertEqual(mantenimiento.cliente, "Cliente corregido")
        self.assertEqual(mantenimiento.estado_operativo, "PENDIENTE")


class PermisosMantenimientosTests(TestCase):
    def test_roles_operativos_no_pueden_abrir_mantenimientos(self):
        for nombre_rol in ("Almacen", "Programador", "Facturacion"):
            with self.subTest(rol=nombre_rol):
                usuario = User.objects.create_user(
                    f"usuario_{nombre_rol.lower()}", password="prueba123"
                )
                grupo, _ = Group.objects.get_or_create(name=nombre_rol)
                usuario.groups.add(grupo)
                self.client.force_login(usuario)

                response = self.client.get(reverse("listar_mantenimientos"))

                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("home")))

    def test_administrador_puede_abrir_mantenimientos(self):
        usuario = User.objects.create_user("admin_mantenimientos", password="prueba123")
        grupo, _ = Group.objects.get_or_create(name="Administrador")
        usuario.groups.add(grupo)
        self.client.force_login(usuario)

        response = self.client.get(reverse("listar_mantenimientos"))

        self.assertEqual(response.status_code, 200)

    def test_coordinador_opera_ambos_modulos_sin_acceso_administrativo(self):
        usuario = User.objects.create_user("coordinador", password="prueba123")
        grupo, _ = Group.objects.get_or_create(name="Coordinador")
        usuario.groups.add(grupo)
        self.client.force_login(usuario)

        mantenimiento = Mantenimiento.objects.create(
            codigo="COORD-1", cliente="Cliente", direccion="Calle 1"
        )

        self.assertEqual(
            self.client.get(reverse("listar_mantenimientos")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("registro_inst")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("configuracion_usuarios")).status_code, 302
        )
        self.assertEqual(self.client.get("/admin/").status_code, 302)

        response = self.client.post(
            reverse("mantenimiento_eliminar", args=[mantenimiento.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Mantenimiento.objects.filter(pk=mantenimiento.pk).exists())


class ConfiguracionUsuariosTests(TestCase):
    def test_superusuario_crea_tecnico_sin_acceso_a_admin_django(self):
        administrador = User.objects.create_superuser(
            "superconfig", "super@example.com", "ClaveSegura-4567"
        )
        tecnico = Tecnico.objects.create(nombre="Técnico creado")
        grupo = Group.objects.create(name="Tecnico")
        self.client.force_login(administrador)

        response = self.client.post(reverse("configuracion_usuarios"), {
            "accion": "crear_usuario",
            "username": "nuevo_tecnico",
            "first_name": "Nuevo",
            "last_name": "Técnico",
            "email": "tecnico@example.com",
            "password1": "ClaveTecnico-9876",
            "password2": "ClaveTecnico-9876",
            "grupo_id": grupo.pk,
            "tecnico_id": tecnico.pk,
        })

        self.assertRedirects(response, reverse("configuracion_usuarios"))
        usuario = User.objects.get(username="nuevo_tecnico")
        tecnico.refresh_from_db()
        self.assertEqual(tecnico.usuario, usuario)
        self.assertTrue(usuario.groups.filter(name="Tecnico").exists())
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)


class PortalTecnicoTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("tecnico_movil", password="prueba123")
        self.otro_usuario = User.objects.create_user("otro_tecnico", password="prueba123")
        self.tecnico = Tecnico.objects.create(nombre="Técnico móvil", usuario=self.usuario)
        self.otro_tecnico = Tecnico.objects.create(nombre="Otro técnico", usuario=self.otro_usuario)
        self.servicio = Mantenimiento.objects.create(
            codigo="MOV-001", cliente="Cliente móvil", ciudad="Pasto",
            direccion="Calle móvil", tecnico=self.tecnico,
            fecha_programada=timezone.localdate(),
        )
        Mantenimiento.objects.create(
            codigo="AJENO-001", cliente="Servicio ajeno", ciudad="Cali",
            direccion="Calle ajena", tecnico=self.otro_tecnico,
            fecha_programada=timezone.localdate(),
        )
        self.client.force_login(self.usuario)

    def test_api_solo_entrega_servicios_del_tecnico_autenticado(self):
        response = self.client.get(reverse("api_servicios_tecnico"))

        self.assertEqual(response.status_code, 200)
        codigos = [item["codigo"] for item in response.json()["servicios"]]
        self.assertEqual(codigos, ["MOV-001"])

    def test_api_oculta_realizados_de_dias_anteriores(self):
        ayer = timezone.localdate() - timedelta(days=1)
        Mantenimiento.objects.create(
            codigo="REALIZADO-AYER",
            cliente="Servicio anterior",
            direccion="Calle anterior",
            tecnico=self.tecnico,
            fecha_programada=timezone.localdate(),
            realizado=ayer,
            estado_operativo="FINALIZADO",
        )
        Mantenimiento.objects.create(
            codigo="REALIZADO-HOY",
            cliente="Servicio de hoy",
            direccion="Calle de hoy",
            tecnico=self.tecnico,
            fecha_programada=ayer,
            realizado=timezone.localdate(),
            estado_operativo="FINALIZADO",
        )

        response = self.client.get(reverse("api_servicios_tecnico"))
        codigos = [item["codigo"] for item in response.json()["servicios"]]

        self.assertIn("REALIZADO-HOY", codigos)
        self.assertNotIn("REALIZADO-AYER", codigos)

    def test_tecnico_puede_iniciar_servicio_asignado(self):
        response = self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "EN_PROCESO", "novedad": "En sitio"}' % self.servicio.pk,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado_operativo, "EN_PROCESO")
        self.assertIsNotNone(self.servicio.inicio_tecnico)
        self.assertEqual(self.servicio.novedad, "En sitio")
        self.assertIn("[NOTA TÉCNICO - Técnico móvil -", self.servicio.observacion)
        self.assertIn("En sitio", self.servicio.observacion)
        self.assertEqual(response.json()["servicio"]["codigo"], "MOV-001")

        self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "FINALIZADO", "novedad": "En sitio"}' % self.servicio.pk,
            content_type="application/json",
        )
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.observacion.count("[NOTA TÉCNICO"), 1)
        self.assertEqual(self.servicio.realizado, timezone.localdate())

    def test_finalizado_solo_admite_orden_y_luego_queda_bloqueado(self):
        Ciudad.objects.create(nombre="Pasto")
        self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "EN_PROCESO", "novedad": ""}' % self.servicio.pk,
            content_type="application/json",
        )
        self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "FINALIZADO", "novedad": "Terminado"}' % self.servicio.pk,
            content_type="application/json",
        )
        administrador = User.objects.create_user("operador_orden", password="prueba123")
        grupo = Group.objects.create(name="Administrador")
        administrador.groups.add(grupo)
        self.client.force_login(administrador)

        response = self.client.post(
            reverse("mantenimiento_actualizar", args=[self.servicio.pk]),
            {
                "orden": "OT-987",
                "realizado": "2026-07-27",
                "hora_entrada": "08:10:00",
                "hora_salida": "09:25:00",
                "novedad": "Se reemplazó el sensor y quedó funcionando.",
                "cliente": "Nombre no permitido",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.orden, "OT-987")
        self.assertEqual(self.servicio.cliente, "Cliente móvil")
        self.assertIsNotNone(self.servicio.fecha_orden)
        self.assertEqual(self.servicio.hora_entrada.strftime("%H:%M:%S"), "08:10:00")
        self.assertEqual(self.servicio.hora_salida.strftime("%H:%M:%S"), "09:25:00")
        self.assertEqual(self.servicio.duracion_servicio, "01:15:00")
        self.assertEqual(self.servicio.realizado.isoformat(), "2026-07-27")
        self.assertEqual(
            self.servicio.novedad,
            "Se reemplazó el sensor y quedó funcionando.",
        )
        self.assertIn("[NOTA OPERADOR - operador_orden -", self.servicio.observacion)
        self.assertIn("Se reemplazó el sensor", self.servicio.observacion)
        self.assertTrue(
            self.servicio.observacion.startswith(
                "[NOTA OPERADOR - operador_orden -"
            )
        )

        segundo_cambio = self.client.post(
            reverse("mantenimiento_actualizar", args=[self.servicio.pk]),
            {"orden": "OT-OTRA"},
        )
        self.assertEqual(segundo_cambio.status_code, 409)
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.orden, "OT-987")

    def test_no_permite_dos_servicios_en_ejecucion(self):
        segundo = Mantenimiento.objects.create(
            codigo="MOV-002", cliente="Segundo", ciudad="Pasto",
            direccion="Calle 2", tecnico=self.tecnico,
            fecha_programada=timezone.localdate(),
        )
        primero = self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "EN_PROCESO", "novedad": ""}' % self.servicio.pk,
            content_type="application/json",
        )
        intento_segundo = self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "EN_PROCESO", "novedad": ""}' % segundo.pk,
            content_type="application/json",
        )

        self.assertEqual(primero.status_code, 200)
        self.assertEqual(intento_segundo.status_code, 409)
        segundo.refresh_from_db()
        self.assertEqual(segundo.estado_operativo, "PENDIENTE")

    def test_finalizar_exige_novedad(self):
        self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "EN_PROCESO", "novedad": ""}' % self.servicio.pk,
            content_type="application/json",
        )

        response = self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "FINALIZADO", "novedad": ""}' % self.servicio.pk,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.servicio.refresh_from_db()
        self.assertEqual(self.servicio.estado_operativo, "EN_PROCESO")

    def test_asignacion_sin_fecha_se_programa_automaticamente(self):
        servicio = Mantenimiento.objects.create(
            codigo="SIN-FECHA", cliente="Sin fecha", direccion="Calle 3"
        )

        registrar_cambio_tecnico(servicio, None, self.tecnico, self.usuario)

        servicio.refresh_from_db()
        self.assertEqual(servicio.fecha_programada, timezone.localdate())

    def test_conserva_fecha_y_hora_reales_del_dispositivo(self):
        self.servicio.fecha_inicio = timezone.make_aware(
            datetime(2026, 7, 15, 15, 10)
        )
        self.servicio.fecha_fin = timezone.make_aware(
            datetime(2026, 7, 15, 15, 48)
        )
        self.servicio.horas = "0.63"
        self.servicio.save()

        inicio = self.client.post(
            reverse("api_servicios_tecnico"),
            data=(
                '{"id": %d, "estado": "EN_PROCESO", "novedad": "", '
                '"fecha_evento": "2026-07-24T14:15:00.000Z", "registrado_offline": true}'
            ) % self.servicio.pk,
            content_type="application/json",
        )
        fin = self.client.post(
            reverse("api_servicios_tecnico"),
            data=(
                '{"id": %d, "estado": "FINALIZADO", "novedad": "Trabajo terminado", '
                '"fecha_evento": "2026-07-24T14:15:35.000Z", "registrado_offline": true}'
            ) % self.servicio.pk,
            content_type="application/json",
        )

        self.assertEqual(inicio.status_code, 200)
        self.assertEqual(fin.status_code, 200)
        self.servicio.refresh_from_db()
        inicio_local = timezone.localtime(self.servicio.inicio_tecnico)
        fin_local = timezone.localtime(self.servicio.fin_tecnico)
        self.assertEqual((inicio_local.hour, inicio_local.minute), (9, 15))
        self.assertEqual((fin_local.hour, fin_local.minute, fin_local.second), (9, 15, 35))
        self.assertEqual(self.servicio.hora_entrada.strftime("%H:%M:%S"), "09:15:00")
        self.assertEqual(self.servicio.hora_salida.strftime("%H:%M:%S"), "09:15:35")
        self.assertEqual(str(self.servicio.horas), "0.01")
        self.assertEqual(self.servicio.duracion_servicio, "00:00:35")
        self.assertEqual(self.servicio.realizado.isoformat(), "2026-07-24")
        self.assertIn("2026-07-24 09:15", self.servicio.observacion)

    def test_tabla_administrativa_muestra_cambios_del_portal_movil(self):
        self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "EN_PROCESO", "novedad": "En sitio"}' % self.servicio.pk,
            content_type="application/json",
        )
        administrador = User.objects.create_user("admin_tabla", password="prueba123")
        grupo = Group.objects.create(name="Administrador")
        administrador.groups.add(grupo)
        self.client.force_login(administrador)

        response = self.client.get(reverse("listar_mantenimientos"))

        self.assertContains(response, "Estado móvil")
        self.assertContains(response, "En proceso")
        self.assertContains(response, "En sitio")

    def test_tecnico_no_puede_actualizar_servicio_ajeno(self):
        ajeno = Mantenimiento.objects.get(codigo="AJENO-001")
        response = self.client.post(
            reverse("api_servicios_tecnico"),
            data='{"id": %d, "estado": "FINALIZADO"}' % ajeno.pk,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_reasignacion_avisa_al_tecnico_anterior_y_al_nuevo(self):
        registrar_cambio_tecnico(
            self.servicio, self.tecnico, self.otro_tecnico, self.usuario
        )

        self.assertEqual(HistorialAsignacionMantenimiento.objects.count(), 1)
        self.assertTrue(NotificacionTecnico.objects.filter(
            tecnico=self.tecnico, tipo="RETIRADO"
        ).exists())
        self.assertTrue(NotificacionTecnico.objects.filter(
            tecnico=self.otro_tecnico, tipo="REASIGNACION"
        ).exists())


class ImportacionMantenimientosPdfTests(TestCase):
    TEXTO_ASIGNADO = """
    Descripción Trabajo Abonado: 1823 Partición: 01 Nombre: CLIENTE PRUEBA
    Orden Nro. 64590 Dirección: Teléfono Celular:CALLE 1 2-3
    Asignado Estado: Etapa TecnicoREVISION GENERAL DE PANICOS
    FALLOS EQUIPOS ASIGNADO Creado por:
    """

    TEXTO_FINALIZADO = """
    Descripción Trabajo Abonado: 3419 Partición: 01 Nombre: CLIENTE FINAL
    Orden Nro. 64511 Dirección: Teléfono Celular:CALLE 17 13-56
    Finalizada Estado: Etapa TecnicoPROGRAMAR TIEMPO
    PROGRAMACION DATOS ACTA Fecha Inicio : 2026-07-0308:37:59
    Codigo Acta : 159-800 Tecnico : DIEGO COLIMBA MOTIVO VISITA
    Motivo visita: MANTENIMIENTO CORRECTIVO Mantenimiento correctivo: PROGRAMACION
    DATOS DEL CLIENTE Problema solucionado: SI DATOS COTIZACIÓN Cotizacion: NO
    Trabajo realizado: se configura el tiempo de entrada FIRMA CLIENTE
    MÁS DETALLES Fecha Fin : 2026-07-0308:59:51 PROGRAMACION FINALIZADA
    Creado: 2026-07-20 06:04:33
    Creado por:
    """

    def test_extrae_columnas_reales_y_fechas_sin_espacio(self):
        asignado = extraer_mantenimiento_desde_texto(self.TEXTO_ASIGNADO)
        finalizado = extraer_mantenimiento_desde_texto(self.TEXTO_FINALIZADO)

        self.assertEqual(asignado["estado_ticket"], "ASIGNADO")
        self.assertEqual(asignado["tipo_falla"], "FALLOS EQUIPOS")
        self.assertIn("REVISION GENERAL", asignado["pendiente"])
        self.assertEqual(finalizado["tecnico_nombre"], "DIEGO COLIMBA")
        self.assertEqual(finalizado["tipo_falla"], "PROGRAMACION")
        self.assertEqual(str(finalizado["horas"]), "0.36")
        self.assertEqual(
            finalizado["fecha_creacion_servicio"],
            datetime(2026, 7, 20, 6, 4, 33),
        )
        self.assertEqual(
            finalizado["observacion"],
            "se configura el tiempo de entrada",
        )

    def test_asocia_fecha_creado_de_pagina_continuacion_al_ticket_anterior(self):
        pagina_ticket = MagicMock()
        pagina_ticket.extract_text.return_value = self.TEXTO_ASIGNADO
        pagina_continuacion = MagicMock()
        pagina_continuacion.extract_text.return_value = """
            Creado por: RODRIGUEZ
            Creado: Tecnico: 2026-07-06 18:06:11
            Fecha Visita:
            Materiales:
        """

        with patch(
            "app_instalaciones.utils.importar_mantenimientos_pdf.PdfReader"
        ) as lector:
            lector.return_value.pages = [pagina_ticket, pagina_continuacion]
            resultados = analizar_pdf_mantenimientos(MagicMock())

        self.assertEqual(len(resultados), 1)
        self.assertEqual(
            resultados[0]["data"]["fecha_creacion_servicio"],
            datetime(2026, 7, 6, 18, 6, 11),
        )

    def test_extrae_fecha_cuando_pypdf_pone_el_valor_antes_de_creado(self):
        texto = """
            Creado por:
            Observación:
            RODRIGUEZ
            2026-07-06 18:06:11
            Creado:
            Fecha Visita:
            Tecnico:
            Materiales:
        """

        resultado = extraer_mantenimiento_desde_texto(texto)

        self.assertEqual(
            resultado["fecha_creacion_servicio"],
            datetime(2026, 7, 6, 18, 6, 11),
        )

    def test_no_actualiza_ticket_cerrado_con_orden_manual(self):
        usuario = User.objects.create_user("importador", password="prueba123")
        mantenimiento = Mantenimiento.objects.create(
            numero_ticket="64590",
            codigo="ANTERIOR",
            cliente="Anterior",
            direccion="Anterior",
            orden="ORDEN-MANUAL",
        )
        data = extraer_mantenimiento_desde_texto(self.TEXTO_ASIGNADO)
        data.update({"ciudad": "Pasto", "tecnico_id": None})

        resumen = importar_resultados_pdf(
            [{"data": data}],
            usuario,
            actualizar_existentes=True,
        )

        mantenimiento.refresh_from_db()
        self.assertEqual(resumen["actualizados"], 0)
        self.assertEqual(resumen["repetidos"], 1)
        self.assertEqual(mantenimiento.codigo, "ANTERIOR")
        self.assertFalse(mantenimiento.estado_ticket)
        self.assertEqual(mantenimiento.orden, "ORDEN-MANUAL")

    def test_muestra_duracion_importada_en_formato_horas_y_minutos(self):
        data = extraer_mantenimiento_desde_texto(self.TEXTO_FINALIZADO)
        mantenimiento = Mantenimiento(
            fecha_inicio=data["fecha_inicio"],
            fecha_fin=data["fecha_fin"],
            horas=data["horas"],
        )

        self.assertEqual(mantenimiento.duracion_servicio, "00:21:52")

    def test_codigo_acta_se_guarda_como_numero_de_orden(self):
        usuario = User.objects.create_user("importador_acta", password="prueba123")
        data = extraer_mantenimiento_desde_texto(self.TEXTO_FINALIZADO)
        data.update({"ciudad": "Pasto", "tecnico_id": None})

        resumen = importar_resultados_pdf([{"data": data}], usuario)

        mantenimiento = Mantenimiento.objects.get(numero_ticket="64511")
        self.assertEqual(resumen["creados"], 1)
        self.assertEqual(mantenimiento.codigo_acta, "159-800")
        self.assertEqual(mantenimiento.orden, "159-800")

    def test_muestra_duracion_manual_y_deja_vacio_si_no_hay_tiempos(self):
        mantenimiento = Mantenimiento(
            hora_entrada=time(8, 15),
            hora_salida=time(9, 45),
        )
        sin_tiempos = Mantenimiento()

        self.assertEqual(mantenimiento.duracion_servicio, "01:30:00")
        self.assertEqual(sin_tiempos.duracion_servicio, "")

    def test_restauracion_convierte_fechas_pdf_a_zona_horaria(self):
        data = extraer_mantenimiento_desde_texto(self.TEXTO_FINALIZADO)
        resultados = preparar_resultados_para_session([{"data": data}])

        restaurados = restaurar_resultados_desde_session(resultados)

        self.assertTrue(timezone.is_aware(restaurados[0]["data"]["fecha_inicio"]))
        self.assertTrue(timezone.is_aware(restaurados[0]["data"]["fecha_fin"]))

    def test_importacion_recorta_textos_al_limite_de_postgresql(self):
        usuario = User.objects.create_user("importador_largo", password="prueba123")
        data = extraer_mantenimiento_desde_texto(self.TEXTO_ASIGNADO)
        data.update({
            "numero_ticket": "LARGO-1",
            "codigo": "C" * 80,
            "cliente": "Cliente " * 30,
            "direccion": "Dirección " * 30,
            "omt": "O" * 180,
            "tecnico_nombre": "T" * 140,
            "tecnico_id": None,
            "ciudad": "Pasto",
        })

        resumen = importar_resultados_pdf([{"data": data}], usuario)

        mantenimiento = Mantenimiento.objects.get(numero_ticket="LARGO-1")
        self.assertEqual(resumen["creados"], 1)
        self.assertEqual(len(mantenimiento.codigo), 50)
        self.assertEqual(len(mantenimiento.cliente), 100)
        self.assertEqual(len(mantenimiento.direccion), 100)
        self.assertEqual(len(mantenimiento.omt), 100)
        self.assertEqual(len(mantenimiento.tecnico.nombre), 100)
        self.assertIsNotNone(mantenimiento.fecha_creacion_servicio)
        self.assertEqual(
            timezone.localtime(mantenimiento.fecha_creacion_servicio).date(),
            timezone.localdate(),
        )
