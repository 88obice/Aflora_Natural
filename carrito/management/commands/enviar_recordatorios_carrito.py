"""
Recordatorio de carrito abandonado.

Envía un email a los usuarios LOGUEADOS que dejaron productos en el carrito y no
compraron. Solo aplica a carritos con usuario (los anónimos no tienen email
hasta el checkout, que además vacía el carrito).

Criterio de "abandonado":
- El carrito tiene items.
- No se toca hace más de N horas (default 24) — ya no está "comprando ahora".
- No es más viejo que M días (default 7) — no molestamos con carritos fósiles.
- No se le envió recordatorio antes (recordatorio_enviado is null) — una sola vez.

Uso:
    python manage.py enviar_recordatorios_carrito                 # 24h a 7 días
    python manage.py enviar_recordatorios_carrito --horas 12      # umbral distinto
    python manage.py enviar_recordatorios_carrito --max-dias 3
    python manage.py enviar_recordatorios_carrito --dry-run       # no envía, informa

Pensado para correr por una tarea programada (cron) — ver README/notas de deploy.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from carrito.models import Carrito

logger = logging.getLogger('aflora.carrito')


class Command(BaseCommand):
    help = 'Envía recordatorios de carrito abandonado a usuarios logueados.'

    def add_arguments(self, parser):
        parser.add_argument('--horas', type=int, default=24,
                            help='Horas de inactividad para considerarlo abandonado (default: 24).')
        parser.add_argument('--max-dias', type=int, default=7,
                            help='No recordar carritos más viejos que esto (default: 7 días).')
        parser.add_argument('--dry-run', action='store_true',
                            help='No envía nada, solo informa a quiénes se enviaría.')

    def handle(self, *args, **options):
        ahora = timezone.now()
        corte_reciente = ahora - timedelta(hours=options['horas'])   # más nuevo que esto = sigue comprando
        corte_viejo = ahora - timedelta(days=options['max_dias'])    # más viejo que esto = fósil
        dry = options['dry_run']

        qs = (Carrito.objects
              .filter(usuario__isnull=False,
                      recordatorio_enviado__isnull=True,
                      actualizado__lte=corte_reciente,
                      actualizado__gte=corte_viejo)
              .exclude(items__isnull=True)         # debe tener al menos un item
              .select_related('usuario')
              .prefetch_related('items__producto', 'items__variante')
              .distinct())

        enviados = 0
        saltados = 0
        for carrito in qs:
            email = carrito.usuario.email
            if not email:
                saltados += 1
                continue
            # Revalidar que tenga items (por si quedó vacío)
            items = list(carrito.items.all())
            if not items:
                saltados += 1
                continue

            if dry:
                self.stdout.write(
                    '[dry-run] recordatorio a {} ({} items, ${})'.format(
                        email, sum(i.cantidad for i in items), int(carrito.total()))
                )
                enviados += 1
                continue

            if self._enviar(carrito, items, email):
                carrito.recordatorio_enviado = ahora
                carrito.save(update_fields=['recordatorio_enviado'])
                enviados += 1
            else:
                saltados += 1

        resumen = '{}: {} recordatorio(s){}, {} saltado(s).'.format(
            'DRY-RUN' if dry else 'Recordatorios de carrito',
            enviados, ' que se enviarían' if dry else ' enviado(s)', saltados)
        self.stdout.write(self.style.SUCCESS(resumen))
        logger.info(resumen)

    def _enviar(self, carrito, items, email):
        nombre = carrito.usuario.get_full_name() or carrito.usuario.first_name or 'Hola'
        base_url = getattr(settings, 'BASE_URL', '').rstrip('/')
        link_carrito = '{}/carrito/'.format(base_url) if base_url else '/carrito/'

        lineas = '\n'.join(
            '  - {} x{}: ${:,}'.format(
                it.nombre_mostrar(), it.cantidad, int(it.subtotal())
            ).replace(',', '.')
            for it in items
        )
        mensaje = """Hola {nombre},

Dejaste algunos productos en tu carrito en Aflora Natural y no queremos que se te pierdan:

{lineas}

Total: ${total:,}

Retoma tu compra acá: {link}

Si ya no te interesan, ignora este mensaje.

-- Aflora Natural
""".format(
            nombre=nombre,
            lineas=lineas,
            total=int(carrito.total()),
            link=link_carrito,
        ).replace(',', '.')

        try:
            send_mail(
                subject='¿Se te quedó algo en el carrito? -- Aflora Natural',
                message=mensaje,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            logger.info('Recordatorio de carrito enviado a %s (carrito #%s)', email, carrito.pk)
            return True
        except Exception:
            logger.exception('Error enviando recordatorio de carrito a %s (carrito #%s)', email, carrito.pk)
            return False
