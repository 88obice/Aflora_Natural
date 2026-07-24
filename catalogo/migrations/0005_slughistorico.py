import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0004_campananewsletter_suscriptornewsletter_token_baja'),
    ]

    operations = [
        migrations.CreateModel(
            name='SlugHistorico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(db_index=True, max_length=220, unique=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='slugs_historicos', to='catalogo.producto')),
            ],
            options={
                'verbose_name': 'Slug histórico',
                'verbose_name_plural': 'Slugs históricos',
            },
        ),
    ]
