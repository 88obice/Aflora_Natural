from django.db import models
from django.contrib.auth.models import User
from catalogo.models import Producto, Variante


class Pedido(models.Model):
    ESTADO_CHOICES = [
        ('pendiente',  'Pendiente'),
        ('confirmado', 'Confirmado'),
        ('preparando', 'Preparando'),
        ('enviado',    'Enviado'),
        ('entregado',  'Entregado'),
        ('cancelado',  'Cancelado'),
    ]

    METODO_ENVIO_CHOICES = [
        ('envio_domicilio', 'Envio a domicilio'),
        ('retiro_local',    'Retiro en local'),
    ]

    METODO_PAGO_CHOICES = [
        ('flow',          'Flow'),
        ('mercado_pago',  'Mercado Pago'),
        ('transferencia', 'Transferencia bancaria'),
    ]

    # Ciclo de vida del PAGO — eje independiente del `estado` (cumplimiento).
    # Antes "pagado" se infería de estado != pendiente/cancelado; eso no podía
    # representar "reembolsado" (ej: pago recibido pero sin stock → cancelado
    # pero con plata que hay que devolver). Ahora es explícito.
    ESTADO_PAGO_CHOICES = [
        ('pendiente',   'Pendiente'),
        ('pagado',      'Pagado'),
        ('rechazado',   'Rechazado'),
        ('reembolsado', 'Reembolsado'),
    ]

    # Instrumento REAL usado por el cliente. No se elige en el checkout: lo
    # reporta la pasarela después de pagar (Flow: paymentData.media;
    # MP: payment_method_id). Distinto de `metodo_pago`, que es la pasarela.
    MEDIO_PAGO_CHOICES = [
        ('webpay',           'Webpay'),
        ('onepay',           'Onepay'),
        ('mach',             'MACH'),
        ('servipag',         'Servipag'),
        ('multicaja',        'Multicaja'),
        ('transferencia',    'Transferencia'),
        ('tarjeta_credito',  'Tarjeta de crédito'),
        ('tarjeta_debito',   'Tarjeta de débito'),
        ('mercado_pago',     'Mercado Pago'),
        ('otro',             'Otro'),
    ]

    # Usuario opcional para checkout invitado
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos')

    # Datos contacto (logueado o invitado)
    nombre_cliente = models.CharField(max_length=120, blank=True)
    email_cliente = models.EmailField(blank=True)

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')

    # Envio
    metodo_envio = models.CharField(max_length=30, choices=METODO_ENVIO_CHOICES, default='envio_domicilio')
    calle_numero = models.CharField(max_length=200, blank=True)
    depto = models.CharField(max_length=60, blank=True)
    comuna = models.CharField(max_length=80, blank=True)
    region = models.CharField(max_length=80, blank=True, default='Region Metropolitana')
    referencia = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=20)

    # Legacy: campo antiguo
    direccion_entrega = models.TextField(blank=True,
                                         help_text="Legacy: direccion como texto. Nuevos pedidos usan campos estructurados.")

    # Costos
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    costo_envio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    # Tracking
    codigo_seguimiento = models.CharField(max_length=80, blank=True,
                                          help_text="Numero de seguimiento del courier")
    nota_cliente = models.TextField(blank=True, help_text="Comentario opcional del cliente")

    # Pago
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default='mercado_pago')
    # Estado del pago (independiente del cumplimiento). Ver ESTADO_PAGO_CHOICES.
    estado_pago = models.CharField(max_length=20, choices=ESTADO_PAGO_CHOICES,
                                   default='pendiente', db_index=True)
    # Instrumento real (webpay, mach, etc.) informado por la pasarela tras pagar.
    medio_pago_detalle = models.CharField(max_length=30, choices=MEDIO_PAGO_CHOICES, blank=True)
    mp_payment_id = models.CharField(max_length=80, blank=True, db_index=True)
    mp_status = models.CharField(max_length=30, blank=True)
    # Identificadores de Flow (análogos a mp_payment_id/mp_status).
    flow_token = models.CharField(max_length=100, blank=True, db_index=True)
    flow_order = models.CharField(max_length=40, blank=True)
    # Comprobante opcional para transferencias (el cliente sube screenshot)
    comprobante_transferencia = models.ImageField(
        upload_to='comprobantes/', blank=True, null=True,
        help_text="Screenshot del comprobante de transferencia (opcional, ayuda a confirmar antes)"
    )

    # Token publico impredecible para URL de tracking sin login (defensa IDOR).
    # Auto-generado en save() si esta vacio. Se usa en /pedidos/track/<token>/
    # y en TODOS los emails al cliente. El ID secuencial nunca se expone publicamente.
    # null=True/blank=True para soportar el AddField inicial; el save() siempre
    # llena el valor antes de guardar a la BD.
    token_publico = models.CharField(max_length=64, blank=True, null=True, unique=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Pedidos"
        ordering = ['-creado']
        indexes = [
            models.Index(fields=['estado']),
            models.Index(fields=['-creado']),
        ]

    def __str__(self):
        quien = self.usuario or self.email_cliente or 'invitado'
        return f"Pedido #{self.id} - {quien} - {self.estado}"

    def save(self, *args, **kwargs):
        if not self.token_publico:
            import secrets
            # Asegurar unicidad — en la practica con 32 chars random la colision
            # es ~10^-19, pero por defensa total iteramos si ocurre.
            for _ in range(5):
                candidato = secrets.token_urlsafe(24)
                if not Pedido.objects.filter(token_publico=candidato).exclude(pk=self.pk).exists():
                    self.token_publico = candidato
                    break
        super().save(*args, **kwargs)

    @property
    def es_invitado(self):
        return self.usuario is None

    @property
    def email_destinatario(self):
        if self.usuario and self.usuario.email:
            return self.usuario.email
        return self.email_cliente

    @property
    def nombre_destinatario(self):
        if self.usuario:
            return self.usuario.get_full_name() or self.usuario.username
        return self.nombre_cliente or 'Cliente'

    def direccion_formateada(self):
        if self.metodo_envio == 'retiro_local':
            return 'Retiro en local'
        if self.calle_numero:
            partes = [self.calle_numero]
            if self.depto:
                partes.append(self.depto)
            if self.comuna:
                partes.append(self.comuna)
            if self.region:
                partes.append(self.region)
            return ', '.join(partes)
        return self.direccion_entrega or ''


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    variante = models.ForeignKey(Variante, on_delete=models.PROTECT, null=True, blank=True)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    nombre_snapshot = models.CharField(max_length=240, blank=True,
                                       help_text="Nombre del producto al momento de la compra")

    def __str__(self):
        nombre = self.nombre_snapshot or self.producto.nombre
        if self.variante:
            return f"{self.cantidad} x {nombre} ({self.variante.nombre})"
        return f"{self.cantidad} x {nombre}"

    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def nombre_mostrar(self):
        nombre = self.nombre_snapshot or self.producto.nombre
        if self.variante:
            return f"{nombre} ({self.variante.nombre})"
        return nombre
