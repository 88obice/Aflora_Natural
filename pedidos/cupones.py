"""
Helpers de cupones compartidos entre el carrito y el checkout.

El cupón vive en la sesión (`session['cupon_codigo']`) mientras el cliente
navega. NUNCA se confía en un descuento guardado: se recalcula siempre contra
el subtotal actual y se revalida (vigencia, mínimo, usos) en cada pantalla y,
sobre todo, al crear el pedido.
"""
from decimal import Decimal

SESSION_KEY = 'cupon_codigo'


def obtener_cupon(codigo):
    """Busca un cupón por código (case-insensitive). None si no existe."""
    from .models import Cupon
    if not codigo:
        return None
    return Cupon.objects.filter(codigo__iexact=codigo.strip()).first()


def email_para_cupon(request):
    """Email con el que validar el tope por persona. Vacío si es invitado sin email."""
    if request.user.is_authenticated:
        return request.user.email or ''
    return ''


def cupon_aplicado(request, subtotal, email=''):
    """
    Lee el cupón de la sesión y lo revalida contra el subtotal/email actuales.
    Devuelve (cupon, descuento, error):
      - (Cupon, Decimal, '')  si aplica.
      - (None, 0, '')         si no hay cupón en sesión.
      - (None, 0, mensaje)    si había uno pero ya no aplica (mensaje explica).
    """
    codigo = request.session.get(SESSION_KEY)
    if not codigo:
        return None, Decimal('0'), ''
    cupon = obtener_cupon(codigo)
    if not cupon:
        return None, Decimal('0'), 'El cupón ya no está disponible.'
    ok, msg = cupon.validar(subtotal, email)
    if not ok:
        return None, Decimal('0'), msg
    return cupon, cupon.calcular_descuento(subtotal), ''


def limpiar_cupon(request):
    """Saca el cupón de la sesión."""
    request.session.pop(SESSION_KEY, None)
