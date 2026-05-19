import secrets
from django.db import migrations, models


def llenar_tokens_existentes(apps, schema_editor):
    """
    Para pedidos creados antes de esta migracion, generar token publico
    aleatorio. Como el campo se agrega con null=True, los pedidos viejos
    arrancan con NULL y aca los llenamos.
    """
    Pedido = apps.get_model('pedidos', 'Pedido')
    for p in Pedido.objects.filter(token_publico__isnull=True).only('pk'):
        for _ in range(5):
            candidato = secrets.token_urlsafe(24)
            if not Pedido.objects.filter(token_publico=candidato).exclude(pk=p.pk).exists():
                Pedido.objects.filter(pk=p.pk).update(token_publico=candidato)
                break


def vaciar_tokens(apps, schema_editor):
    pass  # Reverse: no hace falta deshacer el llenado


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0003_pedido_metodo_pago_comprobante'),
    ]

    operations = [
        # AddField con unique=True desde el inicio (sin db_index para evitar
        # que Postgres cree dos veces el indice _like, lo que hacia chocar
        # la migracion anterior). null=True para permitir el AddField sin
        # tener que generar valores en la misma operacion.
        migrations.AddField(
            model_name='pedido',
            name='token_publico',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.RunPython(llenar_tokens_existentes, vaciar_tokens),
    ]
