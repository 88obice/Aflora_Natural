from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import (
    Categoria, Producto, Resena, Wishlist,
    SuscriptorNewsletter, NotificacionStock,
)


# --- Home -----------------------------------------------------------------

def inicio(request):
    productos_destacados = (
        Producto.objects
        .filter(disponible=True, destacado=True)
        .select_related('categoria')
        .prefetch_related('imagenes', 'variantes')[:8]
    )
    if not productos_destacados:
        # Si nadie marco destacado todavia, caer a los mas recientes
        productos_destacados = (
            Producto.objects
            .filter(disponible=True)
            .select_related('categoria')
            .prefetch_related('imagenes', 'variantes')[:8]
        )
    categorias = Categoria.objects.all()
    return render(request, 'catalogo/inicio.html', {
        'productos': productos_destacados,
        'categorias': categorias,
        'hero_imagen': settings.HERO_IMAGEN_URL,
    })


# --- Listado con busqueda, filtros, orden y paginacion --------------------

def lista_productos(request):
    qs = (
        Producto.objects
        .filter(disponible=True)
        .select_related('categoria')
        .prefetch_related('imagenes', 'variantes', 'resenas')
    )

    # Filtro por categoria (acepta id o slug)
    cat_param = request.GET.get('categoria', '').strip()
    categoria_actual = None
    if cat_param:
        categoria_actual = (
            Categoria.objects.filter(slug=cat_param).first()
            or Categoria.objects.filter(pk=cat_param).first()
            if cat_param.isdigit() else
            Categoria.objects.filter(slug=cat_param).first()
        )
        if categoria_actual:
            qs = qs.filter(categoria=categoria_actual)

    # Busqueda libre
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(descripcion_corta__icontains=q) |
            Q(sku__icontains=q) |
            Q(categoria__nombre__icontains=q)
        ).distinct()

    # Filtro de precio
    precio_min = request.GET.get('precio_min', '').strip()
    precio_max = request.GET.get('precio_max', '').strip()
    if precio_min.isdigit():
        qs = qs.filter(precio__gte=int(precio_min))
    if precio_max.isdigit():
        qs = qs.filter(precio__lte=int(precio_max))

    # Solo en stock
    if request.GET.get('en_stock') == '1':
        qs = qs.filter(stock__gt=0)

    # Orden
    orden = request.GET.get('orden', 'recientes')
    ordenes_validos = {
        'recientes':   '-creado',
        'antiguos':    'creado',
        'precio_asc':  'precio',
        'precio_desc': '-precio',
        'nombre':      'nombre',
    }
    qs = qs.order_by(ordenes_validos.get(orden, '-creado'))

    # Paginacion
    paginator = Paginator(qs, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Querystring sin 'page' para reusar en links de paginacion
    params = request.GET.copy()
    params.pop('page', None)
    qs_params = params.urlencode()

    return render(request, 'catalogo/lista_productos.html', {
        'productos': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'qs_params': qs_params,
        'categorias': Categoria.objects.all(),
        'categoria_actual': categoria_actual,
        'q': q,
        'orden_actual': orden,
        'precio_min': precio_min,
        'precio_max': precio_max,
        'solo_en_stock': request.GET.get('en_stock') == '1',
        'total_resultados': paginator.count,
    })


# --- Detalle producto -----------------------------------------------------

def _detalle_render(request, producto):
    # Resenas aprobadas y agregados
    resenas = producto.resenas.filter(aprobada=True).select_related('usuario')
    rating_promedio = producto.rating_promedio
    total_resenas = producto.total_resenas

    # Productos relacionados: misma categoria, excluyendo este, max 4
    relacionados = (
        Producto.objects
        .filter(disponible=True, categoria=producto.categoria)
        .exclude(pk=producto.pk)
        .select_related('categoria')
        .prefetch_related('imagenes', 'variantes')[:4]
    )

    # Ya valoró? (para mostrar/ocultar formulario)
    ya_valoro = False
    puede_valorar = False
    if request.user.is_authenticated:
        from pedidos.models import ItemPedido
        ya_valoro = Resena.objects.filter(producto=producto, usuario=request.user).exists()
        # Solo puede valorar si compro y el pedido esta entregado
        puede_valorar = (
            not ya_valoro and
            ItemPedido.objects.filter(
                producto=producto,
                pedido__usuario=request.user,
                pedido__estado='entregado',
            ).exists()
        )

    en_wishlist = (
        request.user.is_authenticated and
        Wishlist.objects.filter(usuario=request.user, producto=producto).exists()
    )

    return render(request, 'catalogo/detalle_producto.html', {
        'producto': producto,
        'resenas': resenas,
        'rating_promedio': rating_promedio,
        'total_resenas': total_resenas,
        'relacionados': relacionados,
        'ya_valoro': ya_valoro,
        'puede_valorar': puede_valorar,
        'en_wishlist': en_wishlist,
        'variantes': producto.variantes.filter(activa=True),
        'imagenes_galeria': producto.imagenes_galeria,
    })


def detalle_producto(request, slug):
    producto = get_object_or_404(
        Producto.objects.prefetch_related('imagenes', 'variantes'),
        slug=slug, disponible=True,
    )
    return _detalle_render(request, producto)


def detalle_producto_por_id(request, pk):
    """Compatibilidad con URLs viejas /producto/<id>/. Redirige a la URL con slug."""
    producto = get_object_or_404(Producto, pk=pk, disponible=True)
    return HttpResponseRedirect(reverse('catalogo:detalle_producto', args=[producto.slug]))


# --- Notify-me cuando vuelve el stock ------------------------------------

@require_POST
def avisame_stock(request, slug):
    producto = get_object_or_404(Producto, slug=slug)
    email = request.POST.get('email', '').strip()
    if not email:
        messages.error(request, 'Necesitamos tu email para avisarte.')
        return redirect('catalogo:detalle_producto', slug=slug)
    NotificacionStock.objects.get_or_create(producto=producto, email=email)
    messages.success(request, f'Te avisaremos a {email} cuando "{producto.nombre}" vuelva a estar disponible.')
    return redirect('catalogo:detalle_producto', slug=slug)


# --- Wishlist -------------------------------------------------------------

@login_required
def ver_wishlist(request):
    items = (
        Wishlist.objects
        .filter(usuario=request.user)
        .select_related('producto', 'producto__categoria')
        .prefetch_related('producto__imagenes', 'producto__variantes')
    )
    return render(request, 'catalogo/wishlist.html', {'items': items})


@login_required
@require_POST
def toggle_wishlist(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    obj, creado = Wishlist.objects.get_or_create(usuario=request.user, producto=producto)
    if not creado:
        obj.delete()
        en_wishlist = False
    else:
        en_wishlist = True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'en_wishlist': en_wishlist})
    return redirect(producto.get_absolute_url())


# --- Resenas --------------------------------------------------------------

@login_required
@require_POST
def crear_resena(request, slug):
    producto = get_object_or_404(Producto, slug=slug)
    from pedidos.models import ItemPedido
    compro_y_recibio = ItemPedido.objects.filter(
        producto=producto,
        pedido__usuario=request.user,
        pedido__estado='entregado',
    ).exists()
    if not compro_y_recibio:
        messages.error(request, 'Solo puedes resenar productos que ya recibiste.')
        return redirect('catalogo:detalle_producto', slug=slug)

    try:
        rating = int(request.POST.get('rating', 0))
    except (ValueError, TypeError):
        rating = 0
    titulo = request.POST.get('titulo', '').strip()[:120]
    comentario = request.POST.get('comentario', '').strip()

    if rating < 1 or rating > 5 or len(comentario) < 10:
        messages.error(request, 'Calificacion entre 1 y 5 y comentario de al menos 10 caracteres.')
        return redirect('catalogo:detalle_producto', slug=slug)

    Resena.objects.update_or_create(
        producto=producto, usuario=request.user,
        defaults={'rating': rating, 'titulo': titulo, 'comentario': comentario, 'aprobada': True},
    )
    messages.success(request, 'Gracias por tu resena.')
    return redirect('catalogo:detalle_producto', slug=slug)


# --- Newsletter -----------------------------------------------------------

@require_POST
def suscribir_newsletter(request):
    email = request.POST.get('email', '').strip()
    if not email or '@' not in email:
        messages.error(request, 'Email invalido.')
        return redirect(request.META.get('HTTP_REFERER', '/'))
    SuscriptorNewsletter.objects.get_or_create(email=email, defaults={'activo': True})
    messages.success(request, 'Te suscribiste al newsletter. Gracias!')
    return redirect(request.META.get('HTTP_REFERER', '/'))


# --- Paginas estaticas (renderizan templates simples) --------------------

def sobre_nosotros(request):
    return render(request, 'paginas/sobre_nosotros.html')


def pagina_envios(request):
    return render(request, 'paginas/envios.html')


def pagina_terminos(request):
    return render(request, 'paginas/terminos.html')


def pagina_privacidad(request):
    return render(request, 'paginas/privacidad.html')


def pagina_contacto(request):
    return render(request, 'paginas/contacto.html')


# --- Newsletter unsubscribe (publico, por token) -------------------------

def unsubscribe_newsletter(request, token):
    """Pagina publica de baja del newsletter."""
    # Token del modo prueba/preview: no es un suscriptor real. Mostramos un
    # mensaje claro en vez de "link no valido" (evita el falso susto al probar).
    if token == 'preview-test':
        return render(request, 'catalogo/unsubscribe_ok.html', {'preview': True})
    s = SuscriptorNewsletter.objects.filter(token_baja=token).first()
    if s and s.activo:
        s.activo = False
        s.save(update_fields=['activo'])
        return render(request, 'catalogo/unsubscribe_ok.html', {'email': s.email})
    if s:
        return render(request, 'catalogo/unsubscribe_ok.html', {'email': s.email, 'ya_dado_de_baja': True})
    return render(request, 'catalogo/unsubscribe_ok.html', {'invalido': True})
