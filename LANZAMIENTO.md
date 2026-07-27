# Checklist de lanzamiento — Aflora Natural

Qué hay que tener listo antes de abrir la tienda al público, en orden.
Marcá con `[x]` a medida que avances.

La regla de oro: **lo peligroso no es lo que falla con un error rojo, sino lo
que falla en silencio.** Esas cosas están marcadas con ⚠ y son las que hay que
revisar dos veces.

---

## 1. Pagos

- [ ] La dueña abre su cuenta en **Flow** (a su nombre y RUT, no al tuyo).
- [ ] Cargar en las variables del host las **tres**:
  - `FLOW_API_KEY`
  - `FLOW_SECRET_KEY`
  - ⚠ `FLOW_API_URL = https://www.flow.cl/api`
- [ ] ⚠ Verificar que `FLOW_API_URL` NO quedó en sandbox. Si queda en
      `sandbox.flow.cl`, el checkout funciona, el cliente ve "pago exitoso",
      el pedido se confirma... y **no entra un peso**. Es el error más caro
      posible y no da ningún aviso.
- [ ] Hacer una compra real de prueba (monto chico) y confirmar que la plata
      aparece en la cuenta de Flow de la dueña.

**Transferencia bancaria** (opcional, si la quiere ofrecer):

- [ ] Cargar `BANCO_TITULAR`, `BANCO_RUT`, `BANCO_NOMBRE`,
      `BANCO_TIPO_CUENTA`, `BANCO_NUMERO_CUENTA`, `BANCO_EMAIL_AVISO`.
- [ ] Si `BANCO_TITULAR` queda vacío, la opción no aparece en el checkout.
      Eso es a propósito: mejor no ofrecerla que ofrecerla con datos incompletos.

**Mercado Pago**: mientras Flow tenga llaves, MP no se ofrece. Si algún día
sacás las llaves de Flow, el checkout vuelve solo a MP.

---

## 2. Imágenes ⚠

- [ ] Cargar `CLOUDINARY_URL` (una sola variable, formato
      `cloudinary://api_key:api_secret@cloud_name`, se copia entera desde
      Cloudinary → Settings → API Keys).
- [ ] ⚠ Sin esto, las fotos de productos y los comprobantes de transferencia
      que suben los clientes **se borran en cada deploy**: el disco del host es
      efímero. No da error: las imágenes simplemente desaparecen.
- [ ] Subir una foto de prueba desde `/gestion/`, hacer un deploy, y verificar
      que la foto sigue ahí.

---

## 3. Emails ⚠

- [ ] Cargar `BREVO_API_KEY`.
- [ ] Cargar `DEFAULT_FROM_EMAIL` con un remitente **verificado en Brevo**
      (Brevo rechaza los envíos de remitentes que no verificó).
- [ ] ⚠ Si falta la API key, el sitio anda perfecto pero no sale ni un email:
      ni confirmación de pedido, ni recuperar contraseña, ni newsletter. Nadie
      se entera hasta que un cliente reclama.
- [ ] Probar de punta a punta: hacer un pedido de prueba y confirmar que llega
      el email al cliente **y** el aviso a `ADMIN_EMAIL`.
- [ ] Probar "olvidé mi contraseña" con una cuenta real.

---

## 4. Contenido

- [ ] Cargar los productos reales: nombre, descripción, precio, **stock**, foto.
- [ ] Borrar los productos de prueba.
- [ ] Borrar los pedidos de prueba (o dejarlos si no molestan en las métricas
      del panel — las de clientes cuentan solo pedidos pagados).
- [ ] Marcar como **destacados** los que van en la portada (si no hay ninguno,
      la home muestra los más recientes).
- [ ] Reemplazar el texto de "Sobre nosotros" con la historia real de la dueña.
- [ ] Revisar la página de envíos: costos y plazos reales.
- [ ] Confirmar que los datos de contacto del footer son los correctos
      (`CONTACTO_EMAIL`, `CONTACTO_WHATSAPP`, `CONTACTO_INSTAGRAM`).

---

## 5. Acceso al panel

- [ ] Cargar `SUPERUSER_NAME`, `SUPERUSER_PASSWORD`, `SUPERUSER_EMAIL`.
      El comando `crear_superusuario` corre en cada deploy y las usa.
- [ ] ⚠ Sin estas variables no se crea la cuenta y te quedás sin poder entrar
      a `/admin/` ni a `/gestion/`.
- [ ] Contraseña larga: esa cuenta ve todos los pedidos y datos de clientes.
- [ ] Crear la cuenta de la dueña como usuario `staff` (no superusuario) para
      que use `/gestion/` sin tocar `/admin/`.
- [ ] Enseñarle el panel: confirmar pagos, cambiar estados, cargar stock.

---

## 6. Prueba completa antes de abrir

Recorrer el camino del cliente, en el sitio de producción:

- [ ] Entrar como visitante, buscar un producto, agregarlo al carrito.
- [ ] Comprar **sin cuenta** (checkout invitado) y pagar con Flow.
- [ ] Verificar que llega el email de confirmación con el link de seguimiento.
- [ ] Abrir ese link de seguimiento y ver el estado del pedido.
- [ ] Entrar a `/gestion/` y confirmar que el pedido aparece, con el stock ya
      descontado.
- [ ] Cambiar el estado a "enviado" con código de seguimiento y verificar que
      le llega el email al cliente.
- [ ] Registrarse como cliente, comprar de nuevo, y ver el pedido en el perfil.
- [ ] Probar un cupón: aplicarlo, abandonar el pago, y confirmar que el cupón
      sigue disponible (se consume recién al pagar).
- [ ] Probar desde el celular: el checkout es donde más duele un error de
      diseño en pantalla chica.

---

## 7. El día que abrís

- [ ] ⚠ Poner `SITE_NOINDEX=False`. Mientras esté en `True`, todo el sitio sale
      con `noindex` y **Google no lo indexa nunca**. Es un interruptor fácil de
      olvidar porque nada se ve distinto.
- [ ] Verificar que `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` tengan el dominio
      definitivo. Sin `CSRF_TRUSTED_ORIGINS` fallan todos los formularios.
- [ ] `BASE_URL` con el dominio real y sin barra al final (se usa en los links
      de todos los emails).
- [ ] Enviar el sitemap a Google Search Console: `https://tudominio.cl/sitemap.xml`.
- [ ] Revisar que `robots.txt` no esté bloqueando el sitio.

---

## 8. Después de abrir

- [ ] `SENTRY_DSN` para enterarte de los errores 500 sin depender de que un
      cliente te avise.
- [ ] `MP_WEBHOOK_SECRET` si algún día volvés a usar Mercado Pago.
- [ ] Programar el cron de carrito abandonado (`enviar_recordatorios_carrito`)
      y el de limpieza (`purgar_carritos`). Depende del host que elijas.
- [ ] Definir cómo se respaldan los datos: los pedidos son la contabilidad del
      negocio. Como mínimo, exportar el CSV de pedidos cada tanto desde
      `/gestion/pedidos/exportar/`.
- [ ] Subir `SECURE_HSTS_SECONDS` a `31536000` (1 año) cuando el dominio lleve
      un par de semanas estable.
- [ ] Si activás `GA4_MEASUREMENT_ID` o `META_PIXEL_ID`: esos scripts cargan
      sin pasar por el banner de cookies. Habría que agregar consentimiento
      real o actualizar la política de privacidad.

---

## Pendientes conocidos (no bloquean el lanzamiento)

- Boleta electrónica SII: hoy no se emite ninguna. Hay que ver cómo lo maneja
  la dueña (¿boleta manual? ¿algún servicio de facturación?).
- Cupones restringidos a clientes puntuales: hoy el cupón es genérico, cualquiera
  con el código lo puede usar.

---

## Comandos útiles

Todo con el Python del entorno virtual (`python` a secas es 3.10 y no tiene
Django instalado):

```bash
.\venv\Scripts\python.exe manage.py test
```

```bash
.\venv\Scripts\python.exe manage.py check --deploy
```

```bash
.\venv\Scripts\python.exe manage.py showmigrations
```
