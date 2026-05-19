from django.urls import path
from . import views

app_name = 'pedidos'

urlpatterns = [
    path('crear/', views.crear_pedido, name='crear_pedido'),
    path('historial/', views.historial_pedidos, name='historial'),
    path('<int:pk>/', views.detalle_pedido, name='detalle_pedido'),
    path('<int:pk>/transferencia/', views.pago_transferencia, name='pago_transferencia'),
    path('<int:pk>/comprobante/', views.subir_comprobante, name='subir_comprobante'),
    path('<int:pk>/cancelar/', views.cancelar_pedido, name='cancelar_pedido'),
    # URL publica por token (defensa IDOR) — esta es la que va en los emails
    path('track/<str:token>/', views.track_pedido, name='track_pedido'),
    path('track/<str:token>/cancelar/', views.cancelar_pedido_por_token, name='cancelar_pedido_por_token'),
    path('pago/exitoso/', views.pago_exitoso, name='pago_exitoso'),
    path('pago/fallido/', views.pago_fallido, name='pago_fallido'),
    path('pago/pendiente/', views.pago_pendiente, name='pago_pendiente'),
    path('webhook/mp/', views.webhook_mp, name='webhook_mp'),
]
