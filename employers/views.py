from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.core.exceptions import ValidationError
from django.db import transaction
from django.views.decorators.http import require_http_methods
import csv
import io
import secrets
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.db.models import F
from django.views.decorators.http import require_GET

from accounts.decorators import recruiter_required
from accounts.notification_helpers import notify
from accounts.notification_helpers import notify
from accounts.calendar import build_month_calendar
from applications.forms import ApplicationStatusForm, InterviewForm
from applications.models import Interview, JobApplication
from jobs.forms import JobForm
from jobs.models import Job
from jobs.imports import (IMPORT_FIELDS, REQUIRED_FIELDS, import_instructions, read_import,
                          template_example, template_headers, validate_import)
from jobs.reference_catalog import suggest_skills_for_title
from matching.ml_model import predict_suitability
from matching.services import calculate_overall_suitability

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
    action = request.POST.get("action", "") if request.method == "POST" else ""
    reference_kind, _, reference_index = action.partition(":")
    reference_action = reference_kind in {"suggest_reference", "use_reference_required", "use_reference_preferred"}
    form_data = request.POST or None
    suggestions = []

    if reference_action:
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.is_pro:
            messages.error(request, "Pro access is required for reference suggestions.")
        else:
            title = request.POST.get("title", "").strip()
            if title:
                try:
                    suggestions = suggest_skills_for_title(title)
                except (FileNotFoundError, OSError, ValueError) as error:
                    messages.error(request, f"Reference catalogue unavailable: {error}")
        if suggestions and reference_kind in {"use_reference_required", "use_reference_preferred"}:
            try:
                suggestion = suggestions[int(reference_index)]
            except (IndexError, TypeError, ValueError):
                messages.error(request, "That reference match is no longer available.")
            else:
                form_data = request.POST.copy()
                field_name = "required_skills" if reference_kind.endswith("required") else "preferred_skills"
                form_data[field_name] = ", ".join(suggestion["skills"])

    form = JobForm(form_data)
    response = None if reference_action else _publish_listing(request, recruiter, form)
    if response:
        return response
    return render(
        request,
        "employers/create_listing.html",
        _context(request, form=form, company=recruiter.company, suggestions=suggestions),
    )


@recruiter_required
def job_detail(request, job_id):
    job = get_object_or_404(
        Job.objects.select_related("company"),
        pk=job_id,
        created_by=request.user,
    )
    return render(request, "employers/job_detail.html", _context(request, job=job))


@recruiter_required
def edit_listing(request, job_id):
    job = get_object_or_404(Job, pk=job_id, created_by=request.user)
    form = JobForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job listing updated.")
        return redirect("recruiter_job_detail", job_id=job.id)
    return render(request, "employers/edit_listing.html", _context(request, form=form, job=job))


@recruiter_required
@require_GET
def job_import_template(request):
    example = template_example()
    if request.GET.get("format") == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Jobs"
        sheet.append(template_headers())
        sheet.append([example[field] for field in IMPORT_FIELDS])
        sheet.freeze_panes = "A2"
        for index, field in enumerate(IMPORT_FIELDS, start=1):
            cell = sheet.cell(1, index)
            cell.font = Font(bold=True, color="C62828" if field in REQUIRED_FIELDS else "172447")
            sheet.column_dimensions[cell.column_letter].width = 28
        instructions = workbook.create_sheet("Instructions")
        for row in import_instructions():
            instructions.append(row)
        instructions.column_dimensions["A"].width = 24
        instructions.column_dimensions["B"].width = 110
        output = io.BytesIO()
        workbook.save(output)
        response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="skillbridge-job-template.xlsx"'
    else:
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="skillbridge-job-template.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(template_headers())
        writer.writerow([example[field] for field in IMPORT_FIELDS])
    return response


@recruiter_required
@require_http_methods(["GET", "POST"])
def import_listings(request):
    recruiter = _recruiter(request)
    errors = []
    preview = []
    token = ""
    if request.method == "GET":
        request.session.pop("job_import_preview", None)
    if request.method == "POST" and recruiter.company_id:
        if request.POST.get("action") == "confirm":
            pending = request.session.get("job_import_preview") or {}
            if (not pending or pending.get("company_id") != recruiter.company_id
                    or not secrets.compare_digest(str(pending.get("token", "")), request.POST.get("token", ""))
                    or timezone.now().timestamp() - pending.get("created_at", 0) > 1800):
                messages.error(request, "This preview has expired or changed. Upload the file again.")
            else:
                forms, errors = validate_import(pending["rows"])
                if not errors:
                    with transaction.atomic():
                        for form in forms:
                            job = form.save(commit=False)
                            job.company = recruiter.company
                            job.created_by = request.user
                            job.save()
                    request.session.pop("job_import_preview", None)
                    messages.success(request, f"Created {len(forms)} job listing(s).")
                    return redirect("recruiter_listings")
        else:
            request.session.pop("job_import_preview", None)
            upload = request.FILES.get("file")
            if not upload:
                messages.error(request, "Choose a CSV or Excel .xlsx file.")
            else:
                try:
                    rows = read_import(upload)
                    forms, errors = validate_import(rows)
                    if not errors:
                        token = secrets.token_hex(24)
                        request.session["job_import_preview"] = {
                            "rows": rows, "company_id": recruiter.company_id,
                            "token": token, "created_at": timezone.now().timestamp(),
                        }
                        preview = [form.save(commit=False) for form in forms]
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
    elif request.method == "POST":
        messages.error(request, "Complete your company profile before importing listings.")
    return render(request, "employers/import_listings.html", _context(
        request, company=recruiter.company, errors=errors, preview=preview,
        token=token, instructions=import_instructions(),
    ))


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
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    jobs = Job.objects.filter(created_by=request.user)
    applications = JobApplication.objects.filter(job__in=jobs).select_related("candidate", "job")
    for application in applications:
        application.status_form = ApplicationStatusForm(instance=application)
    if has_pro:
        for application in applications:
            application.ml_prediction = predict_suitability(application.candidate, application.job)
            application.overall_score = calculate_overall_suitability(
                application.match_score,
                application.ml_prediction["score"],
            )
    job_id = request.GET.get("job")
    status = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    if job_id:
        applications = applications.filter(job_id=job_id)
    if status:
        applications = applications.filter(status=status)
    if query:
        applications = applications.filter(candidate__username__icontains=query)

    sort = "match" if request.GET.get("sort") == "match" and request.user.profile.is_pro else "newest"
    if sort == "match":
        applications = applications.order_by(F("match_score").desc(nulls_last=True), "-created_at", "-pk")

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
    return render(request, "employers/applicants.html", _context(request, applications=applications, jobs=jobs, status_form=status_form, sort=sort, has_pro=has_pro))


@recruiter_required
def applicant_detail(request, application_id):
    profile = getattr(request.user, "profile", None)
    has_pro = profile.is_pro if profile else False
    application = get_object_or_404(
        JobApplication.objects.select_related("candidate", "job__company"),
        pk=application_id,
        job__created_by=request.user,
    )
    candidate_profile = getattr(application.candidate, "candidate_profile", None)
    profile = getattr(application.candidate, "profile", None)
    ml_prediction = predict_suitability(application.candidate, application.job) if has_pro else None
    overall_score = calculate_overall_suitability(
        application.match_score,
        ml_prediction["score"] if ml_prediction else None,
    )
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
            has_pro=has_pro,
            ml_prediction=ml_prediction,
            overall_score=overall_score,
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
    has_pro = getattr(request.user, "profile", None)
    has_pro = has_pro.is_pro if has_pro else False
    recent_applications = applications.select_related("candidate", "job")[:5]
    if has_pro:
        for application in recent_applications:
            ml_prediction = predict_suitability(application.candidate, application.job)
            application.overall_score = calculate_overall_suitability(
                application.match_score,
                ml_prediction["score"],
            )
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
            recent_applications=recent_applications,
            has_pro=has_pro,
            upcoming_interviews=interviews.filter(scheduled_start__gte=now).select_related("application__job")[:5],
            pending_reschedules=interviews.filter(reschedule_status="pending").select_related("application__candidate", "application__job"),
        ),
    )
