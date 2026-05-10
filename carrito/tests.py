"""Tests del carrito: agregar, variantes, actualizar cantidad."""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from catalogo.models import Categoria, Producto, Variante
from carrito.models import Carrito, ItemCarrito


class CarritoSimpleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10,
        )

    def test_agregar_producto_simple_invitado(self):
        url = reverse('carrito:agregar', args=[self.producto.pk])
        resp = self.client.post(url, {'cantidad': '2'})
        self.assertEqual(resp.status_code, 302)  # redirect a carrito
        self.assertEqual(ItemCarrito.objects.count(), 1)
        item = ItemCarrito.objects.first()
        self.assertEqual(item.cantidad, 2)
        self.assertEqual(item.subtotal(), Decimal('10000'))

    def test_agregar_dos_veces_el_mismo_suma_cantidad(self):
        url = reverse('carrito:agregar', args=[self.producto.pk])
        self.client.post(url, {'cantidad': '2'})
        self.client.post(url, {'cantidad': '3'})
        self.assertEqual(ItemCarrito.objects.count(), 1)
        self.assertEqual(ItemCarrito.objects.first().cantidad, 5)

    def test_no_puede_exceder_stock(self):
        url = reverse('carrito:agregar', args=[self.producto.pk])
        # Pedimos 100, hay 10 -> se cap a 10
        self.client.post(url, {'cantidad': '100'})
        item = ItemCarrito.objects.first()
        self.assertEqual(item.cantidad, 10)


class CarritoConVariantesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=0,
        )
        self.var100 = Variante.objects.create(
            producto=self.producto, nombre='100g',
            precio=Decimal('5000'), stock=10,
        )
        self.var200 = Variante.objects.create(
            producto=self.producto, nombre='200g',
            precio=Decimal('8000'), stock=5,
        )

    def test_agregar_sin_variante_falla_si_producto_tiene_variantes(self):
        url = reverse('carrito:agregar', args=[self.producto.pk])
        self.client.post(url, {'cantidad': '1'})
        # No se crea item -- redirect al detalle con error
        self.assertEqual(ItemCarrito.objects.count(), 0)

    def test_agregar_con_variante_funciona(self):
        url = reverse('carrito:agregar', args=[self.producto.pk])
        self.client.post(url, {'cantidad': '2', 'variante': str(self.var100.pk)})
        self.assertEqual(ItemCarrito.objects.count(), 1)
        item = ItemCarrito.objects.first()
        self.assertEqual(item.variante, self.var100)
        self.assertEqual(item.precio_unitario, Decimal('5000'))

    def test_dos_variantes_distintas_son_dos_items(self):
        url = reverse('carrito:agregar', args=[self.producto.pk])
        self.client.post(url, {'cantidad': '1', 'variante': str(self.var100.pk)})
        self.client.post(url, {'cantidad': '1', 'variante': str(self.var200.pk)})
        self.assertEqual(ItemCarrito.objects.count(), 2)


class ActualizarCantidadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='V', descripcion='x',
            precio=Decimal('1000'), stock=10,
        )
        self.client.post(reverse('carrito:agregar', args=[self.producto.pk]), {'cantidad': '3'})
        self.item = ItemCarrito.objects.first()

    def test_actualizar_a_cantidad_valida(self):
        resp = self.client.post(
            reverse('carrito:actualizar', args=[self.item.pk]),
            {'cantidad': '5'},
        )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.cantidad, 5)

    def test_actualizar_a_cero_elimina(self):
        self.client.post(
            reverse('carrito:actualizar', args=[self.item.pk]),
            {'cantidad': '0'},
        )
        self.assertEqual(ItemCarrito.objects.count(), 0)

    def test_actualizar_no_puede_exceder_stock(self):
        self.client.post(
            reverse('carrito:actualizar', args=[self.item.pk]),
            {'cantidad': '999'},
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.cantidad, 10)
