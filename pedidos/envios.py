"""
Costo de envio.

DECISION (julio 2026): el despacho va POR PAGAR. El sitio no cobra envio; el
courier le cobra al destinatario cuando entrega.

Por que: antes habia tres tarifas escritas a mano ($3.500 RM urbana, $4.500
resto de RM, $5.500 regiones) que nunca salieron de una cotizacion real. La de
regiones era la peligrosa: cobraba lo mismo mandar a Vina que a Punta Arenas,
asi que cada envio largo se vendia a perdida sin que nadie se enterara.

Preferimos no cobrar nada antes que cobrar un numero inventado: una estimacion
equivocada le cuesta plata a la duenia o le arruina la compra al cliente.

IMPORTANTE: como el cliente no paga el despacho en el sitio, hay que decirselo
CLARO antes de comprar (checkout) y repetirlo en el email de confirmacion. Si
se enterara al recibir el paquete, podria rechazarlo, y ahi la duenia paga ida
y vuelta y pierde la venta.

Cuando la duenia tenga convenio con un courier (Blue Express, Chilexpress) y
credenciales de su API, esto se reemplaza por una cotizacion real: la firma de
calcular_costo_envio() ya recibe comuna, region y subtotal, asi que el cambio
queda contenido en este archivo.
"""
from decimal import Decimal

from .regiones_chile import normalizar


# Comunas de la RM, para el select del checkout. Ya no definen tarifas: estan
# solo para ofrecer una lista conocida al elegir comuna.
COMUNAS_URBANAS_RM = [
    'Santiago', 'Providencia', 'Las Condes', 'Vitacura', 'Lo Barnechea',
    'Nunoa', 'Macul', 'La Reina', 'La Florida', 'Penalolen',
    'Maipu', 'San Miguel', 'San Joaquin', 'Estacion Central',
    'Independencia', 'Recoleta', 'Quinta Normal', 'Cerrillos',
    'Pedro Aguirre Cerda', 'Lo Espejo', 'La Cisterna', 'San Bernardo',
    'Puente Alto', 'La Granja', 'San Ramon', 'El Bosque',
    'Conchali', 'Huechuraba', 'Renca', 'Quilicura', 'Cerro Navia',
    'Lo Prado', 'Pudahuel',
]

COMUNAS_RM_RESTO = [
    'Padre Hurtado', 'Penaflor', 'Talagante', 'El Monte', 'Isla de Maipo',
    'Buin', 'Paine', 'Calera de Tango', 'Pirque', 'Colina', 'Lampa',
    'Til Til', 'Melipilla', 'Curacavi', 'Maria Pinto', 'San Pedro',
    'Alhue',
]

COMUNAS_RM = COMUNAS_URBANAS_RM + COMUNAS_RM_RESTO

# El sitio no cobra despacho: el courier le cobra al destinatario al entregar.
COSTO_ENVIO_POR_PAGAR = Decimal('0')
COSTO_RETIRO_LOCAL    = Decimal('0')


def envio_es_por_pagar(metodo):
    """
    True si a este pedido hay que avisarle que el despacho se paga al recibir.
    El retiro en local no paga nada, asi que queda fuera.

    Los templates y los emails usan esto para mostrar "Por pagar" en vez de
    "$0", que se leeria como envio gratis.
    """
    return metodo != 'retiro_local'


def calcular_costo_envio(metodo, comuna=None, region=None, subtotal=None):
    """
    Devuelve el costo de envio que cobra EL SITIO. Hoy siempre 0: el retiro en
    local es gratis y el despacho a domicilio va por pagar.

    Mantiene la firma completa (comuna, region, subtotal) a proposito: es la
    que va a necesitar la cotizacion real cuando haya API del courier.
    """
    if metodo == 'retiro_local':
        return COSTO_RETIRO_LOCAL
    return COSTO_ENVIO_POR_PAGAR


def comunas_disponibles():
    """Lista ordenada de tuplas (valor, label) para selects."""
    return [(c, c) for c in sorted(set(COMUNAS_RM))]
