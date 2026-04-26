import mercadopago
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.core.mail import send_mail
from .models import Pedido, ItemPedido
from carrito.models import Carrito, ItemCarrito


def _enviar_confirmacion(pedido):
    """Envía email de confirmación al cliente cuando el pago es exitoso."""
    if not pedido.usuario.email:
        return
    try:
        items_texto = '\n'.join(
            f"  - {item.producto.nombre} x{item.cantidad}: ${int(item.precio_unitario * item.cantidad):,}".replace(',', '.')
            for item in pedido.items.all()
        )
        mensaje = f"""Hola {pedido.usuario.username},

¡Tu pedido #{pedido.pk} ha sido confirmado! 🌿

{items_texto}

Total: ${int(pedido.total):,}

Dirección de entrega: {pedido.direccion_entrega}
Teléfono: {pedido.telefono}

Nos contactaremos contigo pronto para coordinar la entrega.

Si tienes dudas, escríbenos por WhatsApp: +56 9 8956 0937

— Aflora Natural
""".replace(',', '.')

        send_mail(
            subject=f'Pedido #{pedido.pk} confirmado — Aflora Natural',
            message=mensaje,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pedido.usuario.email],
            fail_silently=True,  # no rompe el flujo si el email falla
        )
    except Exception:
        pass


def _crear_preferencia_mp(pedido, request):
    """Crea una preferencia de pago en Mercado Pago y devuelve la URL de checkout."""
    sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

    base_url = request.build_absolute_uri('/')[:-1]  # ej: http://127.0.0.1:8000

    items = []
    for item in pedido.items.all():
        items.append({
            "title": item.producto.nombre,
            "quantity": item.cantidad,
            "unit_price": float(item.precio_unitario),
            "currency_id": "CLP",
        })

    preference_data = {
        "items": items,
        "back_urls": {
            "success": f"{base_url}/pedidos/pago/exitoso/",
            "failure": f"{base_url}/pedidos/pago/fallido/",
            "pending": f"{base_url}/pedidos/pago/pendiente/",
        },
        # auto_return hace que MP redirija automáticamente sin mostrar el botón
        # "Volver al comercio". Solo aplica para pagos aprobados.
        "auto_return": "approved",
        "external_reference": str(pedido.id),
        "statement_descriptor": "Aflora Natural",
    }

    response = sdk.preference().create(preference_data)
    preference = response["response"]
    # sandbox_init_point para pruebas, init_point para producción
    return preference.get("sandbox_init_point") or preference.get("init_point")


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
                    ItemPedido.objects.create(
                        pedido=pedido,
                        producto=item.producto,
                        cantidad=item.cantidad,
                        precio_unitario=item.producto.precio
                    )
                carrito.items.all().delete()
        except Exception as e:
            messages.error(request, 'Error al crear el pedido. Intenta de nuevo.')
            return redirect('carrito:ver_carrito')

        # Redirigir a Mercado Pago
        try:
            checkout_url = _crear_preferencia_mp(pedido, request)
            if checkout_url:
                return redirect(checkout_url)
        except Exception:
            messages.warning(request, 'Pedido creado. Hubo un problema al conectar con el sistema de pago.')

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


# ── Callbacks de Mercado Pago ──────────────────────────────────────────────

def pago_exitoso(request):
    pedido_id = request.GET.get('external_reference')
    if pedido_id:
        try:
            with transaction.atomic():
                # select_for_update en el pedido evita que dos requests simultáneos
                # (MP puede reintentar el redirect) procesen el mismo pedido dos veces.
                pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
                if pedido.estado == 'pendiente':
                    # Descontar stock al confirmar el pago
                    for item in pedido.items.all():
                        producto = item.producto.__class__.objects.select_for_update().get(pk=item.producto.pk)
                        if item.cantidad > producto.stock:
                            # Stock insuficiente al momento de confirmar — caso extremo
                            pedido.estado = 'cancelado'
                            pedido.save()
                            return render(request, 'pedidos/pago_resultado.html', {
                                'titulo': 'Stock insuficiente',
                                'mensaje': f'Lo sentimos, "{producto.nombre}" se agotó mientras procesabas el pago. Contáctanos por WhatsApp.',
                                'tipo': 'error',
                            })
                        producto.stock -= item.cantidad
                        if producto.stock == 0:
                            producto.disponible = False
                        producto.save()
                    pedido.estado = 'confirmado'
                    pedido.save()
                    _enviar_confirmacion(pedido)
            if request.user.is_authenticated and pedido.usuario == request.user:
                messages.success(request, '¡Pago recibido! Tu pedido está confirmado.')
                return redirect('pedidos:detalle_pedido', pk=pedido.pk)
        except Pedido.DoesNotExist:
            pass
    return render(request, 'pedidos/pago_resultado.html', {
        'titulo': '¡Pago exitoso!',
        'mensaje': 'Tu pedido fue confirmado. Te contactaremos pronto para coordinar la entrega.',
        'tipo': 'exito',
    })


def pago_fallido(request):
    pedido_id = request.GET.get('external_reference')
    if pedido_id:
        try:
            pedido = Pedido.objects.get(pk=pedido_id)
            pedido.estado = 'cancelado'
            pedido.save()
        except Pedido.DoesNotExist:
            pass
    return render(request, 'pedidos/pago_resultado.html', {
        'titulo': 'Pago no completado',
        'mensaje': 'El pago no pudo procesarse. Puedes intentarlo nuevamente o contactarnos por WhatsApp.',
        'tipo': 'error',
    })


def pago_pendiente(request):
    return render(request, 'pedidos/pago_resultado.html', {
        'titulo': 'Pago pendiente',
        'mensaje': 'Tu pago está siendo procesado. Te notificaremos cuando se confirme.',
        'tipo': 'pendiente',
    })
