from datetime import timedelta

from django.utils import timezone

from .models import Notification, Payment
from .payment_services import PaymentProviderError, extend_stripe_subscription_trial


def _grant_local_pro(profile, days):
    now = timezone.now()
    base = profile.plan_expires_at if profile.plan_expires_at and profile.plan_expires_at > now else now
    profile.plan = "pro"
    profile.plan_expires_at = base + timedelta(days=days)
    profile.save(update_fields=["plan", "plan_expires_at"])
    return profile.plan_expires_at


def award_referral(referral):
    """Award a referral once and keep Stripe billing aligned with paid Pro access."""
    metadata = dict(referral.metadata or {})
    reward_end = timezone.now() + timedelta(days=referral.reward_days)

    if not metadata.get("referred_rewarded"):
        referred_profile = referral.referred_user.profile
        metadata["referred_pro_until"] = _grant_local_pro(referred_profile, referral.reward_days).isoformat()
        metadata["referred_rewarded"] = True
        Notification.objects.create(
            recipient=referral.referred_user,
            title="Your referral reward is active",
            body=f"You received {referral.reward_days} days of SkillBridge Pro.",
            kind="referral",
        )

    if not metadata.get("referrer_rewarded"):
        referrer_profile = referral.referrer.profile
        paid_payment = Payment.objects.filter(
            user=referral.referrer,
            provider="stripe",
            status="paid",
        ).order_by("-created_at").first()
        subscription_id = (paid_payment.metadata or {}).get("subscription", "") if paid_payment else ""
        try:
            if referrer_profile.is_pro and subscription_id:
                stripe_subscription = extend_stripe_subscription_trial(subscription_id, reward_end)
                payment_metadata = dict(paid_payment.metadata or {})
                payment_metadata["referral_trial_end"] = reward_end.isoformat()
                paid_payment.metadata = payment_metadata
                paid_payment.save(update_fields=["metadata"])
                metadata["stripe_trial_end"] = stripe_subscription.get("trial_end", int(reward_end.timestamp()))
            elif not (referrer_profile.plan == "pro" and referrer_profile.plan_expires_at is None):
                metadata["referrer_pro_until"] = _grant_local_pro(referrer_profile, referral.reward_days).isoformat()
            metadata["referrer_rewarded"] = True
            metadata.pop("stripe_error", None)
            Notification.objects.create(
                recipient=referral.referrer,
                title="You earned a referral reward",
                body=f"Your friend joined SkillBridge. You received {referral.reward_days} days of Pro.",
                kind="referral",
            )
        except PaymentProviderError as exc:
            metadata["stripe_error"] = str(exc)

    fully_rewarded = metadata.get("referred_rewarded") and metadata.get("referrer_rewarded")
    referral.status = "rewarded" if fully_rewarded else "partial"
    referral.rewarded_at = timezone.now() if fully_rewarded else None
    referral.metadata = metadata
    referral.save(update_fields=["status", "rewarded_at", "metadata"])
    return referral
