from django import forms

from .models import Company


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "industry", "website", "logo_url", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}
