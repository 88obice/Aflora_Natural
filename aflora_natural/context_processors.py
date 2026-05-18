"""
Context processors globales del proyecto.

Inyecta variables en TODOS los templates renderizados.
"""
from django.conf import settings


def analytics_ids(request):
    """
    Expone los IDs de tracking (GA4, Meta Pixel) en cada template.
    Si no estan configurados en settings, devuelve strings vacios y
    los snippets en base.html no se renderizan.
    """
    return {
        'GA4_MEASUREMENT_ID': getattr(settings, 'GA4_MEASUREMENT_ID', ''),
        'META_PIXEL_ID':      getattr(settings, 'META_PIXEL_ID', ''),
    }
