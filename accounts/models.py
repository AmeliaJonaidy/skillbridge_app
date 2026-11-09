from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings


class UserProfile(models.Model):
    ROLE_CHOICES = [('candidate', 'Candidate'), ('recruiter', 'Recruiter')]
    PLAN_CHOICES = [('free', 'SkillBridge Free'), ('pro', 'SkillBridge Pro')]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    plan_expires_at = models.DateTimeField(blank=True, null=True)
    trial_started_at = models.DateTimeField(blank=True, null=True)
    profile_data = models.JSONField(default=dict, blank=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)

    @property
    def is_pro(self):
        return self.plan == 'pro' and (
            self.plan_expires_at is None or self.plan_expires_at > timezone.now()
        )

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


class Payment(models.Model):
    PROVIDER_CHOICES = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('paynow', 'PayNow / DBS'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='SGD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    external_id = models.CharField(max_length=255, blank=True)
    checkout_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} · {self.provider} · {self.status}'


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    kind = models.CharField(max_length=40, default="update")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient.username} · {self.title}"
