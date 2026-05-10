"""
Signals del catalogo.

notify_stock_repuesto: cuando un producto (o variante) pasa de stock 0 a >0,
mandamos email a todos los clientes que pidieron aviso y marcamos
las notificaciones como ya enviadas.
"""
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Producto, Variante, NotificacionStock

logger = logging.getLogger('aflora.catalogo')


def _capturar_stock_previo(sender, instance, **kwargs):
    """pre_save: guarda el stock anterior en el instance para compararlo en post_save."""
    if instance.pk:
        try:
            anterior = sender.objects.only('stock').get(pk=instance.pk)
            instance._stock_anterior = anterior.stock
        except sender.DoesNotExist:
            instance._stock_anterior = None
    else:
        instance._stock_anterior = None


def _notificar_si_repuesto(producto, contexto=''):
    """
    Para un Producto dado, manda email a todas las NotificacionStock no enviadas
    y las marca como notificadas. Idempotente: si vuelve a correr, no manda 2 veces.
    """
    pendientes = NotificacionStock.objects.filter(producto=producto, notificado=False)
    if not pendientes.exists():
        return 0

    enviados = 0
    fallidos = 0
    url_producto = ''
    try:
        url_producto = producto.get_absolute_url()
    except Exception:
        pass

    asunto = '"{}" volvio a estar disponible -- Aflora Natural'.format(producto.nombre)
    cuerpo_base = (
        'Hola!\n\n'
        '"{nombre}" que estabas esperando ya esta disponible en nuestra tienda.\n\n'
        'Te dejamos el link para que lo pidas antes de que se agote de nuevo:\n'
        '{url}\n\n'
        '-- Aflora Natural\n'
        'WhatsApp +56 9 8956 0937'
    )

    for n in pendientes:
        cuerpo = cuerpo_base.format(nombre=producto.nombre, url=url_producto or '')
        try:
            send_mail(
                subject=asunto,
                message=cuerpo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[n.email],
                fail_silently=False,
            )
            n.notificado = True
            n.save(update_fields=['notificado'])
            enviados += 1
        except Exception:
            logger.exception('Error notificando stock a %s para producto #%s', n.email, producto.pk)
            fallidos += 1

    if enviados or fallidos:
        logger.info('Notify-stock %s producto #%s: %s enviados, %s fallidos',
                    contexto, producto.pk, enviados, fallidos)
    return enviados


def _post_save_producto(sender, instance, created, **kwargs):
    """Cuando se actualiza un Producto sin variantes y su stock pasa de 0 a >0."""
    if created:
        return
    if instance.variantes.exists():
        return
    anterior = getattr(instance, '_stock_anterior', None)
    if anterior is not None and anterior <= 0 and instance.stock > 0:
        _notificar_si_repuesto(instance, contexto='(producto base)')


def _post_save_variante(sender, instance, created, **kwargs):
    """Cuando se actualiza una Variante y su stock pasa de 0 a >0."""
    if created:
        return
    anterior = getattr(instance, '_stock_anterior', None)
    if anterior is not None and anterior <= 0 and instance.stock > 0:
        _notificar_si_repuesto(instance.producto, contexto='(variante "{}")'.format(instance.nombre))


# Conexion explicita con weak=False y dispatch_uid para que sobrevivan al GC
pre_save.connect(_capturar_stock_previo, sender=Producto, weak=False,
                 dispatch_uid='catalogo._capturar_stock_previo_producto')
pre_save.connect(_capturar_stock_previo, sender=Variante, weak=False,
                 dispatch_uid='catalogo._capturar_stock_previo_variante')
post_save.connect(_post_save_producto, sender=Producto, weak=False,
                  dispatch_uid='catalogo._post_save_producto')
post_save.connect(_post_save_variante, sender=Variante, weak=False,
                  dispatch_uid='catalogo._post_save_variante')
