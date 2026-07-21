from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Carrito, ItemCarrito
from catalogo.models import Producto, Variante


def get_or_create_carrito(request):
    if request.user.is_authenticated:
        carrito, _ = Carrito.objects.get_or_create(usuario=request.user)
    else:
        if not request.session.session_key:
            request.session.create()
        carrito, _ = Carrito.objects.get_or_create(sesion_key=request.session.session_key)
    return carrito


UMBRAL_ENVIO_GRATIS = 40000


def ver_carrito(request):
    carrito = get_or_create_carrito(request)
    items = carrito.items.select_related('producto', 'variante').all()
    subtotal = carrito.total()
    falta_para_gratis = max(0, UMBRAL_ENVIO_GRATIS - subtotal)
    return render(request, 'carrito/carrito.html', {
        'carrito': carrito,
        'items': items,
        'falta_para_gratis': falta_para_gratis,
        'umbral_envio_gratis': UMBRAL_ENVIO_GRATIS,
    })


@require_POST
def agregar_al_carrito(request, producto_id):
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    producto = get_object_or_404(Producto, pk=producto_id, disponible=True)

    # Variante opcional
    variante = None
    variante_id = request.POST.get('variante')
    if variante_id:
        try:
            variante = Variante.objects.get(pk=variante_id, producto=producto, activa=True)
        except Variante.DoesNotExist:
            msg = 'Opcion no valida.'
            if es_ajax:
                return JsonResponse({'ok': False, 'error': msg})
            messages.error(request, msg)
            return redirect('catalogo:detalle_producto', slug=producto.slug)

    # Si producto tiene variantes activas y no se selecciono ninguna -> error
    if not variante and producto.variantes.filter(activa=True).exists():
        msg = 'Selecciona una opcion de "{}".'.format(producto.nombre)
        if es_ajax:
            return JsonResponse({'ok': False, 'error': msg})
        messages.error(request, msg)
        return redirect('catalogo:detalle_producto', slug=producto.slug)

    stock_disponible = variante.stock if variante else producto.stock
    if stock_disponible <= 0:
        msg = '"{}" no tiene stock disponible.'.format(producto.nombre)
        if es_ajax:
            return JsonResponse({'ok': False, 'error': msg})
        messages.error(request, msg)
        return redirect('catalogo:detalle_producto', slug=producto.slug)

    try:
        cantidad = int(request.POST.get('cantidad', 1))
        cantidad = max(1, min(cantidad, stock_disponible))
    except (ValueError, TypeError):
        cantidad = 1

    carrito = get_or_create_carrito(request)
    item, created = ItemCarrito.objects.get_or_create(
        carrito=carrito, producto=producto, variante=variante,
        defaults={'cantidad': cantidad},
    )
    if not created:
        nueva_cantidad = item.cantidad + cantidad
        if nueva_cantidad > stock_disponible:
            msg = 'Solo hay {} unidad(es) disponibles.'.format(stock_disponible)
            if es_ajax:
                return JsonResponse({'ok': False, 'error': msg})
            messages.error(request, msg)
            return redirect('carrito:ver_carrito')
        item.cantidad = nueva_cantidad
        item.save()

    if es_ajax:
        return JsonResponse({'ok': True, 'nombre': producto.nombre, 'cantidad': cantidad})
    return redirect('carrito:ver_carrito')


@require_POST
def actualizar_cantidad(request, item_id):
    item = get_object_or_404(ItemCarrito, pk=item_id)
    # Verificar que el item sea del carrito del request
    carrito = get_or_create_carrito(request)
    if item.carrito_id != carrito.id:
        return redirect('carrito:ver_carrito')

    try:
        nueva = int(request.POST.get('cantidad', 1))
    except (ValueError, TypeError):
        nueva = 1

    if nueva <= 0:
        item.delete()
    else:
        nueva = min(nueva, item.stock_disponible)
        item.cantidad = nueva
        item.save()
    return redirect('carrito:ver_carrito')


def eliminar_del_carrito(request, item_id):
    item = get_object_or_404(ItemCarrito, pk=item_id)
    carrito = get_or_create_carrito(request)
    if item.carrito_id == carrito.id:
        item.delete()
    return redirect('carrito:ver_carrito')
