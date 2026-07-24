"""
Anti-spam liviano, sin dependencias ni cuentas externas.

Dos defensas:
1. Honeypot: un campo trampa invisible para humanos (CSS off-screen). Los bots
   que llenan todos los inputs lo completan y se delatan. Ver el partial
   templates/partials/honeypot.html.
2. Rate limiting por IP: límite de intentos por acción en una ventana de tiempo,
   usando el framework de cache de Django (LocMemCache por defecto). Frena
   fuerza bruta en login y flood en registro/newsletter/notify-me.

Nota: LocMemCache es por proceso y se limpia al reiniciar. Suficiente para esta
escala. Si algún día se necesita algo más fuerte (varios workers), se cambia
CACHES a Redis en settings y este módulo sigue igual.
"""
import logging
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger('aflora.antispam')

# Nombre del campo trampa. Debe sonar "llenable" para un bot pero no existir
# para el humano (está oculto por CSS en el partial).
HONEYPOT_FIELD = 'website'


def get_client_ip(request):
    """IP del cliente, considerando el proxy de Railway (X-Forwarded-For)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or 'sin-ip'


def honeypot_ok(request):
    """
    True si NO se detecta bot (el campo trampa vino vacío).
    False si el honeypot fue llenado (probable bot).
    """
    valor = (request.POST.get(HONEYPOT_FIELD) or '').strip()
    if valor:
        logger.warning('Honeypot activado desde IP %s (valor=%r)',
                       get_client_ip(request), valor[:60])
        return False
    return True


def rate_limited(request, action, limit, window):
    """
    True si la IP superó `limit` intentos de `action` dentro de `window` segundos.
    Ventana fija: el TTL arranca en el primer intento y NO se refresca, así el
    bloqueo dura como mucho `window` segundos desde el primer intento.
    Cuenta el intento actual. Si el cache falla, no bloquea (fail-open).
    """
    ip = get_client_ip(request)
    key = 'rl:{}:{}'.format(action, ip)
    try:
        cache.add(key, 0, timeout=window)  # crea con TTL solo si no existe
        try:
            actual = cache.incr(key)
        except ValueError:
            # Expiró entre el add y el incr: reiniciamos la ventana.
            cache.set(key, 1, timeout=window)
            actual = 1
    except Exception:
        return False
    if actual > limit:
        logger.warning('Rate limit: IP %s superó %s intentos de "%s"', ip, limit, action)
        return True
    return False


def rate_limit(action, limit, window):
    """
    Decorador para proteger vistas (incluidas las CBV de Django vía as_view()).
    Solo cuenta POST. Si se supera el límite, devuelve 429 con mensaje simple.
    Para vistas propias conviene usar rate_limited() inline y responder con
    messages + redirect (mejor UX); este decorador es para las vistas que no
    controlamos, como PasswordResetView.
    """
    def deco(viewfunc):
        @wraps(viewfunc)
        def wrapper(request, *args, **kwargs):
            if request.method == 'POST' and rate_limited(request, action, limit, window):
                return HttpResponse(
                    'Demasiados intentos. Esperá unos minutos e intentá de nuevo.',
                    status=429,
                )
            return viewfunc(request, *args, **kwargs)
        return wrapper
    return deco
