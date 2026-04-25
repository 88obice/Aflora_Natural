from django.shortcuts import render, get_object_or_404
from .models import Categoria, Producto

def inicio(request):
    productos_destacados = Producto.objects.filter(disponible=True)[:8]
    categorias = Categoria.objects.all()
    return render(request, 'catalogo/inicio.html', {
        'productos': productos_destacados,
        'categorias': categorias,
    })

def lista_productos(request):
    categorias = Categoria.objects.all()
    productos = Producto.objects.filter(disponible=True)
    categoria_id = request.GET.get('categoria')
    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)
    return render(request, 'catalogo/lista_productos.html', {
        'productos': productos,
        'categorias': categorias,
    })

def detalle_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk, disponible=True)
    return render(request, 'catalogo/detalle_producto.html', {
        'producto': producto,
    })