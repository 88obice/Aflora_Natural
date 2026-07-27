# Aflora Natural — Guía del proyecto (para Claude Code)

E-commerce en **Django 6** para Aflora Natural, pyme de velas aromáticas, homesprays y
difusores en Santiago de Chile. Repo: GitHub `88obice/Aflora_Natural` (rama `main`).
Dueño del proyecto: Angel (estudiante, nivel intermedio-bajo — explicale el porqué de
los cambios, no solo el qué). Cliente real: la dueña de la pyme.

## Stack y entorno
- Django 6 + PostgreSQL (local: base `aflora_db`), Bootstrap 5.
- **Requiere Python 3.12.** El `python` del PATH es 3.10 y NO tiene Django:
  usá siempre `.\venv\Scripts\python.exe` (ese sí es 3.12 con todo instalado).
- Pagos: **Flow es la pasarela principal** (con llaves de sandbox en Railway desde
  julio 2026; faltan las reales de la dueña). Mercado Pago quedó de respaldo: solo
  se ofrece si Flow no tiene llaves. Ver `LANZAMIENTO.md`.
- Imágenes: Cloudinary. Email: Brevo (API HTTP) en prod; Railway bloquea SMTP.
- Hosting actual: Railway (plan gratis por vencer; Angel evalúa migrar a un host de precio fijo).

## Cómo trabajar en este repo
- Corré los tests con `python manage.py test` (usan una BD de prueba; NO tocan datos reales).
- **Verificá SIEMPRE antes de dar por hecho algo**: `git status`, `python manage.py showmigrations`,
  `python manage.py check`. El código en disco manda; esta guía es un snapshot y puede quedar vieja.
- Al crear modelos nuevos: generá la migración (`makemigrations`) y avisá antes de aplicar en prod.
- **NUNCA commitear el archivo `.env`** — tiene credenciales reales (Gmail/Brevo, MP, etc.).
  Está en `.gitignore`; si aparece staged, sacalo.
- Patrón de integraciones "dormidas": si faltan las llaves (env vars), la función no aparece
  (Flow, transferencia bancaria, analytics, Sentry). Así se prueba sin credenciales reales.

## Convenciones del código
- Apps: `catalogo`, `carrito`, `pedidos`, `usuarios`, `gestion`. Panel propio en `/gestion/`
  (para la dueña) que coexiste con `/admin/` (técnico, de Angel).
- Estados del pedido: `estado` (cumplimiento: pendiente→confirmado→preparando→enviado→entregado→cancelado)
  y `estado_pago` (pendiente/pagado/rechazado/reembolsado) son **ejes separados**.
- La verdad de un pago es la consulta a la API (MP `payment().get()`, Flow `getStatus`), nunca
  los parámetros que llegan por el navegador. Webhooks confirman; las back_urls solo dan feedback.
- CLP sin decimales; filtro de template `clp`. Prefijo teléfono `+56 9 `.

## Tests
- 192 tests, todos pasando (`.\venv\Scripts\python.exe manage.py test`).
- Un test que pasa no prueba nada por sí solo: **antes de dar por bueno un test nuevo,
  rompé a propósito lo que vigila y confirmá que se pone en rojo.** Así se descubrió
  que un primer test de cupones no servía (creaba el pedido a mano, sin pasar por el
  checkout) y así apareció el bug del retorno de Flow.
- `pedidos/tests_flow.py` mockea `requests`: los tests no salen a internet.
- Los tests que tocan rate limiting deben limpiar el cache (`cache.clear()`) en
  setUp/tearDown: LocMemCache no se reinicia entre tests y el orden altera el resultado.
- `gestion/tests.py` arma las URLs del panel por introspección del urlconf. Si agregás
  una vista con `<pk>`, el test falla pidiendo sumarla al mapa — es el momento de
  verificar que tenga los decoradores de staff.

## Estado / pendientes (verificar contra el repo real)
- **Antes de lanzar: leer `LANZAMIENTO.md`** — checklist completo, con lo que falla en
  silencio marcado (Cloudinary, Brevo, `SITE_NOINDEX`, `FLOW_API_URL` en sandbox).
- **Sentry**: código listo en `settings.py` (modo errores-only, dormido sin `SENTRY_DSN`).
- **Cron pendientes** (cuando se defina el host): `enviar_recordatorios_carrito` (carrito
  abandonado), `purgar_carritos` y — si se implementa — backup semanal de pedidos.
- **Flow**: al abrir la dueña su cuenta, pegar `FLOW_API_KEY`/`FLOW_SECRET_KEY` reales y
  cambiar `FLOW_API_URL` a `https://www.flow.cl/api` (si no, se cobra contra sandbox).
- Backlog abierto: boleta electrónica SII, historia real de la dueña en "sobre nosotros"
  (necesita contenido de ella), cupón restringido a clientes específicos (hoy es genérico).
- Si se activan GA4 / Meta Pixel: esos scripts cargan sin pasar por el banner de cookies,
  y la política de privacidad dice que no se usan datos de navegación para publicidad.

## Seguridad
- Accesos por token público para tracking de pedidos (defensa IDOR); no exponer el id secuencial.
- Honeypot + rate limiting por IP en formularios públicos (registro, login, newsletter, notify-me).
