from django.urls import path
from . import views

app_name = 'carrito'

urlpatterns = [
    path('', views.ver_carrito, name='ver_carrito'),
    path('agregar/<int:producto_id>/', views.agregar_al_carrito, name='agregar'),
    path('actualizar/<int:item_id>/', views.actualizar_cantidad, name='actualizar'),
    path('eliminar/<int:item_id>/', views.eliminar_del_carrito, name='eliminar'),
]
