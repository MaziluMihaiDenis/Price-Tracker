from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tracker.forms import ComparisonGroupForm, ItemForm, PricePointForm, ProfileForm
from tracker.models import Category, ComparisonGroup, Item, PricePoint


def _items_for(user):
    return (
        Item.objects.filter(owner=user)
        .select_related("category")
        .prefetch_related(
            Prefetch("price_points", queryset=PricePoint.objects.order_by("-recorded_at")[:2], to_attr="_latest_prices")
        )
    )


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
