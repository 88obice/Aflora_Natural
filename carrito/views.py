from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
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
    producto = get_object_or_404(Producto, pk=producto_id, disponible=True)

    if producto.stock <= 0:
        messages.error(request, f'"{producto.nombre}" no tiene stock disponible.')
        return redirect('catalogo:detalle_producto', pk=producto_id)

    carrito = get_or_create_carrito(request)
    item, created = ItemCarrito.objects.get_or_create(carrito=carrito, producto=producto)

    if not created:
        if item.cantidad >= producto.stock:
            messages.error(request, f'No hay más unidades disponibles de "{producto.nombre}" (stock: {producto.stock}).')
            return redirect('carrito:ver_carrito')
        item.cantidad += 1
        item.save()

    return redirect('carrito:ver_carrito')

def eliminar_del_carrito(request, item_id):
    item = get_object_or_404(ItemCarrito, pk=item_id)
    item.delete()
    return redirect('carrito:ver_carrito')