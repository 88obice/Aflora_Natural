from django.urls import path
from . import views

app_name = 'gestion'

urlpatterns = [
    path('',           views.dashboard,       name='dashboard'),
    path('pedidos/',   views.lista_pedidos,   name='pedidos'),
    path('pedidos/<int:pk>/', views.detalle_pedido, name='detalle_pedido'),
    path('productos/', views.lista_productos, name='productos'),
]
