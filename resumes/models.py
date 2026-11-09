from django.conf import settings
from django.db import models

from jobs.models import Job


class TailoredResume(models.Model):
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tailored_resumes",
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="tailored_resumes",
        blank=True,
        null=True,
    )
    title = models.CharField(max_length=200, default="My tailored resume")
    content = models.TextField(blank=True)
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
