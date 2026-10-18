from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import UserProfile
from accounts.decorators import candidate_required
from applications.models import Interview, JobApplication, SavedJob
from jobs.forms import JobFilterForm
from jobs.models import Job
from matching.services import get_or_update_match

from .forms import CandidateProfileForm
from .models import CandidateMilestone, Certification
from .services import sync_candidate_profile


def _context(request, **extra):
    profile = getattr(request.user, "profile", None)
    return {"role": getattr(profile, "role", "candidate"), **extra}


def _profile_initial(request, profile):
    data = profile.profile_data or {}
    return {
        "name": data.get("name", ""),
        "email": request.user.email,
        "phone": data.get("phone", ""),
        "career": data.get("career", ""),
        "specialisation": data.get("specialisation", ""),
        "education": data.get("education", ""),
        "institution": data.get("institution", data.get("school", "")),
        "experience": data.get("experience", ""),
        "certifications": data.get("certifications", ""),
        "skills": data.get("skills", ""),
        "portfolio": data.get("portfolio", data.get("portfolio_links", "")),
        "awards": data.get("awards", ""),
        "linkedin": data.get("linkedin", data.get("linkedin_url", "")),
        "visa": data.get("visa", data.get("visa_status", "")),
    }


def _completion_percent(profile):
    data = profile.profile_data or {}
    fields = ["name", "career", "specialisation", "education", "institution", "experience", "certifications", "skills", "portfolio", "awards", "linkedin", "visa"]
    completed = sum(bool(data.get(field)) for field in fields) + bool(profile.resume)
    return round(completed / (len(fields) + 1) * 100)


@candidate_required
def jobs(request):
    form = JobFilterForm(request.GET or None)
    job_queryset = Job.objects.filter(status="open").select_related("company")
    if form.is_valid():
        query = form.cleaned_data.get("q")
        location = form.cleaned_data.get("location")
        employment_type = form.cleaned_data.get("employment_type")
        industry = form.cleaned_data.get("industry")
        if query:
            job_queryset = job_queryset.filter(
                Q(title__icontains=query)
                | Q(company__name__icontains=query)
                | Q(required_skills__icontains=query)
            )
        if location:
            job_queryset = job_queryset.filter(location__icontains=location)
        if employment_type:
            job_queryset = job_queryset.filter(employment_type=employment_type)
        if industry:
            job_queryset = job_queryset.filter(industry__icontains=industry)

    saved_ids = set(SavedJob.objects.filter(candidate=request.user).values_list("job_id", flat=True))
    job_cards = []
    for job in job_queryset:
        job_cards.append({
            "job": job,
            "match": get_or_update_match(request.user, job),
            "is_saved": job.id in saved_ids,
        })
    return render(request, "candidates/jobs.html", _context(request, form=form, job_cards=job_cards))


@candidate_required
def profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={"role": "candidate"})
    initial = _profile_initial(request, profile)
    form = CandidateProfileForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = dict(profile.profile_data or {})
        for field in form.fields:
            if field == "resume":
                continue
            value = form.cleaned_data.get(field)
            if field == "email":
                request.user.email = value or ""
                request.user.save(update_fields=["email"])
            elif value is not None:
                data[field] = value
        resume = form.cleaned_data.get("resume")
        update_fields = ["profile_data"]
        if resume:
            profile.resume = resume
            update_fields.append("resume")
        profile.profile_data = data
        profile.save(update_fields=update_fields)
        sync_candidate_profile(request.user, data)
        messages.success(request, "Your profile has been updated.")
        form = CandidateProfileForm(initial=_profile_initial(request, profile))
    return render(request, "candidates/profile.html", {**_context(request), "form": form, "profile": profile, "completion_percent": _completion_percent(profile)})


@candidate_required
def resume(request):
    profile = getattr(request.user, "profile", None)
    data = (profile.profile_data if profile else {}) or {}
    return render(request, "candidates/resume.html", _context(request, profile=profile, profile_data=data))


@candidate_required
def applications(request):
    application_list = JobApplication.objects.filter(candidate=request.user).select_related("job__company")
    return render(request, "candidates/applications.html", _context(request, applications=application_list))


@candidate_required
def calendar(request):
    interviews = Interview.objects.filter(application__candidate=request.user).select_related("application__job__company")
    return render(request, "candidates/calendar.html", _context(request, interviews=interviews))


@candidate_required
def learning(request):
    profile = getattr(request.user, "profile", None)
    data = (profile.profile_data if profile else {}) or {}
    certifications = Certification.objects.all()
    if data.get("career"):
        certifications = certifications.filter(career_area__in=[data["career"], ""])
    milestones = CandidateMilestone.objects.filter(candidate=request.user).select_related("certification")
    if request.method == "POST":
        certification = get_object_or_404(Certification, pk=request.POST.get("certification_id"))
        milestone, _ = CandidateMilestone.objects.get_or_create(candidate=request.user, certification=certification)
        next_status = request.POST.get("status", "in_progress")
        milestone.status = next_status
        milestone.completed_at = timezone.now() if next_status == "completed" else None
        milestone.save(update_fields=["status", "completed_at"])
        return redirect("candidate_learning")
    return render(request, "candidates/learning.html", _context(request, profile_data=data, certifications=certifications, milestones=milestones))


@candidate_required
def saved_jobs(request):
    if request.method == "POST":
        job = get_object_or_404(Job, pk=request.POST.get("job_id"))
        saved, created = SavedJob.objects.get_or_create(candidate=request.user, job=job)
        if not created:
            saved.delete()
        return redirect("candidate_saved_jobs")
    saved = SavedJob.objects.filter(candidate=request.user).select_related("job__company")
    return render(request, "candidates/jobs.html", _context(request, form=JobFilterForm(), job_cards=[{"job": item.job, "match": get_or_update_match(request.user, item.job), "is_saved": True} for item in saved], saved_page=True))


def dashboard_context(request):
    applications = JobApplication.objects.filter(candidate=request.user)
    interviews = Interview.objects.filter(application__candidate=request.user).select_related("application__job__company")
    profile = getattr(request.user, "profile", None)
    return {
        "role": "candidate",
        "application_count": applications.count(),
        "interview_count": interviews.count(),
        "saved_count": SavedJob.objects.filter(candidate=request.user).count(),
        "profile_completion": _completion_percent(profile) if profile else 0,
        "upcoming_interviews": interviews[:1],
        "recent_jobs": Job.objects.filter(status="open").select_related("company")[:3],
    }
