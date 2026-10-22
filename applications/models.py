from django.conf import settings
from django.db import models

from jobs.models import Job


class SavedJob(models.Model):
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_jobs",
    )
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "job"],
                name="unique_saved_job",
            )
        ]


class JobApplication(models.Model):
    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("shortlisted", "Shortlisted"),
        ("interview", "Interview"),
        ("offer", "Offer"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_applications",
    )
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="submitted")
    cover_note = models.TextField(blank=True)
    tailored_resume = models.TextField(blank=True)
    match_score = models.PositiveSmallIntegerField(blank=True, null=True)
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    match_breakdown = models.JSONField(default=dict, blank=True)
    match_assessment = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "job"],
                name="unique_job_application",
            )
        ]

    def __str__(self):
        return f"{self.candidate.username} — {self.job.title}"


class Interview(models.Model):
    RESCHEDULE_STATUS_CHOICES = [
        ("", "No pending request"),
        ("pending", "Pending recruiter review"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]
    application = models.ForeignKey(
        JobApplication,
        on_delete=models.CASCADE,
        related_name="interviews",
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField(blank=True, null=True)
    meeting_url = models.URLField(blank=True)
    calcom_event_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    candidate_notes = models.TextField(blank=True)
    proposed_start = models.DateTimeField(blank=True, null=True)
    proposed_end = models.DateTimeField(blank=True, null=True)
    reschedule_status = models.CharField(
        max_length=20,
        choices=RESCHEDULE_STATUS_CHOICES,
        blank=True,
    )
    reschedule_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="interview_reschedule_requests",
    )
    reschedule_message = models.TextField(blank=True)
    reschedule_reason = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_interviews",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_start"]

    def __str__(self):
        return f"Interview for {self.application}"
