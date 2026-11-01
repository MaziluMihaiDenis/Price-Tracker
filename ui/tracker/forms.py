from django import forms

from tracker.models import ComparisonGroup, Item, PricePoint, Profile


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
        self.fields["items"].queryset = Item.objects.filter(owner=owner).select_related("category")
        self.apply_bootstrap_classes()


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("favorite_currency",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
