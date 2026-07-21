from django.db.models import Sum
from .models import ItemCarrito


def carrito_contador(request):
    """
    Contador del carrito para el navbar. Corre en CADA request del sitio, asi
    que resuelve el total con un unico aggregate (SUM en la BD) en vez de traer
    e iterar todos los items en Python (evita N+1 en cada pagina).
    """
    try:
        if request.user.is_authenticated:
            filtro = {'carrito__usuario': request.user}
        else:
            sk = request.session.session_key
            if not sk:
                return {'carrito_count': 0}
            filtro = {'carrito__sesion_key': sk}
        total = ItemCarrito.objects.filter(**filtro).aggregate(n=Sum('cantidad'))['n']
        return {'carrito_count': total or 0}
    except Exception:
        return {'carrito_count': 0}
