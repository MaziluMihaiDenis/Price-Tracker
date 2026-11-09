import re

from django import forms
from django.core.validators import URLValidator

from tracker.adapters import adapter_for, clean_url, supported_site_names
from tracker.models import ComparisonGroup, Item, PricePoint, Profile

# The first link in pasted text, e.g. from a phone app's Share button ("Title https://...").
LINK_IN_TEXT = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}"


class BootstrapFormMixin:
    """Apply the small set of Bootstrap classes shared by tracker forms."""

    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                continue
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class ItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Item
        fields = ("name", "category", "description", "url", "period")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = "Choose a category"
        self.fields["url"].required = False
        self.apply_bootstrap_classes()

    def clean_url(self):
        url = self.cleaned_data["url"]
        # Automatic items are re-checked from their link, so it must stay on a supported site.
        if self.instance.pk and self.instance.source == Item.Source.AUTOMATIC:
            if not url or adapter_for(url) is None:
                raise forms.ValidationError(
                    f"Automatically tracked items need a link from a supported site ({supported_site_names()})."
                )
            url = clean_url(url)
        return url


class LinkForm(BootstrapFormMixin, forms.Form):
    # A plain text field rather than a URL field: the browser's own URL check rejects links
    # without "https://" and shared "title + link" text, and its length limit silently cuts
    # long links. The server finds and checks the link instead (see clean_url).
    url = forms.CharField(
        label="Product or listing link",
        max_length=2000,
        widget=forms.TextInput(attrs={
            "placeholder": "Paste a link, e.g. https://www.emag.ro/...",
            "inputmode": "url",
            "autocomplete": "off",
            "spellcheck": "false",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_url(self):
        text = self.cleaned_data["url"]
        match = LINK_IN_TEXT.search(text)
        if match:
            url = match.group().rstrip(TRAILING_PUNCTUATION)
        elif len(text.split()) == 1 and "." in text:
            url = text  # a bare address such as "storia.ro/ro/oferta/..."
        else:
            raise forms.ValidationError("Paste a link that starts with https:// or www.")
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url

        url = clean_url(url)  # tracking parts removed before the length check below
        try:
            URLValidator(schemes=["http", "https"])(url)
        except forms.ValidationError:
            raise forms.ValidationError("That doesn't look like a valid link.")
        if adapter_for(url) is None:
            raise forms.ValidationError(
                f"This site isn't supported yet — add it manually instead. "
                f"Supported sites: {supported_site_names()}."
            )
        if len(url) > Item._meta.get_field("url").max_length:
            raise forms.ValidationError(
                "This link is too long to store, even without its tracking parts. "
                "Add the item manually instead."
            )
        return url


class AutomaticItemForm(BootstrapFormMixin, forms.ModelForm):
    """Details the user confirms after previewing a link (the URL itself comes from the preview)."""

    class Meta:
        model = Item
        fields = ("name", "category", "description", "period")
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = "Choose a category"
        self.apply_bootstrap_classes()


class PricePointForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PricePoint
        fields = ("amount", "currency", "recorded_at", "note")
        widgets = {
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "recorded_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "note": forms.TextInput(attrs={"placeholder": "Optional context"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recorded_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.apply_bootstrap_classes()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount


class ComparisonGroupForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ComparisonGroup
        fields = ("name", "items")
        widgets = {"items": forms.CheckboxSelectMultiple}

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.fields["items"].queryset = Item.objects.filter(
            owner=owner, archived_at__isnull=True).select_related("category")
        self.apply_bootstrap_classes()

    def clean_items(self):
        # Archived members aren't shown as checkboxes, so add them back: saving the group
        # must never silently drop them (restoring an item brings it back to its groups).
        items = list(self.cleaned_data["items"])
        if self.instance.pk:
            items += list(self.instance.items.filter(archived_at__isnull=False))
        return items

    def clean_name(self):
        # The owner isn't a form field, so Django can't check "one name per person" itself:
        # without this, a duplicate name would crash on save instead of showing an error.
        name = self.cleaned_data["name"].strip()
        others = ComparisonGroup.objects.filter(owner=self.owner, name__iexact=name)
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError("You already have a comparison with this name.")
        return name


class AddToComparisonForm(forms.Form):
    """The "Add to comparison" card on an item page: only your groups that don't contain the item yet."""

    group = forms.ModelChoiceField(queryset=ComparisonGroup.objects.none(), empty_label=None,
                                   label="Add to a comparison")

    def __init__(self, *args, item, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = ComparisonGroup.objects.filter(owner=item.owner).exclude(items=item)
        self.fields["group"].widget.attrs["class"] = "form-select"


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("favorite_currency",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
