from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


def _normalise_choices(choices):
    """Accept Django-style (value, label) choices or a simple list of labels."""
    return list(choices or [])


class SignupForm(UserCreationForm):
    email = forms.EmailField(label="Email address")
    role = forms.ChoiceField(
        label="I want to use SkillBridge as",
        choices=[("candidate", "Applicant — find jobs and build my career"), ("recruiter", "Recruiter — hire candidates")],
        widget=forms.RadioSelect,
        initial="candidate",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "role")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class OnboardingForm(forms.Form):
    def __init__(self, *args, field_name, label, field_type="text", choices=None, required=True, **kwargs):
        super().__init__(*args, **kwargs)
        field_kwargs = {"label": label, "required": required}
        if field_type == "textarea":
            self.fields[field_name] = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), **field_kwargs)
        elif field_type == "choice":
            self.fields[field_name] = forms.ChoiceField(choices=_normalise_choices(choices), widget=forms.RadioSelect, **field_kwargs)
        elif field_type == "select":
            self.fields[field_name] = forms.ChoiceField(choices=[("", "Choose an option")] + _normalise_choices(choices), **field_kwargs)
        else:
            self.fields[field_name] = forms.CharField(max_length=4000, **field_kwargs)
