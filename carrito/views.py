from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from .models import Carrito, ItemCarrito
from catalogo.models import Producto


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
    return render(request, 'carrito/carrito.html', {'carrito': carrito})


def agregar_al_carrito(request, producto_id):
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    producto = get_object_or_404(Producto, pk=producto_id, disponible=True)

    if producto.stock <= 0:
        msg = f'"{producto.nombre}" no tiene stock disponible.'
        if es_ajax:
            return JsonResponse({'ok': False, 'error': msg})
        messages.error(request, msg)
        return redirect('catalogo:detalle_producto', pk=producto_id)

    # Cantidad: viene del POST (formulario del detalle) o por defecto 1
    try:
        cantidad = int(request.POST.get('cantidad', 1))
        cantidad = max(1, min(cantidad, producto.stock))
    except (ValueError, TypeError):
        cantidad = 1

    carrito = get_or_create_carrito(request)
    item, created = ItemCarrito.objects.get_or_create(carrito=carrito, producto=producto)

    if not created:
        nueva_cantidad = item.cantidad + cantidad
        if nueva_cantidad > producto.stock:
            msg = f'Solo hay {producto.stock} unidad(es) disponibles de "{producto.nombre}".'
            if es_ajax:
                return JsonResponse({'ok': False, 'error': msg})
            messages.error(request, msg)
            return redirect('carrito:ver_carrito')
        item.cantidad = nueva_cantidad
        item.save()
    else:
        item.cantidad = cantidad
        item.save()

    if es_ajax:
        return JsonResponse({'ok': True, 'nombre': producto.nombre, 'cantidad': cantidad})

    return redirect('carrito:ver_carrito')


def eliminar_del_carrito(request, item_id):
    item = get_object_or_404(ItemCarrito, pk=item_id)
    item.delete()
    return redirect('carrito:ver_carrito')
