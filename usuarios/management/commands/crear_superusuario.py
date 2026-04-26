import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Crea un superusuario desde variables de entorno si no existe.'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        username = os.environ.get('SUPERUSER_NAME')
        password = os.environ.get('SUPERUSER_PASSWORD')
        email    = os.environ.get('SUPERUSER_EMAIL', '')

        if not username or not password:
            self.stdout.write('SUPERUSER_NAME o SUPERUSER_PASSWORD no definidos. Saltando.')
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Superusuario "{username}" ya existe. Saltando.')
            return

        User.objects.create_superuser(username=username, password=password, email=email)
        self.stdout.write(f'Superusuario "{username}" creado.')
