from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Pedido, ItemPedido
from carrito.models import Carrito, ItemCarrito

@login_required
def crear_pedido(request):
    carrito = get_object_or_404(Carrito, usuario=request.user)
    items = carrito.items.all()
    if not items:
        return redirect('carrito:ver_carrito')
    if request.method == 'POST':
        # Verificar stock antes de crear nada
        for item in items:
            if item.cantidad > item.producto.stock:
                messages.error(
                    request,
                    f'Stock insuficiente para "{item.producto.nombre}". '
                    f'Pediste {item.cantidad} pero hay {item.producto.stock} disponibles.'
                )
                return redirect('carrito:ver_carrito')

        try:
            with transaction.atomic():
                pedido = Pedido.objects.create(
                    usuario=request.user,
                    direccion_entrega=request.POST['direccion'],
                    telefono=request.POST['telefono'],
                    total=carrito.total()
                )
                for item in items:
                    # Bloquea la fila para evitar condiciones de carrera
                    producto = item.producto.__class__.objects.select_for_update().get(pk=item.producto.pk)
                    if item.cantidad > producto.stock:
                        raise ValueError(f'Stock insuficiente para "{producto.nombre}".')
                    producto.stock -= item.cantidad
                    if producto.stock == 0:
                        producto.disponible = False
                    producto.save()
                    ItemPedido.objects.create(
                        pedido=pedido,
                        producto=producto,
                        cantidad=item.cantidad,
                        precio_unitario=producto.precio
                    )
                carrito.items.all().delete()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('carrito:ver_carrito')

        return redirect('pedidos:detalle_pedido', pk=pedido.pk)
    return render(request, 'pedidos/crear_pedido.html', {'carrito': carrito})

@login_required
def historial_pedidos(request):
    pedidos = Pedido.objects.filter(usuario=request.user).order_by('-creado')
    return render(request, 'pedidos/historial.html', {'pedidos': pedidos})

@login_required
def detalle_pedido(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk, usuario=request.user)
    return render(request, 'pedidos/detalle_pedido.html', {'pedido': pedido})