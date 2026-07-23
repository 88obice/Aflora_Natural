"""
Tests criticos del checkout y webhook MP.

Foco: lo que si falla pierdes plata o quedan pedidos en limbo.
- Calculo de costo de envio
- Confirmacion de pedido (descuenta stock, marca confirmado, idempotente)
- Webhook MP
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth.models import User

from catalogo.models import Categoria, Producto, Variante
from pedidos.models import Pedido, ItemPedido
from pedidos.envios import (
    calcular_costo_envio,
    COSTO_ENVIO_RM_URBANA,
    COSTO_ENVIO_RM_RESTO,
    COSTO_ENVIO_REGIONES,
)


# =========================================================================
# 1. Costos de envio
# =========================================================================

class CalculoCostoEnvioTests(TestCase):

    def test_retiro_local_es_gratis(self):
        c = calcular_costo_envio('retiro_local', 'Las Condes', 'Region Metropolitana', 10000)
        self.assertEqual(c, Decimal('0'))

    def test_envio_rm_urbana(self):
        c = calcular_costo_envio('envio_domicilio', 'Las Condes', 'Region Metropolitana', 10000)
        self.assertEqual(c, COSTO_ENVIO_RM_URBANA)

    def test_envio_rm_resto(self):
        c = calcular_costo_envio('envio_domicilio', 'Melipilla', 'Region Metropolitana', 10000)
        self.assertEqual(c, COSTO_ENVIO_RM_RESTO)

    def test_envio_otra_region(self):
        c = calcular_costo_envio('envio_domicilio', 'Vina del Mar', 'Region de Valparaiso', 10000)
        self.assertEqual(c, COSTO_ENVIO_REGIONES)

    def test_comuna_desconocida_cae_en_resto_rm(self):
        # Si la comuna no esta en ninguna lista pero region es RM, cae en resto
        c = calcular_costo_envio('envio_domicilio', 'NoExiste', 'Region Metropolitana', 10000)
        self.assertEqual(c, COSTO_ENVIO_RM_RESTO)


# =========================================================================
# 2. Confirmacion de pedido (stock + idempotencia)
# =========================================================================

class ConfirmarPedidoTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela Lavanda',
            descripcion='Test', precio=Decimal('5000'), stock=10,
        )
        self.user = User.objects.create_user('cliente', 'cli@test.com', 'pass1234')

    def _crear_pedido(self, cantidad=2):
        pedido = Pedido.objects.create(
            usuario=self.user, telefono='+56912345678',
            metodo_envio='retiro_local',
            subtotal=self.producto.precio * cantidad,
            costo_envio=Decimal('0'),
            total=self.producto.precio * cantidad,
        )
        ItemPedido.objects.create(
            pedido=pedido, producto=self.producto,
            cantidad=cantidad, precio_unitario=self.producto.precio,
            nombre_snapshot=self.producto.nombre,
        )
        return pedido

    def test_confirmar_descuenta_stock(self):
        from pedidos.views import _confirmar_pedido
        pedido = self._crear_pedido(cantidad=3)
        _confirmar_pedido(pedido, mp_payment_id='123', mp_status='approved')
        self.producto.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(self.producto.stock, 7)
        self.assertEqual(pedido.estado, 'confirmado')
        self.assertEqual(pedido.mp_payment_id, '123')

    def test_confirmar_es_idempotente(self):
        """Si webhook MP llega 2 veces (lo hace), no descontamos stock 2 veces."""
        from pedidos.views import _confirmar_pedido
        pedido = self._crear_pedido(cantidad=2)
        _confirmar_pedido(pedido, mp_payment_id='123', mp_status='approved')
        _confirmar_pedido(pedido, mp_payment_id='123', mp_status='approved')  # 2da vez
        self.producto.refresh_from_db()
        # Stock deberia haber bajado solo una vez
        self.assertEqual(self.producto.stock, 8)

    def test_confirmar_cancela_si_stock_insuficiente(self):
        """Si el stock se agoto entre el carrito y el pago, cancelar pedido."""
        from pedidos.views import _confirmar_pedido
        pedido = self._crear_pedido(cantidad=15)  # mas que el stock disponible (10)
        _confirmar_pedido(pedido, mp_payment_id='123', mp_status='approved')
        pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(pedido.estado, 'cancelado')
        # Stock NO se toco (no se descontaron unidades de un pedido cancelado)
        self.assertEqual(self.producto.stock, 10)


class ConfirmarPedidoConVarianteTests(TestCase):
    """Confirmacion descuenta stock de la variante, no del producto."""

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela',
            descripcion='Test', precio=Decimal('5000'), stock=0,
        )
        self.variante = Variante.objects.create(
            producto=self.producto, nombre='100g',
            precio=Decimal('5000'), stock=8,
        )
        self.user = User.objects.create_user('cli', 'cli@t.com', 'pass1234')

    def test_descuenta_stock_de_variante(self):
        from pedidos.views import _confirmar_pedido
        pedido = Pedido.objects.create(
            usuario=self.user, telefono='+56912345678',
            metodo_envio='retiro_local', subtotal=10000, costo_envio=0, total=10000,
        )
        ItemPedido.objects.create(
            pedido=pedido, producto=self.producto, variante=self.variante,
            cantidad=2, precio_unitario=Decimal('5000'),
            nombre_snapshot=str(self.variante),
        )
        _confirmar_pedido(pedido, mp_payment_id='X', mp_status='approved')
        self.variante.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(self.variante.stock, 6)
        # El stock del producto base no se toca cuando hay variantes
        self.assertEqual(self.producto.stock, 0)


# =========================================================================
# 3. Webhook MP (la pieza mas critica para no perder dinero)
# =========================================================================

class WebhookMpTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela',
            descripcion='Test', precio=Decimal('5000'), stock=10,
        )
        self.user = User.objects.create_user('cli', 'cli@t.com', 'pass1234')
        self.pedido = Pedido.objects.create(
            usuario=self.user, telefono='+56912345678',
            metodo_envio='retiro_local', subtotal=10000, costo_envio=0, total=10000,
        )
        ItemPedido.objects.create(
            pedido=self.pedido, producto=self.producto,
            cantidad=2, precio_unitario=Decimal('5000'),
            nombre_snapshot=self.producto.nombre,
        )

    @patch('pedidos.views.mercadopago.SDK')
    def test_webhook_approved_confirma_pedido(self, mock_sdk):
        # Simulamos respuesta MP: payment con external_reference apuntando a nuestro pedido
        mock_sdk.return_value.payment.return_value.get.return_value = {
            'response': {
                'status': 'approved',
                'external_reference': str(self.pedido.pk),
            }
        }
        resp = self.client.post(
            '/pedidos/webhook/mp/',
            data='{"type": "payment", "data": {"id": "999"}}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'confirmado')
        self.assertEqual(self.producto.stock, 8)

    @patch('pedidos.views.mercadopago.SDK')
    def test_webhook_rechaza_marca_cancelado(self, mock_sdk):
        mock_sdk.return_value.payment.return_value.get.return_value = {
            'response': {
                'status': 'rejected',
                'external_reference': str(self.pedido.pk),
            }
        }
        resp = self.client.post(
            '/pedidos/webhook/mp/',
            data='{"type": "payment", "data": {"id": "999"}}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'cancelado')
        # Stock NO debe haberse tocado
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)

    @patch('pedidos.views.mercadopago.SDK')
    def test_webhook_pedido_inexistente_no_explota(self, mock_sdk):
        mock_sdk.return_value.payment.return_value.get.return_value = {
            'response': {
                'status': 'approved',
                'external_reference': '99999',  # no existe
            }
        }
        resp = self.client.post(
            '/pedidos/webhook/mp/',
            data='{"type": "payment", "data": {"id": "999"}}',
            content_type='application/json',
        )
        # Devolvemos 200 igualmente para que MP no reintente infinitamente
        self.assertEqual(resp.status_code, 200)

    def test_webhook_sin_payment_id_devuelve_200(self):
        """MP a veces manda merchant_order que ignoramos -- no debe romper."""
        resp = self.client.post(
            '/pedidos/webhook/mp/',
            data='{"type": "merchant_order", "data": {"id": "1"}}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

    @override_settings(MP_WEBHOOK_SECRET='clave-secreta-mp')
    def test_webhook_con_secreto_rechaza_firma_invalida(self):
        """Con MP_WEBHOOK_SECRET configurado, firma invalida -> 401 y no confirma."""
        resp = self.client.post(
            '/pedidos/webhook/mp/?data.id=999&type=payment',
            data='{"type": "payment", "data": {"id": "999"}}',
            content_type='application/json',
            HTTP_X_SIGNATURE='ts=123,v1=firmafalsa',
            HTTP_X_REQUEST_ID='req-1',
        )
        self.assertEqual(resp.status_code, 401)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')

    @override_settings(MP_WEBHOOK_SECRET='clave-secreta-mp')
    @patch('pedidos.views.mercadopago.SDK')
    def test_webhook_con_secreto_acepta_firma_valida(self, mock_sdk):
        """Firma HMAC correcta -> procesa el webhook y confirma."""
        import hashlib
        import hmac
        mock_sdk.return_value.payment.return_value.get.return_value = {
            'response': {'status': 'approved', 'external_reference': str(self.pedido.pk)}
        }
        ts, req_id, data_id = '123', 'req-1', '999'
        manifest = 'id:{};request-id:{};ts:{};'.format(data_id, req_id, ts)
        v1 = hmac.new(b'clave-secreta-mp', manifest.encode(), hashlib.sha256).hexdigest()
        resp = self.client.post(
            '/pedidos/webhook/mp/?data.id=999&type=payment',
            data='{"type": "payment", "data": {"id": "999"}}',
            content_type='application/json',
            HTTP_X_SIGNATURE='ts={},v1={}'.format(ts, v1),
            HTTP_X_REQUEST_ID=req_id,
        )
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'confirmado')


# =========================================================================
# 3b. Back URLs de MP: NO deben confirmar/cancelar por parametros de la URL
# =========================================================================

class BackUrlsSegurasTests(TestCase):
    """
    Las back_urls las visita el navegador del cliente con parametros que el
    controla. No deben cambiar el estado del pedido sin verificar contra MP.
    """

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela',
            descripcion='Test', precio=Decimal('5000'), stock=10,
        )
        self.pedido = Pedido.objects.create(
            telefono='+56912345678', metodo_envio='retiro_local',
            subtotal=10000, costo_envio=0, total=10000,
        )
        ItemPedido.objects.create(
            pedido=self.pedido, producto=self.producto,
            cantidad=2, precio_unitario=Decimal('5000'),
            nombre_snapshot=self.producto.nombre,
        )

    def test_pago_exitoso_no_confirma_por_external_reference_falso(self):
        """Visitar /pago/exitoso/ con external_reference/status en la URL NO confirma."""
        resp = self.client.get(
            '/pedidos/pago/exitoso/?external_reference={}&status=approved'.format(self.pedido.pk)
        )
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')
        self.assertEqual(self.producto.stock, 10)  # stock intacto

    @patch('pedidos.views.mercadopago.SDK')
    def test_pago_exitoso_confirma_solo_si_mp_dice_approved(self, mock_sdk):
        """Si el pago verificado en MP esta approved y coincide, se confirma."""
        mock_sdk.return_value.payment.return_value.get.return_value = {
            'response': {'status': 'approved', 'external_reference': str(self.pedido.pk)}
        }
        resp = self.client.get('/pedidos/pago/exitoso/?payment_id=555')
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'confirmado')

    def test_pago_fallido_no_cancela_pedido(self):
        """/pago/fallido/ con external_reference NO debe cancelar el pedido."""
        resp = self.client.get(
            '/pedidos/pago/fallido/?external_reference={}'.format(self.pedido.pk)
        )
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')


# =========================================================================
# 4. Transferencia bancaria
# =========================================================================

class TransferenciaBancariaTests(TestCase):
    """
    Flow de transferencia: pedido se crea pendiente sin descontar stock,
    la duenia lo confirma manual desde gestion, ahi se descuenta y avisa.
    """

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela',
            descripcion='Test', precio=Decimal('5000'), stock=10,
        )
        self.user = User.objects.create_user('cli', 'cli@t.com', 'pass1234')

    def _crear_pedido_transferencia(self):
        p = Pedido.objects.create(
            usuario=self.user, telefono='+56912345678',
            metodo_envio='retiro_local',
            metodo_pago='transferencia',
            subtotal=Decimal('10000'), costo_envio=Decimal('0'), total=Decimal('10000'),
        )
        ItemPedido.objects.create(
            pedido=p, producto=self.producto,
            cantidad=2, precio_unitario=Decimal('5000'),
            nombre_snapshot=self.producto.nombre,
        )
        return p

    def test_pedido_transferencia_no_descuenta_stock_al_crear(self):
        self._crear_pedido_transferencia()
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)  # intacto

    def test_confirmar_transferencia_desde_gestion_descuenta_stock(self):
        pedido = self._crear_pedido_transferencia()
        staff = User.objects.create_user('admin', 'a@t.com', 'pass1234', is_staff=True)
        self.client.force_login(staff)
        resp = self.client.post(
            '/gestion/pedidos/{}/confirmar-transferencia/'.format(pedido.pk)
        )
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(pedido.estado, 'confirmado')
        self.assertEqual(self.producto.stock, 8)

    def test_confirmar_transferencia_solo_si_pendiente(self):
        pedido = self._crear_pedido_transferencia()
        pedido.estado = 'cancelado'
        pedido.save()
        staff = User.objects.create_user('admin', 'a@t.com', 'pass1234', is_staff=True)
        self.client.force_login(staff)
        self.client.post('/gestion/pedidos/{}/confirmar-transferencia/'.format(pedido.pk))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'cancelado')  # no cambia
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)  # no toca stock

    def test_confirmar_no_aplica_a_pedidos_mp(self):
        """No deberia poder marcar un pedido MP como 'confirmado por transferencia'."""
        pedido = self._crear_pedido_transferencia()
        pedido.metodo_pago = 'mercado_pago'
        pedido.save()
        staff = User.objects.create_user('admin', 'a@t.com', 'pass1234', is_staff=True)
        self.client.force_login(staff)
        self.client.post('/gestion/pedidos/{}/confirmar-transferencia/'.format(pedido.pk))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'pendiente')

    def test_cliente_puede_cancelar_pedido_pendiente_propio(self):
        pedido = self._crear_pedido_transferencia()
        self.client.force_login(self.user)
        resp = self.client.post('/pedidos/{}/cancelar/'.format(pedido.pk))
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'cancelado')

    def test_cliente_no_puede_cancelar_pedido_de_otro_usuario(self):
        pedido = self._crear_pedido_transferencia()
        otro = User.objects.create_user('otro', 'otro@t.com', 'pass1234')
        self.client.force_login(otro)
        self.client.post('/pedidos/{}/cancelar/'.format(pedido.pk))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'pendiente')  # no se canceló

    def test_no_se_puede_cancelar_pedido_confirmado(self):
        pedido = self._crear_pedido_transferencia()
        pedido.estado = 'confirmado'
        pedido.save()
        self.client.force_login(self.user)
        self.client.post('/pedidos/{}/cancelar/'.format(pedido.pk))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'confirmado')  # no se cancela

    def test_subir_comprobante_guarda_archivo(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        pedido = self._crear_pedido_transferencia()
        # PNG valido generado con PIL (uploads reales tienen CRC correcto; la
        # vista valida la imagen con Pillow y rechaza archivos corruptos/falsos).
        buf = io.BytesIO()
        Image.new('RGB', (2, 2), (200, 100, 50)).save(buf, format='PNG')
        comprobante = SimpleUploadedFile('compr.png', buf.getvalue(), content_type='image/png')
        self.client.force_login(self.user)
        resp = self.client.post(
            '/pedidos/{}/comprobante/'.format(pedido.pk),
            data={'comprobante': comprobante},
        )
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertTrue(pedido.comprobante_transferencia)


# =========================================================================
# 5. Tracking publico por token (defensa IDOR + invitados)
# =========================================================================

class TrackingPublicoTokenTests(TestCase):
    """
    Verificacion del flow seguro de acceso a pedidos:
    - Detalle por ID (/pedidos/<pk>/) solo para dueno logueado o invitado en
      esta sesion
    - Track por token (/pedidos/track/<token>/) publico pero impredecible
    """

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela',
            descripcion='x', precio=Decimal('5000'), stock=10,
        )
        self.user = User.objects.create_user('cli', 'cli@t.com', 'pass1234')

    def _crear_pedido_invitado(self):
        return Pedido.objects.create(
            usuario=None,
            nombre_cliente='Juan', email_cliente='j@t.com',
            telefono='+56912345678', metodo_envio='retiro_local',
            subtotal=Decimal('5000'), costo_envio=Decimal('0'), total=Decimal('5000'),
        )

    def test_token_publico_se_genera_al_crear(self):
        p = self._crear_pedido_invitado()
        self.assertTrue(p.token_publico)
        # 24 bytes urlsafe_b64 ≈ 32 chars
        self.assertGreaterEqual(len(p.token_publico), 30)

    def test_dos_pedidos_tienen_tokens_distintos(self):
        p1 = self._crear_pedido_invitado()
        p2 = self._crear_pedido_invitado()
        self.assertNotEqual(p1.token_publico, p2.token_publico)

    def test_invitado_sin_sesion_no_ve_detalle_por_id(self):
        """Defensa contra IDOR: alguien que enumera /pedidos/<n>/ no entra."""
        p = self._crear_pedido_invitado()
        resp = self.client.get('/pedidos/{}/'.format(p.pk))
        # Redirige al tracking publico (que requiere token, no ID)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/track/', resp.url)

    def test_track_por_token_correcto_muestra_pedido(self):
        p = self._crear_pedido_invitado()
        resp = self.client.get('/pedidos/track/{}/'.format(p.token_publico))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pedido #{}'.format(p.pk))

    def test_track_token_inexistente_404(self):
        resp = self.client.get('/pedidos/track/token-falso-que-no-existe-1234/')
        self.assertEqual(resp.status_code, 404)

    def test_usuario_logueado_ajeno_no_ve_detalle(self):
        p = Pedido.objects.create(
            usuario=self.user, telefono='+56912345678', metodo_envio='retiro_local',
            subtotal=Decimal('5000'), costo_envio=Decimal('0'), total=Decimal('5000'),
        )
        otro = User.objects.create_user('otro', 'o@t.com', 'pass1234')
        self.client.force_login(otro)
        resp = self.client.get('/pedidos/{}/'.format(p.pk))
        self.assertEqual(resp.status_code, 302)  # redirect a inicio
        self.assertNotIn('/track/', resp.url)

    def test_cancelar_por_token_funciona(self):
        p = self._crear_pedido_invitado()
        resp = self.client.post('/pedidos/track/{}/cancelar/'.format(p.token_publico))
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.estado, 'cancelado')

    def test_cancelar_por_token_no_aplica_si_no_pendiente(self):
        p = self._crear_pedido_invitado()
        p.estado = 'confirmado'
        p.save()
        self.client.post('/pedidos/track/{}/cancelar/'.format(p.token_publico))
        p.refresh_from_db()
        self.assertEqual(p.estado, 'confirmado')


# =========================================================================
# 6. Endpoints por pk protegidos contra enumeracion (IDOR)
# =========================================================================

class EndpointsPorPkAuthTests(TestCase):
    """pago_transferencia y subir_comprobante no deben exponerse por pk."""

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10)
        self.pedido = Pedido.objects.create(
            usuario=None, nombre_cliente='Juan', email_cliente='j@t.com',
            telefono='+56912345678', metodo_envio='retiro_local', metodo_pago='transferencia',
            subtotal=Decimal('5000'), costo_envio=Decimal('0'), total=Decimal('5000'))

    def test_extrano_no_ve_datos_transferencia_por_pk(self):
        resp = self.client.get('/pedidos/{}/transferencia/'.format(self.pedido.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/track/', resp.url)

    def test_extrano_no_puede_subir_comprobante_por_pk(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        img = SimpleUploadedFile('c.png', b'noimg', content_type='image/png')
        resp = self.client.post('/pedidos/{}/comprobante/'.format(self.pedido.pk),
                                data={'comprobante': img})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/track/', resp.url)
        self.pedido.refresh_from_db()
        self.assertFalse(self.pedido.comprobante_transferencia)
