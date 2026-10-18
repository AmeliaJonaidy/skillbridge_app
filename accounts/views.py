from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from .choices import (
    CAREER_CHOICES,
    EDUCATION_CHOICES,
    INSTITUTION_CHOICES,
    SPECIALISATION_CHOICES,
    VISA_CHOICES,
)
from .forms import OnboardingForm, SignupForm
from .models import UserProfile


CANDIDATE_STEPS = [
    {"id": "resume", "title": "Resume", "question": "Upload your current resume first. We will use it as the starting point for your profile and tailored applications.", "label": "Resume file", "type": "file", "required": True},
    {"id": "name", "title": "Your name", "question": "What should we call you?", "label": "Full name"},
    {"id": "career", "title": "Career interests", "question": "Which broad career area are you interested in?", "label": "Career area", "type": "select", "choices": CAREER_CHOICES},
    {"id": "specialisation", "title": "Specialisation", "question": "Which specialisation would you like to explore?", "label": "Specialisation", "type": "select", "choices": SPECIALISATION_CHOICES},
    {"id": "education", "title": "Education level", "question": "What is your highest education or training level?", "label": "Education level", "type": "select", "choices": EDUCATION_CHOICES},
    {"id": "institution", "title": "Institution", "question": "Which institution did you attend?", "label": "School or institution", "type": "select", "choices": INSTITUTION_CHOICES},
    {"id": "experience", "title": "Experience", "question": "What work, internship, or volunteer experience would you like employers to know about?", "label": "Work experience", "type": "textarea"},
    {"id": "certifications", "title": "Certifications", "question": "Which certifications have you completed or are you currently taking?", "label": "Certifications"},
    {"id": "skills", "title": "Technical skills", "question": "Which tools or technologies are you comfortable using?", "label": "Skills and technology stack", "type": "textarea"},
    {"id": "portfolio", "title": "Portfolio", "question": "Share project, GitHub, or portfolio links that show your work.", "label": "Project portfolio links", "type": "textarea"},
    {"id": "awards", "title": "Achievements", "question": "Do you have any awards, achievements, or leadership experience to add?", "label": "Awards and achievements", "type": "textarea"},
    {"id": "linkedin", "title": "LinkedIn", "question": "Where can recruiters learn more about you?", "label": "LinkedIn profile"},
    {"id": "visa", "title": "Work authorisation", "question": "What is your work-authorisation status?", "label": "Visa or work-authorisation status", "type": "select", "choices": VISA_CHOICES},
]

RECRUITER_STEPS = [
    {"id": "company", "title": "Company", "question": "What is your company called?", "label": "Company name"},
    {"id": "industry", "title": "Industry", "question": "Which industry does your company operate in?", "label": "Industry"},
    {"id": "website", "title": "Company details", "question": "Where can candidates learn more about your company?", "label": "Company website"},
    {"id": "hiring_goal", "title": "Hiring goal", "question": "What kind of candidates are you hoping to find?", "label": "Hiring goal", "type": "textarea"},
]


def _role(request):
    return getattr(getattr(request.user, "profile", None), "role", "candidate")


def _profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={"role": _role(request)})
    return profile


def _profile_is_complete(profile, steps):
    answers = profile.profile_data or {}
    return all(answers.get(step["id"]) for step in steps)


def _next_step(profile, steps):
    answers = profile.profile_data or {}
    for index, step in enumerate(steps):
        if not answers.get(step["id"]):
            return index
    return len(steps)


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


def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)
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
            request.session["onboarding_complete"] = _profile_is_complete(profile, steps)
            return redirect("home")
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
        request.session["onboarding_complete"] = True
        return redirect("home")
    step = steps[step_number]
    initial = {} if step.get("type") == "file" else {step["id"]: answers.get(step["id"], "")}
    form = OnboardingForm(request.POST or None, request.FILES or None, initial=initial, field_name=step["id"], label=step["label"], field_type=step.get("type", "text"), choices=step.get("choices"), required=step.get("required", True))
    if request.method == "POST" and form.is_valid():
        value = form.cleaned_data.get(step["id"])
        if step.get("type") == "file":
            profile.resume = value
            answers[step["id"]] = value.name
        else:
            answers[step["id"]] = value
        profile.profile_data = answers
        profile.save(update_fields=["profile_data", "resume"] if step.get("type") == "file" else ["profile_data"])
        if role == "candidate":
            from candidates.services import sync_candidate_profile

            sync_candidate_profile(request.user, answers)
        request.session["onboarding_answers"] = answers
        request.session["onboarding_step"] = step_number + 1
        if step_number + 1 >= len(steps):
            request.session["onboarding_complete"] = True
            return redirect("home")
        return redirect("onboarding")
    completed_steps = []
    for item in steps[:step_number]:
        answer = answers.get(item["id"], "")
        labels = dict(item.get("choices", []))
        completed_steps.append({
            **item,
            "answer": answer,
            "answer_display": labels.get(answer, answer),
        })
    return render(request, "accounts/onboarding.html", {"role": role, "steps": steps, "step": step, "step_number": step_number, "answers": answers, "completed_steps": completed_steps, "form": form, "total_steps": len(steps)})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")
