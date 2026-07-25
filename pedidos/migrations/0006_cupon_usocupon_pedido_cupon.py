import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0005_pedido_estado_pago_flow'),
    ]

    operations = [
        migrations.CreateModel(
            name='Cupon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(db_index=True, help_text='El código que escribe el cliente (ej: GRACIAS15). Se guarda en mayúsculas.', max_length=40, unique=True)),
                ('tipo', models.CharField(choices=[('porcentaje', 'Porcentaje (%)'), ('monto_fijo', 'Monto fijo ($)')], default='porcentaje', max_length=12)),
                ('valor', models.DecimalField(decimal_places=2, help_text='Si es porcentaje: 15 = 15%. Si es monto fijo: 5000 = $5.000.', max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('activo', models.BooleanField(default=True)),
                ('vence', models.DateField(blank=True, help_text='Opcional. Último día en que sirve (incluido).', null=True)),
                ('monto_minimo', models.DecimalField(decimal_places=2, default=0, help_text='Compra mínima (subtotal) para poder usarlo. 0 = sin mínimo.', max_digits=10)),
                ('usos_maximos', models.PositiveIntegerField(blank=True, help_text='Tope total de usos entre todos los clientes. Vacío = ilimitado.', null=True)),
                ('usos_por_usuario', models.PositiveIntegerField(default=1, help_text='Cuántas veces puede usarlo la misma persona (por email).')),
                ('usos_actuales', models.PositiveIntegerField(default=0)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Cupón',
                'verbose_name_plural': 'Cupones',
                'ordering': ['-creado'],
            },
        ),
        migrations.AddField(
            model_name='pedido',
            name='descuento',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='pedido',
            name='cupon',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pedidos', to='pedidos.cupon'),
        ),
        migrations.CreateModel(
            name='UsoCupon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(db_index=True, max_length=254)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('cupon', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='usos', to='pedidos.cupon')),
                ('pedido', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='pedidos.pedido')),
            ],
        ),
    ]
