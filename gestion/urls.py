from django.urls import path
from . import views

app_name = 'gestion'

urlpatterns = [
    path('',           views.dashboard, name='dashboard'),
    path('pedidos/',   views.lista_pedidos, name='pedidos'),
    path('pedidos/<int:pk>/', views.detalle_pedido, name='detalle_pedido'),
    path('pedidos/exportar/', views.exportar_pedidos_csv, name='exportar_pedidos'),
    path('productos/', views.lista_productos, name='productos'),
    path('productos/nuevo/', views.crear_producto, name='crear_producto'),
    path('productos/<int:pk>/editar/', views.editar_producto, name='editar_producto'),
    path('productos/<int:pk>/eliminar/', views.eliminar_producto, name='eliminar_producto'),
    path('notificaciones-stock/', views.notificaciones_stock, name='notificaciones_stock'),
    path('newsletter/', views.newsletter_lista, name='newsletter_lista'),
    path('newsletter/nueva/', views.newsletter_crear, name='newsletter_crear'),
    path('newsletter/<int:pk>/', views.newsletter_detalle, name='newsletter_detalle'),
    path('newsletter/<int:pk>/prueba/', views.newsletter_enviar_prueba, name='newsletter_enviar_prueba'),
    path('newsletter/<int:pk>/enviar/', views.newsletter_enviar_real, name='newsletter_enviar_real'),
    path('newsletter/suscriptores/', views.newsletter_suscriptores, name='newsletter_suscriptores'),
    path('categorias/', views.categorias_lista, name='categorias_lista'),
    path('categorias/nueva/', views.categoria_crear, name='categoria_crear'),
    path('categorias/<int:pk>/editar/', views.categoria_editar, name='categoria_editar'),
    path('categorias/<int:pk>/eliminar/', views.categoria_eliminar, name='categoria_eliminar'),
    path('resenas/', views.resenas_lista, name='resenas_lista'),
    path('resenas/<int:pk>/toggle/', views.resena_toggle_aprobar, name='resena_toggle_aprobar'),
    path('resenas/<int:pk>/eliminar/', views.resena_eliminar, name='resena_eliminar'),
]
