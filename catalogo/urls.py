from django.urls import path
from . import views

app_name = 'catalogo'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('catalogo/', views.lista_productos, name='lista_productos'),
    # Detalle por slug (preferido). Mantenemos el viejo por id para retrocompat:
    path('producto/<slug:slug>/', views.detalle_producto, name='detalle_producto'),
    path('producto/id/<int:pk>/', views.detalle_producto_por_id, name='detalle_producto_por_id'),
    # Notify-me cuando vuelve el stock
    path('producto/<slug:slug>/avisame/', views.avisame_stock, name='avisame_stock'),
    # Wishlist
    path('wishlist/', views.ver_wishlist, name='ver_wishlist'),
    path('wishlist/toggle/<int:producto_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    # Resenas
    path('producto/<slug:slug>/resenar/', views.crear_resena, name='crear_resena'),
    # Newsletter
    path('newsletter/suscribir/', views.suscribir_newsletter, name='suscribir_newsletter'),
    path('newsletter/baja/<str:token>/', views.unsubscribe_newsletter, name='unsubscribe_newsletter'),
    # Paginas estaticas
    path('sobre-nosotros/', views.sobre_nosotros, name='sobre_nosotros'),
    path('envios-y-devoluciones/', views.pagina_envios, name='pagina_envios'),
    path('terminos/', views.pagina_terminos, name='pagina_terminos'),
    path('privacidad/', views.pagina_privacidad, name='pagina_privacidad'),
    path('contacto/', views.pagina_contacto, name='pagina_contacto'),
]
