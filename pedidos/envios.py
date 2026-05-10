"""
Logica de costos de envio.

Reglas (configurables aca):
  - Retiro en local: gratis
  - Envio a domicilio:
      * Zona urbana RM: $3.500
      * Resto de RM:    $4.500
      * Otras regiones: $5.500
  - Envio gratis sobre $40.000

Esto debe ajustarse cuando la duena confirme tarifas reales con el courier.
"""
from decimal import Decimal


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

COSTO_RETIRO_LOCAL    = Decimal('0')
COSTO_ENVIO_RM_URBANA = Decimal('3500')
COSTO_ENVIO_RM_RESTO  = Decimal('4500')
COSTO_ENVIO_REGIONES  = Decimal('5500')

UMBRAL_ENVIO_GRATIS = Decimal('40000')


def calcular_costo_envio(metodo, comuna, region, subtotal):
    """Devuelve Decimal con el costo de envio para los parametros dados."""
    if metodo == 'retiro_local':
        return COSTO_RETIRO_LOCAL

    subtotal = Decimal(subtotal or 0)
    if subtotal >= UMBRAL_ENVIO_GRATIS:
        return Decimal('0')

    es_rm = (region or '').strip().lower().startswith('region metropolitana')
    if not es_rm:
        return COSTO_ENVIO_REGIONES

    comuna_n = (comuna or '').strip()
    if comuna_n in COMUNAS_URBANAS_RM:
        return COSTO_ENVIO_RM_URBANA
    return COSTO_ENVIO_RM_RESTO


def comunas_disponibles():
    """Lista ordenada de tuplas (valor, label) para selects."""
    return [(c, c) for c in sorted(set(COMUNAS_RM))]
