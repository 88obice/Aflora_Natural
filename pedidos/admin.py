from django.contrib import admin
from .models import Pedido, ItemPedido


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    fields = ['producto', 'variante', 'cantidad', 'precio_unitario', 'nombre_snapshot']
    readonly_fields = ['nombre_snapshot']


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre_destinatario', 'estado', 'metodo_envio', 'comuna', 'total', 'creado']
    list_filter = ['estado', 'metodo_envio', 'comuna']
    list_editable = ['estado']
    search_fields = ['id', 'usuario__username', 'email_cliente', 'nombre_cliente', 'codigo_seguimiento', 'mp_payment_id']
    readonly_fields = ['mp_payment_id', 'mp_status', 'creado', 'actualizado']
    inlines = [ItemPedidoInline]
    fieldsets = (
        ('Cliente', {'fields': ('usuario', 'nombre_cliente', 'email_cliente', 'telefono')}),
        ('Estado', {'fields': ('estado', 'codigo_seguimiento', 'nota_cliente')}),
        ('Envio', {'fields': ('metodo_envio', 'calle_numero', 'depto', 'comuna', 'region', 'referencia')}),
        ('Costos', {'fields': ('subtotal', 'costo_envio', 'total')}),
        ('Pago', {'fields': ('mp_payment_id', 'mp_status')}),
        ('Auditoria', {'fields': ('creado', 'actualizado'), 'classes': ('collapse',)}),
    )
