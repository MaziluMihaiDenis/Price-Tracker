from django.contrib import admin

from tracker.models import Category, CheckAttempt, CheckRun, ComparisonGroup, ExchangeRate, Item, PricePoint, Profile


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "default_period")
    search_fields = ("name",)


class PricePointInline(admin.TabularInline):
    model = PricePoint
    extra = 0


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "category", "status", "source", "updated_at")
    list_filter = ("category", "status", "source")
    search_fields = ("name", "owner__username")
    inlines = (PricePointInline,)


admin.site.register(Profile)
admin.site.register(ExchangeRate)
admin.site.register(CheckAttempt)


@admin.register(CheckRun)
class CheckRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "finished_at", "checked", "ok", "attention", "removed", "skipped")
admin.site.register(ComparisonGroup)
