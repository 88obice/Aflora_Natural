from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from pedidos.models import Pedido
from catalogo.models import Producto


def solo_staff(user):
    return user.is_staff


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def dashboard(request):
    total_pedidos        = Pedido.objects.count()
    pedidos_nuevos       = Pedido.objects.filter(estado='pendiente').count()
    productos_bajo_stock = Producto.objects.filter(stock__lte=3, disponible=True).count()
    pedidos_recientes    = Pedido.objects.order_by('-creado')[:5]

    context = {
        'total_pedidos': total_pedidos,
        'pedidos_nuevos': pedidos_nuevos,
        'productos_bajo_stock': productos_bajo_stock,
        'pedidos_recientes': pedidos_recientes,
    }
    return render(request, 'gestion/dashboard.html', context)


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def lista_pedidos(request):
    estado  = request.GET.get('estado', '')
    pedidos = Pedido.objects.order_by('-creado')
    if estado:
        pedidos = pedidos.filter(estado=estado)
    return render(request, 'gestion/pedidos.html', {
        'pedidos': pedidos,
        'estados': Pedido.ESTADO_CHOICES,
        'estado_actual': estado,
    })


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def detalle_pedido(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    if request.method == 'POST':
        nuevo_estado   = request.POST.get('estado')
        estados_validos = [e[0] for e in Pedido.ESTADO_CHOICES]
        if nuevo_estado in estados_validos:
            pedido.estado = nuevo_estado
            pedido.save()
            messages.success(request, f'Estado actualizado a "{pedido.get_estado_display()}".')
        return redirect('gestion:detalle_pedido', pk=pk)
    return render(request, 'gestion/detalle_pedido.html', {'pedido': pedido})


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def lista_productos(request):
    productos = Producto.objects.order_by('categoria', 'nombre')
    return render(request, 'gestion/productos.html', {'productos': productos})
