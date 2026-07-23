from django.db import migrations, models


def backfill_estado_pago(apps, schema_editor):
    """
    Deriva el estado_pago de los pedidos existentes a partir del `estado`
    de cumplimiento (que hasta ahora hacía las dos veces). Los estados que
    solo se alcanzan tras un pago confirmado se marcan 'pagado'; el resto
    (pendiente, cancelado) queda 'pendiente' (el default), para NO marcar
    falsos rechazos en pedidos viejos.
    """
    Pedido = apps.get_model('pedidos', 'Pedido')
    Pedido.objects.filter(
        estado__in=['confirmado', 'preparando', 'enviado', 'entregado']
    ).update(estado_pago='pagado')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0004_pedido_token_publico'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='estado_pago',
            field=models.CharField(
                choices=[
                    ('pendiente', 'Pendiente'),
                    ('pagado', 'Pagado'),
                    ('rechazado', 'Rechazado'),
                    ('reembolsado', 'Reembolsado'),
                ],
                db_index=True, default='pendiente', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='pedido',
            name='medio_pago_detalle',
            field=models.CharField(
                blank=True,
                choices=[
                    ('webpay', 'Webpay'),
                    ('onepay', 'Onepay'),
                    ('mach', 'MACH'),
                    ('servipag', 'Servipag'),
                    ('multicaja', 'Multicaja'),
                    ('transferencia', 'Transferencia'),
                    ('tarjeta_credito', 'Tarjeta de crédito'),
                    ('tarjeta_debito', 'Tarjeta de débito'),
                    ('mercado_pago', 'Mercado Pago'),
                    ('otro', 'Otro'),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='pedido',
            name='flow_token',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddField(
            model_name='pedido',
            name='flow_order',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AlterField(
            model_name='pedido',
            name='metodo_pago',
            field=models.CharField(
                choices=[
                    ('flow', 'Flow'),
                    ('mercado_pago', 'Mercado Pago'),
                    ('transferencia', 'Transferencia bancaria'),
                ],
                default='mercado_pago', max_length=20,
            ),
        ),
        migrations.RunPython(backfill_estado_pago, noop),
    ]
