from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_CHOICES = [('candidate', 'Candidate'), ('recruiter', 'Recruiter')]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    profile_data = models.JSONField(default=dict, blank=True)

    @property
    def initials(self):
        name = str((self.profile_data or {}).get("name", "")).strip()
        display_name = name or self.user.get_full_name().strip() or self.user.username
        parts = display_name.split()
        if len(parts) > 1:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        return display_name[:2].upper()

    def __str__(self):
        return f'{self.user.username} ({self.role})'

# Create your models here.
