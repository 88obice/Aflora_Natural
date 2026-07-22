import csv
import logging
from datetime import timedelta
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
from django import forms
from django.core.mail import send_mail
from django.conf import settings

from pedidos.models import Pedido, ItemPedido
from catalogo.models import Producto, Categoria, NotificacionStock
from carrito.models import Carrito

logger = logging.getLogger('aflora.gestion')


def solo_staff(user):
    return user.is_staff


# --- Emails de estado de pedido ------------------------------------------

def _enviar_email_cambio_estado(pedido, estado_nuevo):
    """
    Envia email al cliente cuando el estado del pedido cambia a
    'enviado' o 'entregado'. Silencioso ante errores (no rompe el flujo).
    """
    if not pedido.email_destinatario:
        return

    asunto_y_cuerpo = {
        'enviado': (
            'Tu pedido #{pid} fue enviado — Aflora Natural',
            """Hola {nombre},

Tu pedido #{pid} ya esta en camino!

{tracking}
Entrega en: {dir}

Ver estado de tu pedido: {link}

Si tienes dudas: WhatsApp +56 9 8956 0937

-- Aflora Natural
""",
        ),
        'entregado': (
            'Tu pedido #{pid} fue entregado — Aflora Natural',
            """Hola {nombre},

Confirmamos que tu pedido #{pid} fue entregado.

Esperamos que disfrutes tus productos. Si quieres dejarnos una resena,
puedes hacerlo ingresando a tu cuenta en nuestra tienda.

Gracias por elegir Aflora Natural!
WhatsApp +56 9 8956 0937

-- Aflora Natural
""",
        ),
    }

    if estado_nuevo not in asunto_y_cuerpo:
        return

    asunto_tpl, cuerpo_tpl = asunto_y_cuerpo[estado_nuevo]

    tracking = ''
    if estado_nuevo == 'enviado' and pedido.codigo_seguimiento:
        tracking = 'Codigo de seguimiento: {}\n'.format(pedido.codigo_seguimiento)

    # Link de tracking publico (con token impredecible) — funciona sin login
    base_url = getattr(settings, 'BASE_URL', '').rstrip('/')
    link_tracking = '{}/pedidos/track/{}/'.format(base_url, pedido.token_publico) if pedido.token_publico else ''

    asunto = asunto_tpl.format(pid=pedido.pk)
    cuerpo = cuerpo_tpl.format(
        nombre=pedido.nombre_destinatario,
        pid=pedido.pk,
        tracking=tracking,
        dir=pedido.direccion_formateada(),
        link=link_tracking,
    )

    try:
        send_mail(
            subject=asunto,
            message=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pedido.email_destinatario],
            fail_silently=True,
        )
        logger.info('Email estado "%s" enviado para pedido #%s a %s',
                    estado_nuevo, pedido.pk, pedido.email_destinatario)
    except Exception:
        logger.exception('Error enviando email estado "%s" para pedido #%s',
                         estado_nuevo, pedido.pk)


# --- Producto form (CRUD) ------------------------------------------------

def _bootstrap_fields(form_instance):
    """Aplica clases Bootstrap a todos los campos de un form."""
    for f in form_instance.fields.values():
        css = f.widget.attrs.get('class', '')
        if isinstance(f.widget, forms.CheckboxInput):
            f.widget.attrs['class'] = (css + ' form-check-input').strip()
        elif isinstance(f.widget, forms.Select):
            f.widget.attrs['class'] = (css + ' form-select').strip()
        else:
            f.widget.attrs['class'] = (css + ' form-control').strip()


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ['categoria', 'nombre', 'sku', 'descripcion_corta', 'descripcion',
                  'precio', 'stock', 'imagen', 'disponible', 'destacado']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap_fields(self)


# --- Formsets de galería y variantes -------------------------------------

from catalogo.models import ImagenProducto, Variante as VarianteModel
from django.forms import inlineformset_factory


class _ImagenForm(forms.ModelForm):
    class Meta:
        model = ImagenProducto
        fields = ['imagen', 'alt', 'orden']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['imagen'].widget.attrs['class'] = 'form-control form-control-sm'
        self.fields['alt'].widget.attrs.update({'class': 'form-control form-control-sm',
                                                'placeholder': 'Texto alternativo (accesibilidad)'})
        self.fields['orden'].widget.attrs.update({'class': 'form-control form-control-sm', 'style': 'width:70px'})


class _VarianteForm(forms.ModelForm):
    class Meta:
        model = VarianteModel
        fields = ['nombre', 'sku', 'precio', 'stock', 'activa', 'orden']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].widget.attrs.update({'class': 'form-control form-control-sm',
                                                   'placeholder': 'Ej: 200g, Lavanda'})
        self.fields['sku'].widget.attrs.update({'class': 'form-control form-control-sm',
                                                'placeholder': 'SKU opcional'})
        self.fields['precio'].widget.attrs['class'] = 'form-control form-control-sm'
        self.fields['stock'].widget.attrs['class'] = 'form-control form-control-sm'
        self.fields['activa'].widget.attrs['class'] = 'form-check-input'
        self.fields['orden'].widget.attrs.update({'class': 'form-control form-control-sm', 'style': 'width:60px'})


ImagenFormSet = inlineformset_factory(
    Producto, ImagenProducto,
    form=_ImagenForm,
    extra=3,
    max_num=10,
    can_delete=True,
)

VarianteFormSet = inlineformset_factory(
    Producto, VarianteModel,
    form=_VarianteForm,
    extra=2,
    max_num=20,
    can_delete=True,
)


# --- Dashboard -----------------------------------------------------------

@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def dashboard(request):
    hace_30 = timezone.now() - timedelta(days=30)

    ventas_30 = Pedido.objects.filter(
        estado__in=['confirmado', 'preparando', 'enviado', 'entregado'],
        creado__gte=hace_30,
    ).aggregate(total=Sum('total'), n=Count('id'))

    ventas_mes_actual = Pedido.objects.filter(
        estado__in=['confirmado', 'preparando', 'enviado', 'entregado'],
        creado__year=timezone.now().year, creado__month=timezone.now().month,
    ).aggregate(total=Sum('total'), n=Count('id'))

    productos_top = (
        ItemPedido.objects
        .filter(pedido__estado__in=['confirmado', 'preparando', 'enviado', 'entregado'])
        .values('producto__nombre')
        .annotate(vendidos=Sum('cantidad'), ingresos=Sum(F('cantidad') * F('precio_unitario')))
        .order_by('-vendidos')[:5]
    )

    productos_bajo_stock = Producto.objects.filter(stock__lte=3, disponible=True).order_by('stock')[:10]
    notificaciones_pendientes = NotificacionStock.objects.filter(notificado=False).count()

    return render(request, 'gestion/dashboard.html', {
        'total_pedidos': Pedido.objects.count(),
        'pedidos_nuevos': Pedido.objects.filter(estado='confirmado').count(),
        'pedidos_pendientes_pago': Pedido.objects.filter(estado='pendiente').count(),
        'productos_bajo_stock': productos_bajo_stock,
        'productos_bajo_stock_count': productos_bajo_stock.count(),
        'pedidos_recientes': Pedido.objects.order_by('-creado').prefetch_related('items')[:5],
        'ventas_30_total': ventas_30['total'] or 0,
        'ventas_30_n': ventas_30['n'] or 0,
        'ventas_mes_total': ventas_mes_actual['total'] or 0,
        'ventas_mes_n': ventas_mes_actual['n'] or 0,
        'productos_top': productos_top,
        'notificaciones_pendientes': notificaciones_pendientes,
    })


# --- Pedidos -------------------------------------------------------------

@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def lista_pedidos(request):
    estado = request.GET.get('estado', '')
    q = request.GET.get('q', '').strip()
    qs = Pedido.objects.order_by('-creado').prefetch_related('items')
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        from django.db.models import Q
        if q.isdigit():
            qs = qs.filter(Q(id=q) | Q(usuario__username__icontains=q) | Q(email_cliente__icontains=q) | Q(nombre_cliente__icontains=q))
        else:
            qs = qs.filter(Q(usuario__username__icontains=q) | Q(email_cliente__icontains=q) | Q(nombre_cliente__icontains=q) | Q(codigo_seguimiento__icontains=q))

    # Paginacion real (antes se cortaba con [:200] en silencio).
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    # Querystring sin 'page' para reusar en los links de paginacion
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'gestion/pedidos.html', {
        'pedidos': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'qs_params': params.urlencode(),
        'total_pedidos': paginator.count,
        'estados': Pedido.ESTADO_CHOICES,
        'estado_actual': estado,
        'q': q,
    })


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def detalle_pedido(request, pk):
    pedido = get_object_or_404(Pedido.objects.prefetch_related('items__producto', 'items__variante'), pk=pk)
    if request.method == 'POST':
        nuevo_estado = request.POST.get('estado')
        codigo = request.POST.get('codigo_seguimiento', '').strip()
        estados_validos = [e[0] for e in Pedido.ESTADO_CHOICES]
        estado_anterior = pedido.estado
        if nuevo_estado in estados_validos:
            pedido.estado = nuevo_estado
        if codigo is not None:
            pedido.codigo_seguimiento = codigo[:80]
        pedido.save()
        # Enviar email al cliente si el estado cambio a "enviado" o "entregado"
        if nuevo_estado != estado_anterior and nuevo_estado in ('enviado', 'entregado'):
            _enviar_email_cambio_estado(pedido, nuevo_estado)
        messages.success(request, 'Pedido actualizado.')
        return redirect('gestion:detalle_pedido', pk=pk)
    return render(request, 'gestion/detalle_pedido.html', {'pedido': pedido})


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def confirmar_pago_transferencia(request, pk):
    """
    La duenia confirma manualmente que vio el deposito en su cuenta bancaria.
    Reutiliza _confirmar_pedido() de pedidos para descontar stock y mandar emails.

    Opcionalmente recibe `monto_recibido` para registrar discrepancias.
    El JS del template ya advierte si no coincide; aca solo logueamos y
    avisamos en el mensaje flash.
    """
    if request.method != 'POST':
        return redirect('gestion:detalle_pedido', pk=pk)
    pedido = get_object_or_404(Pedido, pk=pk)
    if pedido.metodo_pago != 'transferencia':
        messages.error(request, 'Este pedido no es por transferencia.')
        return redirect('gestion:detalle_pedido', pk=pk)
    if pedido.estado != 'pendiente':
        messages.warning(request, 'Este pedido ya no está pendiente (estado: {}).'.format(pedido.get_estado_display()))
        return redirect('gestion:detalle_pedido', pk=pk)

    # Validacion opcional del monto recibido
    monto_recibido_raw = request.POST.get('monto_recibido', '').strip()
    discrepancia_msg = ''
    if monto_recibido_raw:
        try:
            monto_recibido = int(monto_recibido_raw)
        except (TypeError, ValueError):
            messages.error(request, 'Monto recibido inválido.')
            return redirect('gestion:detalle_pedido', pk=pk)
        total_pedido = int(pedido.total)
        if monto_recibido != total_pedido:
            diferencia = monto_recibido - total_pedido
            if diferencia < 0:
                discrepancia_msg = (
                    ' ⚠ Atención: cliente transfirió ${} pero el pedido era ${} (faltan ${}). '
                    'Contactá al cliente.'
                ).format(
                    '{:,}'.format(monto_recibido).replace(',', '.'),
                    '{:,}'.format(total_pedido).replace(',', '.'),
                    '{:,}'.format(abs(diferencia)).replace(',', '.'),
                )
            else:
                discrepancia_msg = (
                    ' Cliente transfirió ${} (${} de más). Acordate de devolverle la diferencia.'
                ).format(
                    '{:,}'.format(monto_recibido).replace(',', '.'),
                    '{:,}'.format(diferencia).replace(',', '.'),
                )
            logger.warning(
                'Pedido #%s: discrepancia en monto transferencia. Pedido=%s Recibido=%s Dif=%s',
                pedido.pk, total_pedido, monto_recibido, diferencia,
            )

    from pedidos.views import _confirmar_pedido
    p = _confirmar_pedido(pedido, mp_status='transferencia_manual')
    if p.estado == 'confirmado':
        messages.success(
            request,
            'Pago confirmado. Stock descontado y email enviado al cliente.' + discrepancia_msg
        )
    else:
        messages.error(request, 'No se pudo confirmar (estado quedó en "{}"). Revisa stock.'.format(p.get_estado_display()))
    return redirect('gestion:detalle_pedido', pk=pk)


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def exportar_pedidos_csv(request):
    """Exporta pedidos filtrados a CSV (para SII / contabilidad)."""
    estado = request.GET.get('estado', '')
    desde = request.GET.get('desde', '')
    hasta = request.GET.get('hasta', '')
    qs = Pedido.objects.order_by('creado').prefetch_related('items')
    if estado:
        qs = qs.filter(estado=estado)
    if desde:
        qs = qs.filter(creado__gte=desde)
    if hasta:
        qs = qs.filter(creado__lte=hasta)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="pedidos_aflora.csv"'
    response.write('﻿')  # BOM para que Excel abra UTF-8 bien
    w = csv.writer(response)
    w.writerow(['ID', 'Fecha', 'Estado', 'Cliente', 'Email', 'Telefono',
                'Metodo envio', 'Comuna', 'Region', 'Direccion',
                'Subtotal', 'Costo envio', 'Total',
                'MP Payment ID', 'MP Status', 'Codigo seguimiento', 'Items'])
    for p in qs:
        items = '; '.join('{}x{}'.format(it.cantidad, it.nombre_mostrar()) for it in p.items.all())
        w.writerow([
            p.id, p.creado.strftime('%Y-%m-%d %H:%M'), p.get_estado_display(),
            p.nombre_destinatario, p.email_destinatario or '', p.telefono,
            p.get_metodo_envio_display(), p.comuna, p.region, p.direccion_formateada(),
            int(p.subtotal), int(p.costo_envio), int(p.total),
            p.mp_payment_id, p.mp_status, p.codigo_seguimiento, items,
        ])
    return response


# --- Productos CRUD ------------------------------------------------------

@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def lista_productos(request):
    q = request.GET.get('q', '').strip()
    qs = Producto.objects.select_related('categoria').order_by('categoria', 'nombre')
    if q:
        qs = qs.filter(nombre__icontains=q)
    return render(request, 'gestion/productos.html', {'productos': qs, 'q': q})


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def crear_producto(request):
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            producto = form.save()
            # Guardar formsets con la instancia recien creada
            imagen_fs = ImagenFormSet(request.POST, request.FILES, instance=producto, prefix='imagenes')
            variante_fs = VarianteFormSet(request.POST, instance=producto, prefix='variantes')
            if imagen_fs.is_valid() and variante_fs.is_valid():
                imagen_fs.save()
                variante_fs.save()
                messages.success(request, 'Producto "{}" creado.'.format(producto.nombre))
                return redirect('gestion:productos')
            else:
                # Si los formsets fallan, borrar el producto recien creado y volver al form
                producto.delete()
                messages.error(request, 'Hay errores en la galería o las variantes. Revisalos abajo.')
        else:
            imagen_fs = ImagenFormSet(request.POST, request.FILES, prefix='imagenes')
            variante_fs = VarianteFormSet(request.POST, prefix='variantes')
    else:
        form = ProductoForm()
        imagen_fs = ImagenFormSet(prefix='imagenes')
        variante_fs = VarianteFormSet(prefix='variantes')
    return render(request, 'gestion/producto_form.html', {
        'form': form, 'modo': 'crear',
        'imagen_formset': imagen_fs,
        'variante_formset': variante_fs,
    })


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def editar_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        imagen_fs = ImagenFormSet(request.POST, request.FILES, instance=producto, prefix='imagenes')
        variante_fs = VarianteFormSet(request.POST, instance=producto, prefix='variantes')
        if form.is_valid() and imagen_fs.is_valid() and variante_fs.is_valid():
            form.save()
            imagen_fs.save()
            variante_fs.save()
            messages.success(request, 'Producto actualizado.')
            return redirect('gestion:productos')
        else:
            if not form.is_valid():
                messages.error(request, 'Corrige los errores del formulario.')
    else:
        form = ProductoForm(instance=producto)
        imagen_fs = ImagenFormSet(instance=producto, prefix='imagenes')
        variante_fs = VarianteFormSet(instance=producto, prefix='variantes')
    return render(request, 'gestion/producto_form.html', {
        'form': form, 'modo': 'editar', 'producto': producto,
        'imagen_formset': imagen_fs,
        'variante_formset': variante_fs,
    })


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def agregar_stock(request, pk):
    """
    Suma una cantidad al stock actual de un producto (no reemplaza).
    Solo aplica a productos SIN variantes; si tiene variantes, el stock
    vive en cada variante y hay que editarlas desde el form del producto.
    """
    producto = get_object_or_404(Producto, pk=pk)
    if request.method != 'POST':
        return redirect('gestion:productos')
    if producto.variantes.exists():
        messages.warning(
            request,
            'El producto "{}" tiene variantes. Edita el stock de cada variante desde el formulario del producto.'.format(producto.nombre)
        )
        return redirect('gestion:productos')
    try:
        cantidad = int(request.POST.get('cantidad', '0'))
    except (TypeError, ValueError):
        cantidad = 0
    if cantidad <= 0:
        messages.error(request, 'La cantidad a agregar debe ser mayor a 0.')
        return redirect('gestion:productos')
    if cantidad > 9999:
        messages.error(request, 'Cantidad inválida (maximo 9999 por vez).')
        return redirect('gestion:productos')
    stock_anterior = producto.stock
    producto.stock = stock_anterior + cantidad
    producto.save(update_fields=['stock', 'actualizado'])
    messages.success(
        request,
        'Stock de "{}" actualizado: {} → {} (+{})'.format(
            producto.nombre, stock_anterior, producto.stock, cantidad
        )
    )
    return redirect('gestion:productos')


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def eliminar_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        nombre = producto.nombre
        producto.delete()
        messages.success(request, 'Producto "{}" eliminado.'.format(nombre))
        return redirect('gestion:productos')
    return render(request, 'gestion/producto_confirmar_borrado.html', {'producto': producto})


# --- Notificaciones de stock --------------------------------------------

@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def notificaciones_stock(request):
    pendientes = NotificacionStock.objects.filter(notificado=False).select_related('producto').order_by('-creado')
    return render(request, 'gestion/notificaciones_stock.html', {'notificaciones': pendientes})


# --- Newsletter -----------------------------------------------------------

class _CampanaForm(forms.ModelForm):
    class Meta:
        from catalogo.models import CampanaNewsletter
        model = CampanaNewsletter
        fields = ['asunto', 'cuerpo', 'nota_interna']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs['class'] = 'form-control'
        self.fields['cuerpo'].widget.attrs['rows'] = 12
        self.fields['cuerpo'].widget.attrs['placeholder'] = (
            "Hola!\n\nEste mes en Aflora Natural...\n\n(El sistema agrega automaticamente "
            "el link de baja al final del email.)"
        )


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def newsletter_lista(request):
    from catalogo.models import CampanaNewsletter, SuscriptorNewsletter
    campanas = CampanaNewsletter.objects.all()
    total_suscriptores = SuscriptorNewsletter.objects.filter(activo=True).count()
    return render(request, 'gestion/newsletter_lista.html', {
        'campanas': campanas,
        'total_suscriptores': total_suscriptores,
    })


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def newsletter_crear(request):
    if request.method == 'POST':
        form = _CampanaForm(request.POST)
        if form.is_valid():
            c = form.save()
            messages.success(request, 'Campana creada como borrador.')
            return redirect('gestion:newsletter_detalle', pk=c.pk)
    else:
        form = _CampanaForm()
    return render(request, 'gestion/newsletter_form.html', {'form': form, 'modo': 'crear'})


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def newsletter_detalle(request, pk):
    from catalogo.models import CampanaNewsletter, SuscriptorNewsletter
    c = get_object_or_404(CampanaNewsletter, pk=pk)
    total_suscriptores = SuscriptorNewsletter.objects.filter(activo=True).count()
    if request.method == 'POST':
        if c.estado == 'enviada':
            messages.error(request, 'Esta campana ya fue enviada, no se puede editar.')
        else:
            form = _CampanaForm(request.POST, instance=c)
            if form.is_valid():
                form.save()
                messages.success(request, 'Campana actualizada.')
                return redirect('gestion:newsletter_detalle', pk=c.pk)
    else:
        form = _CampanaForm(instance=c)
    return render(request, 'gestion/newsletter_form.html', {
        'form': form, 'modo': 'editar', 'campana': c,
        'total_suscriptores': total_suscriptores,
    })


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def newsletter_enviar_prueba(request, pk):
    from catalogo.models import CampanaNewsletter
    from catalogo.newsletter_sender import enviar_campana
    c = get_object_or_404(CampanaNewsletter, pk=pk)
    email_prueba = request.POST.get('email_prueba', '').strip() or request.user.email
    if not email_prueba:
        messages.error(request, 'No tienes email configurado. Pon uno en el campo o en tu perfil.')
        return redirect('gestion:newsletter_detalle', pk=pk)
    base_url = request.build_absolute_uri('/')[:-1]
    res = enviar_campana(c, base_url, dry_email=email_prueba)
    if res['enviados']:
        messages.success(request, f'Email de prueba enviado a {email_prueba}.')
    else:
        messages.error(request, 'No se pudo enviar el email de prueba. Revisa los logs.')
    return redirect('gestion:newsletter_detalle', pk=pk)


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def newsletter_enviar_real(request, pk):
    from catalogo.models import CampanaNewsletter
    from catalogo.newsletter_sender import enviar_campana
    c = get_object_or_404(CampanaNewsletter, pk=pk)
    if c.estado == 'enviada':
        messages.error(request, 'Esta campana ya fue enviada.')
        return redirect('gestion:newsletter_detalle', pk=pk)
    if request.method == 'POST':
        # Confirmacion explicita
        if request.POST.get('confirmar') == 'SI':
            base_url = request.build_absolute_uri('/')[:-1]
            res = enviar_campana(c, base_url)
            messages.success(request,
                f"Campana enviada: {res['enviados']} enviados, {res['fallidos']} fallidos.")
        else:
            messages.error(request, 'Cancelado: no escribiste SI para confirmar.')
    return redirect('gestion:newsletter_detalle', pk=pk)


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def newsletter_suscriptores(request):
    from catalogo.models import SuscriptorNewsletter
    suscriptores = SuscriptorNewsletter.objects.all()
    return render(request, 'gestion/newsletter_suscriptores.html', {'suscriptores': suscriptores})


# --- Categorias ----------------------------------------------------------

class _CategoriaForm(forms.ModelForm):
    class Meta:
        from catalogo.models import Categoria
        model = Categoria
        fields = ['nombre', 'descripcion', 'imagen', 'orden']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs['class'] = 'form-control'


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def categorias_lista(request):
    from catalogo.models import Categoria
    from django.db.models import Count
    cats = Categoria.objects.annotate(total_productos=Count('productos'))
    return render(request, 'gestion/categorias.html', {'categorias': cats})


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def categoria_crear(request):
    if request.method == 'POST':
        form = _CategoriaForm(request.POST, request.FILES)
        if form.is_valid():
            c = form.save()
            messages.success(request, f'Categoria "{c.nombre}" creada.')
            return redirect('gestion:categorias_lista')
    else:
        form = _CategoriaForm()
    return render(request, 'gestion/categoria_form.html', {'form': form, 'modo': 'crear'})


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def categoria_editar(request, pk):
    from catalogo.models import Categoria
    cat = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        form = _CategoriaForm(request.POST, request.FILES, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoria actualizada.')
            return redirect('gestion:categorias_lista')
    else:
        form = _CategoriaForm(instance=cat)
    return render(request, 'gestion/categoria_form.html', {'form': form, 'modo': 'editar', 'categoria': cat})


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def categoria_eliminar(request, pk):
    from catalogo.models import Categoria
    cat = get_object_or_404(Categoria, pk=pk)
    n_prod = cat.productos.count()
    if request.method == 'POST':
        if n_prod > 0:
            messages.error(request,
                f'No se puede eliminar "{cat.nombre}": tiene {n_prod} producto(s) asociado(s). '
                f'Mueve los productos a otra categoria antes.')
            return redirect('gestion:categorias_lista')
        nombre = cat.nombre
        cat.delete()
        messages.success(request, f'Categoria "{nombre}" eliminada.')
        return redirect('gestion:categorias_lista')
    return render(request, 'gestion/categoria_confirmar_borrado.html',
                  {'categoria': cat, 'n_productos': n_prod})


# --- Resenas (moderacion) ------------------------------------------------

@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def resenas_lista(request):
    from catalogo.models import Resena
    qs = Resena.objects.select_related('producto', 'usuario').order_by('-creado')

    estado = request.GET.get('estado', '')
    if estado == 'aprobadas':
        qs = qs.filter(aprobada=True)
    elif estado == 'pendientes':
        qs = qs.filter(aprobada=False)

    rating = request.GET.get('rating', '')
    if rating.isdigit():
        qs = qs.filter(rating=int(rating))

    return render(request, 'gestion/resenas.html', {
        'resenas': qs[:200],
        'estado_actual': estado,
        'rating_actual': rating,
        'total_pendientes': Resena.objects.filter(aprobada=False).count(),
    })


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def resena_toggle_aprobar(request, pk):
    from catalogo.models import Resena
    r = get_object_or_404(Resena, pk=pk)
    if request.method == 'POST':
        r.aprobada = not r.aprobada
        r.save(update_fields=['aprobada'])
        accion = 'aprobada' if r.aprobada else 'oculta'
        messages.success(request, f'Resena #{r.pk} {accion}.')
    return redirect('gestion:resenas_lista')


@login_required
@user_passes_test(solo_staff, login_url='catalogo:inicio')
def resena_eliminar(request, pk):
    from catalogo.models import Resena
    r = get_object_or_404(Resena, pk=pk)
    if request.method == 'POST':
        r.delete()
        messages.success(request, f'Resena #{pk} eliminada.')
    return redirect('gestion:resenas_lista')
