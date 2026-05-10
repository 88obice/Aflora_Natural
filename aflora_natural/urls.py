from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic import TemplateView

from .sitemaps import SITEMAPS


def robots_txt(request):
    sitemap_url = '{}://{}{}'.format(request.scheme, request.get_host(), '/sitemap.xml')
    return TemplateView.as_view(
        template_name='robots.txt', content_type='text/plain',
        extra_context={'sitemap_url': sitemap_url},
    )(request)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap, {'sitemaps': SITEMAPS}, name='sitemap'),
    path('robots.txt', robots_txt, name='robots'),
    path('', include('catalogo.urls')),
    path('carrito/', include('carrito.urls')),
    path('pedidos/', include('pedidos.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('gestion/', include('gestion.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
