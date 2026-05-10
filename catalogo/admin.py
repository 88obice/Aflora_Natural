from django.contrib import admin
from .models import (
    Categoria, Producto, ImagenProducto, Variante,
    Resena, Wishlist, SuscriptorNewsletter, NotificacionStock,
)


class ImagenProductoInline(admin.TabularInline):
    model = ImagenProducto
    extra = 1
    fields = ['imagen', 'alt', 'orden']


class VarianteInline(admin.TabularInline):
    model = Variante
    extra = 0
    fields = ['nombre', 'sku', 'precio', 'stock', 'activa', 'orden']


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'orden']
    list_editable = ['orden']
    prepopulated_fields = {'slug': ('nombre',)}


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'categoria', 'precio', 'stock', 'disponible', 'destacado']
    list_filter = ['categoria', 'disponible', 'destacado']
    list_editable = ['precio', 'stock', 'disponible', 'destacado']
    search_fields = ['nombre', 'sku', 'descripcion']
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [ImagenProductoInline, VarianteInline]
    fieldsets = (
        (None, {'fields': ('categoria', 'nombre', 'slug', 'sku')}),
        ('Descripcion', {'fields': ('descripcion_corta', 'descripcion')}),
        ('Precio y stock', {'fields': ('precio', 'stock')}),
        ('Imagen principal', {'fields': ('imagen',)}),
        ('Visibilidad', {'fields': ('disponible', 'destacado')}),
    )


@admin.register(Resena)
class ResenaAdmin(admin.ModelAdmin):
    list_display = ['producto', 'usuario', 'rating', 'aprobada', 'creado']
    list_filter = ['rating', 'aprobada']
    list_editable = ['aprobada']
    search_fields = ['producto__nombre', 'usuario__username', 'comentario']


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'producto', 'creado']
    search_fields = ['usuario__username', 'producto__nombre']


@admin.register(SuscriptorNewsletter)
class SuscriptorNewsletterAdmin(admin.ModelAdmin):
    list_display = ['email', 'activo', 'creado']
    list_filter = ['activo']
    search_fields = ['email']


@admin.register(NotificacionStock)
class NotificacionStockAdmin(admin.ModelAdmin):
    list_display = ['producto', 'email', 'notificado', 'creado']
    list_filter = ['notificado']
    search_fields = ['email', 'producto__nombre']
