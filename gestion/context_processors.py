"""
Contexto del panel de gestion: que seccion del menu va marcada y los contadores
que aparecen al lado de cada item.

Por que aca y no en cada vista: la navegacion vive en base_gestion.html, que es
comun a las 17 paginas del panel. Si cada vista tuviera que declarar su seccion
y pasar los contadores, alcanzaria con que UNA se olvidara para que el menu
quedara sin marcar o sin avisos. Deduciendolo de la URL, no hay nada que
olvidarse.
"""
from django.db.models import Q


# A que item del menu corresponde cada URL del panel. Varias URLs caen en la
# misma seccion: editar un producto sigue siendo "Productos".
SECCION_POR_URL = {
    'dashboard':                    'resumen',

    'pedidos':                      'pedidos',
    'detalle_pedido':               'pedidos',
    'confirmar_pago_transferencia': 'pedidos',
    'marcar_reembolsado':           'pedidos',
    'exportar_pedidos':             'pedidos',

    'productos':                    'productos',
    'crear_producto':               'productos',
    'editar_producto':              'productos',
    'agregar_stock':                'productos',
    'eliminar_producto':            'productos',

    'categorias_lista':             'categorias',
    'categoria_crear':              'categorias',
    'categoria_editar':             'categorias',
    'categoria_eliminar':           'categorias',

    'notificaciones_stock':         'avisos_stock',

    'clientes':                     'clientes',
    'exportar_clientes':            'clientes',

    'newsletter_lista':             'newsletter',
    'newsletter_crear':             'newsletter',
    'newsletter_detalle':           'newsletter',
    'newsletter_enviar_prueba':     'newsletter',
    'newsletter_enviar_real':       'newsletter',

    'newsletter_suscriptores':      'suscriptores',
    'exportar_suscriptores':        'suscriptores',

    'cupones':                      'cupones',
    'cupon_crear':                  'cupones',
    'cupon_editar':                 'cupones',
    'cupon_toggle':                 'cupones',

    'resenas_lista':                'resenas',
    'resena_toggle_aprobar':        'resenas',
    'resena_eliminar':              'resenas',
}


def panel_gestion(request):
    """
    Solo hace trabajo dentro del panel y con un usuario staff. En el resto del
    sitio sale enseguida sin tocar la base de datos: este processor corre en
    CADA request, incluidas las de la tienda.
    """
    match = getattr(request, 'resolver_match', None)
    if match is None or match.app_name != 'gestion':
        return {}
    if not getattr(request.user, 'is_staff', False):
        return {}

    from catalogo.models import NotificacionStock, Resena
    from pedidos.models import Pedido

    return {
        'seccion': SECCION_POR_URL.get(match.url_name, ''),
        # Pedidos que ya se pagaron y todavia no salieron: es la pila de
        # trabajo real de la duenia.
        'gestion_por_preparar': Pedido.objects.filter(
            estado__in=['confirmado', 'preparando']).count(),
        'gestion_avisos_stock': NotificacionStock.objects.filter(
            notificado=False).count(),
        'gestion_resenas_pendientes': Resena.objects.filter(aprobada=False).count(),
    }
