from django.db import models
from django.contrib.auth.models import User
from catalogo.models import Producto, Variante


class Carrito(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    sesion_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Carrito de {self.usuario or self.sesion_key}"

    def total(self):
        return sum(item.subtotal() for item in self.items.all())

    def cantidad_items(self):
        return sum(item.cantidad for item in self.items.all())


class ItemCarrito(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    variante = models.ForeignKey(Variante, on_delete=models.CASCADE, null=True, blank=True)
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [('carrito', 'producto', 'variante')]

    def __str__(self):
        if self.variante:
            return f"{self.cantidad} x {self.producto.nombre} ({self.variante.nombre})"
        return f"{self.cantidad} x {self.producto.nombre}"

    @property
    def precio_unitario(self):
        return self.variante.precio if self.variante else self.producto.precio

    @property
    def stock_disponible(self):
        return self.variante.stock if self.variante else self.producto.stock

    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def nombre_mostrar(self):
        if self.variante:
            return f"{self.producto.nombre} ({self.variante.nombre})"
        return self.producto.nombre
