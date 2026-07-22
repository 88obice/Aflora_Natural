"""
Django settings for aflora_natural project.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# ── Rutas base ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga .env en desarrollo (en producción las vars vienen del entorno del host)
load_dotenv(BASE_DIR / '.env')


# ── Seguridad ───────────────────────────────────────────────────────────────
SECRET_KEY = os.environ['SECRET_KEY']  # Obligatorio — falla en arranque si falta

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
ALLOWED_HOSTS += ['healthcheck.railway.app', '.railway.app']

# Dominios de confianza para CSRF (necesario con HTTPS en producción)
_trusted = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _trusted.split(',') if o.strip()]

# Headers de seguridad (solo activos con HTTPS, ignorados en DEBUG)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # Railway termina SSL en el proxy — el contenedor solo recibe HTTP,
    # así que NO redirigimos a HTTPS desde Django.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE    = True


# ── Aplicaciones ────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'django.contrib.sites',
    # Apps del proyecto (con AppConfig explicito para asegurar que ready() corra)
    'usuarios.apps.UsuariosConfig',
    'catalogo.apps.CatalogoConfig',
    'carrito',
    'pedidos',
    'gestion',
]

# WhiteNoise va justo después de SecurityMiddleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',          # ← estáticos en prod
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'aflora_natural.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'carrito.context_processors.carrito_contador',
                'aflora_natural.context_processors.analytics_ids',
                'aflora_natural.context_processors.banco_info',
                'aflora_natural.context_processors.contacto_info',
                'aflora_natural.context_processors.seo_flags',
                'aflora_natural.context_processors.categorias_nav',
            ],
        },
    },
]

WSGI_APPLICATION = 'aflora_natural.wsgi.application'


# ── Base de datos ───────────────────────────────────────────────────────────
# Railway y Render inyectan DATABASE_URL automáticamente.
# En desarrollo se puede seguir usando las variables sueltas en .env.
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }


# Necesario para django.contrib.sites (lo usa el sitemap y los links de emails).
# El dominio del registro Site se autoconfigura desde BASE_URL en cada deploy
# via el command `configurar_sitio` (evita que quede en el default 'example.com').
SITE_ID = 1
SITE_NAME = os.getenv('SITE_NAME', 'Aflora Natural')

# Kill-switch de indexacion. Con SITE_NOINDEX=True, TODO el sitio sale con
# <meta name="robots" content="noindex, nofollow"> para que Google no lo indexe
# mientras haya contenido de prueba. Poner en True hasta el lanzamiento real y
# pasar a False el dia que el catalogo este listo. No requiere tocar codigo.
SITE_NOINDEX = os.getenv('SITE_NOINDEX', 'False') == 'True'

# Imagen del hero de la home. Si tiene una URL (ej. una foto en Cloudinary),
# el inicio muestra esa foto; si esta vacia, cae en la ilustracion SVG por
# defecto. Permite cambiar/quitar la foto sin tocar codigo.
HERO_IMAGEN_URL = os.getenv('HERO_IMAGEN_URL', '').strip()

# Umbral de envio gratis (en CLP). Fuente unica de verdad: antes estaba
# hardcodeado en 3 archivos (envios.py, carrito, pedidos). Configurable por env
# para que se ajuste sin tocar codigo.
ENVIO_GRATIS_UMBRAL = int(os.getenv('ENVIO_GRATIS_UMBRAL', '40000'))


# ── Contraseñas ─────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Autenticacion ───────────────────────────────────────────────────────────
# EmailBackend: clientes entran con su correo.
# ModelBackend: admin/staff siguen entrando con su username (respaldo).
AUTHENTICATION_BACKENDS = [
    'usuarios.backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# ── Internacionalización ────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-cl'
TIME_ZONE     = 'America/Santiago'
USE_I18N      = True
USE_TZ        = True


# ── Archivos estáticos ──────────────────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Carpeta con archivos estaticos propios (favicon, logos, etc).
# collectstatic los copia a STATIC_ROOT durante el build.
_static_dir = BASE_DIR / 'static'
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []

# ── Media (imágenes de productos) ──────────────────────────────────────────
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── Cloudinary (storage de imágenes en producción) ──────────────────────────
# Formato: cloudinary://api_key:api_secret@cloud_name
# En Railway: agregar esta var en Variables. En local: dejar vacía (usa filesystem).
# El SDK de cloudinary lee CLOUDINARY_URL del entorno automaticamente.
_CLOUDINARY_URL = os.getenv('CLOUDINARY_URL', '')

if _CLOUDINARY_URL:
    STORAGES = {
        'default':     {'BACKEND': 'aflora_natural.storage.CloudinaryMediaStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
    }
else:
    STORAGES = {
        'default':     {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
    }


# ── Mercado Pago ────────────────────────────────────────────────────────────
MP_PUBLIC_KEY   = os.getenv('MP_PUBLIC_KEY')
MP_ACCESS_TOKEN = os.getenv('MP_ACCESS_TOKEN')
# Secreto para validar la firma (x-signature) de los webhooks de MP.
# Se obtiene en el panel de MP > Webhooks. Sin el, el webhook acepta
# notificaciones sin verificar firma (se registra advertencia).
MP_WEBHOOK_SECRET = os.getenv('MP_WEBHOOK_SECRET', '')

# ── Email ───────────────────────────────────────────────────────────────────
EMAIL_BACKEND       = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
# Proveedor SMTP configurable por env. Por defecto Gmail (SSL 465).
# Para migrar a otro proveedor (ej. Brevo: smtp-relay.brevo.com, puerto 587, TLS),
# basta con setear estas variables en Railway — sin tocar codigo.
EMAIL_HOST          = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT          = int(os.getenv('EMAIL_PORT', '465'))
EMAIL_USE_TLS       = os.getenv('EMAIL_USE_TLS', 'False') == 'True'
EMAIL_USE_SSL       = os.getenv('EMAIL_USE_SSL', 'True') == 'True'
EMAIL_HOST_USER     = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
# From configurable: algunos proveedores (Brevo) exigen un sender verificado
# distinto del usuario SMTP. Si no se define, usa EMAIL_HOST_USER.
DEFAULT_FROM_EMAIL  = os.getenv('DEFAULT_FROM_EMAIL') or os.getenv('EMAIL_HOST_USER')

# ── Envio por API HTTP (Brevo via Anymail) ──────────────────────────────────
# Railway bloquea SMTP saliente en los planes bajos, asi que en produccion se
# envia por la API HTTP de Brevo (puerto 443, no bloqueado). Si BREVO_API_KEY
# esta seteada, se usa ese backend y se ignora la config SMTP de arriba. Si no,
# queda el EMAIL_BACKEND por defecto (util para consola/tests en local).
# IMPORTANTE: DEFAULT_FROM_EMAIL debe ser un remitente VERIFICADO en Brevo.
BREVO_API_KEY = os.getenv('BREVO_API_KEY', '').strip()
if BREVO_API_KEY:
    INSTALLED_APPS += ['anymail']
    EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'
    ANYMAIL = {'BREVO_API_KEY': BREVO_API_KEY}

# URL base del sitio (usada para links en emails — no se puede construir con
# request.build_absolute_uri porque los emails los manda el management command
# o el signal sin request disponible). En produccion: https://tudominio.cl
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000').strip()

# Admins que reciben notificaciones de errores (Django los manda en produccion
# cuando DEBUG=False) y nuevos pedidos (pedidos/views.py:_notificar_admin_nuevo_pedido).
# Si ADMIN_EMAIL no esta definido, mail_admins hace fallback a DEFAULT_FROM_EMAIL.
_admin_email = os.getenv('ADMIN_EMAIL', '').strip()
_admin_name  = os.getenv('ADMIN_NAME', 'Admin Aflora').strip()
if _admin_email:
    ADMINS   = [(_admin_name, _admin_email)]
    MANAGERS = ADMINS

# ── Datos de contacto (centralizados) ───────────────────────────────────────
# Antes el email de contacto estaba hardcodeado e INCONSISTENTE entre paginas
# (afloranatural.temp@gmail.com vs hola@afloranatural.cl). Ahora sale de aca y
# se inyecta en todos los templates via context processor `contacto_info`.
# Por defecto el email publico usa el mismo que envia el correo (consistente
# con la infra SMTP). La duenia puede sobreescribir CONTACTO_EMAIL en Railway.
CONTACTO = {
    'email':            (os.getenv('CONTACTO_EMAIL', '').strip() or DEFAULT_FROM_EMAIL or ''),
    'whatsapp':         os.getenv('CONTACTO_WHATSAPP', '56989560937').strip(),
    'whatsapp_display': os.getenv('CONTACTO_WHATSAPP_DISPLAY', '+56 9 8956 0937').strip(),
    'instagram':        os.getenv('CONTACTO_INSTAGRAM', 'aflora_natural').strip(),
}

# ── Analytics (GA4 + Meta Pixel) ────────────────────────────────────────────
# Si vacios, los snippets no se renderizan. Activar en produccion poniendo
# las variables en Railway. Sin tracking en local/desarrollo.
GA4_MEASUREMENT_ID = os.getenv('GA4_MEASUREMENT_ID', '').strip()
META_PIXEL_ID      = os.getenv('META_PIXEL_ID', '').strip()

# ── Transferencia bancaria (datos para checkout) ────────────────────────────
# Si BANCO_TITULAR vacio, la opcion "transferencia" no aparece en checkout.
# Cuando la duenia entregue sus datos reales, se pegan en Railway.
BANCO = {
    'titular':       os.getenv('BANCO_TITULAR', '').strip(),
    'rut':           os.getenv('BANCO_RUT', '').strip(),
    'banco':         os.getenv('BANCO_NOMBRE', '').strip(),
    'tipo_cuenta':   os.getenv('BANCO_TIPO_CUENTA', '').strip(),
    'numero_cuenta': os.getenv('BANCO_NUMERO_CUENTA', '').strip(),
    'email_aviso':   os.getenv('BANCO_EMAIL_AVISO', '').strip(),
}


# ── Mensajes → clases Bootstrap ────────────────────────────────────────────
from django.contrib.messages import constants as messages_constants
MESSAGE_TAGS = {
    messages_constants.DEBUG:   'secondary',
    messages_constants.INFO:    'info',
    messages_constants.SUCCESS: 'success',
    messages_constants.WARNING: 'warning',
    messages_constants.ERROR:   'danger',
}

# ── Default primary key ─────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ── Logging ──────────────────────────────────────────────────────────────────
# En desarrollo: logs van a la consola en formato legible.
# En producción: además se envían a Sentry (si SENTRY_DSN está configurado).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Loggers de nuestras apps -- usa logging.getLogger('aflora.pedidos')
        'aflora': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# ── Sentry (monitoreo de errores en producción) ─────────────────────────────
# Configurar SENTRY_DSN en variables de entorno cuando se quiera activar.
# Sin DSN, Sentry no se carga (sin overhead).
SENTRY_DSN = os.getenv('SENTRY_DSN', '')
if SENTRY_DSN and not DEBUG:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=0.1,        # 10% de requests con trazas (perf)
            send_default_pii=False,         # nunca enviar datos personales del cliente
            environment=os.getenv('ENVIRONMENT', 'production'),
        )
    except ImportError:
        # sentry-sdk no instalado: no rompemos arranque
        pass
