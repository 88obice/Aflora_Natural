"""
Tests criticos del checkout y webhook MP.

Foco: lo que si falla pierdes plata o quedan pedidos en limbo.
- Calculo de costo de envio
- Confirmacion de pedido (descuenta stock, marca confirmado, idempotente)
- Webhook MP
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User

from catalogo.models import Categoria, Producto, Variante
from pedidos.models import Pedido, ItemPedido
from pedidos.envios import (
    calcular_costo_envio,
    COSTO_ENVIO_RM_URBANA,
    COSTO_ENVIO_RM_RESTO,
    COSTO_ENVIO_REGIONES,
    UMBRAL_ENVIO_GRATIS,
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

    def test_envio_gratis_sobre_umbral(self):
        # Subtotal por encima del umbral -> envio gratis (excepto retiro local que ya es gratis)
        c = calcular_costo_envio('envio_domicilio', 'Las Condes', 'Region Metropolitana',
                                 UMBRAL_ENVIO_GRATIS + 1)
        self.assertEqual(c, Decimal('0'))

    def test_envio_gratis_sobre_umbral_otra_region(self):
        c = calcular_costo_envio('envio_domicilio', 'Vina del Mar', 'Region de Valparaiso',
                                 UMBRAL_ENVIO_GRATIS + 1)
        self.assertEqual(c, Decimal('0'))

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
