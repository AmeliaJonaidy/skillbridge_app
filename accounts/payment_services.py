import base64
import hashlib
import hmac
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class PaymentProviderError(Exception):
    """Raised when a payment provider cannot create or retrieve a checkout."""


def _stripe_headers():
    secret_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    encoded = base64.b64encode(f"{secret_key}:".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _stripe_request(path, data=None, method="GET"):
    if not getattr(settings, "STRIPE_SECRET_KEY", ""):
        raise PaymentProviderError("Stripe test credentials are not configured.")
    request = Request(
        f"https://api.stripe.com/v1/{path}",
        data=urlencode(data).encode() if data is not None else None,
        headers=_stripe_headers(),
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        detail = "Payment provider request failed."
        if isinstance(exc, HTTPError):
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", detail)
            except (ValueError, OSError):
                pass
        raise PaymentProviderError(detail) from exc


def create_stripe_checkout(*, user, payment_id, success_url, cancel_url):
    amount = int(getattr(settings, "PRO_PLAN_AMOUNT_CENTS", 900))
    currency = getattr(settings, "PRO_PLAN_CURRENCY", "sgd").lower()
    price_id = getattr(settings, "STRIPE_PRICE_ID", "")
    data = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user.id),
        "customer_email": user.email,
        "metadata[payment_id]": str(payment_id),
        "metadata[user_id]": str(user.id),
        "subscription_data[metadata][payment_id]": str(payment_id),
        "line_items[0][quantity]": "1",
    }
    if price_id:
        data["line_items[0][price]"] = price_id
    else:
        data.update({
            "line_items[0][price_data][currency]": currency,
            "line_items[0][price_data][unit_amount]": str(amount),
            "line_items[0][price_data][product_data][name]": "SkillBridge Pro",
            "line_items[0][price_data][product_data][description]": "Advanced SkillBridge matching and applicant ranking",
            "line_items[0][price_data][recurring][interval]": "month",
        })
    return _stripe_request("checkout/sessions", data=data, method="POST")


def retrieve_stripe_checkout(session_id):
    return _stripe_request(f"checkout/sessions/{session_id}")


def cancel_stripe_subscription(subscription_id):
    """Cancel a Stripe subscription in the current Stripe mode."""
    return _stripe_request(f"subscriptions/{subscription_id}", method="DELETE")


def extend_stripe_subscription_trial(subscription_id, trial_end):
    """Move the next Stripe charge to the end of a referral reward period."""
    return _stripe_request(
        f"subscriptions/{subscription_id}",
        data={
            "trial_end": str(int(trial_end.timestamp())),
            "proration_behavior": "none",
            "metadata[last_reward]": "referral_week",
        },
        method="POST",
    )


def stripe_payment_for_subscription(subscription_id):
    """Find the local payment associated with a Stripe subscription."""
    if not subscription_id:
        return None
    from .models import Payment

    return Payment.objects.filter(
        provider="stripe",
        metadata__subscription=subscription_id,
    ).select_related("user").order_by("-created_at").first()


def set_stripe_entitlement(payment, *, active, status, stripe_status=""):
    """Synchronise a Stripe payment and its user's Pro entitlement."""
    from .models import UserProfile

    metadata = dict(payment.metadata or {})
    if stripe_status:
        metadata["subscription_status"] = stripe_status
    payment.status = status
    payment.metadata = metadata
    update_fields = ["status", "metadata"]
    if active and payment.paid_at is None:
        from django.utils import timezone

        payment.paid_at = timezone.now()
        update_fields.append("paid_at")
    payment.save(update_fields=update_fields)

    profile, _ = UserProfile.objects.get_or_create(
        user=payment.user,
        defaults={"role": "candidate"},
    )
    profile.plan = "pro" if active else "free"
    profile.plan_expires_at = None
    profile.save(update_fields=["plan", "plan_expires_at"])
    return profile


def verify_stripe_signature(payload, signature):
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    parts = {}
    for item in signature.split(","):
        key, _, value = item.partition("=")
        parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
        if abs(time.time() - timestamp) > 300:
            return False
        signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode()
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, value) for value in parts.get("v1", []))
    except (KeyError, TypeError, ValueError):
        return False
