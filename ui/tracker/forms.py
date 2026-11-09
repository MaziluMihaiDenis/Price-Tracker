import re

from django import forms
from django.core.validators import URLValidator

from tracker.adapters import adapter_for, clean_url, supported_site_names
from tracker import custom_fields
from tracker.models import Category, ComparisonGroup, Item, PricePoint, Profile

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


class CategoryForm(BootstrapFormMixin, forms.ModelForm):
    """A category's name and default period. Its fields are edited with FieldDefinitionFormSet."""

    class Meta:
        model = Category
        fields = ("name", "default_period")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        others = Category.objects.filter(name__iexact=name)
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name


class FieldDefinitionForm(forms.Form):
    """One row of a category's field list. `key` is set for existing fields, empty for new ones."""

    key = forms.CharField(required=False, widget=forms.HiddenInput)
    label = forms.CharField(required=False, max_length=custom_fields.MAX_LABEL)
    type = forms.ChoiceField(choices=custom_fields.TYPE_CHOICES, initial=custom_fields.TEXT)
    unit = forms.CharField(required=False, max_length=12, help_text="Numbers only, e.g. m²")
    choices = forms.CharField(required=False, max_length=400, help_text="Choice lists only, comma-separated")

    def __init__(self, *args, locked_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.locked_type = locked_type
        if locked_type:
            # A field's type can't change: its stored values were checked against it.
            self.fields["type"].disabled = True
            self.fields["type"].initial = locked_type
        for name, field in self.fields.items():
            if name not in ("key", "ORDER", "DELETE"):
                css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
                field.widget.attrs.setdefault("class", f"{css} form-control-sm" if css == "form-control" else f"{css} form-select-sm")


class BaseFieldDefinitionFormSet(forms.BaseFormSet):
    """The whole field list: limits, unique labels, one Location, stable keys."""

    def __init__(self, *args, existing=(), **kwargs):
        self.existing = {d["key"]: d for d in existing}
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        key = None
        if index is not None and index < len(self.initial or []):
            key = self.initial[index].get("key")
        elif self.is_bound:
            key = self.data.get(self.add_prefix(index) + "-key") if index is not None else None
        kwargs["locked_type"] = self.existing.get(key, {}).get("type")
        return kwargs

    def clean(self):
        if any(self.errors):
            return
        rows = []
        for form in self.ordered_forms if self.can_order else self.forms:
            data = form.cleaned_data
            if not data or data.get("DELETE") or not data.get("label", "").strip():
                continue
            rows.append(form)
        definitions, labels, taken = [], set(), set()
        for form in rows:
            data = form.cleaned_data
            label = " ".join(data["label"].split())
            if label.lower() in labels:
                raise forms.ValidationError(f"Two fields are called “{label}”. Field names must be different.")
            labels.add(label.lower())
            old = self.existing.get(data.get("key"))
            if old and old["key"] not in taken:
                key, kind = old["key"], old["type"]  # the type is locked; the key never changes
            else:
                key, kind = None, data["type"]
            definition = {"key": key, "label": label, "type": kind}
            if kind == custom_fields.NUMBER and data.get("unit", "").strip():
                definition["unit"] = data["unit"].strip()
            if kind == custom_fields.CHOICE:
                options = custom_fields.parse_choices(data.get("choices"))
                if not options:
                    raise forms.ValidationError(f"“{label}” is a choice list: enter its options, separated by commas.")
                if len(options) > custom_fields.MAX_CHOICES:
                    raise forms.ValidationError(f"“{label}” can have at most {custom_fields.MAX_CHOICES} options.")
                definition["choices"] = options
            if key:
                taken.add(key)
            definitions.append(definition)
        if len(definitions) > custom_fields.MAX_FIELDS:
            raise forms.ValidationError(f"A category can have at most {custom_fields.MAX_FIELDS} fields.")
        if sum(d["type"] == custom_fields.LOCATION for d in definitions) > 1:
            raise forms.ValidationError("A category can have only one Location field.")
        for definition in definitions:  # new fields get a key that doesn't clash with kept ones
            if definition["key"] is None:
                definition["key"] = custom_fields.make_key(definition["label"], taken)
                taken.add(definition["key"])
        self.definitions = definitions


FieldDefinitionFormSet = forms.formset_factory(
    FieldDefinitionForm, formset=BaseFieldDefinitionFormSet, extra=3, can_order=True, can_delete=True,
    max_num=custom_fields.MAX_FIELDS + 3)


def field_definition_formset(data=None, category=None):
    """The field list of `category` (or an empty one for a new category)."""
    existing = custom_fields.definitions(category) if category else []
    initial = [{"key": d["key"], "label": d["label"], "type": d["type"], "unit": d.get("unit", ""),
                "choices": ", ".join(d.get("choices", []))} for d in existing]
    return FieldDefinitionFormSet(data, initial=initial, existing=existing, prefix="fields")
