"""
Configura el dominio del framework django.contrib.sites desde BASE_URL.

Django crea el registro Site con el dominio por defecto 'example.com'. Ese
registro lo usan los links del reset de contrasena y el sitemap, asi que si
queda en 'example.com' esos links apuntan al lugar equivocado (y Google indexa
el dominio equivocado).

Este comando corre en cada deploy (ver preDeployCommand en railway.toml) y deja
el Site sincronizado con BASE_URL, de forma que nunca vuelve a 'example.com'
aunque se rehaga la base de datos.

Uso:
    python manage.py configurar_sitio
"""
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Configura el dominio del Site (django.contrib.sites) desde BASE_URL.'

    def handle(self, *args, **options):
        base_url = getattr(settings, 'BASE_URL', '').strip()
        if not base_url:
            self.stdout.write('BASE_URL no definido. Saltando configuracion de Site.')
            return

        # Extraer solo el host (sin esquema ni path). Si BASE_URL viene sin
        # esquema, urlparse deja el host en .path, asi que contemplamos ambos.
        parsed = urlparse(base_url)
        dominio = (parsed.netloc or parsed.path).strip().strip('/')
        if not dominio:
            self.stdout.write(f'No se pudo extraer un dominio de BASE_URL="{base_url}". Saltando.')
            return

        site_id = getattr(settings, 'SITE_ID', 1)
        nombre = getattr(settings, 'SITE_NAME', 'Aflora Natural')
        site, created = Site.objects.update_or_create(
            pk=site_id,
            defaults={'domain': dominio, 'name': nombre},
        )
        verbo = 'creado' if created else 'actualizado'
        self.stdout.write(self.style.SUCCESS(
            f'Site #{site_id} {verbo}: dominio="{dominio}" nombre="{nombre}"'
        ))
