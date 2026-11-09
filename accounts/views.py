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
from django.views.decorators.http import require_GET, require_POST

from employers.choices import INDUSTRY_CHOICES
from employers.services import lookup_company

from .choices import (
    CAREER_CHOICES,
    CAREER_INTERESTS_BY_AREA,
    CAREER_INTEREST_CHOICES,
    CAREER_STAGE_CHOICES,
    EDUCATION_CHOICES,
    INSTITUTION_CHOICES,
    SPECIALISATION_CHOICES,
    SPECIALISATIONS_BY_AREA,
    VISA_CHOICES,
    choices_for_career,
)
from .forms import OnboardingForm, SignupForm
from .models import Notification, Payment, Referral, UserProfile
from .payment_services import (
    PaymentProviderError,
    cancel_stripe_subscription,
    create_stripe_checkout,
    retrieve_stripe_checkout,
    set_stripe_entitlement,
    stripe_payment_for_subscription,
    verify_stripe_signature,
)
from .referral_services import award_referral
from .notification_helpers import notify


CANDIDATE_STEPS = [
    {"id": "resume", "title": "Your resume", "question": "How would you like to build your resume? Upload a PDF, DOCX, or TXT file for automatic extraction, or use our guided resume builder.", "label": "Upload resume", "type": "file", "required": False},
    {"id": "career_stage", "title": "Current level", "question": "Where are you starting from in these directions? This helps us order the roadmap; you can update it later.", "label": "Current level", "type": "select", "choices": CAREER_STAGE_CHOICES, "required": False},
    {"id": "career_interests", "title": "Skill interests", "question": "Which skill areas are you interested in developing? Select all that apply.", "label": "Skill interests", "type": "multi", "choices": CAREER_INTEREST_CHOICES, "required": False},
    {"id": "visa", "title": "Work authorisation", "question": "What is your current work authorisation status? This stays in your SkillBridge profile and is not added to your resume.", "label": "Work authorisation", "type": "select", "choices": VISA_CHOICES, "required": False},
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


def _resume_form_initial(request, profile, answers):
    stored_phone = str(answers.get("phone", "") or "").strip()
    country_code = answers.get("phone_country_code", "") or "+65"
    phone = stored_phone[len(country_code):].strip() if stored_phone.startswith(country_code) else stored_phone
    return {
        "name": answers.get("name", ""), "email": answers.get("email", request.user.email),
        "phone_country_code": country_code, "phone": phone,
        "career": answers.get("career", ""), "specialisation": answers.get("specialisation", ""),
        "career_stage": answers.get("career_stage", ""), "career_interests": answers.get("career_interests", []),
        "education": answers.get("education", ""), "institution": answers.get("institution", answers.get("school", "")),
        "experience": answers.get("experience", ""), "experience_entries": answers.get("experience_entries", []),
        "certifications": answers.get("certifications", ""), "certification_entries": answers.get("certification_entries", []),
        "skills": answers.get("skills", ""), "portfolio": answers.get("portfolio", ""),
        "awards": answers.get("awards", ""), "linkedin": answers.get("linkedin", ""), "visa": answers.get("visa", ""),
    }


def _save_resume_form(request, profile, resume_form, answers):
    for field in resume_form.fields:
        value = resume_form.cleaned_data.get(field)
        if field in {"career_stage", "career_interests", "visa"} and field not in request.POST:
            continue
        if field == "resume":
            if value:
                profile.resume = value
                answers["resume"] = value.name
        elif field == "profile_photo":
            if value:
                profile.profile_photo = value
        elif field == "email":
            request.user.email = value or ""
            request.user.save(update_fields=["email"])
        elif value is not None:
            answers[field] = value
    number = str(answers.get("phone", "") or "").strip()
    code = str(answers.get("phone_country_code", "") or "").strip()
    answers["phone"] = f"{code} {number}".strip() if number else ""
    profile.profile_data = answers
    profile.save()
    from candidates.services import sync_candidate_profile
    sync_candidate_profile(request.user, answers)


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
    referral_code = (
        request.POST.get("referral_code")
        or request.GET.get("ref")
        or request.session.get("referral_code")
        or ""
    ).strip().upper()
    if referral_code:
        request.session["referral_code"] = referral_code
    if request.method == "POST" and form.is_valid():
        user = form.save()
        UserProfile.objects.create(user=user, role=form.cleaned_data["role"])
        if form.cleaned_data["role"] == "recruiter" and form.cleaned_data.get("company_name"):
            from employers.models import Company, RecruiterProfile

            company = Company.objects.create(
                name=form.cleaned_data["company_name"],
                website=form.cleaned_data.get("company_website", ""),
                logo_url=form.cleaned_data.get("company_logo_url", ""),
            )
            RecruiterProfile.objects.create(user=user, company=company)
        referrer_profile = UserProfile.objects.select_related("user").filter(
            referral_code__iexact=referral_code,
            user__is_active=True,
        ).first() if referral_code else None
        if referrer_profile and referrer_profile.user_id != user.id:
            referral = Referral.objects.create(
                referrer=referrer_profile.user,
                referred_user=user,
                referral_code=referrer_profile.referral_code,
            )
            award_referral(referral)
            notify(user, "Referral reward applied", "Your referral was accepted and 7 days of SkillBridge Pro were added.", "account")
        request.session.pop("referral_code", None)
        login(request, user)
        request.session["onboarding_step"] = 0
        request.session["onboarding_answers"] = {}
        request.session["onboarding_complete"] = False
        request.session["sandy_intro_seen"] = False
        requested_next = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
        if requested_next:
            request.session["post_onboarding_next"] = requested_next
        return redirect("onboarding")
    return render(request, "accounts/signup.html", {"form": form, "referral_code": referral_code})


@require_GET
def signup_company_lookup(request):
    query = request.GET.get("q", "").strip()
    return JsonResponse({"query": query, "result": lookup_company(query) if query else None})


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
    step = dict(steps[step_number])
    show_sandy_intro = step_number == 0 and not request.session.get("sandy_intro_seen", False)
    if show_sandy_intro:
        request.session["sandy_intro_seen"] = True
    career_area = answers.get("career", "")
    if step["id"] == "career_interests":
        step["choices"] = choices_for_career(CAREER_INTEREST_CHOICES, CAREER_INTERESTS_BY_AREA, career_area)
    elif step["id"] == "specialisation":
        step["choices"] = choices_for_career(SPECIALISATION_CHOICES, SPECIALISATIONS_BY_AREA, career_area)
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
    resume_form = None
    if role == "candidate" and step["id"] == "resume":
        from candidates.forms import CandidateProfileForm
        resume_form = CandidateProfileForm(
            request.POST or None, request.FILES or None,
            initial=_resume_form_initial(request, profile, answers),
        )
        if request.method == "POST" and len(request.FILES.getlist("resume")) > 1:
            resume_form.is_valid()
            resume_form.add_error("resume", "Upload only one resume at a time.")
    if request.method == "POST" and request.POST.get("back") == "1":
        request.session["onboarding_step"] = max(0, step_number - 1)
        return redirect("onboarding")
    if request.method == "POST" and request.POST.get("skip") == "1":
        return _finish_onboarding(request)
    if request.method == "POST" and step["id"] == "resume" and resume_form and resume_form.is_valid():
        action = request.POST.get("action", "save_resume")
        uploaded_resume = resume_form.cleaned_data.get("resume")
        if action == "extract_resume":
            if profile.resume:
                resume_form.add_error("resume", "Delete the current resume before uploading another one.")
            elif not uploaded_resume:
                resume_form.add_error("resume", "Choose a resume file to upload first.")
            else:
                from candidates.services import autofill_from_resume, sync_candidate_profile
                from candidates.resume_parser import assess_resume_suitability
                updates, extracted_text = autofill_from_resume(uploaded_resume, answers)
                is_suitable, rejection_reason = assess_resume_suitability(extracted_text)
                if is_suitable:
                    profile.resume = uploaded_resume
                    profile.save(update_fields=["resume"])
                    answers.update(updates)
                    answers["resume"] = profile.resume.name
                    profile.profile_data = answers
                    profile.save(update_fields=["profile_data"])
                    sync_candidate_profile(request.user, answers)
                    request.session["onboarding_answers"] = answers
                    request.session["onboarding_step"] = step_number
                    request.session["sandy_intro_seen"] = True
                    notify(request.user, "Resume submitted", "Sandy auto-filled your guided profile fields. Review and edit them before continuing.", "profile")
                    return redirect("onboarding")
                resume_form.add_error("resume", rejection_reason)
        else:
            _save_resume_form(request, profile, resume_form, answers)
            request.session["onboarding_answers"] = answers
            request.session["onboarding_step"] = step_number + 1
            notify(request.user, "Resume profile saved", "Your resume profile was saved and the preview has been updated.", "profile")
            return redirect("onboarding")
    elif request.method == "POST" and step["id"] != "resume" and form.is_valid():
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
    career_choice_map = {
        area: {
            "interests": choices_for_career(CAREER_INTEREST_CHOICES, CAREER_INTERESTS_BY_AREA, area),
            "specialisations": choices_for_career(SPECIALISATION_CHOICES, SPECIALISATIONS_BY_AREA, area),
        }
        for area, _label in CAREER_CHOICES
    }
    display_steps = steps
    return render(request, "accounts/onboarding.html", {"role": role, "profile": profile, "steps": display_steps, "step": step, "step_number": step_number, "answers": answers, "completed_steps": completed_steps, "form": form, "resume_form": resume_form, "show_sandy_intro": show_sandy_intro, "career_choice_map": career_choice_map, "total_steps": len(display_steps)})


@login_required
@require_POST
def scan_resume_upload(request):
    if _role(request) != "candidate":
        return JsonResponse({"ok": False, "error": "Candidate account required."}, status=403)
    uploads = request.FILES.getlist("resume")
    if len(uploads) != 1:
        return JsonResponse({"ok": False, "error": "Upload exactly one resume."}, status=400)
    profile = _profile(request)
    if profile.resume:
        return JsonResponse({"ok": False, "error": "Delete the current resume before uploading another one."}, status=409)
    upload = uploads[0]
    from django.core.exceptions import ValidationError
    from candidates.forms import validate_resume_upload
    from candidates.resume_parser import assess_resume_suitability
    from candidates.services import autofill_from_resume, sync_candidate_profile
    try:
        validate_resume_upload(upload)
    except ValidationError as error:
        return JsonResponse({"ok": False, "error": error.messages[0]}, status=400)
    answers = dict(profile.profile_data or {})
    answers.update(request.session.get("onboarding_answers", {}))
    updates, extracted_text = autofill_from_resume(upload, answers)
    is_suitable, reason = assess_resume_suitability(extracted_text)
    if not is_suitable:
        return JsonResponse({"ok": False, "error": reason}, status=400)
    profile.resume = upload
    answers.update(updates)
    answers["resume"] = upload.name
    profile.profile_data = answers
    profile.save()
    sync_candidate_profile(request.user, answers)
    request.session["onboarding_answers"] = answers
    request.session["onboarding_step"] = 0
    return JsonResponse({"ok": True, "filename": profile.resume.name.rsplit("/", 1)[-1], "updates": updates})


@login_required
@require_POST
def delete_onboarding_resume(request):
    if _role(request) != "candidate":
        return JsonResponse({"ok": False, "error": "Candidate account required."}, status=403)
    profile = _profile(request)
    if profile.resume:
        profile.resume.delete(save=False)
    answers = dict(profile.profile_data or {})
    answers.pop("resume", None)
    profile.resume = None
    profile.profile_data = answers
    profile.save(update_fields=["resume", "profile_data"])
    request.session["onboarding_answers"] = answers
    return JsonResponse({"ok": True})


@login_required
@require_POST
def autosave_resume_draft(request):
    if _role(request) != "candidate":
        return JsonResponse({"ok": False, "error": "Candidate account required."}, status=403)
    from candidates.forms import CandidateProfileForm

    profile = _profile(request)
    answers = dict(profile.profile_data or {})
    answers.update(request.session.get("onboarding_answers", {}))
    form = CandidateProfileForm(request.POST, initial=_resume_form_initial(request, profile, answers))
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    _save_resume_form(request, profile, form, answers)
    request.session["onboarding_answers"] = answers
    return JsonResponse({"ok": True, "message": "Draft saved"})


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
            "referral_url": request.build_absolute_uri(f"{reverse('signup')}?ref={profile.referral_code}"),
            "referrals": Referral.objects.filter(referrer=request.user)[:10],
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
    notify(request.user, "Pro plan cancelled", "Your Pro plan was cancelled. Your account is now on SkillBridge Free.", "payment")
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


def _stripe_subscription_id(stripe_object):
    subscription = stripe_object.get("subscription") or (
        stripe_object.get("parent", {}).get("subscription_details", {}).get("subscription", "")
    )
    return subscription.get("id", "") if isinstance(subscription, dict) else subscription


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
        notify(request.user, "Payment successful", "SkillBridge Pro is now active.", "payment")
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
    event_type = event.get("type", "")
    stripe_object = event.get("data", {}).get("object", {})
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        session = stripe_object
        payment_id = session.get("metadata", {}).get("payment_id")
        payment = Payment.objects.filter(pk=payment_id, provider="stripe").first()
        if payment and session.get("payment_status") == "paid":
            _mark_payment_paid(payment, session)
    elif event_type == "checkout.session.expired":
        payment_id = stripe_object.get("metadata", {}).get("payment_id")
        payment = Payment.objects.filter(pk=payment_id, provider="stripe").first()
        if payment:
            set_stripe_entitlement(payment, active=False, status="expired", stripe_status="expired")
    elif event_type in {"invoice.paid", "invoice.payment_failed"}:
        payment = stripe_payment_for_subscription(_stripe_subscription_id(stripe_object))
        if payment:
            paid = event_type == "invoice.paid"
            set_stripe_entitlement(
                payment,
                active=paid,
                status="paid" if paid else "past_due",
                stripe_status="active" if paid else "past_due",
            )
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_id = stripe_object.get("id", "")
        payment = stripe_payment_for_subscription(subscription_id)
        if payment:
            stripe_status = stripe_object.get("status", "cancelled")
            active = event_type != "customer.subscription.deleted" and stripe_status in {"active", "trialing"}
            deleted = event_type == "customer.subscription.deleted"
            local_status = "paid" if active else ("cancelled" if deleted or stripe_status == "canceled" else "past_due")
            set_stripe_entitlement(
                payment,
                active=active,
                status=local_status,
                stripe_status=stripe_status,
            )
    return JsonResponse({"received": True})
