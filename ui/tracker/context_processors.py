from django.utils.functional import SimpleLazyObject

from tracker.money import RateBook, display_currency_for


def currency(request):
    """Give every page the viewer's favourite currency and a rate book.

    The rate book is lazy: its rates are only loaded if the page actually shows a price.
    """
    if not request.user.is_authenticated:
        return {}
    return {
        "display_currency": display_currency_for(request.user),
        "rate_book": SimpleLazyObject(RateBook.load),
    }
