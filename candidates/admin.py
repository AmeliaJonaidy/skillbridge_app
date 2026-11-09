from django.contrib import admin
from django.utils import timezone

from .services import add_verified_certificate_to_resume
from .models import CandidateMilestone, CandidateProfile, Certification


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "career_area", "specialisation", "profile_complete_percent", "updated_at")
    search_fields = ("user__username", "career_area", "technical_skills")


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "career_area", "cost", "is_recognised")
    list_filter = ("career_area", "is_recognised")
    search_fields = ("title", "provider", "skills")


@admin.register(CandidateMilestone)
class CandidateMilestoneAdmin(admin.ModelAdmin):
    list_display = ("candidate", "certification", "status", "verification_method", "certificate_id", "has_evidence", "verified_at")
    list_filter = ("status", "verification_method")
    readonly_fields = ("verification_url", "verification_method", "verification_details", "verified_at")

    def save_model(self, request, obj, form, change):
        if obj.status == "completed":
            verified_time = obj.verified_at or timezone.now()
            obj.completed_at = verified_time
            obj.verified_at = verified_time
            if not obj.verification_method or obj.verification_method.endswith("_manual"):
                obj.verification_method = "admin_review"
                obj.verification_details = f"Approved by administrator {request.user.get_username()}."
        else:
            obj.completed_at = None
            obj.verified_at = None
        super().save_model(request, obj, form, change)
        if obj.status == "completed":
            add_verified_certificate_to_resume(obj.candidate, obj)

    @admin.display(boolean=True, description="Evidence")
    def has_evidence(self, milestone):
        return bool(milestone.evidence_file)
