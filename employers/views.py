from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.decorators import recruiter_required
from accounts.notification_helpers import notify
from accounts.notification_helpers import notify
from accounts.calendar import build_month_calendar
from applications.forms import ApplicationStatusForm, InterviewForm
from applications.models import Interview, JobApplication
from jobs.forms import JobForm
from jobs.models import Job

from .forms import CompanyForm, CompanyLookupForm
from .models import Company, RecruiterProfile
from .services import lookup_company, website_logo_url

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
                "logo_url": website_logo_url(data.get("website", "")),
            },
        )
        if recruiter.company and not recruiter.company.logo_url and recruiter.company.website:
            recruiter.company.logo_url = website_logo_url(recruiter.company.website)
            recruiter.company.save(update_fields=["logo_url"])
        recruiter.save(update_fields=["company"])
    return recruiter


def _context(request, **extra):
    profile = getattr(request.user, "profile", None)
    return {
        "role": "recruiter",
        "has_pro": profile.is_pro if profile else False,
        **extra,
    }


def _publish_listing(request, recruiter, form):
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
    return None


@recruiter_required
def listings(request):
    recruiter = _recruiter(request)
    form = JobForm(request.POST or None)
    response = _publish_listing(request, recruiter, form)
    if response:
        return response
    jobs = Job.objects.filter(created_by=request.user).select_related("company")
    return render(request, "employers/listings.html", _context(request, jobs=jobs, form=form, company=recruiter.company))


@recruiter_required
def create_listing(request):
    recruiter = _recruiter(request)
    form = JobForm(request.POST or None)
    response = _publish_listing(request, recruiter, form)
    if response:
        return response
    return render(request, "employers/create_listing.html", _context(request, form=form, company=recruiter.company))


@recruiter_required
def edit_listing(request, job_id):
    job = get_object_or_404(Job, pk=job_id, created_by=request.user)
    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job listing updated.")
        return redirect("recruiter_listings")
    recruiter = _recruiter(request)
    return render(
        request,
        "employers/create_listing.html",
        _context(request, form=form, company=recruiter.company, editing=True, job=job),
    )


@recruiter_required
def delete_listing(request, job_id):
    job = get_object_or_404(Job, pk=job_id, created_by=request.user)
    if request.method == "POST":
        title = job.title
        job.delete()
        messages.success(request, f'Job listing "{title}" was deleted.')
        return redirect("recruiter_listings")
    return render(request, "employers/delete_listing.html", _context(request, job=job))


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
            notify(
                application.candidate,
                "Application status updated",
                f"Your application for {application.job.title} is now {application.get_status_display()}.",
                "application",
            )
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
        notify(
            application.candidate,
            "Application status updated",
            f"Your application for {application.job.title} is now {application.get_status_display()}.",
            "application",
        )
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
    applications = JobApplication.objects.filter(
        job__in=jobs,
        status__in=["shortlisted", "interview"],
    ).select_related("candidate", "job")
    interviews = Interview.objects.filter(application__in=applications).select_related("application__candidate", "application__job")
    interview_id = request.POST.get("interview_id")
    interview = None
    if interview_id:
        interview = get_object_or_404(interviews, pk=interview_id)
    action = request.POST.get("action")
    if request.method == "POST" and interview and action in {"accept_reschedule", "reject_reschedule"}:
        if interview.reschedule_status != "pending":
            messages.error(request, "That reschedule request is no longer pending.")
        elif action == "accept_reschedule" and interview.proposed_start:
            interview.scheduled_start = interview.proposed_start
            interview.scheduled_end = interview.proposed_end
            interview.reschedule_status = "accepted"
            interview.reschedule_message = "The recruiter accepted the proposed interview time."
            interview.save(update_fields=[
                "scheduled_start",
                "scheduled_end",
                "reschedule_status",
                "reschedule_message",
            ])
            notify(
                interview.application.candidate,
                "Interview reschedule accepted",
                f"Your interview for {interview.application.job.title} was moved to {interview.scheduled_start:%d %b %Y, %H:%M}.",
                "interview",
            )
            messages.success(request, "Reschedule accepted and the calendar was updated.")
        else:
            interview.reschedule_status = "rejected"
            interview.reschedule_message = "The recruiter rejected the proposed interview time."
            interview.save(update_fields=["reschedule_status", "reschedule_message"])
            notify(
                interview.application.candidate,
                "Interview reschedule declined",
                f"Your requested time change for {interview.application.job.title} was declined by the recruiter.",
                "interview",
            )
            messages.success(request, "Reschedule request rejected.")
        return redirect("recruiter_calendar")
    form = InterviewForm(request.POST or None, instance=interview)
    if request.method == "POST" and form.is_valid():
        interview = form.save(commit=False)
        if interview.pk is None:
            application = get_object_or_404(applications, pk=request.POST.get("application_id"))
            interview.application = application
            interview.created_by = request.user
        else:
            application = interview.application
        interview.save()
        if interview_id:
            interview.reschedule_status = "accepted"
            interview.reschedule_message = "The recruiter changed the interview time."
            interview.save(update_fields=["reschedule_status", "reschedule_message"])
            notify(
                application.candidate,
                "Interview time updated",
                f"The recruiter changed your interview for {application.job.title} to {interview.scheduled_start:%d %b %Y, %H:%M}.",
                "interview",
            )
        application.status = "interview"
        application.save(update_fields=["status", "updated_at"])
        if not interview_id:
            notify(
                application.candidate,
                "Interview scheduled",
                f"An interview for {application.job.title} is scheduled for {interview.scheduled_start:%d %b %Y, %H:%M}.",
                "interview",
            )
        messages.success(request, "Interview rescheduled." if interview_id else "Interview scheduled.")
        return redirect("recruiter_calendar")
    now = timezone.now()
    calendar_data = build_month_calendar(interviews, request.GET.get("month"), request.GET.get("date"))
    return render(request, "employers/calendar.html", _context(
        request,
        interviews=interviews,
        upcoming_interviews=interviews.filter(scheduled_start__gte=now),
        past_interviews=interviews.filter(scheduled_start__lt=now),
        pending_reschedules=interviews.filter(reschedule_status="pending"),
        applications=applications,
        form=form,
        calendar=calendar_data,
    ))


@recruiter_required
def company(request):
    recruiter = _recruiter(request)
    company = recruiter.company
    lookup_form = CompanyLookupForm(request.GET or None)
    lookup_data = None
    lookup_initial = {}
    if request.method == "GET" and lookup_form.is_valid():
        lookup_data = lookup_company(lookup_form.cleaned_data["query"])
        if lookup_data:
            lookup_initial = {key: value for key, value in lookup_data.items() if key in CompanyForm().fields}
        else:
            messages.info(request, "No company record was found. Enter the company details manually.")
    form = CompanyForm(request.POST or None, request.FILES or None, instance=company, initial=lookup_initial)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        profile_photo = form.cleaned_data.get("profile_photo")
        if profile_photo:
            request.user.profile.profile_photo = profile_photo
            request.user.profile.save(update_fields=["profile_photo"])
        recruiter.company = company
        recruiter.save(update_fields=["company"])
        messages.success(request, "Company profile saved.")
        return redirect("recruiter_company")
    return render(request, "employers/company.html", _context(request, form=form, company=company, lookup_form=lookup_form, lookup_data=lookup_data))


@recruiter_required
@require_GET
def company_lookup(request):
    query = request.GET.get("q", "")
    result = lookup_company(query)
    return JsonResponse({"query": query, "result": result})


@recruiter_required
def dashboard(request):
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs)
    interviews = Interview.objects.filter(application__in=applications)
    now = timezone.now()
    return render(
        request,
        "employers/dashboard.html",
        _context(
            request,
            active_jobs=jobs.filter(status="open").count(),
            applicant_count=applications.count(),
            shortlisted_count=applications.filter(status="shortlisted").count(),
            interview_count=interviews.filter(scheduled_start__gte=now).count(),
            recent_applications=applications.select_related("candidate", "job")[:5],
            upcoming_interviews=interviews.filter(scheduled_start__gte=now).select_related("application__job")[:5],
            pending_reschedules=interviews.filter(reschedule_status="pending").select_related("application__candidate", "application__job"),
        ),
    )
