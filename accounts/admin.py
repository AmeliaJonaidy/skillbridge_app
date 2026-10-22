from django.contrib import admin
from .models import Payment, UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "plan", "plan_expires_at")
    list_filter = ("role", "plan")
    search_fields = ("user__username", "user__email")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "amount", "currency", "status", "created_at", "paid_at")
    list_filter = ("provider", "status")
    search_fields = ("user__username", "user__email", "external_id")

# Register your models here.
