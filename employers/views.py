from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import recruiter_required
from accounts.calendar import build_month_calendar
from applications.forms import ApplicationStatusForm, InterviewForm
from applications.models import Interview, JobApplication
from jobs.forms import JobForm
from jobs.models import Job

from .forms import CompanyForm
from .models import Company, RecruiterProfile

def _recruiter(request):
    recruiter, _ = RecruiterProfile.objects.get_or_create(user=request.user)
    profile = getattr(request.user, "profile", None)
    data = (profile.profile_data if profile else {}) or {}
    if recruiter.company_id is None and data.get("company"):
        recruiter.company, _ = Company.objects.get_or_create(
            name=data["company"],
            defaults={
                "industry": data.get("industry", ""),
                "website": data.get("website", ""),
            },
        )
        recruiter.save(update_fields=["company"])
    return recruiter


def _context(request, **extra):
    return {"role": "recruiter", **extra}


@recruiter_required
def listings(request):
    recruiter = _recruiter(request)
    form = JobForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if recruiter.company is None:
            messages.error(request, "Complete your company profile before creating a listing.")
        else:
            job = form.save(commit=False)
            job.company = recruiter.company
            job.created_by = request.user
            job.save()
            messages.success(request, "Job listing created.")
            return redirect("recruiter_listings")
    jobs = Job.objects.filter(created_by=request.user).select_related("company")
    return render(request, "employers/listings.html", _context(request, jobs=jobs, form=form, company=recruiter.company))


@recruiter_required
def applicants(request):
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs).select_related("candidate", "job")
    job_id = request.GET.get("job")
    status = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    if job_id:
        applications = applications.filter(job_id=job_id)
    if status:
        applications = applications.filter(status=status)
    if query:
        applications = applications.filter(candidate__username__icontains=query)

    if request.method == "POST":
        application = get_object_or_404(applications, pk=request.POST.get("application_id"))
        status_form = ApplicationStatusForm(request.POST, instance=application)
        if status_form.is_valid():
            status_form.save()
            if application.candidate.email:
                send_mail(
                    subject=f"Application update for {application.job.title}",
                    message=f"Your application status is now: {application.get_status_display()}.",
                    from_email="noreply@skillbridge.local",
                    recipient_list=[application.candidate.email],
                    fail_silently=True,
                )
            messages.success(request, "Applicant status updated.")
            return redirect("recruiter_applicants")
    else:
        status_form = ApplicationStatusForm()
    return render(request, "employers/applicants.html", _context(request, applications=applications, jobs=jobs, status_form=status_form))


@recruiter_required
def applicant_detail(request, application_id):
    application = get_object_or_404(
        JobApplication.objects.select_related("candidate", "job__company"),
        pk=application_id,
        job__created_by=request.user,
    )
    candidate_profile = getattr(application.candidate, "candidate_profile", None)
    profile = getattr(application.candidate, "profile", None)
    status_form = ApplicationStatusForm(request.POST or None, instance=application)
    if request.method == "POST" and status_form.is_valid():
        status_form.save()
        messages.success(request, "Applicant status updated.")
        return redirect("recruiter_applicant_detail", application_id=application.id)
    return render(
        request,
        "employers/applicant_detail.html",
        _context(
            request,
            application=application,
            candidate_profile=candidate_profile,
            profile=profile,
            status_form=status_form,
        ),
    )


@recruiter_required
def calendar(request):
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs).select_related("candidate", "job")
    interviews = Interview.objects.filter(application__in=applications).select_related("application__candidate", "application__job")
    form = InterviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        interview = form.save(commit=False)
        application = get_object_or_404(applications, pk=request.POST.get("application_id"))
        interview.application = application
        interview.created_by = request.user
        interview.save()
        application.status = "interview"
        application.save(update_fields=["status", "updated_at"])
        messages.success(request, "Interview scheduled.")
        return redirect("recruiter_calendar")
    calendar_data = build_month_calendar(interviews, request.GET.get("month"), request.GET.get("date"))
    return render(request, "employers/calendar.html", _context(request, interviews=interviews, applications=applications, form=form, calendar=calendar_data))


@recruiter_required
def company(request):
    recruiter = _recruiter(request)
    company = recruiter.company
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        recruiter.company = company
        recruiter.save(update_fields=["company"])
        messages.success(request, "Company profile saved.")
        return redirect("recruiter_company")
    return render(request, "employers/company.html", _context(request, form=form, company=company))


@recruiter_required
def dashboard(request):
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs)
    interviews = Interview.objects.filter(application__in=applications)
    return render(
        request,
        "employers/dashboard.html",
        _context(
            request,
            active_jobs=jobs.filter(status="open").count(),
            applicant_count=applications.count(),
            shortlisted_count=applications.filter(status="shortlisted").count(),
            interview_count=interviews.count(),
            recent_applications=applications.select_related("candidate", "job")[:5],
            upcoming_interviews=interviews.select_related("application__job")[:5],
        ),
    )
