from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Category(models.Model):
    PERIOD_CHOICES = [
        ("one_time", "One-time"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    ]
    name = models.CharField(max_length=80, unique=True)
    field_definitions = models.JSONField(default=list, blank=True)
    default_period = models.CharField(max_length=12, choices=PERIOD_CHOICES, default="one_time")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Currency(models.TextChoices):
        RON = "RON", "Romanian leu (RON)"
        EUR = "EUR", "Euro (EUR)"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    favorite_currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.RON
    )

    def __str__(self):
        return f"{self.user} profile"


class Item(models.Model):
    class Period(models.TextChoices):
        ONE_TIME = "one_time", "One-time"
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        REMOVED = "removed", "Listing removed"
        ERROR = "error", "Needs attention"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        AUTOMATIC = "automatic", "Automatic"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="items")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL)
    period = models.CharField(max_length=12, choices=Period.choices, default=Period.ONE_TIME)
    custom_values = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    last_checked = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    # Empty for normal items. Archived items are hidden and not checked, but keep their status,
    # prices and comparison groups, so restoring brings them back exactly as they were.
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at", "name"]

    def __str__(self):
        return self.name

    @property
    def is_archived(self):
        return self.archived_at is not None

    @property
    def latest_prices(self):
        """The two newest price points, prefetched by dashboard and list views."""
        cached = getattr(self, "_latest_prices", None)
        if cached is not None:
            return cached
        return list(self.price_points.order_by("-recorded_at", "-id")[:2])

    @property
    def current_price(self):
        prices = self.latest_prices
        return prices[0] if prices else None


class PricePoint(models.Model):
    class Currency(models.TextChoices):
        RON = "RON", "RON"
        EUR = "EUR", "EUR"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        AUTOMATIC = "automatic", "Automatic"

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="price_points")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    recorded_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL)
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["recorded_at", "id"]

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Enter a price greater than zero."})

    def __str__(self):
        return f"{self.amount} {self.currency} on {self.recorded_at:%Y-%m-%d}"


class ExchangeRate(models.Model):
    date = models.DateField()
    currency = models.CharField(max_length=3, choices=PricePoint.Currency.choices)
    ron_per_unit = models.DecimalField(max_digits=12, decimal_places=6)

    class Meta:
        ordering = ["-date", "currency"]
        constraints = [
            models.UniqueConstraint(fields=["date", "currency"], name="unique_currency_rate_per_day")
        ]

    def __str__(self):
        return f"{self.currency} rate for {self.date}"


class CheckRun(models.Model):
    """One run of the daily `check_prices` command, covering every household item."""

    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)  # empty while running, or if interrupted
    checked = models.PositiveIntegerField(default=0)
    ok = models.PositiveIntegerField(default=0)
    attention = models.PositiveIntegerField(default=0)
    removed = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Daily check on {timezone.localtime(self.started_at):%Y-%m-%d %H:%M}"


class CheckAttempt(models.Model):
    class Outcome(models.TextChoices):
        OK = "ok", "Successful"
        BLOCKED = "blocked", "Blocked"
        REMOVED = "removed", "Removed"
        ERROR = "error", "Error"

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="check_attempts")
    # Empty for a manual "Check now"; set when the attempt was part of a daily run.
    run = models.ForeignKey(CheckRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="attempts")
    attempted_at = models.DateTimeField(default=timezone.now)
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    message = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-attempted_at"]


class ComparisonGroup(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comparison_groups")
    name = models.CharField(max_length=120)
    items = models.ManyToManyField(Item, related_name="comparison_groups", blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_group_name_per_user")
        ]

    def clean(self):
        if self.pk and self.items.exclude(owner=self.owner).exists():
            raise ValidationError("A comparison group can contain only your own items.")

    def __str__(self):
        return self.name
