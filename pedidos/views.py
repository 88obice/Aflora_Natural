from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Pedido, ItemPedido
from carrito.models import Carrito, ItemCarrito

@login_required
def crear_pedido(request):
    carrito = get_object_or_404(Carrito, usuario=request.user)
    items = carrito.items.all()
    if not items:
        return redirect('carrito:ver_carrito')
    if request.method == 'POST':
        pedido = Pedido.objects.create(
            usuario=request.user,
            direccion_entrega=request.POST['direccion'],
            telefono=request.POST['telefono'],
            total=carrito.total()
        )
        for item in items:
            ItemPedido.objects.create(
                pedido=pedido,
                producto=item.producto,
                cantidad=item.cantidad,
                precio_unitario=item.producto.precio
            )
        carrito.items.all().delete()
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