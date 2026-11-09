from django import forms

from candidates.resume_parser import KNOWN_SKILLS

from .models import Job


class JobForm(forms.ModelForm):
    skill_choices = [
        (skill, skill)
        for skill in [
            *KNOWN_SKILLS,
            "FastAPI", "Flask", "Spring Boot", "Node.js", "Vue", "Next.js",
            "REST APIs", "GraphQL", "Machine learning", "Deep learning",
            "Statistics", "Data visualisation", "UI/UX", "User research",
            "Prototyping", "Communication", "Creativity",
        ]
    ]
    required_skill_choices = forms.MultipleChoiceField(
        required=False,
        label="Skills needed",
        choices=skill_choices,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Select the skills candidates should have. Add custom skills below if needed.",
    )
    skill_weights = forms.CharField(
        required=False,
        label="Skill weights",
        help_text="One per line, for example: FastAPI: 60, UI/UX: 40. Weights must total 100.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "FastAPI: 60\nUI/UX: 40"}),
    )
    evidence_weights = forms.CharField(
        required=False,
        label="Evidence weights",
        help_text="One per line, for example: Projects: 40, Internship: 50, Self-proclaimed skills: 10.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Projects: 40\nInternship: 50\nSelf-proclaimed skills: 10"}),
    )

    @staticmethod
    def _weight_text(value):
        return "\n".join(f"{label}: {weight:g}" for label, weight in (value or {}).items())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["skill_weights"] = self._weight_text(self.instance.skill_weights)
            self.initial["evidence_weights"] = self._weight_text(self.instance.evidence_weights)
            self.initial["required_skill_choices"] = self.instance.required_skill_list
    class Meta:
        model = Job
        fields = [
            "title",
            "role_type",
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
        for field_name in ("skill_weights", "evidence_weights"):
            raw = cleaned.get(field_name, "")
            parsed = {}
            for line in raw.replace(",", "\n").splitlines():
                if not line.strip():
                    continue
                try:
                    label, weight = line.rsplit(":", 1)
                    parsed[label.strip()] = float(weight.strip())
                except ValueError:
                    self.add_error(field_name, "Use one entry per line in the format Skill: weight.")
                    continue
            if parsed and (any(value < 0 for value in parsed.values()) or round(sum(parsed.values()), 6) != 100):
                self.add_error(field_name, "Weights must be non-negative and total exactly 100.")
            cleaned[field_name] = parsed
        selected_skills = cleaned.get("required_skill_choices") or []
        custom_skills = Job.split_skills(cleaned.get("required_skills", ""))
        merged = []
        seen = set()
        for skill in [*selected_skills, *custom_skills]:
            key = skill.casefold()
            if key not in seen:
                merged.append(skill)
                seen.add(key)
        cleaned["required_skills"] = ", ".join(merged)
        return cleaned


class JobFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search jobs")
    location = forms.CharField(required=False)
    employment_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any employment type")] + Job.EMPLOYMENT_TYPES,
    )
    industry = forms.ChoiceField(required=False, choices=[("", "Any industry")] + list(Job._meta.get_field("industry").choices))
