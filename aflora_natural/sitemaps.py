from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from catalogo.models import Producto, Categoria


class StaticViewSitemap(Sitemap):
    """Paginas estaticas (home, catalogo, sobre nosotros, etc.)."""
    priority = 0.7
    changefreq = 'monthly'

    def items(self):
        return [
            'catalogo:inicio',
            'catalogo:lista_productos',
            'catalogo:sobre_nosotros',
            'catalogo:pagina_envios',
            'catalogo:pagina_terminos',
            'catalogo:pagina_privacidad',
            'catalogo:pagina_contacto',
        ]

    def location(self, item):
        return reverse(item)


class ProductoSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.9

    def items(self):
        return Producto.objects.filter(disponible=True)

    def lastmod(self, obj):
        return obj.actualizado

    def location(self, obj):
        return obj.get_absolute_url()


class CategoriaSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        return Categoria.objects.all()

    def location(self, obj):
        return reverse('catalogo:lista_productos') + '?categoria=' + obj.slug


SITEMAPS = {
    'static':     StaticViewSitemap,
    'productos':  ProductoSitemap,
    'categorias': CategoriaSitemap,
}
