"""
Cliente mínimo del API de Flow (https://developers.flow.cl).

Solo lo necesario para el checkout: crear una orden de pago y consultar su
estado (única fuente de verdad, igual que hacemos con Mercado Pago). NO se
confía en los parámetros que llegan por el navegador del cliente.

Firma (según doc oficial): se ordenan los parámetros por nombre, se concatena
`clave+valor` sin separadores, se firma con HMAC-SHA256 usando la secretKey y
el hex resultante se agrega como parámetro `s`.

Config por env (ver settings): FLOW_API_KEY, FLOW_SECRET_KEY, FLOW_API_URL.
Si no hay llaves, `flow_configurado()` es False y el checkout no ofrece Flow.
"""
import hashlib
import hmac
import logging
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger('aflora.pedidos')

# Estados que devuelve Flow en getStatus (campo `status`).
STATUS_PENDIENTE = 1
STATUS_PAGADO    = 2
STATUS_RECHAZADO = 3
STATUS_ANULADO   = 4

# Mapea el `paymentData.media` de Flow a nuestros choices MEDIO_PAGO_CHOICES.
# Flow no garantiza un set cerrado; lo que no reconozcamos cae en 'otro'.
_MEDIA_MAP = {
    'webpay':        'webpay',
    'webpay plus':   'webpay',
    'onepay':        'onepay',
    'mach':          'mach',
    'servipag':      'servipag',
    'multicaja':     'multicaja',
    'transferencia': 'transferencia',
    'transferencia bancaria': 'transferencia',
}


class FlowError(Exception):
    """Error al comunicarse con Flow."""


def flow_configurado():
    """True si hay llaves configuradas (la opción Flow puede ofrecerse)."""
    return bool(getattr(settings, 'FLOW_API_KEY', '') and
                getattr(settings, 'FLOW_SECRET_KEY', ''))


def _firmar(params):
    """
    Firma HMAC-SHA256 de los params (ordenados por clave, concatenando
    clave+valor sin separadores). Devuelve el hex. No incluye `s`.
    """
    secret = settings.FLOW_SECRET_KEY.encode()
    to_sign = ''.join('{}{}'.format(k, params[k]) for k in sorted(params))
    return hmac.new(secret, to_sign.encode(), hashlib.sha256).hexdigest()


def _con_firma(params):
    """Devuelve una copia de params con el parámetro `s` (firma) agregado."""
    firmado = dict(params)
    firmado['s'] = _firmar(params)
    return firmado


def media_a_medio_detalle(media):
    """Normaliza el paymentData.media de Flow a un valor de MEDIO_PAGO_CHOICES."""
    if not media:
        return ''
    return _MEDIA_MAP.get(str(media).strip().lower(), 'otro')


def crear_pago(commerce_order, subject, amount, email,
               url_confirmation, url_return, optional=None, timeout=15):
    """
    Crea una orden de pago en Flow (payment/create).

    Devuelve la URL a la que hay que redirigir al cliente: '{url}?token={token}'.
    `amount` debe ser entero (CLP no admite decimales). Lanza FlowError si falla.
    """
    params = {
        'apiKey':          settings.FLOW_API_KEY,
        'commerceOrder':   str(commerce_order),
        'subject':         subject[:255],
        'currency':        'CLP',
        'amount':          int(amount),
        'email':           email,
        'urlConfirmation': url_confirmation,
        'urlReturn':       url_return,
    }
    if optional:
        params['optional'] = optional

    url = '{}/payment/create'.format(settings.FLOW_API_URL)
    try:
        resp = requests.post(
            url, data=urlencode(_con_firma(params)),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise FlowError('No se pudo conectar con Flow: {}'.format(e))

    if resp.status_code != 200:
        raise FlowError('Flow payment/create respondió {}: {}'.format(
            resp.status_code, resp.text[:300]))

    data = resp.json()
    token = data.get('token')
    pago_url = data.get('url')
    if not token or not pago_url:
        raise FlowError('Respuesta de Flow sin token/url: {}'.format(data))

    # Guardamos flowOrder si vino, para trazabilidad.
    return {
        'redirect_url': '{}?token={}'.format(pago_url, token),
        'token':        token,
        'flow_order':   str(data.get('flowOrder', '')),
    }


def get_status(token, timeout=15):
    """
    Consulta el estado real de una orden (payment/getStatus, método GET).
    Devuelve el dict JSON de Flow. Lanza FlowError si falla.
    """
    params = {
        'apiKey': settings.FLOW_API_KEY,
        'token':  token,
    }
    url = '{}/payment/getStatus?{}'.format(
        settings.FLOW_API_URL, urlencode(_con_firma(params)))
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise FlowError('No se pudo consultar el estado en Flow: {}'.format(e))

    if resp.status_code != 200:
        raise FlowError('Flow getStatus respondió {}: {}'.format(
            resp.status_code, resp.text[:300]))
    return resp.json()
