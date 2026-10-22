from django.conf import settings
from django.db import models

from jobs.models import Job


class JobMatch(models.Model):
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_matches",
    )
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="matches")
    score = models.PositiveSmallIntegerField()
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    score_breakdown = models.JSONField(default=dict, blank=True)
    assessment = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "job"],
                name="unique_job_match",
            )
        ]
