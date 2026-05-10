"""
Envio de campanas de newsletter.

Procesa una CampanaNewsletter y manda email a todos los suscriptores activos.
- Manda en lotes de 30 con pausa de 1s para no saturar Gmail SMTP
- Cada email lleva link de unsubscribe personalizado
- Marca la campana como 'enviada' al terminar y registra metricas
"""
import logging
import time
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import CampanaNewsletter, SuscriptorNewsletter

logger = logging.getLogger('aflora.newsletter')

LOTE_SIZE = 30
PAUSA_ENTRE_LOTES = 1.0  # segundos


def construir_cuerpo(cuerpo, suscriptor, base_url):
    """Reemplaza {variables} y agrega footer con link de baja."""
    url_baja = '{}{}'.format(
        base_url, reverse('catalogo:unsubscribe_newsletter', args=[suscriptor.token_baja])
    )
    cuerpo_personalizado = cuerpo.replace('{email}', suscriptor.email)
    footer = (
        '\n\n--\n'
        'Recibiste este mail porque te suscribiste al newsletter de Aflora Natural.\n'
        'Si quieres dejar de recibirlo, haz click aqui: {}\n'
    ).format(url_baja)
    return cuerpo_personalizado + footer


def enviar_campana(campana, base_url, dry_email=None):
    """
    Envia la campana. Si dry_email se pasa, manda SOLO a ese email (modo prueba).
    """
    if dry_email:
        # Modo prueba: un suscriptor falso
        suscriptor_fake = SuscriptorNewsletter(email=dry_email, token_baja='preview-test')
        cuerpo = construir_cuerpo(campana.cuerpo, suscriptor_fake, base_url)
        try:
            send_mail(
                subject='[PRUEBA] ' + campana.asunto,
                message=cuerpo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[dry_email],
                fail_silently=False,
            )
            return {'enviados': 1, 'fallidos': 0, 'modo': 'prueba'}
        except Exception:
            logger.exception('Error en envio de prueba a %s', dry_email)
            return {'enviados': 0, 'fallidos': 1, 'modo': 'prueba'}

    # Envio real
    suscriptores = list(SuscriptorNewsletter.objects.filter(activo=True))
    campana.estado = 'enviando'
    campana.total_destinatarios = len(suscriptores)
    campana.save(update_fields=['estado', 'total_destinatarios'])

    enviados = 0
    fallidos = 0

    for i in range(0, len(suscriptores), LOTE_SIZE):
        lote = suscriptores[i:i+LOTE_SIZE]
        for s in lote:
            cuerpo = construir_cuerpo(campana.cuerpo, s, base_url)
            try:
                send_mail(
                    subject=campana.asunto,
                    message=cuerpo,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[s.email],
                    fail_silently=False,
                )
                enviados += 1
            except Exception:
                logger.exception('Newsletter campana #%s: fallo envio a %s', campana.pk, s.email)
                fallidos += 1
        # Pausa entre lotes para no saturar SMTP
        if i + LOTE_SIZE < len(suscriptores):
            time.sleep(PAUSA_ENTRE_LOTES)

    campana.estado = 'enviada' if fallidos == 0 else 'error'
    campana.enviada_en = timezone.now()
    campana.total_enviados = enviados
    campana.total_fallidos = fallidos
    campana.save(update_fields=['estado', 'enviada_en', 'total_enviados', 'total_fallidos'])

    logger.info('Newsletter campana #%s: %s enviados, %s fallidos', campana.pk, enviados, fallidos)
    return {'enviados': enviados, 'fallidos': fallidos, 'modo': 'real'}
