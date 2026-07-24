from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carrito', '0002_itemcarrito_variante_alter_carrito_sesion_key_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='carrito',
            name='recordatorio_enviado',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
