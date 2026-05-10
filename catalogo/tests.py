"""Tests del catalogo: slug, agotado, resenas, propiedades de Producto."""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from catalogo.models import (
    Categoria, Producto, Variante, Resena, Wishlist, NotificacionStock,
)
from pedidos.models import Pedido, ItemPedido


class SlugTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas Aromaticas')

    def test_categoria_genera_slug(self):
        self.assertEqual(self.cat.slug, 'velas-aromaticas')

    def test_producto_genera_slug(self):
        p = Producto.objects.create(
            categoria=self.cat, nombre='Vela Lavanda 200g',
            descripcion='x', precio=Decimal('5000'),
        )
        self.assertEqual(p.slug, 'vela-lavanda-200g')

    def test_producto_slug_evita_colisiones(self):
        p1 = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x', precio=Decimal('5000'),
        )
        p2 = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x', precio=Decimal('5000'),
        )
        p3 = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x', precio=Decimal('5000'),
        )
        self.assertEqual(p1.slug, 'vela')
        self.assertEqual(p2.slug, 'vela-2')
        self.assertEqual(p3.slug, 'vela-3')


class AgotadoTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')

    def test_producto_sin_stock_es_agotado(self):
        p = Producto.objects.create(
            categoria=self.cat, nombre='V1', descripcion='x',
            precio=Decimal('1000'), stock=0,
        )
        self.assertTrue(p.agotado)

    def test_producto_con_stock_no_es_agotado(self):
        p = Producto.objects.create(
            categoria=self.cat, nombre='V2', descripcion='x',
            precio=Decimal('1000'), stock=5,
        )
        self.assertFalse(p.agotado)

    def test_producto_con_variantes_agotadas_es_agotado(self):
        """Si tiene variantes, su 'agotado' depende SOLO de las variantes."""
        p = Producto.objects.create(
            categoria=self.cat, nombre='V3', descripcion='x',
            precio=Decimal('1000'), stock=100,  # stock base alto
        )
        Variante.objects.create(producto=p, nombre='100g', precio=Decimal('1000'), stock=0)
        Variante.objects.create(producto=p, nombre='200g', precio=Decimal('2000'), stock=0)
        self.assertTrue(p.agotado)

    def test_producto_con_alguna_variante_disponible_no_es_agotado(self):
        p = Producto.objects.create(
            categoria=self.cat, nombre='V4', descripcion='x',
            precio=Decimal('1000'), stock=0,
        )
        Variante.objects.create(producto=p, nombre='100g', precio=Decimal('1000'), stock=0)
        Variante.objects.create(producto=p, nombre='200g', precio=Decimal('2000'), stock=3)
        self.assertFalse(p.agotado)


class PrecioDesdeTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')

    def test_sin_variantes_es_precio_base(self):
        p = Producto.objects.create(
            categoria=self.cat, nombre='V', descripcion='x', precio=Decimal('5000'),
        )
        self.assertEqual(p.precio_desde, Decimal('5000'))

    def test_con_variantes_es_la_mas_barata(self):
        p = Producto.objects.create(
            categoria=self.cat, nombre='V', descripcion='x', precio=Decimal('99999'),
        )
        Variante.objects.create(producto=p, nombre='200g', precio=Decimal('8000'), stock=1)
        Variante.objects.create(producto=p, nombre='100g', precio=Decimal('5000'), stock=1)
        self.assertEqual(p.precio_desde, Decimal('5000'))


class RatingTests(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='V', descripcion='x', precio=Decimal('1000'),
        )
        self.u1 = User.objects.create_user('u1', 'u1@t.com', 'pass1234')
        self.u2 = User.objects.create_user('u2', 'u2@t.com', 'pass1234')
        self.u3 = User.objects.create_user('u3', 'u3@t.com', 'pass1234')

    def test_rating_promedio_solo_aprobadas(self):
        Resena.objects.create(producto=self.producto, usuario=self.u1,
                              rating=5, comentario='excelente!!', aprobada=True)
        Resena.objects.create(producto=self.producto, usuario=self.u2,
                              rating=3, comentario='regularcito', aprobada=True)
        Resena.objects.create(producto=self.producto, usuario=self.u3,
                              rating=1, comentario='no me gusto', aprobada=False)  # no cuenta
        self.assertEqual(self.producto.rating_promedio, 4)
        self.assertEqual(self.producto.total_resenas, 2)

    def test_rating_sin_resenas_es_none(self):
        self.assertIsNone(self.producto.rating_promedio)


class WishlistUniqueTests(TestCase):
    def test_no_se_puede_duplicar(self):
        cat = Categoria.objects.create(nombre='Velas')
        p = Producto.objects.create(categoria=cat, nombre='V', descripcion='x', precio=Decimal('1000'))
        u = User.objects.create_user('u', 'u@t.com', 'pass1234')
        Wishlist.objects.create(usuario=u, producto=p)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Wishlist.objects.create(usuario=u, producto=p)


class NotifyStockSignalTests(TestCase):
    """Cuando reponen stock, los emails capturados deben dispararse automaticamente."""

    def setUp(self):
        from django.core import mail
        mail.outbox = []
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela X', descripcion='x',
            precio=Decimal('5000'), stock=0,
        )
        # 2 clientes esperando aviso
        NotificacionStock.objects.create(producto=self.producto, email='ana@test.com')
        NotificacionStock.objects.create(producto=self.producto, email='beti@test.com')

    def test_stock_de_cero_a_positivo_envia_emails(self):
        from django.core import mail
        self.producto.stock = 5
        self.producto.save()
        # Deberian haberse mandado 2 emails (uno a cada cliente)
        self.assertEqual(len(mail.outbox), 2)
        destinatarios = sorted([m.to[0] for m in mail.outbox])
        self.assertEqual(destinatarios, ['ana@test.com', 'beti@test.com'])
        # Y deben quedar marcadas como notificadas
        self.assertEqual(NotificacionStock.objects.filter(notificado=True).count(), 2)

    def test_stock_no_cambia_no_envia(self):
        """Si guardamos sin cambiar stock, no se manda nada."""
        from django.core import mail
        self.producto.descripcion = 'Cambio descripcion solo'
        self.producto.save()
        self.assertEqual(len(mail.outbox), 0)

    def test_segunda_vez_no_envia_de_nuevo(self):
        """Idempotente: si reponen, mandan, despues si stock vuelve a 0 y a >0, no remandan."""
        from django.core import mail
        self.producto.stock = 5
        self.producto.save()
        self.assertEqual(len(mail.outbox), 2)
        # Reset outbox y simular ciclo: agotar y reponer
        mail.outbox = []
        self.producto.stock = 0
        self.producto.save()
        self.producto.stock = 3
        self.producto.save()
        # Las notificaciones ya estan marcadas como notificado=True, asi que no se reenvian
        self.assertEqual(len(mail.outbox), 0)

    def test_producto_con_variantes_no_dispara_signal_de_producto(self):
        """Si el producto tiene variantes, su stock base no es lo que se vende -- no notificar."""
        from django.core import mail
        Variante.objects.create(producto=self.producto, nombre='100g',
                                precio=Decimal('5000'), stock=0)
        mail.outbox = []
        self.producto.stock = 5  # cambia el stock base
        self.producto.save()
        # No se manda nada porque el cliente compra la variante, no el producto base
        self.assertEqual(len(mail.outbox), 0)

    def test_variante_de_cero_a_positivo_envia_emails(self):
        """Si el producto tiene variantes, reponer la variante si dispara el aviso."""
        from django.core import mail
        v = Variante.objects.create(producto=self.producto, nombre='100g',
                                    precio=Decimal('5000'), stock=0)
        mail.outbox = []
        v.stock = 3
        v.save()
        self.assertEqual(len(mail.outbox), 2)


class NewsletterTests(TestCase):
    def setUp(self):
        from django.core import mail
        mail.outbox = []
        from catalogo.models import SuscriptorNewsletter, CampanaNewsletter
        self.s1 = SuscriptorNewsletter.objects.create(email='ana@test.com')
        self.s2 = SuscriptorNewsletter.objects.create(email='beti@test.com')
        self.s3 = SuscriptorNewsletter.objects.create(email='inactiva@test.com', activo=False)
        self.campana = CampanaNewsletter.objects.create(
            asunto='Hola',
            cuerpo='Hola {email}, tenemos novedades.',
        )

    def test_token_baja_se_genera_automatico(self):
        self.assertTrue(self.s1.token_baja)
        self.assertNotEqual(self.s1.token_baja, self.s2.token_baja)

    def test_envio_real_solo_a_activos(self):
        from django.core import mail
        from catalogo.newsletter_sender import enviar_campana
        res = enviar_campana(self.campana, 'http://test.local')
        # solo 2 activos -> 2 emails
        self.assertEqual(res['enviados'], 2)
        self.assertEqual(len(mail.outbox), 2)
        destinatarios = sorted([m.to[0] for m in mail.outbox])
        self.assertEqual(destinatarios, ['ana@test.com', 'beti@test.com'])

    def test_envio_marca_estado_y_metricas(self):
        from catalogo.newsletter_sender import enviar_campana
        enviar_campana(self.campana, 'http://test.local')
        self.campana.refresh_from_db()
        self.assertEqual(self.campana.estado, 'enviada')
        self.assertEqual(self.campana.total_destinatarios, 2)
        self.assertEqual(self.campana.total_enviados, 2)

    def test_email_incluye_link_de_baja(self):
        from django.core import mail
        from catalogo.newsletter_sender import enviar_campana
        enviar_campana(self.campana, 'http://test.local')
        cuerpo = mail.outbox[0].body
        self.assertIn('newsletter/baja/', cuerpo)
        self.assertIn('Aflora Natural', cuerpo)
        # variable {email} reemplazada
        self.assertIn(mail.outbox[0].to[0], cuerpo)

    def test_dry_email_solo_a_uno(self):
        from django.core import mail
        from catalogo.newsletter_sender import enviar_campana
        res = enviar_campana(self.campana, 'http://test.local', dry_email='dev@test.com')
        self.assertEqual(res['enviados'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['dev@test.com'])
        self.assertTrue(mail.outbox[0].subject.startswith('[PRUEBA]'))

    def test_unsubscribe_marca_inactivo(self):
        from django.test import Client
        from catalogo.models import SuscriptorNewsletter
        c = Client()
        resp = c.get(f'/newsletter/baja/{self.s1.token_baja}/')
        self.assertEqual(resp.status_code, 200)
        self.s1.refresh_from_db()
        self.assertFalse(self.s1.activo)

    def test_unsubscribe_token_invalido(self):
        from django.test import Client
        c = Client()
        resp = c.get('/newsletter/baja/token-falso-xyz/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'no es correcto')
