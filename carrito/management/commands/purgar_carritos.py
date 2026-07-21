"""
Purga carritos anonimos viejos.

Cada visitante anonimo/bot genera una fila Carrito (por sesion). Sin limpieza,
la tabla crece indefinidamente. Este comando borra los carritos SIN usuario
(anonimos) que no se han tocado en N dias.

Uso:
    python manage.py purgar_carritos            # borra anonimos > 30 dias
    python manage.py purgar_carritos --dias 7   # umbral personalizado
    python manage.py purgar_carritos --dry-run  # solo cuenta, no borra

Recomendado correrlo periodicamente (ej. tarea programada semanal).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from carrito.models import Carrito


class Command(BaseCommand):
    help = 'Borra carritos anonimos (sin usuario) no modificados en N dias.'

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=30,
                            help='Antiguedad minima en dias (default: 30).')
        parser.add_argument('--dry-run', action='store_true',
                            help='No borra, solo informa cuantos se borrarian.')

    def handle(self, *args, **options):
        dias = options['dias']
        corte = timezone.now() - timedelta(days=dias)
        qs = Carrito.objects.filter(usuario__isnull=True, actualizado__lt=corte)
        total = qs.count()

        if options['dry_run']:
            self.stdout.write(f'[dry-run] Se borrarian {total} carritos anonimos (> {dias} dias).')
            return

        borrados, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Purga completa: {total} carritos anonimos borrados (> {dias} dias).'
        ))
