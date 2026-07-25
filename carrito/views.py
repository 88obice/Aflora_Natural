from django.conf import settings
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


def ver_carrito(request):
    carrito = get_or_create_carrito(request)
    items = carrito.items.select_related('producto', 'variante').all()

    from pedidos.cupones import cupon_aplicado, email_para_cupon, limpiar_cupon
    subtotal = carrito.total()
    cupon, descuento, error = cupon_aplicado(request, subtotal, email_para_cupon(request))
    # Si había un cupón en sesión que ya no aplica, lo sacamos y avisamos.
    if error:
        limpiar_cupon(request)
        messages.warning(request, error)

    return render(request, 'carrito/carrito.html', {
        'carrito': carrito,
        'items': items,
        'subtotal': subtotal,
        'cupon': cupon,
        'descuento': descuento,
        'total_con_descuento': subtotal - descuento,
    })


@require_POST
def aplicar_cupon(request):
    from pedidos.cupones import obtener_cupon, email_para_cupon, SESSION_KEY
    codigo = request.POST.get('codigo', '').strip()
    if not codigo:
        messages.error(request, 'Escribí un código de cupón.')
        return redirect('carrito:ver_carrito')
    carrito = get_or_create_carrito(request)
    subtotal = carrito.total()
    if subtotal <= 0:
        messages.error(request, 'Tu carrito está vacío.')
        return redirect('carrito:ver_carrito')
    cupon = obtener_cupon(codigo)
    if not cupon:
        messages.error(request, 'Ese código no existe o no es válido.')
        return redirect('carrito:ver_carrito')
    ok, msg = cupon.validar(subtotal, email_para_cupon(request))
    if not ok:
        messages.error(request, msg)
        return redirect('carrito:ver_carrito')
    request.session[SESSION_KEY] = cupon.codigo
    desc = cupon.calcular_descuento(subtotal)
    messages.success(request, 'Cupón {} aplicado: ${:,.0f} de descuento.'.format(
        cupon.codigo, desc).replace(',', '.'))
    return redirect('carrito:ver_carrito')


@require_POST
def quitar_cupon(request):
    from pedidos.cupones import limpiar_cupon
    limpiar_cupon(request)
    messages.info(request, 'Cupón quitado.')
    return redirect('carrito:ver_carrito')


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
