from django import forms

from accounts.choices import (
    CAREER_CHOICES,
    EDUCATION_CHOICES,
    INSTITUTION_CHOICES,
    SPECIALISATION_CHOICES,
    VISA_CHOICES,
)


class CandidateProfileForm(forms.Form):
    """Editable version of the information collected by profile onboarding."""

    name = forms.CharField(label="Full name", required=False, max_length=200)
    email = forms.EmailField(label="Email address", required=False)
    phone = forms.CharField(label="Phone number", required=False, max_length=40)
    career = forms.ChoiceField(label="Career area", required=False, choices=[("", "Choose an option")] + CAREER_CHOICES)
    specialisation = forms.ChoiceField(label="Specialisation", required=False, choices=[("", "Choose an option")] + SPECIALISATION_CHOICES)
    education = forms.ChoiceField(label="Education level", required=False, choices=[("", "Choose an option")] + EDUCATION_CHOICES)
    institution = forms.ChoiceField(label="School or institution", required=False, choices=[("", "Choose an option")] + INSTITUTION_CHOICES)
    experience = forms.CharField(label="Work experience", required=False, widget=forms.Textarea(attrs={"rows": 5}))
    certifications = forms.CharField(label="Certifications", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    skills = forms.CharField(label="Technical skills and technology stack", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    portfolio = forms.CharField(label="Project portfolio links", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    awards = forms.CharField(label="Awards and achievements", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    linkedin = forms.URLField(label="LinkedIn profile", required=False)
    visa = forms.ChoiceField(label="Visa / work authorisation", required=False, choices=[("", "Choose an option")] + VISA_CHOICES)
