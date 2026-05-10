from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class PerfilUsuario(models.Model):
    """Datos extra del usuario para autocompletar checkout y contacto."""
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefono = models.CharField(max_length=20, blank=True)
    recibir_newsletter = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Perfil de {self.usuario.username}"


class Direccion(models.Model):
    """Direcciones guardadas para reusar en checkout."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direcciones')
    alias = models.CharField(max_length=40, default='Casa', help_text="Ej: Casa, Trabajo")
    nombre_destinatario = models.CharField(max_length=120)
    calle_numero = models.CharField(max_length=200, help_text="Calle y numero")
    depto = models.CharField(max_length=60, blank=True, help_text="Depto/oficina (opcional)")
    comuna = models.CharField(max_length=80)
    region = models.CharField(max_length=80, default='Region Metropolitana')
    referencia = models.CharField(max_length=200, blank=True, help_text="Como llegar / referencia")
    telefono = models.CharField(max_length=20)
    es_predeterminada = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-es_predeterminada', '-creado']
        verbose_name_plural = "Direcciones"

    def __str__(self):
        return f"{self.alias} -- {self.calle_numero}, {self.comuna}"

    def linea_completa(self):
        partes = [self.calle_numero]
        if self.depto:
            partes.append(self.depto)
        partes.append(self.comuna)
        partes.append(self.region)
        return ', '.join(partes)

    def save(self, *args, **kwargs):
        if self.es_predeterminada:
            Direccion.objects.filter(
                usuario=self.usuario, es_predeterminada=True
            ).exclude(pk=self.pk).update(es_predeterminada=False)
        super().save(*args, **kwargs)


@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.get_or_create(usuario=instance)
