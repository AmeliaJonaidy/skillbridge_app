from django import forms

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

    class Meta:
        model = Interview
        fields = ["scheduled_start", "scheduled_end", "meeting_url", "calcom_event_url", "notes"]
        widgets = {
            "scheduled_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
