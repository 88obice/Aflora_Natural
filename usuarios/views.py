from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegistroForm, LoginForm, PerfilForm, DireccionForm
from .models import PerfilUsuario, Direccion
from aflora_natural.antispam import honeypot_ok, rate_limited


def registro(request):
    if request.method == 'POST':
        # Anti-spam: honeypot + límite de registros por IP.
        if not honeypot_ok(request):
            return redirect('catalogo:inicio')  # bot: descartar en silencio
        if rate_limited(request, 'registro', limit=5, window=600):
            messages.error(request, 'Demasiados intentos. Esperá unos minutos e intentá de nuevo.')
            return redirect('usuarios:registro')
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Con multiples backends configurados, login() exige indicar cual.
            login(request, user, backend='usuarios.backends.EmailBackend')
            messages.success(request, '¡Listo! Tu cuenta fue creada.')
            return redirect('catalogo:inicio')
    else:
        form = RegistroForm()
    return render(request, 'usuarios/registro.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        # Rate limit contra fuerza bruta de contraseñas (por IP).
        if rate_limited(request, 'login', limit=10, window=300):
            messages.error(request, 'Demasiados intentos de inicio de sesión. Esperá unos minutos.')
            return redirect('usuarios:login')
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            # Guardar sesion_key anonima ANTES de login() — login() la regenera
            sesion_key_anonima = request.session.session_key
            login(request, user)
            # Fusionar carrito anonimo al carrito del usuario
            _merge_carrito(sesion_key_anonima, user)
            next_url = request.GET.get('next') or request.POST.get('next')
            return redirect(next_url or 'catalogo:inicio')
    else:
        form = LoginForm()
    return render(request, 'usuarios/login.html', {'form': form, 'next': request.GET.get('next', '')})


def _merge_carrito(sesion_key_anonima, user):
    """
    Fusiona el carrito anonimo al carrito del usuario logueado.
    - Si un item ya existe en el carrito del usuario, suma cantidades (tope: stock disponible).
    - Borra el carrito anonimo al finalizar.
    """
    if not sesion_key_anonima:
        return
    from carrito.models import Carrito, ItemCarrito
    try:
        carrito_anonimo = Carrito.objects.get(sesion_key=sesion_key_anonima)
    except Carrito.DoesNotExist:
        return
    items_anonimos = list(carrito_anonimo.items.select_related('producto', 'variante').all())
    if not items_anonimos:
        carrito_anonimo.delete()
        return
    carrito_usuario, _ = Carrito.objects.get_or_create(usuario=user)
    for item in items_anonimos:
        stock_max = item.variante.stock if item.variante else item.producto.stock
        item_existente = carrito_usuario.items.filter(
            producto=item.producto, variante=item.variante
        ).first()
        if item_existente:
            nueva_cantidad = min(item_existente.cantidad + item.cantidad, stock_max)
            item_existente.cantidad = nueva_cantidad
            item_existente.save(update_fields=['cantidad'])
        else:
            cantidad = min(item.cantidad, stock_max)
            if cantidad > 0:
                ItemCarrito.objects.create(
                    carrito=carrito_usuario,
                    producto=item.producto,
                    variante=item.variante,
                    cantidad=cantidad,
                )
    carrito_anonimo.delete()


def logout_view(request):
    logout(request)
    return redirect('catalogo:inicio')


@login_required
def perfil(request):
    from pedidos.models import Pedido
    pedidos_recientes = Pedido.objects.filter(usuario=request.user).order_by('-creado').prefetch_related('items')[:5]
    direcciones = request.user.direcciones.all()
    return render(request, 'usuarios/perfil.html', {
        'pedidos_recientes': pedidos_recientes,
        'direcciones': direcciones,
    })


@login_required
def editar_perfil(request):
    perfil_obj, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)
    if request.method == 'POST':
        form = PerfilForm(request.POST, instance=perfil_obj, usuario=request.user)
        if form.is_valid():
            form.save_full(request.user)
            messages.success(request, 'Perfil actualizado.')
            return redirect('usuarios:perfil')
    else:
        form = PerfilForm(instance=perfil_obj, usuario=request.user)
    return render(request, 'usuarios/editar_perfil.html', {'form': form})


@login_required
def lista_direcciones(request):
    direcciones = request.user.direcciones.all()
    return render(request, 'usuarios/direcciones.html', {'direcciones': direcciones})


@login_required
def crear_direccion(request):
    if request.method == 'POST':
        form = DireccionForm(request.POST)
        if form.is_valid():
            d = form.save(commit=False)
            d.usuario = request.user
            d.save()
            messages.success(request, 'Direccion guardada.')
            return redirect('usuarios:direcciones')
    else:
        form = DireccionForm()
    return render(request, 'usuarios/direccion_form.html', {'form': form, 'modo': 'crear'})


@login_required
def editar_direccion(request, pk):
    direccion = get_object_or_404(Direccion, pk=pk, usuario=request.user)
    if request.method == 'POST':
        form = DireccionForm(request.POST, instance=direccion)
        if form.is_valid():
            form.save()
            messages.success(request, 'Direccion actualizada.')
            return redirect('usuarios:direcciones')
    else:
        form = DireccionForm(instance=direccion)
    return render(request, 'usuarios/direccion_form.html', {'form': form, 'modo': 'editar'})


@login_required
def eliminar_direccion(request, pk):
    direccion = get_object_or_404(Direccion, pk=pk, usuario=request.user)
    if request.method == 'POST':
        direccion.delete()
        messages.success(request, 'Direccion eliminada.')
    return redirect('usuarios:direcciones')
