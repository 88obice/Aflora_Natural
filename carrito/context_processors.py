from .models import Carrito


def carrito_contador(request):
    """Contador del carrito para mostrar en navbar (usado por todas las paginas)."""
    try:
        if request.user.is_authenticated:
            carrito = Carrito.objects.filter(usuario=request.user).first()
        else:
            sk = request.session.session_key
            carrito = Carrito.objects.filter(sesion_key=sk).first() if sk else None
        if carrito:
            total = sum(it.cantidad for it in carrito.items.all())
            return {'carrito_count': total}
    except Exception:
        pass
    return {'carrito_count': 0}
