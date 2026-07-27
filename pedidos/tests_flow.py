"""
Tests de la integracion con Flow (la pasarela principal).

Flow es por donde entra la plata, y nada de esto se habia ejercitado nunca:
ni en tests ni en produccion. Lo que se cubre:

- La firma HMAC-SHA256 que Flow exige en cada request (si se arma mal, Flow
  rechaza TODO y no se puede cobrar).
- crear_pago / get_status contra la API (con requests mockeado: los tests no
  salen a internet).
- El webhook, que es la unica fuente de verdad de un pago.
- El commerceOrder con formato "id-timestamp" y su parseo de vuelta a pedido.
- El patron "dormido": sin llaves, Flow no aparece en el checkout.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from catalogo.models import Categoria, Producto
from pedidos import flow as flow_api
from pedidos.models import Pedido, ItemPedido


LLAVES_DE_PRUEBA = dict(
    FLOW_API_KEY='llave-publica',
    FLOW_SECRET_KEY='secreto-de-prueba',
    FLOW_API_URL='https://sandbox.flow.cl/api',
)


# =========================================================================
# 1. Firma HMAC — si esto se rompe, Flow rechaza todo
# =========================================================================

@override_settings(**LLAVES_DE_PRUEBA)
class FirmaFlowTests(TestCase):

    def test_firma_conocida(self):
        """
        Valor de referencia calculado aparte. Si alguien toca _firmar (el
        orden, el separador, el algoritmo), este test lo caza aunque el
        resto siga "funcionando" en apariencia.
        """
        params = {
            'apiKey': 'llave-publica',
            'commerceOrder': '12-1700000000',
            'amount': 19990,
        }
        self.assertEqual(
            flow_api._firmar(params),
            'a3ae3e06cae2a0bc7491f0f22601ff68d4342e246c25a5ad16ed8c3cf7541077',
        )

    def test_los_parametros_se_ordenan_alfabeticamente(self):
        """Flow exige orden por nombre, no el orden en que se escribieron."""
        uno = {'apiKey': 'k', 'amount': 100, 'subject': 'x'}
        otro = {'subject': 'x', 'amount': 100, 'apiKey': 'k'}
        self.assertEqual(flow_api._firmar(uno), flow_api._firmar(otro))

    def test_cambiar_un_valor_cambia_la_firma(self):
        base = {'apiKey': 'k', 'amount': 100}
        distinto = {'apiKey': 'k', 'amount': 101}
        self.assertNotEqual(flow_api._firmar(base), flow_api._firmar(distinto))

    @override_settings(FLOW_SECRET_KEY='otro-secreto')
    def test_cambiar_el_secreto_cambia_la_firma(self):
        params = {'apiKey': 'k', 'amount': 100}
        firma_con_otro_secreto = flow_api._firmar(params)
        with override_settings(**LLAVES_DE_PRUEBA):
            firma_original = flow_api._firmar(params)
        self.assertNotEqual(firma_original, firma_con_otro_secreto)

    def test_con_firma_agrega_s_sin_tocar_el_resto(self):
        params = {'apiKey': 'k', 'amount': 100}
        firmado = flow_api._con_firma(params)
        self.assertEqual(firmado['s'], flow_api._firmar(params))
        self.assertNotIn('s', params)  # no muta el original
        self.assertEqual(firmado['amount'], 100)


# =========================================================================
# 2. Patron "dormido": sin llaves, Flow no existe
# =========================================================================

class FlowConfiguradoTests(TestCase):

    @override_settings(**LLAVES_DE_PRUEBA)
    def test_con_ambas_llaves_esta_configurado(self):
        self.assertTrue(flow_api.flow_configurado())

    @override_settings(FLOW_API_KEY='', FLOW_SECRET_KEY='secreto')
    def test_sin_api_key_no_esta_configurado(self):
        self.assertFalse(flow_api.flow_configurado())

    @override_settings(FLOW_API_KEY='llave', FLOW_SECRET_KEY='')
    def test_sin_secret_key_no_esta_configurado(self):
        self.assertFalse(flow_api.flow_configurado())


# =========================================================================
# 3. crear_pago contra la API
# =========================================================================

@override_settings(**LLAVES_DE_PRUEBA)
class CrearPagoFlowTests(TestCase):

    def _respuesta(self, status_code=200, json_data=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data if json_data is not None else {}
        resp.text = 'cuerpo de error'
        return resp

    @patch('pedidos.flow.requests.post')
    def test_devuelve_la_url_de_checkout_con_el_token(self, mock_post):
        mock_post.return_value = self._respuesta(json_data={
            'token': 'tok-abc', 'url': 'https://sandbox.flow.cl/app/web/pay.php',
            'flowOrder': 555,
        })
        res = flow_api.crear_pago(
            commerce_order='12-1700000000', subject='Pedido #12', amount=19990,
            email='cli@t.com', url_confirmation='https://x.cl/webhook/',
            url_return='https://x.cl/retorno/')
        self.assertEqual(
            res['redirect_url'],
            'https://sandbox.flow.cl/app/web/pay.php?token=tok-abc')
        self.assertEqual(res['token'], 'tok-abc')
        self.assertEqual(res['flow_order'], '555')

    @patch('pedidos.flow.requests.post')
    def test_manda_los_parametros_que_flow_espera(self, mock_post):
        mock_post.return_value = self._respuesta(json_data={
            'token': 't', 'url': 'https://sandbox.flow.cl/pay'})
        flow_api.crear_pago(
            commerce_order='12-1700000000', subject='Pedido #12',
            amount=Decimal('19990'), email='cli@t.com',
            url_confirmation='https://x.cl/webhook/', url_return='https://x.cl/retorno/')

        cuerpo = mock_post.call_args.kwargs['data']
        self.assertIn('currency=CLP', cuerpo)
        self.assertIn('apiKey=llave-publica', cuerpo)
        self.assertIn('s=', cuerpo)  # la firma viaja
        # CLP no admite decimales: tiene que ir entero, no "19990.00"
        self.assertIn('amount=19990', cuerpo)
        self.assertNotIn('19990.00', cuerpo)

    @patch('pedidos.flow.requests.post')
    def test_error_http_lanza_flowerror(self, mock_post):
        mock_post.return_value = self._respuesta(status_code=401)
        with self.assertRaises(flow_api.FlowError):
            flow_api.crear_pago(
                commerce_order='1-1', subject='x', amount=1000,
                email='c@t.com', url_confirmation='u', url_return='u')

    @patch('pedidos.flow.requests.post')
    def test_respuesta_sin_token_lanza_flowerror(self, mock_post):
        mock_post.return_value = self._respuesta(json_data={'error': 'algo'})
        with self.assertRaises(flow_api.FlowError):
            flow_api.crear_pago(
                commerce_order='1-1', subject='x', amount=1000,
                email='c@t.com', url_confirmation='u', url_return='u')

    @patch('pedidos.flow.requests.post', side_effect=flow_api.requests.RequestException('sin red'))
    def test_caida_de_red_lanza_flowerror(self, _mock_post):
        with self.assertRaises(flow_api.FlowError):
            flow_api.crear_pago(
                commerce_order='1-1', subject='x', amount=1000,
                email='c@t.com', url_confirmation='u', url_return='u')


# =========================================================================
# 4. get_status
# =========================================================================

@override_settings(**LLAVES_DE_PRUEBA)
class GetStatusFlowTests(TestCase):

    @patch('pedidos.flow.requests.get')
    def test_consulta_firmada_y_devuelve_el_json(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'status': 2, 'commerceOrder': '12-1700000000'}
        mock_get.return_value = resp

        data = flow_api.get_status('tok-abc')
        self.assertEqual(data['status'], 2)
        url = mock_get.call_args.args[0]
        self.assertIn('payment/getStatus', url)
        self.assertIn('token=tok-abc', url)
        self.assertIn('s=', url)

    @patch('pedidos.flow.requests.get')
    def test_error_http_lanza_flowerror(self, mock_get):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = 'boom'
        mock_get.return_value = resp
        with self.assertRaises(flow_api.FlowError):
            flow_api.get_status('tok-abc')


# =========================================================================
# 5. Mapeo del medio de pago informado por Flow
# =========================================================================

class MediaFlowTests(TestCase):

    def test_mapea_los_medios_conocidos(self):
        casos = {
            'Webpay': 'webpay',
            'webpay plus': 'webpay',
            'MACH': 'mach',
            'Servipag': 'servipag',
            'transferencia bancaria': 'transferencia',
        }
        for media, esperado in casos.items():
            with self.subTest(media=media):
                self.assertEqual(flow_api.media_a_medio_detalle(media), esperado)

    def test_medio_desconocido_cae_en_otro(self):
        self.assertEqual(flow_api.media_a_medio_detalle('CriptoLunar'), 'otro')

    def test_sin_media_devuelve_vacio(self):
        self.assertEqual(flow_api.media_a_medio_detalle(None), '')
        self.assertEqual(flow_api.media_a_medio_detalle(''), '')


# =========================================================================
# 6. Webhook de Flow: la unica fuente de verdad del pago
# =========================================================================

@override_settings(**LLAVES_DE_PRUEBA)
class WebhookFlowTests(TestCase):

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10)
        self.pedido = Pedido.objects.create(
            usuario=None, nombre_cliente='Juan', email_cliente='juan@t.com',
            telefono='+56912345678', metodo_envio='retiro_local',
            metodo_pago='flow', flow_token='tok-abc',
            subtotal=Decimal('10000'), costo_envio=Decimal('0'),
            total=Decimal('10000'))
        ItemPedido.objects.create(
            pedido=self.pedido, producto=self.producto, cantidad=2,
            precio_unitario=Decimal('5000'), nombre_snapshot='Vela')

    def _webhook(self, token='tok-abc'):
        return self.client.post('/pedidos/webhook/flow/', data={'token': token})

    @patch('pedidos.flow.get_status')
    def test_pago_aprobado_confirma_y_descuenta_stock(self, mock_status):
        mock_status.return_value = {
            'status': flow_api.STATUS_PAGADO,
            'commerceOrder': '{}-1700000000'.format(self.pedido.pk),
            'paymentData': {'media': 'Webpay'},
        }
        resp = self._webhook()
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'confirmado')
        self.assertEqual(self.pedido.estado_pago, 'pagado')
        self.assertEqual(self.pedido.medio_pago_detalle, 'webpay')
        self.assertEqual(self.producto.stock, 8)

    @patch('pedidos.flow.get_status')
    def test_webhook_repetido_no_descuenta_dos_veces(self, mock_status):
        """Flow puede reintentar la notificacion."""
        mock_status.return_value = {
            'status': flow_api.STATUS_PAGADO,
            'commerceOrder': '{}-1700000000'.format(self.pedido.pk),
            'paymentData': {'media': 'Webpay'},
        }
        self._webhook()
        self._webhook()
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)

    @patch('pedidos.flow.get_status')
    def test_pago_rechazado_cancela_el_pedido(self, mock_status):
        mock_status.return_value = {
            'status': flow_api.STATUS_RECHAZADO,
            'commerceOrder': '{}-1700000000'.format(self.pedido.pk),
        }
        self._webhook()
        self.pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'cancelado')
        self.assertEqual(self.pedido.estado_pago, 'rechazado')
        self.assertEqual(self.producto.stock, 10)  # no se descuenta

    @patch('pedidos.flow.get_status')
    def test_pago_anulado_cancela_el_pedido(self, mock_status):
        mock_status.return_value = {
            'status': flow_api.STATUS_ANULADO,
            'commerceOrder': '{}-1700000000'.format(self.pedido.pk),
        }
        self._webhook()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'cancelado')

    @patch('pedidos.flow.get_status')
    def test_pago_pendiente_no_toca_el_pedido(self, mock_status):
        mock_status.return_value = {
            'status': flow_api.STATUS_PENDIENTE,
            'commerceOrder': '{}-1700000000'.format(self.pedido.pk),
        }
        self._webhook()
        self.pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')
        self.assertEqual(self.producto.stock, 10)

    @patch('pedidos.flow.get_status')
    def test_recupera_el_pedido_por_commerceorder_si_el_token_no_coincide(self, mock_status):
        """
        Respaldo del mapeo: si el token guardado no matchea (reintento con
        otro token), el pedido se recupera del commerceOrder "id-timestamp".
        """
        self.pedido.flow_token = 'otro-token-viejo'
        self.pedido.save(update_fields=['flow_token'])
        mock_status.return_value = {
            'status': flow_api.STATUS_PAGADO,
            'commerceOrder': '{}-1700000000'.format(self.pedido.pk),
            'paymentData': {'media': 'MACH'},
        }
        self._webhook(token='token-nuevo-no-guardado')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'confirmado')
        self.assertEqual(self.pedido.medio_pago_detalle, 'mach')

    @patch('pedidos.flow.get_status')
    def test_commerceorder_desconocido_no_rompe(self, mock_status):
        mock_status.return_value = {
            'status': flow_api.STATUS_PAGADO, 'commerceOrder': '99999-1700000000'}
        resp = self._webhook(token='token-huerfano')
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')

    @patch('pedidos.flow.get_status', side_effect=flow_api.FlowError('sin red'))
    def test_si_falla_la_consulta_no_confirma_nada(self, _mock_status):
        """Ante la duda, el pedido NO se confirma."""
        resp = self._webhook()
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')

    def test_webhook_sin_token_responde_200(self):
        resp = self.client.post('/pedidos/webhook/flow/', data={})
        self.assertEqual(resp.status_code, 200)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')

    @patch('pedidos.flow.get_status')
    def test_el_webhook_no_exige_csrf(self, mock_status):
        """Flow postea server-to-server: no hay token CSRF que mandar."""
        mock_status.return_value = {
            'status': flow_api.STATUS_PENDIENTE,
            'commerceOrder': '{}-1'.format(self.pedido.pk)}
        from django.test import Client
        resp = Client(enforce_csrf_checks=True).post(
            '/pedidos/webhook/flow/', data={'token': 'tok-abc'})
        self.assertEqual(resp.status_code, 200)


# =========================================================================
# 7. URL de retorno (lo que ve el cliente al volver de Flow)
# =========================================================================

@override_settings(**LLAVES_DE_PRUEBA)
class RetornoFlowTests(TestCase):

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10)
        self.pedido = Pedido.objects.create(
            usuario=None, nombre_cliente='Juan', email_cliente='juan@t.com',
            telefono='+56912345678', metodo_envio='retiro_local',
            metodo_pago='flow', flow_token='tok-abc',
            subtotal=Decimal('10000'), costo_envio=Decimal('0'),
            total=Decimal('10000'))
        ItemPedido.objects.create(
            pedido=self.pedido, producto=self.producto, cantidad=1,
            precio_unitario=Decimal('5000'), nombre_snapshot='Vela')

    @patch('pedidos.flow.get_status')
    def test_pago_ok_muestra_confirmacion(self, mock_status):
        mock_status.return_value = {
            'status': flow_api.STATUS_PAGADO,
            'commerceOrder': '{}-1'.format(self.pedido.pk),
            'paymentData': {'media': 'Webpay'},
        }
        resp = self.client.post('/pedidos/pago/flow/retorno/', data={'token': 'tok-abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pago recibido')

    @patch('pedidos.flow.get_status')
    def test_pago_rechazado_muestra_el_error(self, mock_status):
        mock_status.return_value = {
            'status': flow_api.STATUS_RECHAZADO,
            'commerceOrder': '{}-1'.format(self.pedido.pk)}
        resp = self.client.post('/pedidos/pago/flow/retorno/', data={'token': 'tok-abc'})
        self.assertContains(resp, 'no pudo procesarse')

    def test_sin_token_muestra_en_proceso(self):
        resp = self.client.post('/pedidos/pago/flow/retorno/', data={})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Estamos confirmando')

    @patch('pedidos.flow.get_status')
    def test_el_retorno_no_es_la_fuente_de_verdad(self, mock_status):
        """
        El cliente podria volver con un token ajeno. Lo que decide es lo que
        responde getStatus, no el parametro del navegador: si Flow dice
        pendiente, el pedido NO se confirma por mas que el cliente vuelva.
        """
        mock_status.return_value = {
            'status': flow_api.STATUS_PENDIENTE,
            'commerceOrder': '{}-1'.format(self.pedido.pk)}
        self.client.post('/pedidos/pago/flow/retorno/', data={'token': 'tok-abc'})
        self.pedido.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')
        self.assertEqual(self.producto.stock, 10)


# =========================================================================
# 8. Checkout: eleccion de pasarela segun haya llaves o no
# =========================================================================

class CheckoutEligePasarelaTests(TestCase):

    def setUp(self):
        from carrito.models import Carrito, ItemCarrito
        from django.contrib.auth.models import User
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10)
        self.user = User.objects.create_user('ana@t.com', 'ana@t.com', 'clave123456')
        self.client.force_login(self.user)
        carrito = Carrito.objects.create(usuario=self.user)
        ItemCarrito.objects.create(carrito=carrito, producto=self.producto, cantidad=1)

    def _checkout(self, **extra):
        data = {'metodo_envio': 'retiro_local', 'telefono': '+56912345678'}
        data.update(extra)
        return self.client.post('/pedidos/crear/', data=data)

    @override_settings(**LLAVES_DE_PRUEBA)
    @patch('pedidos.views._crear_pago_flow', return_value='https://sandbox.flow.cl/pay?token=t')
    def test_con_llaves_el_pedido_va_por_flow(self, mock_crear):
        resp = self._checkout()
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.metodo_pago, 'flow')
        mock_crear.assert_called_once()
        self.assertEqual(resp.status_code, 302)
        self.assertIn('flow.cl', resp.url)

    @override_settings(FLOW_API_KEY='', FLOW_SECRET_KEY='')
    @patch('pedidos.views._crear_preferencia_mp', return_value='')
    def test_sin_llaves_cae_a_mercado_pago(self, _mock_mp):
        """El patron dormido: sin llaves, Flow no se ofrece."""
        self._checkout()
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.metodo_pago, 'mercado_pago')

    @override_settings(FLOW_API_KEY='', FLOW_SECRET_KEY='')
    @patch('pedidos.views._crear_preferencia_mp', return_value='')
    def test_forzar_flow_por_POST_sin_llaves_no_cuela(self, _mock_mp):
        """Aunque manden metodo_pago=flow a mano, sin llaves cae a MP."""
        self._checkout(metodo_pago='flow')
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.metodo_pago, 'mercado_pago')

    @override_settings(**LLAVES_DE_PRUEBA)
    @patch('pedidos.views._crear_pago_flow', side_effect=flow_api.FlowError('Flow caido'))
    def test_si_flow_falla_el_pedido_igual_queda_guardado(self, _mock_crear):
        """
        Si Flow no responde, no se pierde el pedido: queda pendiente y el
        cliente ve un aviso de que lo van a contactar.
        """
        resp = self._checkout()
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.estado, 'pendiente')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/pedidos/{}/'.format(pedido.pk), resp.url)


# =========================================================================
# 9. commerceOrder: unico por intento, y mapeable de vuelta al pedido
# =========================================================================

@override_settings(**LLAVES_DE_PRUEBA)
class CommerceOrderTests(TestCase):

    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10)
        self.pedido = Pedido.objects.create(
            usuario=None, nombre_cliente='Juan', email_cliente='juan@t.com',
            telefono='+56912345678', metodo_envio='retiro_local',
            metodo_pago='flow', subtotal=Decimal('5000'),
            costo_envio=Decimal('0'), total=Decimal('5000'))

    @patch('pedidos.flow.crear_pago')
    def test_lleva_el_id_del_pedido_y_guarda_token_y_orden(self, mock_crear):
        from django.test import RequestFactory
        from pedidos.views import _crear_pago_flow
        mock_crear.return_value = {
            'redirect_url': 'https://sandbox.flow.cl/pay?token=t',
            'token': 'tok-1', 'flow_order': '777'}

        request = RequestFactory().post('/pedidos/crear/')
        _crear_pago_flow(self.pedido, request)

        commerce_order = mock_crear.call_args.kwargs['commerce_order']
        # Formato "id-timestamp": el id se recupera con split('-')[0]
        self.assertEqual(commerce_order.split('-')[0], str(self.pedido.pk))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.flow_token, 'tok-1')
        self.assertEqual(self.pedido.flow_order, '777')

    @patch('pedidos.flow.crear_pago')
    def test_dos_intentos_generan_commerceorder_distintos(self, mock_crear):
        """
        Flow exige commerceOrder unico. Si el cliente reintenta el pago del
        mismo pedido, no puede chocar con el intento anterior.
        """
        from django.test import RequestFactory
        from pedidos.views import _crear_pago_flow
        mock_crear.return_value = {
            'redirect_url': 'x', 'token': 't', 'flow_order': '1'}
        request = RequestFactory().post('/pedidos/crear/')

        with patch('time.time', return_value=1700000000):
            _crear_pago_flow(self.pedido, request)
            primero = mock_crear.call_args.kwargs['commerce_order']
        with patch('time.time', return_value=1700000099):
            _crear_pago_flow(self.pedido, request)
            segundo = mock_crear.call_args.kwargs['commerce_order']

        self.assertNotEqual(primero, segundo)
        self.assertEqual(primero.split('-')[0], segundo.split('-')[0])
