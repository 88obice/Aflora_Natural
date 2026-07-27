"""
Tests de cuentas de cliente.

Foco: la puerta de entrada al sitio y los datos personales que hay detras.
- Registro (username = email, anti-spam: honeypot + rate limit)
- Login por email y limite de intentos (fuerza bruta)
- Fusion del carrito anonimo al iniciar sesion
- Direcciones: que nadie toque las de otro (IDOR)
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from aflora_natural.antispam import HONEYPOT_FIELD
from carrito.models import Carrito, ItemCarrito
from catalogo.models import Categoria, Producto
from usuarios.models import Direccion


class _BaseUsuariosTest(TestCase):
    """
    El rate limiting guarda los contadores en el cache (LocMemCache), que vive
    en el proceso y NO se limpia entre tests. Sin este clear(), los intentos
    de un test se suman a los del siguiente y el orden de ejecucion cambia el
    resultado.
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()


# =========================================================================
# 1. Registro
# =========================================================================

class RegistroTests(_BaseUsuariosTest):

    def _datos(self, **extra):
        datos = {
            'nombre': 'Ana',
            'apellido': 'Perez',
            'email': 'ana@test.com',
            'password1': 'unaClaveLarga123',
            'password2': 'unaClaveLarga123',
        }
        datos.update(extra)
        return datos

    def test_registro_crea_la_cuenta_con_username_igual_al_email(self):
        """El cliente nunca ve un 'usuario': su identidad es el correo."""
        resp = self.client.post(reverse('usuarios:registro'), data=self._datos())
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(email='ana@test.com')
        self.assertEqual(user.username, 'ana@test.com')
        self.assertEqual(user.first_name, 'Ana')
        self.assertEqual(user.last_name, 'Perez')

    def test_registro_deja_la_sesion_iniciada(self):
        self.client.post(reverse('usuarios:registro'), data=self._datos())
        resp = self.client.get(reverse('usuarios:perfil'))
        self.assertEqual(resp.status_code, 200)

    def test_email_se_normaliza_a_minusculas(self):
        self.client.post(reverse('usuarios:registro'),
                         data=self._datos(email='ANA@TEST.COM'))
        self.assertTrue(User.objects.filter(email='ana@test.com').exists())

    def test_no_permite_dos_cuentas_con_el_mismo_email(self):
        self.client.post(reverse('usuarios:registro'), data=self._datos())
        self.client.logout()
        self.client.post(reverse('usuarios:registro'),
                         data=self._datos(nombre='Otra'))
        self.assertEqual(User.objects.filter(email='ana@test.com').count(), 1)

    def test_email_duplicado_no_distingue_mayusculas(self):
        self.client.post(reverse('usuarios:registro'), data=self._datos())
        self.client.logout()
        self.client.post(reverse('usuarios:registro'),
                         data=self._datos(email='ANA@TEST.COM'))
        self.assertEqual(User.objects.count(), 1)

    def test_honeypot_lleno_descarta_el_registro(self):
        """Un bot llena todos los campos, incluido el invisible."""
        datos = self._datos()
        datos[HONEYPOT_FIELD] = 'http://spam.example.com'
        self.client.post(reverse('usuarios:registro'), data=datos)
        self.assertFalse(User.objects.filter(email='ana@test.com').exists())

    def test_nombre_con_numeros_se_rechaza(self):
        self.client.post(reverse('usuarios:registro'),
                         data=self._datos(nombre='Ana123'))
        self.assertFalse(User.objects.filter(email='ana@test.com').exists())

    def test_passwords_distintas_no_crean_cuenta(self):
        self.client.post(reverse('usuarios:registro'),
                         data=self._datos(password2='otraClaveLarga123'))
        self.assertFalse(User.objects.filter(email='ana@test.com').exists())

    def test_rate_limit_corta_el_flood_de_registros(self):
        """Limite de 5 por IP cada 10 minutos."""
        for i in range(5):
            self.client.post(reverse('usuarios:registro'),
                             data=self._datos(email='libre{}@test.com'.format(i)))
            self.client.logout()
        creados_antes = User.objects.count()
        # El 6to ya cae fuera del limite
        self.client.post(reverse('usuarios:registro'),
                         data=self._datos(email='tarde@test.com'))
        self.assertEqual(User.objects.count(), creados_antes)
        self.assertFalse(User.objects.filter(email='tarde@test.com').exists())


# =========================================================================
# 2. Login
# =========================================================================

class LoginTests(_BaseUsuariosTest):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='ana@test.com', email='ana@test.com', password='claveSegura123')

    def _login(self, email='ana@test.com', password='claveSegura123', **extra):
        datos = {'username': email, 'password': password}
        datos.update(extra)
        return self.client.post(reverse('usuarios:login'), data=datos)

    def test_entra_con_su_correo(self):
        self._login()
        resp = self.client.get(reverse('usuarios:perfil'))
        self.assertEqual(resp.status_code, 200)

    def test_correo_en_mayusculas_tambien_entra(self):
        self._login(email='ANA@TEST.COM')
        self.assertEqual(self.client.get(reverse('usuarios:perfil')).status_code, 200)

    def test_clave_incorrecta_no_entra(self):
        self._login(password='claveEquivocada')
        self.assertEqual(self.client.get(reverse('usuarios:perfil')).status_code, 302)

    def test_usuario_inexistente_no_entra(self):
        self._login(email='nadie@test.com')
        self.assertEqual(self.client.get(reverse('usuarios:perfil')).status_code, 302)

    def test_respeta_el_next(self):
        resp = self.client.post(
            '{}?next=/carrito/'.format(reverse('usuarios:login')),
            data={'username': 'ana@test.com', 'password': 'claveSegura123'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/carrito/')

    def test_rate_limit_corta_la_fuerza_bruta(self):
        """
        Limite de 10 intentos por IP cada 5 minutos: despues de eso, ni
        siquiera la clave correcta pasa (se corta antes de validar).
        """
        for _ in range(10):
            self._login(password='claveEquivocada')
        self._login()  # la correcta, pero ya paso el limite
        self.assertEqual(self.client.get(reverse('usuarios:perfil')).status_code, 302)

    def test_logout_cierra_la_sesion(self):
        self._login()
        self.client.get(reverse('usuarios:logout'))
        self.assertEqual(self.client.get(reverse('usuarios:perfil')).status_code, 302)


# =========================================================================
# 3. Fusion del carrito anonimo al iniciar sesion
# =========================================================================

class MergeCarritoAlLoginTests(_BaseUsuariosTest):

    def setUp(self):
        super().setUp()
        self.cat = Categoria.objects.create(nombre='Velas')
        self.producto = Producto.objects.create(
            categoria=self.cat, nombre='Vela', descripcion='x',
            precio=Decimal('5000'), stock=10)
        self.user = User.objects.create_user(
            username='ana@test.com', email='ana@test.com', password='claveSegura123')

    def _carrito_anonimo_con(self, cantidad):
        """Deja un carrito anonimo asociado a la sesion actual del client."""
        session = self.client.session
        session['iniciar'] = True
        session.save()
        carrito = Carrito.objects.create(sesion_key=session.session_key)
        ItemCarrito.objects.create(carrito=carrito, producto=self.producto,
                                   cantidad=cantidad)
        return carrito

    def _login(self):
        return self.client.post(reverse('usuarios:login'), data={
            'username': 'ana@test.com', 'password': 'claveSegura123'})

    def test_el_carrito_anonimo_pasa_al_usuario(self):
        """Lo que el cliente cargo sin cuenta no se pierde al loguearse."""
        self._carrito_anonimo_con(2)
        self._login()
        carrito_usuario = Carrito.objects.get(usuario=self.user)
        self.assertEqual(carrito_usuario.items.count(), 1)
        self.assertEqual(carrito_usuario.items.first().cantidad, 2)

    def test_se_suman_las_cantidades_sin_pasar_el_stock(self):
        carrito_usuario = Carrito.objects.create(usuario=self.user)
        ItemCarrito.objects.create(carrito=carrito_usuario, producto=self.producto,
                                   cantidad=9)
        self._carrito_anonimo_con(5)  # 9 + 5 = 14, pero hay 10 de stock
        self._login()
        item = Carrito.objects.get(usuario=self.user).items.first()
        self.assertEqual(item.cantidad, 10)

    def test_el_carrito_anonimo_se_borra_despues_de_fusionar(self):
        anonimo = self._carrito_anonimo_con(1)
        self._login()
        self.assertFalse(Carrito.objects.filter(pk=anonimo.pk).exists())


# =========================================================================
# 4. Direcciones: datos personales de cada cliente
# =========================================================================

class DireccionesTests(_BaseUsuariosTest):

    def setUp(self):
        super().setUp()
        self.ana = User.objects.create_user('ana@test.com', 'ana@test.com', 'clave123456')
        self.beto = User.objects.create_user('beto@test.com', 'beto@test.com', 'clave123456')
        self.direccion_de_ana = Direccion.objects.create(
            usuario=self.ana, alias='Casa', nombre_destinatario='Ana Perez',
            calle_numero='Los Olmos 123', comuna='Nunoa', telefono='+56911111111')

    def test_anonimo_no_ve_direcciones(self):
        resp = self.client.get(reverse('usuarios:direcciones'))
        self.assertEqual(resp.status_code, 302)

    def test_cada_cliente_ve_solo_las_suyas(self):
        Direccion.objects.create(
            usuario=self.beto, alias='Oficina', nombre_destinatario='Beto Soto',
            calle_numero='Av Otra 999', comuna='Maipu', telefono='+56922222222')
        self.client.force_login(self.ana)
        resp = self.client.get(reverse('usuarios:direcciones'))
        self.assertContains(resp, 'Los Olmos 123')
        self.assertNotContains(resp, 'Av Otra 999')

    def test_no_se_puede_editar_la_direccion_de_otro(self):
        """IDOR: Beto prueba con el pk de la direccion de Ana."""
        self.client.force_login(self.beto)
        resp = self.client.get(
            reverse('usuarios:editar_direccion', args=[self.direccion_de_ana.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_no_se_puede_borrar_la_direccion_de_otro(self):
        self.client.force_login(self.beto)
        resp = self.client.post(
            reverse('usuarios:eliminar_direccion', args=[self.direccion_de_ana.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Direccion.objects.filter(pk=self.direccion_de_ana.pk).exists())

    def test_la_direccion_nueva_queda_a_nombre_de_quien_la_crea(self):
        self.client.force_login(self.beto)
        self.client.post(reverse('usuarios:crear_direccion'), data={
            'alias': 'Casa', 'nombre_destinatario': 'Beto Soto',
            'calle_numero': 'Nueva 456', 'comuna': 'Maipu',
            'region': 'Region Metropolitana', 'telefono': '+56922222222',
        })
        direccion = Direccion.objects.get(calle_numero='Nueva 456')
        self.assertEqual(direccion.usuario, self.beto)

    def test_solo_una_predeterminada_por_cliente(self):
        self.direccion_de_ana.es_predeterminada = True
        self.direccion_de_ana.save()
        segunda = Direccion.objects.create(
            usuario=self.ana, alias='Trabajo', nombre_destinatario='Ana Perez',
            calle_numero='Oficina 1', comuna='Santiago', telefono='+56911111111',
            es_predeterminada=True)
        self.direccion_de_ana.refresh_from_db()
        self.assertFalse(self.direccion_de_ana.es_predeterminada)
        self.assertTrue(segunda.es_predeterminada)

    def test_el_borrado_pide_POST(self):
        """Un GET no puede borrar: si no, bastaria un link para perder datos."""
        self.client.force_login(self.ana)
        self.client.get(
            reverse('usuarios:eliminar_direccion', args=[self.direccion_de_ana.pk]))
        self.assertTrue(Direccion.objects.filter(pk=self.direccion_de_ana.pk).exists())


# =========================================================================
# 5. Perfil
# =========================================================================

class PerfilTests(_BaseUsuariosTest):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('ana@test.com', 'ana@test.com', 'clave123456')

    def test_perfil_requiere_login(self):
        self.assertEqual(self.client.get(reverse('usuarios:perfil')).status_code, 302)

    def test_se_crea_el_perfil_junto_con_el_usuario(self):
        """Lo hace un signal post_save; si se rompe, editar_perfil falla."""
        self.assertTrue(hasattr(self.user, 'perfil'))

    def test_editar_perfil_guarda_nombre_y_telefono(self):
        self.client.force_login(self.user)
        self.client.post(reverse('usuarios:editar_perfil'), data={
            'first_name': 'Ana', 'last_name': 'Perez',
            'email': 'ana@test.com', 'telefono': '+56 9 1234 5678',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ana')
        self.assertEqual(self.user.perfil.telefono, '+56 9 1234 5678')
