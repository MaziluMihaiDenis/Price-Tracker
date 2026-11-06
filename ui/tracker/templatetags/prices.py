from django import template

from tracker.money import display_price

register = template.Library()


@register.simple_tag(takes_context=True)
def converted_price(context, point):
    """{% converted_price point as p %}: the price point as this viewer should see it.

    Uses `display_currency` and `rate_book` from tracker.context_processors.currency.
    Render it with {% include 'tracker/_price.html' with p=p %}.
    """
    return display_price(point.amount, point.currency, point.recorded_at,
                         context.get("display_currency"), context.get("rate_book"))
