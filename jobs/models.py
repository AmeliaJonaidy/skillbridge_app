from django.conf import settings
from django.db import models

from employers.models import Company


class Job(models.Model):
    EMPLOYMENT_TYPES = [
        ("internship", "Internship"),
        ("full_time", "Full-time"),
        ("part_time", "Part-time"),
        ("contract", "Contract"),
        ("temporary", "Temporary"),
    ]
    EXPERIENCE_LEVELS = [
        ("entry", "Entry level"),
        ("junior", "Junior"),
        ("mid", "Mid-level"),
        ("senior", "Senior"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("open", "Open"),
        ("closed", "Closed"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_jobs",
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    industry = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=120, blank=True)
    employment_type = models.CharField(max_length=30, choices=EMPLOYMENT_TYPES)
    experience_level = models.CharField(
        max_length=30,
        choices=EXPERIENCE_LEVELS,
        default="entry",
    )
    salary_min = models.PositiveIntegerField(blank=True, null=True)
    salary_max = models.PositiveIntegerField(blank=True, null=True)
    stipend = models.CharField(max_length=120, blank=True)
    required_skills = models.TextField(blank=True)
    preferred_skills = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} at {self.company.name}"

    @staticmethod
    def split_skills(value):
        return [
            item.strip()
            for item in value.replace("\n", ",").split(",")
            if item.strip()
        ]

    @property
    def required_skill_list(self):
        return self.split_skills(self.required_skills)

    @property
    def preferred_skill_list(self):
        return self.split_skills(self.preferred_skills)
