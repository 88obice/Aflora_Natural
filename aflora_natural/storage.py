"""
Storage backend de Cloudinary para Aflora Natural.

Reemplaza el filesystem de Django en producción (Railway).
En local, si CLOUDINARY_URL no está en el entorno, este archivo ni se importa.

Uso en settings.py (solo cuando CLOUDINARY_URL está configurada):
    STORAGES = {
        'default': {'BACKEND': 'aflora_natural.storage.CloudinaryMediaStorage'},
        ...
    }
"""
import cloudinary
import cloudinary.uploader
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryMediaStorage(Storage):
    """
    Storage minimo para media files (imagenes de productos).
    Compatible con Django 6+.

    El SDK de cloudinary lee CLOUDINARY_URL del entorno automaticamente.
    No hay que configurar nada mas aqui.
    """

    def _save(self, name, content):
        """Sube el archivo a Cloudinary y devuelve el public_id."""
        name = name.replace('\\', '/')           # Windows safe
        folder = '/'.join(name.split('/')[:-1]) if '/' in name else ''
        options = {
            'use_filename': True,
            'unique_filename': True,
            'overwrite': False,
            'resource_type': 'auto',             # image, video, raw segun extension
        }
        if folder:
            options['folder'] = folder
        response = cloudinary.uploader.upload(content, **options)
        return response['public_id']

    def url(self, name):
        """Devuelve la URL publica de Cloudinary para el archivo."""
        if not name:
            return ''
        resource = cloudinary.CloudinaryResource(name, resource_type='image')
        return resource.url

    def exists(self, name):
        """
        Siempre False: dejamos que Cloudinary gestione duplicados con
        unique_filename=True en _save. Evita una llamada HTTP extra en cada upload.
        """
        return False

    def delete(self, name):
        """Borra el archivo de Cloudinary."""
        if not name:
            return
        try:
            cloudinary.uploader.destroy(name, resource_type='image', invalidate=True)
        except Exception:
            pass  # no romper si el archivo ya no existe

    def _open(self, name, mode='rb'):
        """
        Lectura directa desde Cloudinary (necesario para algunas operaciones internas).
        En la practica casi nunca se llama para media files normales.
        """
        import requests
        from django.core.files.base import ContentFile
        resource = cloudinary.CloudinaryResource(name, resource_type='image')
        response = requests.get(resource.url, timeout=10)
        response.raise_for_status()
        return ContentFile(response.content, name=name)

    def size(self, name):
        """Tamanio desconocido sin consultar la API. Devuelve None."""
        return None

    def get_available_name(self, name, max_length=None):
        """
        Cloudinary maneja unicidad con unique_filename=True.
        Devolvemos el nombre tal como viene (sin agregar sufijos numericos).
        """
        if max_length:
            return name[:max_length]
        return name
