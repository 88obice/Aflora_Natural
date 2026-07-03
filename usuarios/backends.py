"""
Backend de autenticacion por correo electronico.

Se usa JUNTO con ModelBackend (ver AUTHENTICATION_BACKENDS en settings):
  1. EmailBackend  -> clientes entran con su correo.
  2. ModelBackend  -> admin/staff siguen entrando con su username.

Asi el login por correo no le quita el acceso al panel al superusuario.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        # AuthenticationForm pasa el valor del campo como 'username'.
        identifier = username or kwargs.get('email')
        if identifier is None or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=identifier.strip())
        except User.DoesNotExist:
            # Ejecuta el hasher igual para no filtrar por tiempo si el correo existe.
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # No deberia ocurrir (correo unico en registro), pero por seguridad
            # tomamos el mas antiguo de forma determinista.
            user = User.objects.filter(email__iexact=identifier.strip()).order_by('id').first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
