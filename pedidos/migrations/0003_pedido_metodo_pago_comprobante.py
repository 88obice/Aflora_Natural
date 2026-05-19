from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0002_alter_pedido_options_itempedido_nombre_snapshot_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='metodo_pago',
            field=models.CharField(
                choices=[
                    ('mercado_pago', 'Mercado Pago'),
                    ('transferencia', 'Transferencia bancaria'),
                ],
                default='mercado_pago',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='pedido',
            name='comprobante_transferencia',
            field=models.ImageField(
                blank=True, null=True,
                upload_to='comprobantes/',
                help_text='Screenshot del comprobante de transferencia (opcional, ayuda a confirmar antes)',
            ),
        ),
    ]
