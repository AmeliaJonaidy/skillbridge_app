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
            "salary_currency",
            "salary_period",
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

    def clean(self):
        cleaned = super().clean()
        salary_min = cleaned.get("salary_min")
        salary_max = cleaned.get("salary_max")
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            self.add_error("salary_max", "Maximum salary must be greater than or equal to minimum salary.")
        return cleaned


class JobFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search jobs")
    location = forms.CharField(required=False)
    employment_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any employment type")] + Job.EMPLOYMENT_TYPES,
    )
    industry = forms.ChoiceField(required=False, choices=[("", "Any industry")] + list(Job._meta.get_field("industry").choices))
