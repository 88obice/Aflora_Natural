from django import template

register = template.Library()

@register.filter
def clp(value):
    """Formatea un número como peso chileno: $10.000"""
    try:
        numero = int(round(float(value)))
        return f"${numero:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return value
