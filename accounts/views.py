import json
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from employers.choices import INDUSTRY_CHOICES

from .choices import (
    CAREER_CHOICES,
    CAREER_INTEREST_CHOICES,
    CAREER_STAGE_CHOICES,
    EDUCATION_CHOICES,
    INSTITUTION_CHOICES,
    SPECIALISATION_CHOICES,
    VISA_CHOICES,
)
from .forms import OnboardingForm, SignupForm
from .models import Notification, Payment, UserProfile
from .payment_services import (
    PaymentProviderError,
    cancel_stripe_subscription,
    create_stripe_checkout,
    retrieve_stripe_checkout,
    verify_stripe_signature,
)


CANDIDATE_STEPS = [
    {"id": "resume", "title": "Your resume", "question": "Upload your current resume. We will use it to auto-fill your profile, improve job matching, and give you feedback. You can skip this for now.", "label": "Resume file", "type": "file", "required": False},
    {"id": "name", "title": "Your name", "question": "What should we call you?", "label": "Full name"},
    {"id": "career", "title": "Career interests", "question": "Which broad career area are you interested in?", "label": "Career area", "type": "select", "choices": CAREER_CHOICES},
    {"id": "career_stage", "title": "Current level", "question": "Where are you starting from in these directions? This helps us order the roadmap; you can update it later.", "label": "Current level", "type": "select", "choices": CAREER_STAGE_CHOICES, "required": False},
    {"id": "career_interests", "title": "Career directions", "question": "Which career directions should we track for you? Select all that interest you.", "label": "Career directions", "type": "multi", "choices": CAREER_INTEREST_CHOICES, "required": False},
    {"id": "specialisation", "title": "Specialisation", "question": "Which specialisation would you like to explore?", "label": "Specialisation", "type": "select", "choices": SPECIALISATION_CHOICES},
]

RECRUITER_STEPS = [
    {"id": "company", "title": "Company", "question": "What is your company called?", "label": "Company name"},
    {"id": "industry", "title": "Industry", "question": "Which industry does your company operate in?", "label": "Industry", "type": "select", "choices": INDUSTRY_CHOICES},
    {"id": "website", "title": "Company details", "question": "Where can candidates learn more about your company?", "label": "Company website"},
    {"id": "hiring_goal", "title": "Hiring goal", "question": "What kind of candidates are you hoping to find?", "label": "Hiring goal", "type": "textarea"},
]


def _role(request):
    return getattr(getattr(request.user, "profile", None), "role", "candidate")


def _profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={"role": _role(request)})
    return profile


def _step_value(profile, answers, step):
    if step["id"] == "resume":
        return profile.resume
    return answers.get(step["id"])


def _profile_is_complete(profile, steps):
    answers = profile.profile_data or {}
    return all(
        not step.get("required", True) or _step_value(profile, answers, step)
        for step in steps
    )


def _next_step(profile, steps):
    answers = profile.profile_data or {}
    for index, step in enumerate(steps):
        if not _step_value(profile, answers, step):
            return index
    return len(steps)


def _safe_next_url(request, value):
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return ""


def _finish_onboarding(request):
    request.session["onboarding_complete"] = True
    next_url = request.session.pop("post_onboarding_next", "")
    return redirect(next_url or "home")


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    role = _role(request)
    profile = _profile(request)
    steps = RECRUITER_STEPS if role == "recruiter" else CANDIDATE_STEPS
    if not request.session.get("onboarding_complete") and not _profile_is_complete(profile, steps):
        request.session["onboarding_step"] = _next_step(profile, steps)
        return redirect("onboarding")
    if role == "recruiter":
        from employers.views import dashboard

        return dashboard(request)

    from candidates.views import dashboard_context

    return render(request, "candidates/dashboard.html", dashboard_context(request))


@login_required
def inbox(request):
    notifications = Notification.objects.filter(recipient=request.user)
    if request.method == "POST":
        notifications.filter(is_read=False).update(is_read=True)
        return redirect("inbox")
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, "accounts/inbox.html", {
        "role": _role(request),
        "notifications": notifications,
    })


def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)
    requested_next = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=identifier, password=password)
        if user is None and "@" in identifier:
            email_user = User.objects.filter(email__iexact=identifier).first()
            if email_user:
                user = authenticate(request, username=email_user.username, password=password)
        if user is not None:
            login(request, user)
            profile = _profile(request)
            steps = RECRUITER_STEPS if profile.role == "recruiter" else CANDIDATE_STEPS
            request.session["onboarding_answers"] = profile.profile_data or {}
            request.session["onboarding_step"] = _next_step(profile, steps)
            # Onboarding is required immediately after signup, but logging in
            # to an existing account should always return to its workspace.
            # Users can still continue or edit the questionnaire from Profile.
            request.session["onboarding_complete"] = True
            return redirect(requested_next or "home")
        form.add_error(None, "Invalid username/email or password.")
    return render(request, "accounts/login.html", {"form": form})


def signup_view(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        UserProfile.objects.create(user=user, role=form.cleaned_data["role"])
        login(request, user)
        request.session["onboarding_step"] = 0
        request.session["onboarding_answers"] = {}
        request.session["onboarding_complete"] = False
        requested_next = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
        if requested_next:
            request.session["post_onboarding_next"] = requested_next
        return redirect("onboarding")
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def onboarding(request):
    role = _role(request)
    steps = RECRUITER_STEPS if role == "recruiter" else CANDIDATE_STEPS
    profile = _profile(request)
    answers = dict(profile.profile_data or {})
    answers.update(request.session.get("onboarding_answers", {}))
    step_number = int(request.session.get("onboarding_step", _next_step(profile, steps)))
    if step_number >= len(steps):
        return _finish_onboarding(request)
    step = steps[step_number]
    initial = {} if step.get("type") == "file" else {
        step["id"]: answers.get(step["id"], [] if step.get("type") == "multi" else "")
    }
    form = OnboardingForm(
        request.POST or None,
        request.FILES or None,
        initial=initial,
        field_name=step["id"],
        label=step["label"],
        field_type=step.get("type", "text"),
        choices=step.get("choices"),
        required=step.get("required", True),
    )
    if request.method == "POST" and request.POST.get("skip") == "1":
        return _finish_onboarding(request)
    if request.method == "POST" and form.is_valid():
        value = form.cleaned_data.get(step["id"])
        if step["id"] == "resume":
            if value:
                profile.resume = value
                profile.save(update_fields=["resume"])
            answers[step["id"]] = profile.resume.name if profile.resume else ""
            if value and role == "candidate":
                from candidates.services import autofill_from_resume

                updates, _ = autofill_from_resume(value, answers)
                answers.update(updates)
        else:
            answers[step["id"]] = value
        profile.profile_data = answers
        profile.save(update_fields=["profile_data"])
        if role == "candidate":
            from candidates.services import sync_candidate_profile

            sync_candidate_profile(request.user, answers)
        request.session["onboarding_answers"] = answers
        request.session["onboarding_step"] = step_number + 1
        if step_number + 1 >= len(steps):
            return _finish_onboarding(request)
        return redirect("onboarding")
    completed_steps = []
    for item in steps[:step_number]:
        answer = _step_value(profile, answers, item) or ""
        if item["id"] == "resume" and hasattr(answer, "name"):
            answer = answer.name
        labels = dict(item.get("choices", []))
        if isinstance(answer, (list, tuple)):
            answer_display = ", ".join(labels.get(value, value) for value in answer)
        else:
            answer_display = labels.get(answer, answer)
        completed_steps.append({
            **item,
            "answer": answer,
            "answer_display": answer_display,
        })
    return render(request, "accounts/onboarding.html", {"role": role, "steps": steps, "step": step, "step_number": step_number, "answers": answers, "completed_steps": completed_steps, "form": form, "total_steps": len(steps)})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def plans(request):
    profile = _profile(request)
    return render(
        request,
        "accounts/plans.html",
        {
            "role": profile.role,
            "profile": profile,
            "has_pro": profile.is_pro,
            "payments": Payment.objects.filter(user=request.user)[:5],
            "stripe_enabled": settings.STRIPE_SECRET_KEY.startswith("sk_test_"),
            "pro_plan_price": f"{settings.PRO_PLAN_CURRENCY.upper()} {settings.PRO_PLAN_AMOUNT_CENTS / 100:.2f}",
        },
    )


@login_required
def pro_checkout_confirm(request):
    profile = _profile(request)
    if profile.is_pro:
        messages.info(request, "Your SkillBridge Pro plan is already active.")
        return redirect("plans")
    return render(
        request,
        "accounts/checkout_confirm.html",
        {
            "profile": profile,
            "stripe_enabled": settings.STRIPE_SECRET_KEY.startswith("sk_test_"),
            "pro_plan_price": f"{settings.PRO_PLAN_CURRENCY.upper()} {settings.PRO_PLAN_AMOUNT_CENTS / 100:.2f}",
        },
    )


@login_required
def cancel_pro_confirm(request):
    profile = _profile(request)
    if not profile.is_pro:
        messages.info(request, "Your account is already on the Free plan.")
        return redirect("plans")
    return render(request, "accounts/cancel_pro_confirm.html", {"profile": profile})


@login_required
@require_POST
def cancel_pro(request):
    profile = _profile(request)
    if not profile.is_pro:
        messages.info(request, "Your account is already on the Free plan.")
        return redirect("plans")

    paid_payments = Payment.objects.filter(
        user=request.user,
        provider="stripe",
        status="paid",
    ).order_by("-created_at")
    payment = next(
        (
            item for item in paid_payments
            if (item.metadata or {}).get("subscription")
        ),
        None,
    )
    if not payment:
        messages.error(request, "No active Stripe subscription was found for this account.")
        return redirect("plans")

    try:
        cancel_stripe_subscription(payment.metadata["subscription"])
    except PaymentProviderError as exc:
        messages.error(request, f"Stripe could not cancel the subscription: {exc}")
        return redirect("plans")

    payment.status = "cancelled"
    payment.save(update_fields=["status"])
    profile.plan = "free"
    profile.plan_expires_at = None
    profile.save(update_fields=["plan", "plan_expires_at"])
    messages.success(request, "Pro has been cancelled. Your account is now on SkillBridge Free.")
    return redirect("plans")


def _mark_payment_paid(payment, session_data):
    payment.status = "paid"
    payment.paid_at = timezone.now()
    payment.metadata = {
        "checkout_status": session_data.get("status", ""),
        "payment_status": session_data.get("payment_status", ""),
        "subscription": session_data.get("subscription", ""),
    }
    payment.save(update_fields=["status", "paid_at", "metadata"])
    profile = _profile_for_user(payment.user)
    profile.plan = "pro"
    profile.plan_expires_at = None
    profile.save(update_fields=["plan", "plan_expires_at"])


def _profile_for_user(user):
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": "candidate"})
    return profile


@login_required
@require_POST
def start_pro_checkout(request):
    if _profile(request).is_pro:
        messages.info(request, "Your SkillBridge Pro plan is already active.")
        return redirect("plans")

    provider = request.POST.get("provider", "stripe")
    if provider != "stripe":
        messages.info(request, "Stripe test checkout is enabled first. PayPal sandbox and PayNow/DBS merchant flows can be added with their credentials.")
        return redirect("plans")
    if not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        messages.error(request, "Stripe test mode is not configured yet. Add a Stripe sk_test_ key to your environment first.")
        return redirect("plans")

    amount = Decimal(settings.PRO_PLAN_AMOUNT_CENTS) / Decimal("100")
    payment = Payment.objects.create(
        user=request.user,
        provider="stripe",
        amount=amount,
        currency=settings.PRO_PLAN_CURRENCY.upper(),
    )
    success_url = request.build_absolute_uri(reverse("pro_payment_success")) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = request.build_absolute_uri(reverse("plans"))
    try:
        session = create_stripe_checkout(
            user=request.user,
            payment_id=payment.id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except PaymentProviderError as exc:
        payment.status = "failed"
        payment.metadata = {"error": str(exc)}
        payment.save(update_fields=["status", "metadata"])
        messages.error(request, str(exc))
        return redirect("plans")

    payment.external_id = session.get("id", "")
    payment.checkout_url = session.get("url", "")
    payment.save(update_fields=["external_id", "checkout_url"])
    if not payment.checkout_url:
        payment.status = "failed"
        payment.metadata = {"error": "Stripe did not return a checkout URL."}
        payment.save(update_fields=["status", "metadata"])
        messages.error(request, "Stripe did not return a checkout URL.")
        return redirect("plans")
    return redirect(payment.checkout_url)


@login_required
def pro_payment_success(request):
    session_id = request.GET.get("session_id", "")
    payment = Payment.objects.filter(user=request.user, external_id=session_id, provider="stripe").first()
    if not payment:
        messages.error(request, "We could not match this checkout to your account.")
        return redirect("plans")
    try:
        session = retrieve_stripe_checkout(session_id)
    except PaymentProviderError as exc:
        messages.error(request, str(exc))
        return redirect("plans")
    if session.get("payment_status") == "paid" and session.get("status") == "complete":
        _mark_payment_paid(payment, session)
        messages.success(request, "Payment successful. SkillBridge Pro is now active.")
    else:
        messages.info(request, "Checkout returned, but payment has not been confirmed yet.")
    return redirect("plans")


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not verify_stripe_signature(request.body, request.headers.get("Stripe-Signature", "")):
        return JsonResponse({"error": "Invalid Stripe signature."}, status=400)
    try:
        event = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    if event.get("type") in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        session = event.get("data", {}).get("object", {})
        payment_id = session.get("metadata", {}).get("payment_id")
        payment = Payment.objects.filter(pk=payment_id, provider="stripe").first()
        if payment and session.get("payment_status") == "paid":
            _mark_payment_paid(payment, session)
    return JsonResponse({"received": True})
