from django.contrib import admin
from .models import PerfilUsuario, Direccion


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'telefono', 'recibir_newsletter']
    search_fields = ['usuario__username', 'usuario__email', 'telefono']


@admin.register(Direccion)
class DireccionAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'alias', 'comuna', 'es_predeterminada']
    list_filter = ['region', 'comuna', 'es_predeterminada']
    search_fields = ['usuario__username', 'calle_numero', 'comuna']
