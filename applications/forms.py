from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .models import Interview, JobApplication


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ["cover_note"]
        widgets = {"cover_note": forms.Textarea(attrs={"rows": 5})}


class ApplicationStatusForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ["status"]


class InterviewForm(forms.ModelForm):
    scheduled_start = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    scheduled_end = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    meeting_url = forms.CharField(
        required=False,
        label="Meeting link (Teams, Google Meet, Zoom, etc.)",
    )
    calcom_event_url = forms.CharField(
        required=False,
        label="Optional booking link (Cal.com or other)",
    )

    class Meta:
        model = Interview
        fields = ["scheduled_start", "scheduled_end", "meeting_url", "calcom_event_url", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def _clean_url(self, field_name):
        value = self.cleaned_data.get(field_name, "").strip()
        if not value:
            return ""
        if "://" not in value:
            value = f"https://{value}"
        try:
            URLValidator()(value)
        except ValidationError:
            raise forms.ValidationError("Enter a valid URL, for example https://cal.com/your-link.")
        return value

    def clean_meeting_url(self):
        return self._clean_url("meeting_url")

    def clean_calcom_event_url(self):
        return self._clean_url("calcom_event_url")

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("scheduled_start")
        end = cleaned.get("scheduled_end")
        if start and end and end <= start:
            self.add_error("scheduled_end", "End time must be after the start time.")
        return cleaned
