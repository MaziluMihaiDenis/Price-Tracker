import math
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from tracker.adapters import adapter_for
from tracker.adapters.base import PageResult
from tracker.checks import can_be_checked, check_item, read_page, seconds_until_next_check, start_tracking
from tracker.forms import AutomaticItemForm, ComparisonGroupForm, ItemForm, LinkForm, PricePointForm, ProfileForm
from tracker.daily import running_check
from tracker.models import Category, CheckAttempt, CheckRun, ComparisonGroup, Item, PricePoint

# The price read during "Add by link" is kept in the session between preview and save,
# so the saved price is the one the app read, not one sent back by the browser.
LINK_PREVIEW_KEY = "link_preview"


def _items_for(user):
    return (
        Item.objects.filter(owner=user)
        .select_related("category")
        .prefetch_related(
            Prefetch("price_points", queryset=PricePoint.objects.order_by("-recorded_at")[:2], to_attr="_latest_prices")
        )
    )


def _daily_check_summary(user):
    """The latest daily check, counted for this user's items only (never other people's)."""
    run = CheckRun.objects.first()
    if run is None:
        return None
    attempts = run.attempts.filter(item__owner=user)
    Outcome = CheckAttempt.Outcome
    end = run.finished_at or timezone.now()
    return {
        "run": run,
        "running": run.finished_at is None and running_check() == run,
        "ok": attempts.filter(outcome=Outcome.OK).count(),
        "attention": attempts.filter(outcome__in=[Outcome.BLOCKED, Outcome.ERROR]).count(),
        "removed": attempts.filter(outcome=Outcome.REMOVED).count(),
        "new_prices": PricePoint.objects.filter(
            item__owner=user, source=PricePoint.Source.AUTOMATIC,
            recorded_at__gte=run.started_at, recorded_at__lte=end,
        ).count(),
    }


@login_required
def dashboard(request):
    items = _items_for(request.user)
    recent_items = list(items[:5])
    recent_prices = PricePoint.objects.filter(item__owner=request.user).select_related(
        "item", "item__category"
    )[:6]
    context = {
        "active_count": items.filter(status=Item.Status.ACTIVE).count(),
        "attention_count": items.filter(status__in=[Item.Status.ERROR, Item.Status.REMOVED]).count(),
        "item_count": items.count(),
        "recent_items": recent_items,
        "recent_prices": recent_prices,
        "groups": ComparisonGroup.objects.filter(owner=request.user).prefetch_related("items")[:3],
        "daily_check": _daily_check_summary(request.user),
    }
    return render(request, "tracker/dashboard.html", context)


@login_required
def item_list(request):
    items = _items_for(request.user)
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    status = request.GET.get("status", "")
    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category_id.isdigit():
        items = items.filter(category_id=category_id)
    if status in Item.Status.values:
        items = items.filter(status=status)
    return render(request, "tracker/item_list.html", {
        "items": items,
        "categories": Category.objects.all(),
        "query": query,
        "selected_category": category_id,
        "selected_status": status,
        "statuses": Item.Status.choices,
    })


@login_required
def item_create(request):
    item_form = ItemForm(request.POST or None)
    price_form = PricePointForm(request.POST or None, prefix="price")
    if request.method == "POST" and item_form.is_valid() and price_form.is_valid():
        item = item_form.save(commit=False)
        item.owner = request.user
        item.source = Item.Source.MANUAL
        item.save()
        price = price_form.save(commit=False)
        price.item = item
        price.source = PricePoint.Source.MANUAL
        price.save()
        messages.success(request, "Item and first price saved.")
        return redirect("item-detail", pk=item.pk)
    return render(request, "tracker/item_form.html", {
        "item_form": item_form,
        "price_form": price_form,
        "page_title": "Add an item",
        "submit_label": "Save item",
    })


@login_required
def item_add_link(request):
    """Add an automatically tracked item: step 1 reads the link, step 2 confirms and saves."""
    step = request.POST.get("step") if request.method == "POST" else None
    preview = request.session.get(LINK_PREVIEW_KEY)

    if step == "save" and preview:
        details_form = AutomaticItemForm(request.POST)
        if details_form.is_valid():
            existing = Item.objects.filter(owner=request.user, url=preview["url"]).first()
            if existing:
                messages.info(request, "You already track this link.")
                return redirect("item-detail", pk=existing.pk)
            item = details_form.save(commit=False)
            item.owner = request.user
            item.url = preview["url"]
            page = PageResult(title=preview["title"], price=Decimal(preview["price"]),
                              currency=preview["currency"], available=preview["available"])
            start_tracking(item, page)
            del request.session[LINK_PREVIEW_KEY]
            messages.success(request, f"Now tracking {item.name} at {page.price} {page.currency}.")
            return redirect("item-detail", pk=item.pk)
        return render(request, "tracker/item_link_form.html", {"preview": preview, "details_form": details_form})

    link_form = LinkForm(request.POST if step == "preview" else None)
    existing_item = None
    if step == "preview" and link_form.is_valid():
        url = link_form.cleaned_data["url"]
        existing_item = Item.objects.filter(owner=request.user, url=url).first()
        if existing_item:
            link_form.add_error("url", "You already track this link.")
        else:
            result = read_page(url)
            if result.outcome != CheckAttempt.Outcome.OK:
                link_form.add_error("url", result.message)
            else:
                adapter = adapter_for(url)
                page = result.page
                preview = {
                    "url": url, "site": adapter.name, "title": page.title, "price": str(page.price),
                    "currency": page.currency, "available": page.available, "note": result.message,
                }
                request.session[LINK_PREVIEW_KEY] = preview
                details_form = AutomaticItemForm(initial={"name": page.title[:180], "period": adapter.default_period})
                return render(request, "tracker/item_link_form.html", {"preview": preview, "details_form": details_form})
    elif request.method == "GET":
        request.session.pop(LINK_PREVIEW_KEY, None)  # "Start over" clears an old preview
    return render(request, "tracker/item_link_form.html", {"link_form": link_form, "existing_item": existing_item})


@login_required
@require_POST
def item_check(request, pk):
    """The "Check now" button: read today's price for one automatic item."""
    item = get_object_or_404(Item, pk=pk, owner=request.user)
    if not can_be_checked(item):
        messages.info(request, "This item isn't checked automatically.")
        return redirect("item-detail", pk=item.pk)
    wait = seconds_until_next_check(item)
    if wait:
        minutes = math.ceil(wait / 60)
        messages.info(request, f"Checked recently. You can check again in {minutes} minute{'s' if minutes != 1 else ''}.")
        return redirect("item-detail", pk=item.pk)
    result = check_item(item)
    if result.outcome == CheckAttempt.Outcome.OK:
        messages.success(request, result.message)
    else:
        messages.warning(request, f"Couldn't check the price: {result.message}")
    return redirect("item-detail", pk=item.pk)


@login_required
def item_update(request, pk):
    item = get_object_or_404(Item, pk=pk, owner=request.user)
    form = ItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Item details updated.")
        return redirect("item-detail", pk=item.pk)
    return render(request, "tracker/item_form.html", {
        "item_form": form,
        "page_title": "Edit item",
        "submit_label": "Save changes",
        "editing": True,
    })


@login_required
def item_detail(request, pk):
    item = get_object_or_404(_items_for(request.user), pk=pk)
    price_form = PricePointForm(request.POST or None, prefix="price")
    if request.method == "POST":
        if price_form.is_valid():
            point = price_form.save(commit=False)
            point.item = item
            point.source = PricePoint.Source.MANUAL
            point.save()
            messages.success(request, "Price added to the history.")
            return redirect("item-detail", pk=item.pk)
    points = list(item.price_points.order_by("recorded_at", "id"))
    chart_data = {
        "labels": [timezone.localtime(point.recorded_at).strftime("%d %b %Y") for point in points],
        "values": [str(point.amount) for point in points],
        "currencies": [point.currency for point in points],
    }
    return render(request, "tracker/item_detail.html", {
        "item": item,
        "price_form": price_form,
        "price_points": list(reversed(points)),
        "chart_data": chart_data,
        "can_check": can_be_checked(item),
    })


@login_required
def comparison_list(request):
    groups = ComparisonGroup.objects.filter(owner=request.user).prefetch_related("items")
    return render(request, "tracker/comparison_list.html", {"groups": groups})


@login_required
def comparison_create(request):
    form = ComparisonGroupForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.owner = request.user
        group.save()
        form.save_m2m()
        messages.success(request, "Comparison saved.")
        return redirect("comparison-detail", pk=group.pk)
    return render(request, "tracker/comparison_form.html", {"form": form})


@login_required
def comparison_detail(request, pk):
    group = get_object_or_404(
        ComparisonGroup.objects.filter(owner=request.user).prefetch_related(
            Prefetch(
                "items",
                queryset=Item.objects.select_related("category").prefetch_related(
                    Prefetch(
                        "price_points",
                        queryset=PricePoint.objects.order_by("-recorded_at")[:2],
                        to_attr="_latest_prices",
                    )
                ),
            )
        ),
        pk=pk,
    )
    return render(request, "tracker/comparison_detail.html", {"group": group})


@login_required
def settings_view(request):
    from tracker.models import Profile

    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Preferences updated.")
        return redirect("settings")
    return render(request, "tracker/settings.html", {"form": form})
