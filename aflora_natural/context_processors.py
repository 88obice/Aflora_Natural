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


def banco_info(request):
    """
    Expone los datos bancarios al template. Si BANCO.titular esta vacio,
    transferencia_disponible es False y la opcion no aparece en checkout.
    """
    banco = getattr(settings, 'BANCO', {})
    return {
        'BANCO': banco,
        'transferencia_disponible': bool(banco.get('titular') and banco.get('numero_cuenta')),
    }


def contacto_info(request):
    """
    Expone los datos de contacto centralizados (email, WhatsApp, Instagram)
    en TODOS los templates. Evita el email hardcodeado e inconsistente que
    habia antes entre paginas.
    """
    return {'CONTACTO': getattr(settings, 'CONTACTO', {})}


def categorias_nav(request):
    """
    Expone las categorias en TODOS los templates para el panel deslizante
    (offcanvas) del navbar. Import local para evitar problemas al cargar apps.
    """
    from catalogo.models import Categoria
    return {'nav_categorias': Categoria.objects.all()}
