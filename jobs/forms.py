from django import forms

from .models import Job


class JobForm(forms.ModelForm):
    skill_weights = forms.CharField(
        required=False,
        label="Skill weights",
        help_text="Optional: one skill per line, for example Creativity: 60 and UI/UX: 40. Weights must total 100.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Creativity: 60\nUI/UX: 40"}),
    )
    evidence_weights = forms.CharField(
        required=False,
        label="Evidence weights",
        help_text="Optional: Projects, internship/work experience, and self-proclaimed skills. Weights must total 100.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Projects: 40\nInternship: 50\nSelf-proclaimed skills: 10"}),
    )

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
        cleaned["skill_weights"] = self._parse_weights(cleaned.get("skill_weights"), "skill")
        cleaned["evidence_weights"] = self._parse_weights(cleaned.get("evidence_weights"), "evidence")
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["skill_weights"] = self._format_weights(self.instance.skill_weights)
            self.initial["evidence_weights"] = self._format_weights(self.instance.evidence_weights)

    def _parse_weights(self, value, label):
        if not value:
            return {}
        weights = {}
        for line in value.splitlines():
            if not line.strip():
                continue
            name, separator, raw_weight = line.partition(":")
            if not separator or not name.strip():
                self.add_error(
                    f"{label}_weights",
                    "Use one entry per line in the format Name: percentage.",
                )
                continue
            try:
                weight = float(raw_weight.strip().rstrip("%"))
            except ValueError:
                self.add_error(f"{label}_weights", f"{name.strip()} must have a numeric percentage.")
                continue
            if weight < 0:
                self.add_error(f"{label}_weights", f"{name.strip()} cannot have a negative percentage.")
                continue
            key = name.strip()
            if key.casefold() in {item.casefold() for item in weights}:
                self.add_error(f"{label}_weights", f"{key} is listed more than once.")
                continue
            weights[key] = weight
        if weights and round(sum(weights.values()), 2) != 100:
            self.add_error(f"{label}_weights", "Weights must total exactly 100%.")
        return {key: value for key, value in weights.items()}

    @staticmethod
    def _format_weights(weights):
        return "\n".join(f"{key}: {value:g}" for key, value in (weights or {}).items())


class JobFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search jobs")
    location = forms.CharField(required=False)
    employment_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any employment type")] + Job.EMPLOYMENT_TYPES,
    )
    industry = forms.ChoiceField(required=False, choices=[("", "Any industry")] + list(Job._meta.get_field("industry").choices))
