from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MinLengthValidator, MaxValueValidator
from django.utils.text import slugify
from django.urls import reverse


class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    descripcion = models.TextField(blank=True)
    imagen = models.ImageField(upload_to='categorias/', blank=True, null=True)
    orden = models.PositiveIntegerField(default=0, help_text="Menor = aparece primero")

    class Meta:
        verbose_name_plural = "Categorias"
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)


class Producto(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='productos')
    nombre = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True, db_index=True)
    sku = models.CharField(max_length=40, blank=True, db_index=True, help_text="Codigo interno opcional")
    descripcion = models.TextField()
    descripcion_corta = models.CharField(
        max_length=200, blank=True,
        help_text="Aparece en listados y meta description (SEO). Si vacio, se genera automatico."
    )
    precio = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    stock = models.PositiveIntegerField(default=0)
    imagen = models.ImageField(upload_to='productos/', blank=True, null=True,
                               help_text="Imagen principal (tambien se muestra como primera de la galeria)")
    disponible = models.BooleanField(default=True,
                                     help_text="Si esta en falso, no aparece en el catalogo (oculto manualmente).")
    destacado = models.BooleanField(default=False, help_text="Aparece en la home como destacado.")
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Productos"
        ordering = ['-creado']
        indexes = [
            models.Index(fields=['disponible', 'categoria']),
            models.Index(fields=['-creado']),
        ]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nombre)[:200] or 'producto'
            slug_candidato = base
            i = 2
            while Producto.objects.filter(slug=slug_candidato).exclude(pk=self.pk).exists():
                slug_candidato = f"{base}-{i}"
                i += 1
            self.slug = slug_candidato
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('catalogo:detalle_producto', kwargs={'slug': self.slug})

    @property
    def agotado(self):
        if self.variantes.exists():
            return not self.variantes.filter(stock__gt=0, activa=True).exists()
        return self.stock <= 0

    @property
    def precio_desde(self):
        if self.variantes.exists():
            v = self.variantes.filter(activa=True).order_by('precio').values_list('precio', flat=True).first()
            return v or self.precio
        return self.precio

    @property
    def imagenes_galeria(self):
        return list(self.imagenes.all().order_by('orden', 'id'))

    @property
    def rating_promedio(self):
        from django.db.models import Avg
        agg = self.resenas.filter(aprobada=True).aggregate(avg=Avg('rating'))
        return agg['avg']

    @property
    def total_resenas(self):
        return self.resenas.filter(aprobada=True).count()


class ImagenProducto(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='imagenes')
    imagen = models.ImageField(upload_to='productos/galeria/')
    alt = models.CharField(max_length=160, blank=True, help_text="Texto alternativo (accesibilidad y SEO)")
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']
        verbose_name = "Imagen de producto"
        verbose_name_plural = "Imagenes de producto"

    def __str__(self):
        return f"{self.producto.nombre} -- img #{self.pk}"


class Variante(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='variantes')
    nombre = models.CharField(max_length=120, help_text="Ej: '200g', 'Lavanda', 'Vainilla 100g'")
    sku = models.CharField(max_length=40, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    stock = models.PositiveIntegerField(default=0)
    activa = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']
        verbose_name_plural = "Variantes"

    def __str__(self):
        return f"{self.producto.nombre} -- {self.nombre}"


class Resena(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='resenas')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resenas')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    titulo = models.CharField(max_length=120, blank=True)
    comentario = models.TextField(validators=[MinLengthValidator(10)])
    aprobada = models.BooleanField(default=True, help_text="Moderacion: si False, no se muestra al publico.")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        unique_together = [('producto', 'usuario')]
        verbose_name = "Resena"
        verbose_name_plural = "Resenas"

    def __str__(self):
        return f"{self.producto.nombre} -- {self.rating} estrellas por {self.usuario.username}"


class Wishlist(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='en_wishlist')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('usuario', 'producto')]
        ordering = ['-creado']

    def __str__(self):
        return f"{self.usuario.username} fav {self.producto.nombre}"


class SuscriptorNewsletter(models.Model):
    email = models.EmailField(unique=True)
    activo = models.BooleanField(default=True)
    token_baja = models.CharField(max_length=40, blank=True, db_index=True,
                                  help_text="Token unico para link de unsubscribe")
    creado = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token_baja:
            import secrets
            self.token_baja = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-creado']
        verbose_name = "Suscriptor newsletter"
        verbose_name_plural = "Suscriptores newsletter"

    def __str__(self):
        return self.email


class NotificacionStock(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='notificaciones_stock')
    email = models.EmailField()
    notificado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('producto', 'email')]
        ordering = ['-creado']
        verbose_name = "Notificacion de stock"
        verbose_name_plural = "Notificaciones de stock"

    def __str__(self):
        return f"{self.email} -> {self.producto.nombre}"


class CampanaNewsletter(models.Model):
    """Una campana de email a todos los suscriptores activos."""
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('enviando', 'Enviando'),
        ('enviada',  'Enviada'),
        ('error',    'Error'),
    ]

    asunto = models.CharField(max_length=200)
    cuerpo = models.TextField(help_text="Texto plano. Las {variables} se reemplazan al enviar.")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    creado = models.DateTimeField(auto_now_add=True)
    enviada_en = models.DateTimeField(null=True, blank=True)
    total_destinatarios = models.PositiveIntegerField(default=0)
    total_enviados = models.PositiveIntegerField(default=0)
    total_fallidos = models.PositiveIntegerField(default=0)
    nota_interna = models.TextField(blank=True, help_text="Nota privada solo visible en gestion")

    class Meta:
        ordering = ['-creado']
        verbose_name = "Campana de newsletter"
        verbose_name_plural = "Campanas de newsletter"

    def __str__(self):
        return f"#{self.pk} -- {self.asunto[:60]}"

