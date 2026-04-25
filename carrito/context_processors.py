from django.db.models import Sum
from .models import Carrito


def carrito_contador(request):
    """Pasa el total de unidades en el carrito a todos los templates."""
    count = 0
    try:
        if request.user.is_authenticated:
            carrito = Carrito.objects.filter(usuario=request.user).first()
        else:
            session_key = request.session.session_key
            carrito = Carrito.objects.filter(sesion_key=session_key).first() if session_key else None

        if carrito:
            total = carrito.items.aggregate(total=Sum('cantidad'))['total']
            count = total or 0
    except Exception:
        pass
    return {'carrito_count': count}
