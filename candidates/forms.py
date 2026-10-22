from urllib.parse import urlparse

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from accounts.choices import (
    CAREER_CHOICES,
    CAREER_INTEREST_CHOICES,
    CAREER_STAGE_CHOICES,
    EDUCATION_CHOICES,
    INSTITUTION_CHOICES,
    PHONE_COUNTRY_CODE_CHOICES,
    SPECIALISATION_CHOICES,
    VISA_CHOICES,
)


class CandidateProfileForm(forms.Form):
    """Editable version of the information collected by profile onboarding."""

    name = forms.CharField(label="Full name", required=False, max_length=200)
    resume = forms.FileField(
        label="Resume",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.doc,.docx,.txt"}),
    )
    email = forms.EmailField(label="Email address", required=False)
    phone_country_code = forms.ChoiceField(
        label="Country code",
        required=False,
        choices=PHONE_COUNTRY_CODE_CHOICES,
        initial="+65",
    )
    phone = forms.CharField(label="Phone number", required=False, max_length=40)
    career = forms.ChoiceField(label="Career area", required=False, choices=[("", "Choose an option")] + CAREER_CHOICES)
    specialisation = forms.ChoiceField(label="Specialisation", required=False, choices=[("", "Choose an option")] + SPECIALISATION_CHOICES)
    career_stage = forms.ChoiceField(label="Current level", required=False, choices=[("", "Choose your current level")] + CAREER_STAGE_CHOICES)
    career_interests = forms.MultipleChoiceField(
        label="Career directions to track",
        required=False,
        choices=CAREER_INTEREST_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    education = forms.ChoiceField(label="Education level", required=False, choices=[("", "Choose an option")] + EDUCATION_CHOICES)
    institution = forms.ChoiceField(label="School or institution", required=False, choices=[("", "Choose an option")] + INSTITUTION_CHOICES)
    experience = forms.CharField(label="Work experience", required=False, widget=forms.Textarea(attrs={"rows": 5}))
    certifications = forms.CharField(label="Certifications", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    skills = forms.CharField(label="Technical skills and technology stack", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    portfolio = forms.CharField(label="Project portfolio links", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    awards = forms.CharField(label="Awards and achievements", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    linkedin = forms.CharField(label="LinkedIn profile", required=False, max_length=300)
    visa = forms.ChoiceField(label="Visa / work authorisation", required=False, choices=[("", "Choose an option")] + VISA_CHOICES)

    def clean_linkedin(self):
        value = self.cleaned_data.get("linkedin", "").strip()
        if not value:
            return ""
        if "://" not in value:
            value = f"https://{value}"
        try:
            URLValidator()(value)
        except ValidationError:
            raise forms.ValidationError("Enter a valid LinkedIn URL, for example linkedin.com/in/your-name.")
        hostname = (urlparse(value).hostname or "").casefold()
        if hostname not in {"linkedin.com", "www.linkedin.com"}:
            raise forms.ValidationError("Please enter a LinkedIn profile URL.")
        return value
