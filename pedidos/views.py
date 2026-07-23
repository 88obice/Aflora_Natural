import hashlib
import hmac
import json
import logging
import mercadopago
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.core.mail import send_mail, mail_admins
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Pedido, ItemPedido
from .envios import calcular_costo_envio, comunas_disponibles
from carrito.models import Carrito, ItemCarrito
from carrito.views import get_or_create_carrito

logger = logging.getLogger('aflora.pedidos')


# --- Helpers --------------------------------------------------------------

def _enviar_confirmacion_cliente(pedido):
    if not pedido.email_destinatario:
        return
    items_texto = '\n'.join(
        '  - {} x{}: ${:,}'.format(
            it.nombre_mostrar(), it.cantidad, int(it.precio_unitario * it.cantidad)
        ).replace(',', '.')
        for it in pedido.items.all()
    )
    direccion = pedido.direccion_formateada()
    base_url = getattr(settings, 'BASE_URL', '').rstrip('/')
    link_tracking = '{}/pedidos/track/{}/'.format(base_url, pedido.token_publico) if pedido.token_publico else ''

    mensaje = """Hola {nombre},

Tu pedido #{pid} fue confirmado.

{items}

Subtotal: ${sub:,}
Envio:    ${env:,}
Total:    ${tot:,}

Entrega: {dir}
Telefono: {tel}

Ver estado de tu pedido: {link}

Nos contactamos contigo pronto para coordinar.
Si tienes dudas: WhatsApp +56 9 8956 0937

-- Aflora Natural
""".format(
        nombre=pedido.nombre_destinatario,
        pid=pedido.pk,
        items=items_texto,
        sub=int(pedido.subtotal),
        env=int(pedido.costo_envio),
        tot=int(pedido.total),
        dir=direccion,
        tel=pedido.telefono,
        link=link_tracking,
    ).replace(',', '.')

    try:
        send_mail(
            subject='Pedido #{} confirmado -- Aflora Natural'.format(pedido.pk),
            message=mensaje,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pedido.email_destinatario],
            fail_silently=False,
        )
    except Exception:
        # No rompemos el flujo del pedido, pero SI dejamos rastro: si el cliente
        # no recibe su confirmacion hay que poder saberlo (revisar logs/Sentry).
        logger.exception('No se pudo enviar email de confirmacion del pedido #%s', pedido.pk)


def _notificar_admin_nuevo_pedido(pedido):
    """Notifica al staff por email cuando entra un pedido confirmado."""
    items_texto = '\n'.join(
        '  - {} x{}'.format(it.nombre_mostrar(), it.cantidad)
        for it in pedido.items.all()
    )
    mensaje = """Nuevo pedido #{pid}

Cliente: {nombre} ({email})
Telefono: {tel}
Metodo: {met}
Direccion: {dir}

Items:
{items}

Subtotal: ${sub:,}
Envio:    ${env:,}
TOTAL:    ${tot:,}

Ver en gestion: /gestion/pedidos/{pid}/
""".format(
        pid=pedido.pk,
        nombre=pedido.nombre_destinatario,
        email=pedido.email_destinatario or 'sin email',
        tel=pedido.telefono,
        met=pedido.get_metodo_envio_display(),
        dir=pedido.direccion_formateada(),
        items=items_texto,
        sub=int(pedido.subtotal),
        env=int(pedido.costo_envio),
        tot=int(pedido.total),
    ).replace(',', '.')

    # mail_admins respeta settings.ADMINS. Si esta vacio, hacemos fallback al EMAIL_HOST_USER
    try:
        if getattr(settings, 'ADMINS', None):
            mail_admins(
                subject='Nuevo pedido #{}'.format(pedido.pk),
                message=mensaje, fail_silently=True,
            )
        elif settings.DEFAULT_FROM_EMAIL:
            send_mail(
                subject='Nuevo pedido #{} -- Aflora Natural'.format(pedido.pk),
                message=mensaje,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],
                fail_silently=True,
            )
    except Exception:
        pass


def _notificar_admin_transferencia_pendiente(pedido):
    """
    Notifica al admin que entro un pedido por transferencia que espera
    confirmacion manual de pago. Es distinto al email de MP confirmado
    porque acA todavia no se descuenta stock — la duenia tiene que
    verificar el deposito en su cuenta bancaria y confirmar desde gestion.
    """
    items_texto = '\n'.join(
        '  - {} x{}'.format(it.nombre_mostrar(), it.cantidad)
        for it in pedido.items.all()
    )
    mensaje = """Nuevo pedido POR TRANSFERENCIA #{pid} (esperando deposito)

Cliente: {nombre} ({email})
Telefono: {tel}
Direccion: {dir}

Items:
{items}

TOTAL: ${tot:,}

ACCION REQUERIDA: revisar tu cuenta bancaria y confirmar el pago
desde /gestion/pedidos/{pid}/ cuando llegue el deposito.

Ver en gestion: /gestion/pedidos/{pid}/
""".format(
        pid=pedido.pk,
        nombre=pedido.nombre_destinatario,
        email=pedido.email_destinatario or 'sin email',
        tel=pedido.telefono,
        dir=pedido.direccion_formateada(),
        items=items_texto,
        tot=int(pedido.total),
    ).replace(',', '.')
    try:
        if getattr(settings, 'ADMINS', None):
            mail_admins(
                subject='Pedido por transferencia #{} (esperando deposito)'.format(pedido.pk),
                message=mensaje, fail_silently=True,
            )
        elif settings.DEFAULT_FROM_EMAIL:
            send_mail(
                subject='Pedido por transferencia #{} -- Aflora Natural'.format(pedido.pk),
                message=mensaje,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],
                fail_silently=True,
            )
    except Exception:
        pass


def _crear_preferencia_mp(pedido, request):
    sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
    base_url = request.build_absolute_uri('/')[:-1]

    items = []
    for it in pedido.items.all():
        items.append({
            'title': it.nombre_mostrar()[:240],
            'quantity': it.cantidad,
            'unit_price': float(it.precio_unitario),
            'currency_id': 'CLP',
        })
    if pedido.costo_envio and pedido.costo_envio > 0:
        items.append({
            'title': 'Envio',
            'quantity': 1,
            'unit_price': float(pedido.costo_envio),
            'currency_id': 'CLP',
        })

    preference_data = {
        'items': items,
        'back_urls': {
            'success': '{}/pedidos/pago/exitoso/'.format(base_url),
            'failure': '{}/pedidos/pago/fallido/'.format(base_url),
            'pending': '{}/pedidos/pago/pendiente/'.format(base_url),
        },
        'auto_return': 'approved',
        'external_reference': str(pedido.id),
        'statement_descriptor': 'Aflora Natural',
        'notification_url': '{}/pedidos/webhook/mp/'.format(base_url),
    }

    response = sdk.preference().create(preference_data)
    pref = response.get('response', {})
    return pref.get('init_point') or pref.get('sandbox_init_point')


def _notificar_admin_sin_stock(pedido):
    """
    ALERTA: el pago fue recibido (MP aprobado o transferencia confirmada) pero
    al momento de confirmar ya no quedaba stock. El pedido queda cancelado y
    hay que REEMBOLSAR al cliente manualmente. Esto no debe pasar en silencio.
    """
    mensaje = """ALERTA -- Pedido #{pid} PAGADO pero SIN STOCK

El cliente pago, pero al confirmar el pedido ya no habia stock suficiente.
El pedido quedo CANCELADO. Hay que REEMBOLSAR al cliente manualmente.

Cliente: {nombre} ({email})
Telefono: {tel}
Metodo de pago: {pago}
MP Payment ID: {mpid}
TOTAL a reembolsar: ${tot:,}

Ver en gestion: /gestion/pedidos/{pid}/
""".format(
        pid=pedido.pk,
        nombre=pedido.nombre_destinatario,
        email=pedido.email_destinatario or 'sin email',
        tel=pedido.telefono,
        pago=pedido.get_metodo_pago_display(),
        mpid=pedido.mp_payment_id or 'N/A',
        tot=int(pedido.total),
    ).replace(',', '.')
    try:
        if getattr(settings, 'ADMINS', None):
            mail_admins(
                subject='ALERTA REEMBOLSO pedido #{} (pagado sin stock)'.format(pedido.pk),
                message=mensaje, fail_silently=False,
            )
        elif settings.DEFAULT_FROM_EMAIL:
            send_mail(
                subject='ALERTA REEMBOLSO pedido #{} -- Aflora Natural'.format(pedido.pk),
                message=mensaje,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],
                fail_silently=False,
            )
    except Exception:
        # Alerta critica (hay plata de por medio): si ni el email sale, que
        # quede en los logs con nivel ERROR para no perderlo.
        logger.exception('FALLO al enviar alerta de reembolso del pedido #%s', pedido.pk)


def _confirmar_pedido(pedido, mp_payment_id='', mp_status=''):
    """
    Confirma el pedido: descuenta stock, marca confirmado, manda emails.
    Idempotente: si ya esta confirmado (o cualquier estado != pendiente),
    no hace nada.

    Valida el stock de TODOS los items ANTES de descontar, para no dejar
    descuentos parciales si un item falla. Si falta stock, el pedido se
    cancela y se avisa al admin: el pago ya fue recibido y hay que reembolsar.
    """
    from catalogo.models import Variante, Producto
    sin_stock = False
    with transaction.atomic():
        p = Pedido.objects.select_for_update().get(pk=pedido.pk)
        if p.estado != 'pendiente':
            return p

        # Paso 1: bloquear y validar stock de todos los items sin descontar aun.
        a_descontar = []  # [(obj_bloqueado, cantidad)]
        for item in p.items.select_related('producto', 'variante').all():
            if item.variante:
                obj = Variante.objects.select_for_update().get(pk=item.variante.pk)
            else:
                obj = Producto.objects.select_for_update().get(pk=item.producto.pk)
            if item.cantidad > obj.stock:
                sin_stock = True
                break
            a_descontar.append((obj, item.cantidad))

        if mp_payment_id:
            p.mp_payment_id = mp_payment_id
        if mp_status:
            p.mp_status = mp_status

        if sin_stock:
            p.estado = 'cancelado'
            p.save()
        else:
            # Paso 2: descontar todo (ya validado que alcanza).
            for obj, cantidad in a_descontar:
                obj.stock -= cantidad
                obj.save(update_fields=['stock'])
            p.estado = 'confirmado'
            p.save()

    if sin_stock:
        logger.error(
            'Pedido #%s: PAGO recibido pero SIN STOCK. Cancelado. Requiere reembolso manual.',
            p.pk,
        )
        _notificar_admin_sin_stock(p)
        return p

    _enviar_confirmacion_cliente(p)
    _notificar_admin_nuevo_pedido(p)
    return p


# --- Checkout -------------------------------------------------------------

def crear_pedido(request):
    """Acepta usuarios logueados y checkout invitado."""
    carrito = get_or_create_carrito(request)
    items = carrito.items.select_related('producto', 'variante').all()
    if not items:
        return redirect('carrito:ver_carrito')

    # Pre-validar stock
    for item in items:
        if item.cantidad > item.stock_disponible:
            messages.error(
                request,
                'Stock insuficiente para "{}". Pediste {} pero hay {}.'.format(
                    item.producto.nombre, item.cantidad, item.stock_disponible
                )
            )
            return redirect('carrito:ver_carrito')

    if request.method == 'POST':
        # Email obligatorio (logueado: tomamos del user; invitado: del form)
        if request.user.is_authenticated:
            email = request.user.email or request.POST.get('email', '').strip()
            nombre = request.user.get_full_name() or request.user.username
        else:
            email = request.POST.get('email', '').strip()
            nombre = request.POST.get('nombre', '').strip()
            if not email or not nombre:
                messages.error(request, 'Necesitamos tu nombre y email.')
                return redirect('pedidos:crear_pedido')

        metodo = request.POST.get('metodo_envio', 'envio_domicilio')
        telefono = request.POST.get('telefono', '').strip()
        if not telefono:
            messages.error(request, 'Necesitamos un telefono de contacto.')
            return redirect('pedidos:crear_pedido')

        calle = depto = comuna = referencia = ''
        region = 'Region Metropolitana'
        if metodo == 'envio_domicilio':
            calle = request.POST.get('calle_numero', '').strip()
            depto = request.POST.get('depto', '').strip()
            comuna = request.POST.get('comuna', '').strip()
            region = request.POST.get('region', 'Region Metropolitana').strip() or 'Region Metropolitana'
            referencia = request.POST.get('referencia', '').strip()
            if not calle or not comuna:
                messages.error(request, 'Necesitamos calle y comuna para el envio.')
                return redirect('pedidos:crear_pedido')

        subtotal = sum(i.subtotal() for i in items)
        costo_envio = calcular_costo_envio(metodo, comuna, region, subtotal)
        total = subtotal + costo_envio

        # Metodo de pago: por defecto MP, transferencia solo si habilitada
        metodo_pago = request.POST.get('metodo_pago', 'mercado_pago')
        if metodo_pago not in ('mercado_pago', 'transferencia'):
            metodo_pago = 'mercado_pago'
        if metodo_pago == 'transferencia' and not settings.BANCO.get('titular'):
            metodo_pago = 'mercado_pago'  # fallback si banco no configurado

        try:
            with transaction.atomic():
                pedido = Pedido.objects.create(
                    usuario=request.user if request.user.is_authenticated else None,
                    nombre_cliente=nombre if not request.user.is_authenticated else '',
                    email_cliente=email if not request.user.is_authenticated else '',
                    metodo_envio=metodo,
                    metodo_pago=metodo_pago,
                    calle_numero=calle, depto=depto,
                    comuna=comuna, region=region, referencia=referencia,
                    telefono=telefono,
                    nota_cliente=request.POST.get('nota', '').strip()[:500],
                    subtotal=subtotal,
                    costo_envio=costo_envio,
                    total=total,
                )
                for item in items:
                    nombre_snap = item.producto.nombre
                    if item.variante:
                        nombre_snap += ' ({})'.format(item.variante.nombre)
                    ItemPedido.objects.create(
                        pedido=pedido,
                        producto=item.producto,
                        variante=item.variante,
                        cantidad=item.cantidad,
                        precio_unitario=item.precio_unitario,
                        nombre_snapshot=nombre_snap,
                    )
                # Vaciar el carrito
                carrito.items.all().delete()
        except Exception as e:
            logger.exception('Error al crear pedido para %s', email)
            messages.error(request, 'Error al crear el pedido: {}'.format(str(e)[:120]))
            return redirect('carrito:ver_carrito')

        logger.info('Pedido #%s creado (subtotal=%s envio=%s total=%s metodo_pago=%s)',
                    pedido.pk, subtotal, costo_envio, total, metodo_pago)

        # Si es invitado, guardar el pedido en la sesion para que pueda
        # verlo durante esta sesion del navegador sin login.
        if not request.user.is_authenticated:
            pedidos_invitado = request.session.get('pedidos_invitado', [])
            if pedido.pk not in pedidos_invitado:
                pedidos_invitado.append(pedido.pk)
                request.session['pedidos_invitado'] = pedidos_invitado

        # Transferencia: redirigir a pantalla con datos bancarios e instrucciones
        if metodo_pago == 'transferencia':
            _notificar_admin_transferencia_pendiente(pedido)
            return redirect('pedidos:pago_transferencia', pk=pedido.pk)

        # Mercado Pago: crear preferencia y redirigir al checkout MP
        try:
            checkout_url = _crear_preferencia_mp(pedido, request)
            if checkout_url:
                return redirect(checkout_url)
        except Exception:
            logger.exception('Error creando preferencia MP para pedido #%s', pedido.pk)
            messages.warning(request, 'Pedido creado. Hubo un problema al conectar con el sistema de pago. Te contactaremos.')

        return redirect('pedidos:detalle_pedido', pk=pedido.pk)

    # GET: render formulario
    perfil = None
    direccion_predet = None
    if request.user.is_authenticated:
        perfil = getattr(request.user, 'perfil', None)
        direccion_predet = request.user.direcciones.filter(es_predeterminada=True).first()

    subtotal_actual = sum(i.subtotal() for i in items)

    return render(request, 'pedidos/crear_pedido.html', {
        'carrito': carrito,
        'items': items,
        'subtotal': subtotal_actual,
        'comunas': comunas_disponibles(),
        'perfil': perfil,
        'direccion_predet': direccion_predet,
    })


@login_required
def historial_pedidos(request):
    pedidos = Pedido.objects.filter(usuario=request.user).order_by('-creado').prefetch_related('items')
    return render(request, 'pedidos/historial.html', {'pedidos': pedidos})


def detalle_pedido(request, pk):
    """
    URL privada por ID secuencial. Solo dueno logueado o staff.
    Los invitados deben usar /pedidos/track/<token>/ — esa URL es publica
    pero impredecible (defensa contra IDOR).

    Excepcion practica: si el invitado acaba de crear el pedido en ESTA
    sesion del navegador, le permitimos ver via ID directo (lo guardamos
    en session['pedidos_invitado']). Si pierde la cookie, recupera acceso
    por el link del email (que lleva al tracking publico por token).
    """
    pedido = get_object_or_404(Pedido.objects.prefetch_related('items__producto', 'items__variante'), pk=pk)
    if request.user.is_authenticated:
        if pedido.usuario == request.user or request.user.is_staff:
            return render(request, 'pedidos/detalle_pedido.html', {'pedido': pedido})
        # Logueado pero no es su pedido ni es staff
        return redirect('catalogo:inicio')
    # Anonimo: solo dejar pasar si lo creo en esta sesion
    pedidos_invitado = request.session.get('pedidos_invitado', [])
    if pedido.pk in pedidos_invitado and pedido.usuario is None:
        return render(request, 'pedidos/detalle_pedido.html', {'pedido': pedido})
    # Sin sesion valida: redirigir al tracking por token (si lo tiene)
    if pedido.token_publico:
        return redirect('pedidos:track_pedido', token=pedido.token_publico)
    return redirect('catalogo:inicio')


def track_pedido(request, token):
    """
    URL publica del pedido, accesible por token impredecible.
    Esta es la URL que va en TODOS los emails al cliente.
    Sin login. Solo lectura — para cancelar tambien hay que tener el token.
    """
    pedido = get_object_or_404(
        Pedido.objects.prefetch_related('items__producto', 'items__variante'),
        token_publico=token,
    )
    return render(request, 'pedidos/track_pedido.html', {'pedido': pedido})


def _puede_acceder_pedido(request, pedido):
    """
    Autorizacion por ID secuencial (misma logica que detalle_pedido):
    - staff, o
    - dueno logueado, o
    - invitado que creo el pedido en ESTA sesion (session['pedidos_invitado']).
    Evita que cualquiera enumere pks y acceda a pedidos ajenos (IDOR).
    """
    if request.user.is_authenticated:
        return pedido.usuario == request.user or request.user.is_staff
    return pedido.usuario is None and pedido.pk in request.session.get('pedidos_invitado', [])


def pago_transferencia(request, pk):
    """
    Muestra los datos bancarios al cliente y un form opcional para subir
    el comprobante de transferencia. Accesible tras crear pedido con
    metodo_pago='transferencia'. Protegido contra enumeracion de pks: solo
    el dueno/invitado-de-sesion/staff pueden verlo.
    """
    pedido = get_object_or_404(Pedido, pk=pk)
    if not _puede_acceder_pedido(request, pedido):
        if pedido.token_publico:
            return redirect('pedidos:track_pedido', token=pedido.token_publico)
        return redirect('catalogo:inicio')
    if pedido.metodo_pago != 'transferencia':
        return redirect('pedidos:detalle_pedido', pk=pedido.pk)
    return render(request, 'pedidos/pago_transferencia.html', {
        'pedido': pedido,
    })


@require_POST
def cancelar_pedido(request, pk):
    """
    Cancelacion via ID (usuario logueado dueno, o invitado con sesion).
    Para invitados sin sesion (ej. desde email en otro dispositivo),
    usar /pedidos/track/<token>/cancelar/ que valida con el token.
    """
    pedido = get_object_or_404(Pedido, pk=pk)
    autorizado = False
    if request.user.is_authenticated and pedido.usuario == request.user:
        autorizado = True
    elif pedido.usuario is None and pedido.pk in request.session.get('pedidos_invitado', []):
        autorizado = True
    if not autorizado:
        messages.error(request, 'No tienes permiso para cancelar este pedido.')
        return redirect('catalogo:inicio')
    return _aplicar_cancelacion(request, pedido)


@require_POST
def cancelar_pedido_por_token(request, token):
    """
    Cancelacion publica via token (el link del email del invitado).
    Sin login, pero requiere conocer el token impredecible.
    """
    pedido = get_object_or_404(Pedido, token_publico=token)
    return _aplicar_cancelacion(request, pedido)


def _aplicar_cancelacion(request, pedido):
    if pedido.estado != 'pendiente':
        messages.warning(
            request,
            'Solo puedes cancelar pedidos pendientes de pago. Este está "{}". '
            'Para cualquier cambio, contáctanos por WhatsApp.'.format(pedido.get_estado_display())
        )
        # Redirigir a donde corresponda
        if request.user.is_authenticated and pedido.usuario == request.user:
            return redirect('pedidos:detalle_pedido', pk=pedido.pk)
        return redirect('pedidos:track_pedido', token=pedido.token_publico)
    pedido.estado = 'cancelado'
    pedido.save(update_fields=['estado', 'actualizado'])
    quien = request.user.username if request.user.is_authenticated else 'invitado'
    logger.info('Pedido #%s cancelado por %s', pedido.pk, quien)
    messages.success(request, 'Pedido #{} cancelado.'.format(pedido.pk))
    if request.user.is_authenticated:
        return redirect('usuarios:perfil')
    return redirect('pedidos:track_pedido', token=pedido.token_publico)


@require_POST
def subir_comprobante(request, pk):
    """
    El cliente sube screenshot del comprobante de transferencia.
    No cambia el estado del pedido — la duenia confirma manual desde gestion.
    """
    pedido = get_object_or_404(Pedido, pk=pk)
    if not _puede_acceder_pedido(request, pedido):
        if pedido.token_publico:
            return redirect('pedidos:track_pedido', token=pedido.token_publico)
        return redirect('catalogo:inicio')
    if pedido.metodo_pago != 'transferencia':
        messages.error(request, 'Este pedido no es por transferencia.')
        return redirect('pedidos:detalle_pedido', pk=pedido.pk)
    archivo = request.FILES.get('comprobante')
    if not archivo:
        messages.error(request, 'Adjunta una imagen del comprobante.')
        return redirect('pedidos:pago_transferencia', pk=pedido.pk)
    # Validar el archivo: tamanio y que sea imagen (no confiar en el content_type
    # del cliente; se valida ademas abriendo con Pillow).
    if archivo.size > 5 * 1024 * 1024:
        messages.error(request, 'La imagen es muy grande (maximo 5 MB).')
        return redirect('pedidos:pago_transferencia', pk=pedido.pk)
    try:
        from PIL import Image
        Image.open(archivo).verify()
        archivo.seek(0)
    except Exception:
        messages.error(request, 'El archivo no es una imagen valida.')
        return redirect('pedidos:pago_transferencia', pk=pedido.pk)
    pedido.comprobante_transferencia = archivo
    pedido.save(update_fields=['comprobante_transferencia', 'actualizado'])
    messages.success(request, 'Comprobante recibido. Te avisaremos por email cuando confirmemos el pago.')
    logger.info('Comprobante de transferencia subido para pedido #%s', pedido.pk)
    return redirect('pedidos:pago_transferencia', pk=pedido.pk)


# --- Callbacks de Mercado Pago (back_urls) -------------------------------
#
# IMPORTANTE: las back_urls son URLs que el NAVEGADOR del cliente visita, con
# parametros que el cliente controla. NUNCA confirmamos ni cancelamos un pedido
# creyendole a esos parametros. La fuente de verdad es el webhook (firmado) o
# una consulta directa a la API de MP. Aca solo mostramos feedback; si podemos
# verificar el pago real contra MP, adelantamos la confirmacion para dar mejor UX.

def _obtener_pago_mp(payment_id):
    """Consulta la API de MP y devuelve el dict del pago, o None si falla."""
    if not payment_id:
        return None
    try:
        sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
        return sdk.payment().get(payment_id).get('response', {})
    except Exception:
        logger.exception('Error consultando pago MP %s', payment_id)
        return None


def pago_exitoso(request):
    """
    Back URL tras un pago que MP considero aprobado. Verificamos contra la API
    de MP antes de confirmar: consultamos el pago real y comprobamos que este
    'approved' y que su external_reference apunte a este pedido. Si no podemos
    verificar, mostramos un mensaje neutro y dejamos que el webhook confirme.
    """
    payment_id = request.GET.get('payment_id', '') or request.GET.get('collection_id', '')
    pedido = None
    pago = _obtener_pago_mp(payment_id)
    if pago and pago.get('status') == 'approved':
        try:
            pedido = Pedido.objects.get(pk=pago.get('external_reference'))
            _confirmar_pedido(pedido, mp_payment_id=str(payment_id), mp_status='approved')
        except (Pedido.DoesNotExist, ValueError, TypeError):
            pedido = None

    if pedido and request.user.is_authenticated and pedido.usuario == request.user:
        messages.success(request, 'Pago recibido. Tu pedido esta confirmado.')
        return redirect('pedidos:detalle_pedido', pk=pedido.pk)

    return render(request, 'pedidos/pago_resultado.html', {
        'titulo': 'Pago recibido',
        'mensaje': 'Estamos confirmando tu pago. Te enviaremos un email en cuanto quede listo.',
        'tipo': 'exito',
    })


def pago_fallido(request):
    """
    Back URL de pago fallido/cancelado. NO cancelamos el pedido aca (seria
    cancelable por cualquiera con el ID en la URL). El webhook cancela cuando
    MP confirma 'rejected'/'cancelled'. El pedido pendiente tambien se puede
    reintentar o lo cancela el propio cliente/staff.
    """
    return render(request, 'pedidos/pago_resultado.html', {
        'titulo': 'Pago no completado',
        'mensaje': 'El pago no pudo procesarse. Puedes intentarlo de nuevo o contactarnos por WhatsApp.',
        'tipo': 'error',
    })


def pago_pendiente(request):
    return render(request, 'pedidos/pago_resultado.html', {
        'titulo': 'Pago pendiente',
        'mensaje': 'Tu pago esta siendo procesado. Te avisaremos cuando se confirme.',
        'tipo': 'pendiente',
    })


# --- Webhook de Mercado Pago ---------------------------------------------

def _validar_firma_webhook(request):
    """
    Valida el header x-signature de Mercado Pago (HMAC-SHA256).
    Doc: https://www.mercadopago.cl/developers/es/docs/your-integrations/notifications/webhooks

    El manifest es 'id:<data.id>;request-id:<x-request-id>;ts:<ts>;'.
    Si MP_WEBHOOK_SECRET no esta configurado, no validamos (retorna True) para
    no romper antes de que se configure el secreto en produccion, pero se
    registra una advertencia. Con el secreto puesto, la firma es obligatoria.
    """
    secret = getattr(settings, 'MP_WEBHOOK_SECRET', '')
    if not secret:
        logger.warning('Webhook MP sin MP_WEBHOOK_SECRET: firma NO validada. Configuralo en produccion.')
        return True

    firma = request.headers.get('x-signature', '')
    request_id = request.headers.get('x-request-id', '')
    partes = dict(
        p.strip().split('=', 1) for p in firma.split(',') if '=' in p
    )
    ts = partes.get('ts', '')
    v1 = partes.get('v1', '')
    if not ts or not v1:
        return False

    data_id = request.GET.get('data.id', '') or request.GET.get('id', '')
    # MP recomienda usar el data.id en minusculas cuando es alfanumerico.
    if data_id:
        data_id = data_id.lower()
    manifest = 'id:{};request-id:{};ts:{};'.format(data_id, request_id, ts)
    esperado = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1)


@csrf_exempt
@require_POST
def webhook_mp(request):
    """
    Webhook de notificaciones de Mercado Pago.
    MP envia POST con info del pago. Validamos la firma y luego consultamos su
    API para verificar el estado real del pago (unica fuente de verdad).
    """
    if not _validar_firma_webhook(request):
        logger.warning('Webhook MP: firma invalida. Rechazado.')
        return HttpResponse(status=401)

    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        # MP a veces manda querystring -- aceptamos ambos
        data = {'type': request.GET.get('type', ''), 'data': {'id': request.GET.get('id', '')}}

    tipo = data.get('type') or data.get('topic') or ''
    payment_id = ''
    if tipo == 'payment':
        payment_id = (data.get('data') or {}).get('id') or data.get('resource')
    elif tipo == 'merchant_order':
        # Soporte basico: ignorar por ahora, MP suele mandar tambien 'payment'
        return HttpResponse(status=200)

    if not payment_id:
        return HttpResponse(status=200)

    logger.info('Webhook MP recibido: tipo=%s payment_id=%s', tipo, payment_id)

    try:
        sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
        pago = sdk.payment().get(payment_id).get('response', {})
    except Exception:
        logger.exception('Webhook MP: error consultando payment %s', payment_id)
        return HttpResponse(status=200)

    estado_mp = pago.get('status', '')
    external_reference = pago.get('external_reference')
    if not external_reference:
        logger.warning('Webhook MP sin external_reference: payment_id=%s', payment_id)
        return HttpResponse(status=200)

    try:
        pedido = Pedido.objects.get(pk=external_reference)
    except Pedido.DoesNotExist:
        logger.error('Webhook MP: pedido #%s no existe (payment_id=%s)', external_reference, payment_id)
        return HttpResponse(status=200)

    if estado_mp == 'approved':
        logger.info('Webhook MP confirmando pedido #%s (payment %s)', pedido.pk, payment_id)
        _confirmar_pedido(pedido, mp_payment_id=str(payment_id), mp_status=estado_mp)
    elif estado_mp in ('rejected', 'cancelled'):
        logger.info('Webhook MP rechazo pedido #%s estado=%s', pedido.pk, estado_mp)
        if pedido.estado == 'pendiente':
            pedido.estado = 'cancelado'
            pedido.mp_status = estado_mp
            pedido.mp_payment_id = str(payment_id)
            pedido.save(update_fields=['estado', 'mp_status', 'mp_payment_id'])
    else:
        logger.info('Webhook MP estado no manejado: %s pedido #%s', estado_mp, pedido.pk)

    return HttpResponse(status=200)
