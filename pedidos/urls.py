from django.urls import path
from . import views

app_name = 'pedidos'

urlpatterns = [
    path('crear/', views.crear_pedido, name='crear_pedido'),
    path('historial/', views.historial_pedidos, name='historial'),
    path('<int:pk>/', views.detalle_pedido, name='detalle_pedido'),
    path('pago/exitoso/', views.pago_exitoso, name='pago_exitoso'),
    path('pago/fallido/', views.pago_fallido, name='pago_fallido'),
    path('pago/pendiente/', views.pago_pendiente, name='pago_pendiente'),
    path('webhook/mp/', views.webhook_mp, name='webhook_mp'),
]
