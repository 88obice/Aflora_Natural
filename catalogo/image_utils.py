"""
Compresion de imagenes antes de guardarlas al storage (Cloudinary o filesystem).

Defensa principal: que la duenia suba fotos de 5MB del celular y no se
coman el bandwidth gratis de Cloudinary (25GB/mes) ni hagan el sitio
lento al servirlas.

Estrategia: redimensionar a max 1200px lado mayor, JPEG calidad 85,
optimize=True, progressive=True. Es el sweet spot de la industria.
Una foto de 12MP (5MB) queda en ~150-300KB sin perdida visible.
"""
import io
import logging
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

logger = logging.getLogger('aflora.catalogo')


MAX_SIZE_PX = 1200
JPEG_QUALITY = 85


def comprimir_imagen(image_field, max_size=MAX_SIZE_PX, quality=JPEG_QUALITY):
    """
    Toma un ImageFieldFile y devuelve un ContentFile con la version
    comprimida lista para asignar de vuelta al field, o None si no
    hay nada que hacer (campo vacio o archivo ya en storage).

    Heuristica: solo procesa uploads nuevos del usuario. Si el archivo
    ya esta cargado desde el storage (no es un upload reciente), no
    lo toca — evita recomprimir y subir de nuevo la misma foto cada
    vez que se edita un producto sin cambiar la imagen.

    Convierte siempre a JPEG. Imagenes PNG con transparencia quedan
    con fondo blanco (acordado: no se necesita transparencia para velas).

    Args:
        image_field: instance.imagen u otro FieldFile
        max_size:    lado mayor maximo en pixeles (default 1200)
        quality:     calidad JPEG 1-100 (default 85)

    Returns:
        ContentFile con bytes JPEG y nombre .jpg, o None.
    """
    if not image_field:
        return None

    archivo = getattr(image_field, 'file', None)
    if archivo is None:
        return None

    # Solo procesar uploads nuevos. Si es un FieldFile cargado desde storage,
    # archivo es un FileWrapper o similar, no UploadedFile.
    if not isinstance(archivo, (InMemoryUploadedFile, TemporaryUploadedFile)):
        return None

    try:
        img = Image.open(archivo)
        img.load()  # forzar carga (algunas operaciones son lazy)
    except Exception as e:
        logger.warning('No se pudo abrir imagen "%s" para comprimir: %s',
                       image_field.name, e)
        return None

    # Corregir orientacion segun EXIF (fotos de celular suelen estar
    # rotadas en metadata, no en pixeles — sin esto se ven de costado).
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass  # imagen sin EXIF, sigue normal

    # JPEG no soporta canal alpha. Si la imagen tiene transparencia,
    # aplastar contra fondo blanco antes de convertir.
    if img.mode in ('RGBA', 'LA'):
        fondo = Image.new('RGB', img.size, (255, 255, 255))
        # mask = canal alpha
        canal_alpha = img.split()[-1]
        fondo.paste(img, mask=canal_alpha)
        img = fondo
    elif img.mode == 'P':
        # Indexed (gif/png paletizado) — convertir a RGB plano
        img = img.convert('RGB')
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # Redimensionar solo si excede max_size en algun lado.
    # thumbnail mantiene aspect ratio y no agranda.
    if max(img.size) > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Re-guardar a JPEG optimizado en un buffer en memoria.
    buffer = io.BytesIO()
    img.save(
        buffer,
        format='JPEG',
        quality=quality,
        optimize=True,
        progressive=True,
    )

    # Mantener el nombre original pero forzar extension .jpg.
    nombre = image_field.name or 'imagen'
    nombre_sin_ext = nombre.rsplit('.', 1)[0] if '.' in nombre else nombre
    nuevo_nombre = nombre_sin_ext + '.jpg'

    return ContentFile(buffer.getvalue(), name=nuevo_nombre)
