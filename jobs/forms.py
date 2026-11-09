from django import forms

from candidates.resume_parser import KNOWN_SKILLS

from .models import Job


class JobForm(forms.ModelForm):
    skill_catalog = list(dict.fromkeys([
        *KNOWN_SKILLS,
        "FastAPI", "Flask", "Spring Boot", "Node.js", "Vue", "Next.js",
        "REST APIs", "GraphQL", "Machine learning", "Deep learning",
        "Statistics", "Data visualisation", "UI/UX", "User research",
        "Prototyping", "Communication", "Creativity", "Management",
        "Leadership", "Problem solving", "Critical thinking", "Teamwork",
        "Agile", "Scrum", "Product management", "Business analysis",
        "Requirements gathering", "Wireframing", "Usability testing",
        "SEO", "Content writing", "Marketing", "Sales", "Negotiation",
        "Financial analysis", "Risk management", "Accounting", "Research",
    ]))
    skill_choices = [(skill, skill) for skill in skill_catalog]
    required_skill_choices = forms.MultipleChoiceField(
        required=False,
        label="Skills needed",
        choices=skill_choices,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Select the skills candidates should have. Add custom skills below if needed.",
    )
    preferred_skill_choices = forms.MultipleChoiceField(
        required=False,
        label="Preferred skills",
        choices=skill_choices,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Search and select skills that would be a bonus for this role.",
    )
    skill_weights = forms.CharField(
        required=False,
        label="Skill importance",
        help_text="Rate each selected skill from 1–10. SkillBridge converts the ratings into percentages automatically.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "FastAPI: 9\nUI/UX: 6"}),
    )
    evidence_weights = forms.CharField(
        required=False,
        label="Evidence importance",
        help_text="Rate each evidence type from 1–10. The result is distributed across the 30% evidence portion.",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Projects: 8\nInternship: 10\nSelf-proclaimed skills: 2"}),
    )

    @staticmethod
    def _weight_text(value):
        values = list((value or {}).values())
        maximum = max(values, default=0)
        if maximum > 10:
            return "\n".join(
                f"{label}: {round(float(weight) * 10 / maximum, 1):g}"
                for label, weight in (value or {}).items()
            )
        return "\n".join(f"{label}: {weight:g}" for label, weight in (value or {}).items())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["skill_weights"] = self._weight_text(self.instance.skill_weights)
            self.initial["evidence_weights"] = self._weight_text(self.instance.evidence_weights)
            self.initial["required_skill_choices"] = self.instance.required_skill_list
            self.initial["preferred_skill_choices"] = self.instance.preferred_skill_list
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
            legacy_percentages = parsed and max(parsed.values()) > 10 and round(sum(parsed.values()), 6) == 100
            if parsed and any(value < 0 or value > 10 for value in parsed.values()) and not legacy_percentages:
                self.add_error(field_name, "Importance ratings must be between 1 and 10.")
            if parsed and all(0 <= value <= 10 for value in parsed.values()):
                total = sum(parsed.values())
                if total:
                    cleaned[field_name] = {
                        label: round(value * 100 / total, 4)
                        for label, value in parsed.items()
                    }
            elif legacy_percentages:
                cleaned[field_name] = parsed
        canonical = {skill.casefold(): skill for skill in self.skill_catalog}
        for field_name, model_name in (
            ("required_skill_choices", "required_skills"),
            ("preferred_skill_choices", "preferred_skills"),
        ):
            selected_skills = cleaned.get(field_name) or []
            custom_skills = Job.split_skills(cleaned.get(model_name, ""))
            merged = []
            seen = set()
            for skill in [*selected_skills, *custom_skills]:
                key = skill.casefold()
                standard = canonical.get(key, " ".join(word.capitalize() for word in skill.split()))
                if key not in seen:
                    merged.append(standard)
                    seen.add(key)
            cleaned[model_name] = ", ".join(merged)
        return cleaned


class JobFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search jobs")
    location = forms.CharField(required=False)
    employment_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any employment type")] + Job.EMPLOYMENT_TYPES,
    )
    industry = forms.ChoiceField(required=False, choices=[("", "Any industry")] + list(Job._meta.get_field("industry").choices))
