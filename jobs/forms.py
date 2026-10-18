from django import forms

from .models import Job


class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = [
            "title",
            "description",
            "industry",
            "location",
            "employment_type",
            "experience_level",
            "salary_min",
            "salary_max",
            "stipend",
            "required_skills",
            "preferred_skills",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "required_skills": forms.Textarea(attrs={"rows": 3}),
            "preferred_skills": forms.Textarea(attrs={"rows": 3}),
        }


class JobFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search jobs")
    location = forms.CharField(required=False)
    employment_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any employment type")] + Job.EMPLOYMENT_TYPES,
    )
    industry = forms.CharField(required=False)
