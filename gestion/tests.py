"""
Tests del panel de gestion (el que usa la duenia).

Foco: lo que si falla duele de verdad.
- Que NADIE que no sea staff entre al panel (recorre todas las rutas)
- Confirmar pago por transferencia (descuenta stock, idempotente)
- Marcar reembolsado
- Agregar stock (suma, no reemplaza)
- Cambio de estado del pedido + email al cliente
- Newsletter: no mandar un envio masivo sin confirmacion explicita
- Borrado de categoria con productos asociados
- Exports CSV (cuentan solo pedidos pagados)
"""
from decimal import Decimal
from urllib.parse import urlparse

from django.core import mail
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse, NoReverseMatch

from catalogo.models import (
    Categoria, Producto, Variante, Resena,
    CampanaNewsletter, SuscriptorNewsletter,
)
from pedidos.models import Pedido, ItemPedido, Cupon


# =========================================================================
# 1. Control de acceso: el panel es solo para staff
# =========================================================================

class AccesoPanelGestionTests(TestCase):
    """
    Recorre TODAS las rutas de gestion/urls.py y verifica que ni un anonimo
    ni un cliente registrado puedan entrar a ninguna.

    Se construyen por introspeccion del urlconf a proposito: si maniana se
    agrega una vista nueva al panel, queda cubierta sola. Si esa vista lleva
    <pk>, el test falla pidiendo que la agreguen al mapa de abajo — que es
    justo el momento de preguntarse si quedo bien protegida.
    """

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela Lavanda', descripcion='x',
            precio=Decimal('5000'), stock=10,
        )
        self.cliente = User.objects.create_user('cliente', 'cli@t.com', 'pass1234')
        self.staff = User.objects.create_user('duenia', 'duenia@t.com', 'pass1234',
                                              is_staff=True)
        self.pedido = Pedido.objects.create(
            usuario=self.cliente, telefono='+56912345678', metodo_envio='retiro_local',
            subtotal=Decimal('5000'), costo_envio=Decimal('0'), total=Decimal('5000'),
        )
        self.campana = CampanaNewsletter.objects.create(asunto='Hola', cuerpo='Texto')
        self.cupon = Cupon.objects.create(codigo='TEST10', tipo='porcentaje',
                                          valor=Decimal('10'))
        self.resena = Resena.objects.create(
            producto=self.producto, usuario=self.cliente, rating=5,
            comentario='Muy buena vela de verdad',
        )

    def _pk_para(self, nombre_ruta):
        """A que objeto apunta el <pk> de cada ruta del panel."""
        mapa = {
            'detalle_pedido':               self.pedido.pk,
            'confirmar_pago_transferencia': self.pedido.pk,
            'marcar_reembolsado':           self.pedido.pk,
            'editar_producto':              self.producto.pk,
            'agregar_stock':                self.producto.pk,
            'eliminar_producto':            self.producto.pk,
            'newsletter_detalle':           self.campana.pk,
            'newsletter_enviar_prueba':     self.campana.pk,
            'newsletter_enviar_real':       self.campana.pk,
            'categoria_editar':             self.cat.pk,
            'categoria_eliminar':           self.cat.pk,
            'cupon_editar':                 self.cupon.pk,
            'cupon_toggle':                 self.cupon.pk,
            'resena_toggle_aprobar':        self.resena.pk,
            'resena_eliminar':              self.resena.pk,
        }
        if nombre_ruta not in mapa:
            self.fail(
                'La ruta "gestion:{}" lleva <pk> y no esta en el mapa de este '
                'test. Agregala — y de paso revisa que la vista tenga los '
                'decoradores de staff.'.format(nombre_ruta)
            )
        return mapa[nombre_ruta]

    def _todas_las_urls(self):
        from gestion.urls import urlpatterns
        urls = []
        for patron in urlpatterns:
            nombre = 'gestion:{}'.format(patron.name)
            try:
                url = reverse(nombre)
            except NoReverseMatch:
                url = reverse(nombre, args=[self._pk_para(patron.name)])
            urls.append((patron.name, url))
        return urls

    def test_el_urlconf_tiene_rutas(self):
        """Red de seguridad: si esto da 0, los tests de abajo no prueban nada."""
        self.assertGreaterEqual(len(self._todas_las_urls()), 30)

    def test_anonimo_no_entra_a_ninguna_vista_del_panel(self):
        for nombre, url in self._todas_las_urls():
            with self.subTest(ruta=nombre):
                resp = self.client.get(url)
                self.assertEqual(
                    resp.status_code, 302,
                    'gestion:{} dejo pasar a un anonimo (status {})'.format(
                        nombre, resp.status_code),
                )

    def test_cliente_registrado_no_entra_al_panel(self):
        """Estar logueado no alcanza: hace falta is_staff."""
        self.client.force_login(self.cliente)
        for nombre, url in self._todas_las_urls():
            with self.subTest(ruta=nombre):
                resp = self.client.get(url)
                self.assertEqual(
                    resp.status_code, 302,
                    'gestion:{} dejo pasar a un cliente comun'.format(nombre))
                # Rebota al inicio (la redireccion lleva ?next=, no importa).
                self.assertEqual(
                    urlparse(resp.url).path, '/',
                    'gestion:{} deberia rebotar al inicio, fue a {}'.format(
                        nombre, resp.url))

    def test_cliente_registrado_tampoco_puede_por_POST(self):
        """Las acciones destructivas son POST: el rebote tiene que valer igual."""
        self.client.force_login(self.cliente)
        for nombre, url in self._todas_las_urls():
            with self.subTest(ruta=nombre):
                resp = self.client.post(url, data={})
                self.assertEqual(
                    resp.status_code, 302,
                    'gestion:{} acepto un POST de un cliente comun'.format(nombre))
                self.assertEqual(urlparse(resp.url).path, '/')

    def test_staff_si_entra(self):
        """Contraparte: con is_staff no debe rebotar a inicio ni al login."""
        self.client.force_login(self.staff)
        for nombre, url in self._todas_las_urls():
            with self.subTest(ruta=nombre):
                resp = self.client.get(url)
                self.assertIn(resp.status_code, (200, 302))
                if resp.status_code == 302:
                    # Puede redirigir dentro del panel (vistas solo-POST),
                    # pero nunca expulsarlo.
                    self.assertNotEqual(resp.url, '/')
                    self.assertNotIn('login', resp.url)


# =========================================================================
# 2. Confirmar pago por transferencia
# =========================================================================

class ConfirmarPagoTransferenciaTests(TestCase):
    """
    La duenia vio el deposito en su banco y confirma a mano. Es el unico
    camino de cobro que no valida ninguna pasarela, asi que conviene que
    este bien cubierto: descuenta stock y dispara emails al cliente.
    """

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10,
        )
        self.staff = User.objects.create_user('duenia', 'duenia@t.com', 'pass1234',
                                              is_staff=True)
        self.client.force_login(self.staff)

    def _pedido(self, metodo_pago='transferencia', cantidad=2):
        pedido = Pedido.objects.create(
            usuario=None, nombre_cliente='Juan', email_cliente='juan@t.com',
            telefono='+56912345678', metodo_envio='retiro_local',
            metodo_pago=metodo_pago,
            subtotal=Decimal('10000'), costo_envio=Decimal('0'),
            total=Decimal('10000'),
        )
        ItemPedido.objects.create(
            pedido=pedido, producto=self.producto, cantidad=cantidad,
            precio_unitario=Decimal('5000'), nombre_snapshot='Vela',
        )
        return pedido

    def _confirmar(self, pedido, **data):
        return self.client.post(
            reverse('gestion:confirmar_pago_transferencia', args=[pedido.pk]),
            data=data,
        )

    def test_confirmar_descuenta_stock_y_marca_pagado(self):
        pedido = self._pedido()
        self._confirmar(pedido)
        pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(pedido.estado, 'confirmado')
        self.assertEqual(pedido.estado_pago, 'pagado')
        self.assertEqual(pedido.medio_pago_detalle, 'transferencia')
        self.assertEqual(self.producto.stock, 8)

    def test_confirmar_dos_veces_no_descuenta_stock_dos_veces(self):
        """Doble click en el boton, o dos pestanias abiertas."""
        pedido = self._pedido()
        self._confirmar(pedido)
        self._confirmar(pedido)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)

    def test_confirmar_manda_email_al_cliente(self):
        pedido = self._pedido()
        mail.outbox = []
        self._confirmar(pedido)
        destinatarios = [d for m in mail.outbox for d in m.to]
        self.assertIn('juan@t.com', destinatarios)

    def test_no_confirma_un_pedido_que_no_es_transferencia(self):
        pedido = self._pedido(metodo_pago='flow')
        self._confirmar(pedido)
        pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(pedido.estado, 'pendiente')
        self.assertEqual(self.producto.stock, 10)

    def test_monto_invalido_no_confirma(self):
        pedido = self._pedido()
        self._confirmar(pedido, monto_recibido='no-es-un-numero')
        pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(pedido.estado, 'pendiente')
        self.assertEqual(self.producto.stock, 10)

    def test_monto_distinto_igual_confirma_pero_avisa(self):
        """Transfirio de menos: se confirma igual y el mensaje lo advierte."""
        pedido = self._pedido()
        resp = self._confirmar(pedido, monto_recibido='8000')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'confirmado')
        mensajes = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any('faltan' in m.lower() for m in mensajes), mensajes)

    def test_sin_stock_cancela_y_avisa_para_reembolso(self):
        """
        Pago recibido pero el stock se agoto: el pedido se cancela y queda
        estado_pago='pagado' = hay plata que devolver.
        """
        pedido = self._pedido(cantidad=15)  # stock es 10
        self._confirmar(pedido)
        pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(pedido.estado, 'cancelado')
        self.assertEqual(pedido.estado_pago, 'pagado')
        self.assertEqual(self.producto.stock, 10)

    def test_get_no_confirma_nada(self):
        """Solo POST: un GET no puede cobrar un pedido."""
        pedido = self._pedido()
        self.client.get(
            reverse('gestion:confirmar_pago_transferencia', args=[pedido.pk]))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'pendiente')


# =========================================================================
# 3. Marcar reembolsado
# =========================================================================

class MarcarReembolsadoTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('duenia', 'd@t.com', 'pass1234',
                                              is_staff=True)
        self.client.force_login(self.staff)
        self.pedido = Pedido.objects.create(
            usuario=None, nombre_cliente='Juan', email_cliente='juan@t.com',
            telefono='+56912345678', metodo_envio='retiro_local',
            subtotal=Decimal('5000'), costo_envio=Decimal('0'), total=Decimal('5000'),
        )

    def _reembolsar(self):
        return self.client.post(
            reverse('gestion:marcar_reembolsado', args=[self.pedido.pk]))

    def test_reembolsa_un_pedido_pagado(self):
        self.pedido.estado_pago = 'pagado'
        self.pedido.save(update_fields=['estado_pago'])
        self._reembolsar()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado_pago, 'reembolsado')

    def test_no_reembolsa_un_pedido_impago(self):
        """No se puede devolver plata que nunca entro."""
        self._reembolsar()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado_pago, 'pendiente')

    def test_get_no_reembolsa(self):
        self.pedido.estado_pago = 'pagado'
        self.pedido.save(update_fields=['estado_pago'])
        self.client.get(reverse('gestion:marcar_reembolsado', args=[self.pedido.pk]))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado_pago, 'pagado')


# =========================================================================
# 4. Agregar stock
# =========================================================================

class AgregarStockTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10,
        )
        self.staff = User.objects.create_user('duenia', 'd@t.com', 'pass1234',
                                              is_staff=True)
        self.client.force_login(self.staff)

    def _agregar(self, cantidad):
        return self.client.post(
            reverse('gestion:agregar_stock', args=[self.producto.pk]),
            data={'cantidad': cantidad},
        )

    def test_suma_al_stock_existente(self):
        """SUMA, no reemplaza: 10 + 5 = 15, no 5."""
        self._agregar(5)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 15)

    def test_cantidad_cero_o_negativa_no_cambia_nada(self):
        for cantidad in (0, -3):
            with self.subTest(cantidad=cantidad):
                self._agregar(cantidad)
                self.producto.refresh_from_db()
                self.assertEqual(self.producto.stock, 10)

    def test_cantidad_absurda_se_rechaza(self):
        """Tope de 9999 por vez: atajo para el cero de mas al tipear."""
        self._agregar(50000)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)

    def test_cantidad_no_numerica_no_rompe(self):
        self._agregar('muchas')
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)

    def test_producto_con_variantes_no_toca_el_stock_base(self):
        """Con variantes el stock vive en cada una; el base se ignora."""
        Variante.objects.create(producto=self.producto, nombre='200g',
                                precio=Decimal('7000'), stock=4)
        self._agregar(5)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)


# =========================================================================
# 5. Cambio de estado del pedido (y el email que dispara)
# =========================================================================

class CambioEstadoPedidoTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('duenia', 'd@t.com', 'pass1234',
                                              is_staff=True)
        self.client.force_login(self.staff)
        self.pedido = Pedido.objects.create(
            usuario=None, nombre_cliente='Juan', email_cliente='juan@t.com',
            telefono='+56912345678', metodo_envio='envio_domicilio',
            calle_numero='Av Siempreviva 742', comuna='Nunoa',
            subtotal=Decimal('5000'), costo_envio=Decimal('3000'),
            total=Decimal('8000'), estado='confirmado',
        )

    def _cambiar(self, estado, **extra):
        data = {'estado': estado}
        data.update(extra)
        return self.client.post(
            reverse('gestion:detalle_pedido', args=[self.pedido.pk]), data=data)

    def test_cambia_el_estado(self):
        self._cambiar('preparando')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'preparando')

    def test_estado_invalido_no_se_aplica(self):
        self._cambiar('estado-que-no-existe')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'confirmado')

    def test_marcar_enviado_avisa_al_cliente_con_el_seguimiento(self):
        mail.outbox = []
        self._cambiar('enviado', codigo_seguimiento='CH123456')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.codigo_seguimiento, 'CH123456')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('juan@t.com', mail.outbox[0].to)
        self.assertIn('CH123456', mail.outbox[0].body)

    def test_marcar_entregado_avisa_al_cliente(self):
        mail.outbox = []
        self._cambiar('entregado')
        self.assertEqual(len(mail.outbox), 1)

    def test_estados_intermedios_no_mandan_email(self):
        """Solo enviado/entregado avisan; el resto es ruido para el cliente."""
        mail.outbox = []
        self._cambiar('preparando')
        self.assertEqual(len(mail.outbox), 0)

    def test_reguardar_el_mismo_estado_no_reenvia_el_email(self):
        self._cambiar('enviado')
        mail.outbox = []
        self._cambiar('enviado')
        self.assertEqual(len(mail.outbox), 0)


# =========================================================================
# 6. Newsletter: no mandar un envio masivo por accidente
# =========================================================================

class NewsletterEnvioTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('duenia', 'd@t.com', 'pass1234',
                                              is_staff=True)
        self.client.force_login(self.staff)
        self.campana = CampanaNewsletter.objects.create(
            asunto='Novedades de agosto', cuerpo='Hola! Este mes...')
        SuscriptorNewsletter.objects.create(email='uno@t.com')
        SuscriptorNewsletter.objects.create(email='dos@t.com')
        SuscriptorNewsletter.objects.create(email='baja@t.com', activo=False)

    def _enviar(self, **data):
        return self.client.post(
            reverse('gestion:newsletter_enviar_real', args=[self.campana.pk]),
            data=data)

    def test_sin_confirmacion_explicita_no_manda_nada(self):
        """El envio masivo exige escribir SI. Sin eso, ni un email."""
        mail.outbox = []
        self._enviar()
        self.assertEqual(len(mail.outbox), 0)
        self.campana.refresh_from_db()
        self.assertEqual(self.campana.estado, 'borrador')

    def test_confirmacion_equivocada_no_manda_nada(self):
        mail.outbox = []
        self._enviar(confirmar='si-dale')
        self.assertEqual(len(mail.outbox), 0)

    def test_con_confirmacion_manda_solo_a_los_activos(self):
        mail.outbox = []
        self._enviar(confirmar='SI')
        destinatarios = sorted(d for m in mail.outbox for d in m.to)
        self.assertEqual(destinatarios, ['dos@t.com', 'uno@t.com'])

    def test_una_campana_ya_enviada_no_se_reenvia(self):
        self._enviar(confirmar='SI')
        mail.outbox = []
        self._enviar(confirmar='SI')
        self.assertEqual(len(mail.outbox), 0)

    def test_get_no_dispara_el_envio(self):
        mail.outbox = []
        self.client.get(
            reverse('gestion:newsletter_enviar_real', args=[self.campana.pk]))
        self.assertEqual(len(mail.outbox), 0)


# =========================================================================
# 7. Categorias: no romper productos existentes
# =========================================================================

class CategoriaEliminarTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('duenia', 'd@t.com', 'pass1234',
                                              is_staff=True)
        self.client.force_login(self.staff)
        self.cat = Categoria.objects.create(nombre='Velas')

    def test_no_borra_categoria_con_productos(self):
        Producto.objects.create(categoria=self.cat, nombre='Vela',
                                descripcion='x', precio=Decimal('5000'), stock=1)
        self.client.post(reverse('gestion:categoria_eliminar', args=[self.cat.pk]))
        self.assertTrue(Categoria.objects.filter(pk=self.cat.pk).exists())

    def test_borra_categoria_vacia(self):
        self.client.post(reverse('gestion:categoria_eliminar', args=[self.cat.pk]))
        self.assertFalse(Categoria.objects.filter(pk=self.cat.pk).exists())

    def test_get_solo_muestra_la_confirmacion(self):
        resp = self.client.get(
            reverse('gestion:categoria_eliminar', args=[self.cat.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Categoria.objects.filter(pk=self.cat.pk).exists())


# =========================================================================
# 8. Exports CSV
# =========================================================================

class ExportsCsvTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10)
        self.staff = User.objects.create_user('duenia', 'd@t.com', 'pass1234',
                                              is_staff=True)
        self.cliente = User.objects.create_user('cliente', 'cli@t.com', 'pass1234')
        self.client.force_login(self.staff)

    def _pedido(self, estado, total='10000'):
        return Pedido.objects.create(
            usuario=self.cliente, telefono='+56912345678',
            metodo_envio='retiro_local', estado=estado,
            subtotal=Decimal(total), costo_envio=Decimal('0'), total=Decimal(total),
        )

    def test_export_pedidos_devuelve_csv_con_el_pedido(self):
        pedido = self._pedido('confirmado')
        resp = self.client.get(reverse('gestion:exportar_pedidos'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn(str(pedido.pk), resp.content.decode('utf-8'))

    def test_export_pedidos_respeta_el_filtro_de_estado(self):
        cancelado = self._pedido('cancelado')
        confirmado = self._pedido('confirmado')
        resp = self.client.get(
            reverse('gestion:exportar_pedidos'), {'estado': 'confirmado'})
        cuerpo = resp.content.decode('utf-8')
        filas = [l for l in cuerpo.splitlines()[1:] if l.strip()]
        self.assertEqual(len(filas), 1)
        self.assertTrue(filas[0].startswith(str(confirmado.pk)))
        self.assertNotIn('Cancelado', cuerpo)
        self.assertTrue(Pedido.objects.filter(pk=cancelado.pk).exists())

    def test_export_clientes_cuenta_solo_pedidos_pagados(self):
        """
        Un pedido pendiente o cancelado no es una compra. Si contara, la
        duenia segmentaria mal a quien mandarle cupones.
        """
        self._pedido('entregado', total='10000')
        self._pedido('pendiente', total='99000')
        self._pedido('cancelado', total='99000')
        resp = self.client.get(reverse('gestion:exportar_clientes'))
        fila = [l for l in resp.content.decode('utf-8').splitlines()
                if l.startswith('cli@t.com')]
        self.assertEqual(len(fila), 1, resp.content.decode('utf-8'))
        # ...,Numero de pedidos,Total comprado
        campos = fila[0].split(',')
        self.assertEqual(campos[-2], '1')
        self.assertEqual(campos[-1], '10000')

    def test_export_clientes_no_incluye_al_staff(self):
        resp = self.client.get(reverse('gestion:exportar_clientes'))
        self.assertNotIn('duenia@t.com', resp.content.decode('utf-8'))
