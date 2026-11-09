from pathlib import Path

from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.models import UserProfile
from accounts.notification_helpers import notify
from accounts.choices import (
    CAREER_CHOICES,
    CAREER_INTEREST_CHOICES,
    CAREER_STAGE_CHOICES,
    EDUCATION_CHOICES,
    INSTITUTION_CHOICES,
    PHONE_COUNTRY_CODE_CHOICES,
    SPECIALISATION_CHOICES,
)
from accounts.calendar import build_month_calendar
from accounts.decorators import candidate_required
from accounts.notification_helpers import notify
from applications.forms import CandidateInterviewForm
from applications.models import Interview, JobApplication, SavedJob
from jobs.forms import JobFilterForm
from jobs.models import Job
from matching.services import calculate_overall_suitability, get_or_update_match, recommend_certifications_for_gap
from matching.ml_model import predict_suitability

from .forms import CandidateProfileForm
from .career_paths import CAREER_PATHS, career_progress
from .models import CandidateMilestone, Certification
from .resume_parser import extract_resume_text, review_resume
from .services import (
    autofill_from_resume,
    merge_completed_certifications,
    sync_candidate_profile,
)

CERTIFICATE_FILE_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"}
MAX_CERTIFICATE_FILE_SIZE = 10 * 1024 * 1024


def _current_profile(request):
    """Read the profile from the database for every request.

    The auth user can keep a cached reverse one-to-one relation. That cache
    can still contain the old profile_data after the profile form has saved a
    new career direction, which makes Skill development look stale.
    """
    return UserProfile.objects.filter(user=request.user).first()


def _selected_career_interests(data):
    """Resolve the candidate's chosen direction into roadmap keys.

    New profiles use the multi-select career directions field. Older profiles
    may only have a specialisation, so use that specific target as a fallback
    instead of leaving the roadmap empty.
    """
    raw_interests = (data or {}).get("career_interests", [])
    if isinstance(raw_interests, str):
        raw_interests = [item.strip() for item in raw_interests.split(",") if item.strip()]
    if not isinstance(raw_interests, (list, tuple)):
        return []

    if not raw_interests:
        specialisation_map = {
            "backend": "software-engineering",
            "frontend": "software-engineering",
            "software-engineering": "software-engineering",
            "computer-science": "computer-science",
            "fintech": "fintech",
            "crypto": "fintech",
            "cloud-devops": "cloud-devops",
            "ai-ml": "machine-learning",
            "ai-engineering": "ai-engineering",
            "data-analytics": "machine-learning",
            "data-science": "data-science",
            "bioinformatics": "bioinformatics",
            "biomedical-science": "biomedical-science",
            "clinical-research": "clinical-research",
            "scientific-research": "scientific-research",
            "medicine-technology": "medicine-technology",
            "business-analysis": "business-analysis",
            "product-management": "business-analysis",
            "finance-investment": "finance",
            "investment": "investment",
            "audit-accounting": "audit-accounting",
            "ux-ui": "ux-ui",
        }
        fallback = specialisation_map.get(str((data or {}).get("specialisation", "")).casefold())
        raw_interests = [fallback] if fallback else []

    known = {key: key for key, _label in CAREER_INTEREST_CHOICES}
    known.update({label.casefold(): key for key, label in CAREER_INTEREST_CHOICES})
    selected = []
    for value in raw_interests:
        normalised = " ".join(str(value).casefold().replace("_", "-").split())
        key = known.get(normalised) or known.get(normalised.replace("-", " "))
        if key and key not in selected:
            selected.append(key)
    return selected


def _career_interest_labels(interests):
    labels = dict(CAREER_INTEREST_CHOICES)
    return [labels[key] for key in interests if key in labels]


def _context(request, **extra):
    profile = _current_profile(request)
    return {
        "role": getattr(profile, "role", "candidate"),
        "has_pro": profile.is_pro if profile else False,
        **extra,
    }


def _profile_initial(request, profile):
    data = merge_completed_certifications(request.user, profile.profile_data)
    stored_phone = str(data.get("phone", "") or "").strip()
    phone_country_code = data.get("phone_country_code", "") or "+65"
    phone_number = stored_phone
    if stored_phone.startswith(phone_country_code):
        phone_number = stored_phone[len(phone_country_code):].strip()
    elif not data.get("phone_country_code"):
        for code, _label in sorted(PHONE_COUNTRY_CODE_CHOICES, key=lambda item: len(item[0]), reverse=True):
            if stored_phone.startswith(code):
                phone_country_code = code
                phone_number = stored_phone[len(code):].strip()
                break
    return {
        "name": data.get("name", ""),
        "email": request.user.email,
        "phone_country_code": phone_country_code,
        "phone": phone_number,
        "career": data.get("career", ""),
        "specialisation": data.get("specialisation", ""),
        "career_stage": data.get("career_stage", ""),
        "career_interests": data.get("career_interests", []),
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
    fields = ["name", "career", "career_stage", "specialisation", "career_interests", "education", "institution", "experience", "certifications", "skills", "portfolio", "awards", "linkedin", "visa"]
    completed = sum(bool(data.get(field)) for field in fields) + bool(profile.resume)
    return round(completed / (len(fields) + 1) * 100)


def _certificate_upload_error(uploaded_file):
    """Return a user-facing validation message for certificate evidence."""
    if not uploaded_file:
        return         "Enter your certificate ID before marking this milestone complete."
    extension = Path(uploaded_file.name).suffix.casefold()
    if extension not in CERTIFICATE_FILE_EXTENSIONS:
        return "Certificate evidence must be a PDF, DOC, DOCX, PNG, JPG, or JPEG file."
    if uploaded_file.size > MAX_CERTIFICATE_FILE_SIZE:
        return "Certificate evidence must be 10 MB or smaller."
    return ""


def _catalogue_certification(course, career_key):
    """Represent a curated course as a Certification for milestone tracking."""
    certification, _ = Certification.objects.get_or_create(
        title=course["title"],
        provider=course["provider"],
        defaults={
            "career_area": career_key,
            "skills": ", ".join(course.get("covers", [])),
            "url": course.get("url", ""),
            "is_recognised": True,
        },
    )
    return certification


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
    has_pro = _current_profile(request).is_pro
    job_cards = []
    for job in job_queryset:
        match = get_or_update_match(request.user, job) if has_pro else None
        ml_prediction = predict_suitability(request.user, job) if has_pro else None
        job_cards.append({
            "job": job,
            "match": match,
            "ml_prediction": ml_prediction,
            "overall_score": calculate_overall_suitability(
                match.score if match else None,
                ml_prediction["score"] if ml_prediction else None,
            ),
            "is_saved": job.id in saved_ids,
        })
    return render(request, "candidates/jobs.html", _context(request, form=form, job_cards=job_cards))


@candidate_required
def profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={"role": "candidate"})
    merged_profile_data = merge_completed_certifications(request.user, profile.profile_data)
    if merged_profile_data != profile.profile_data:
        profile.profile_data = merged_profile_data
        profile.save(update_fields=["profile_data"])
    initial = _profile_initial(request, profile)
    form = CandidateProfileForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "save")
        if action == "autofill":
            uploaded_resume = form.cleaned_data.get("resume")
            if uploaded_resume:
                profile.resume = uploaded_resume
                profile.save(update_fields=["resume"])
            if not profile.resume:
                messages.error(request, "Upload a resume first, then use auto-fill.")
            else:
                data = dict(profile.profile_data or {})
                updates, extracted_text = autofill_from_resume(profile.resume, data)
                if extracted_text:
                    data.update(updates)
                    data["resume"] = profile.resume.name
                    profile.profile_data = data
                    profile.save(update_fields=["profile_data"])
                    sync_candidate_profile(request.user, data)
                    messages.success(request, f"Auto-filled {len(updates)} profile field(s). Review them before saving.")
                else:
                    messages.error(request, "We could not extract readable text from this resume. PDF support requires the pypdf package.")
            return redirect("candidate_profile")
        data = dict(profile.profile_data or {})
        changed_fields = ["profile_data"]
        for field in form.fields:
            value = form.cleaned_data.get(field)
            if field == "resume":
                if value:
                    profile.resume = value
                    changed_fields.append("resume")
                    data["resume"] = profile.resume.name
            elif field == "email":
                request.user.email = value or ""
                request.user.save(update_fields=["email"])
            elif value is not None:
                data[field] = value
        phone_number = str(data.get("phone", "") or "").strip()
        phone_country_code = str(data.get("phone_country_code", "") or "").strip()
        data["phone"] = f"{phone_country_code} {phone_number}".strip() if phone_number else ""
        profile.profile_data = data
        profile.save(update_fields=changed_fields)
        sync_candidate_profile(request.user, data)
        messages.success(request, "Your profile has been updated.")
        return redirect("candidate_profile")
    return render(request, "candidates/profile.html", {**_context(request), "form": form, "profile": profile, "completion_percent": _completion_percent(profile)})


@candidate_required
def resume(request):
    profile = _current_profile(request)
    data = merge_completed_certifications(
        request.user,
        profile.profile_data if profile else {},
    )
    resume_data = dict(data)
    resume_data["email"] = request.user.email
    resume_data["career_label"] = dict(CAREER_INTEREST_CHOICES).get(
        data.get("career"),
        dict(CAREER_CHOICES).get(data.get("career"), data.get("career", "")),
    )
    resume_data["specialisation_label"] = dict(SPECIALISATION_CHOICES).get(
        data.get("specialisation"),
        data.get("specialisation", ""),
    )
    resume_data["education_label"] = dict(EDUCATION_CHOICES).get(
        data.get("education"),
        data.get("education", ""),
    )
    resume_data["institution_label"] = dict(INSTITUTION_CHOICES).get(
        data.get("institution"),
        data.get("institution", ""),
    )
    resume_data["career_stage_label"] = dict(CAREER_STAGE_CHOICES).get(
        data.get("career_stage"),
        data.get("career_stage", ""),
    )
    resume_data["career_interest_labels"] = _career_interest_labels(
        _selected_career_interests(data)
    )
    certificate_entries = list(resume_data.get("completed_career_certificates", []))
    existing_certifications = str(resume_data.get("certifications", "") or "").strip()
    certification_lines = [line.strip() for line in existing_certifications.splitlines() if line.strip()]
    for certificate in certificate_entries:
        title = certificate.get("title", "").strip()
        certificate_id = certificate.get("certificate_id", "").strip()
        if not title:
            continue
        line = f"{title} (Certificate ID: {certificate_id})" if certificate_id else title
        if line not in certification_lines:
            certification_lines.append(line)
    resume_data["certifications"] = "\n".join(certification_lines)
    feedback = None
    if profile and profile.resume:
        with profile.resume.open("rb") as resume_file:
            feedback = review_resume(extract_resume_text(resume_file))
    return render(request, "candidates/resume.html", _context(request, profile=profile, profile_data=resume_data, feedback=feedback))


@candidate_required
def applications(request):
    application_list = JobApplication.objects.filter(candidate=request.user).select_related("job__company")
    has_pro = _current_profile(request).is_pro
    for application in application_list:
        ml_prediction = predict_suitability(request.user, application.job) if has_pro else None
        application.overall_score = calculate_overall_suitability(
            application.match_score,
            ml_prediction["score"] if ml_prediction else None,
        )
    return render(request, "candidates/applications.html", _context(request, applications=application_list))


@candidate_required
def calendar(request):
    interviews = Interview.objects.filter(application__candidate=request.user).select_related("application__job__company")
    interview_id = request.POST.get("interview_id")
    interview = get_object_or_404(interviews, pk=interview_id) if interview_id else None
    form = CandidateInterviewForm(request.POST or None, instance=interview)
    if request.method == "POST" and form.is_valid():
        candidate_notes = form.cleaned_data["candidate_notes"]
        interview.candidate_notes = candidate_notes
        requested_start = form.cleaned_data.get("requested_start")
        requested_end = form.cleaned_data.get("requested_end")
        if requested_start:
            interview.proposed_start = requested_start
            interview.proposed_end = requested_end
            interview.reschedule_status = "pending"
            interview.reschedule_requested_by = request.user
            interview.reschedule_reason = form.cleaned_data.get("reschedule_reason", "")
            interview.reschedule_message = "The candidate requested a new interview time."
            notify(
                interview.application.job.created_by,
                "Interview reschedule requested",
                f"{request.user.username} requested a new time for {interview.application.job.title}. Reason: {interview.reschedule_reason or 'No reason provided.'}",
                "interview",
            )
            messages.success(request, "Your reschedule request was sent to the recruiter.")
        else:
            messages.success(request, "Interview notes saved.")
        interview.save(update_fields=[
            "candidate_notes",
            "proposed_start",
            "proposed_end",
            "reschedule_status",
            "reschedule_requested_by",
            "reschedule_message",
            "reschedule_reason",
        ])
        return redirect("candidate_calendar")
    calendar_data = build_month_calendar(interviews, request.GET.get("month"), request.GET.get("date"))
    now = timezone.now()
    return render(request, "candidates/calendar.html", _context(
        request,
        interviews=interviews,
        upcoming_interviews=interviews.filter(scheduled_start__gte=now),
        past_interviews=interviews.filter(scheduled_start__lt=now),
        form=form,
        calendar=calendar_data,
    ))


@candidate_required
def learning(request):
    profile = _current_profile(request)
    data = (profile.profile_data if profile else {}) or {}
    certifications = Certification.objects.filter(is_recognised=True)
    if data.get("career"):
        certifications = certifications.filter(career_area__in=[data["career"], ""])
    milestones = CandidateMilestone.objects.filter(candidate=request.user).select_related("certification")
    interests = _selected_career_interests(data)
    progress = career_progress(request.user, interests)
    requested_direction = request.GET.get("direction", "")
    if requested_direction in interests:
        progress = [goal for goal in progress if goal["key"] == requested_direction]
    completed_courses = {
        milestone.certification.title: milestone
        for milestone in milestones
        if milestone.status == "completed"
    }
    legacy_completed_courses = set(data.get("completed_career_courses", []))
    for goal in progress:
        goal["completed_courses"] = []
        for course in goal["recommendations"]:
            milestone = completed_courses.get(course["title"])
            course["completed"] = bool(milestone or course["title"] in legacy_completed_courses)
            course["certificate_id"] = milestone.certificate_id if milestone else ""
        for milestone in goal["milestones"]:
            for course in milestone["courses"]:
                completed = completed_courses.get(course["title"])
                course["completed"] = bool(completed or course["title"] in legacy_completed_courses)
                course["certificate_id"] = completed.certificate_id if completed else ""
        visible_titles = {
            course["title"]
            for milestone in goal["milestones"]
            for course in milestone["courses"]
        }
        for completed in milestones:
            certification = completed.certification
            if completed.status != "completed" or certification.title in visible_titles:
                continue
            if certification.career_area not in ("", goal["key"]):
                continue
            goal["completed_courses"].append(
                {
                    "title": certification.title,
                    "provider": certification.provider,
                    "url": certification.url,
                    "certificate_id": completed.certificate_id,
                }
            )
    target_job = None
    match = None
    gap_recommendations = []
    job_id = request.GET.get("job")
    if job_id:
        target_job = get_object_or_404(Job.objects.select_related("company"), pk=job_id)
        if profile and profile.is_pro:
            match = get_or_update_match(request.user, target_job)
            gap_recommendations = recommend_certifications_for_gap(certifications, match.missing_skills)
    if request.method == "POST":
        if request.POST.get("action") == "complete_course":
            career_key = request.POST.get("career_key", "")
            course_title = request.POST.get("course_title", "")
            certificate_id = request.POST.get("certificate_id", "").strip()
            evidence_file = request.FILES.get("evidence_file")
            path = CAREER_PATHS.get(career_key)
            course = next(
                (item for item in (path or {}).get("courses", []) if item["title"] == course_title),
                None,
            )
            upload_error = _certificate_upload_error(evidence_file) if evidence_file else ""
            if not course:
                messages.error(request, "That course milestone could not be found. Refresh the page and try again.")
            elif not certificate_id and not evidence_file:
                messages.error(request, "Enter your certificate ID before marking this course complete.")
            elif upload_error:
                messages.error(request, upload_error)
            else:
                certification = _catalogue_certification(course, career_key)
                milestone, _ = CandidateMilestone.objects.get_or_create(
                    candidate=request.user,
                    certification=certification,
                )
                milestone.evidence_file = evidence_file
                milestone.certificate_id = certificate_id
                milestone.status = "completed"
                milestone.completed_at = timezone.now()
                milestone.notes = "Certificate ID submitted by candidate."
                update_fields = ["certificate_id", "status", "completed_at", "notes"]
                if evidence_file:
                    update_fields.append("evidence_file")
                milestone.save(update_fields=update_fields)

                # Keep the legacy profile fields so existing roadmap cards
                # continue to render as completed after this migration.
                data = dict(profile.profile_data or {})
                completed_courses = list(data.get("completed_career_courses", []))
                if course_title not in completed_courses:
                    completed_courses.append(course_title)
                completed_skills = list(data.get("completed_career_skills", []))
                for skill in course.get("covers", []):
                    if skill not in completed_skills:
                        completed_skills.append(skill)
                data["completed_career_courses"] = completed_courses
                data["completed_career_skills"] = completed_skills
                completed_certificates = list(data.get("completed_career_certificates", []))
                certificate_record = {
                    "title": course_title,
                    "provider": course["provider"],
                    "certificate_id": certificate_id,
                }
                completed_certificates = [
                    item for item in completed_certificates
                    if item.get("title") != course_title
                ]
                completed_certificates.append(certificate_record)
                data["completed_career_certificates"] = completed_certificates
                certification_lines = [
                    line.strip()
                    for line in str(data.get("certifications", "") or "").splitlines()
                    if line.strip()
                ]
                certification_label = course_title
                if certificate_id:
                    certification_label = f"{course_title} (Certificate ID: {certificate_id})"
                certification_lines = [
                    line for line in certification_lines
                    if not line.startswith(f"{course_title} (Certificate ID:")
                    and line != course_title
                ]
                certification_lines.append(certification_label)
                data["certifications"] = "\n".join(certification_lines)
                profile.profile_data = data
                profile.save(update_fields=["profile_data"])
                sync_candidate_profile(request.user, data)
                messages.success(request, f"{course_title} was validated and marked completed. Your readiness bars have been updated.")
            return redirect(request.get_full_path())

        certification = get_object_or_404(Certification, pk=request.POST.get("certification_id"))
        milestone, _ = CandidateMilestone.objects.get_or_create(candidate=request.user, certification=certification)
        next_status = request.POST.get("status", "in_progress")
        evidence_file = request.FILES.get("evidence_file")
        if next_status == "completed":
            upload_error = _certificate_upload_error(evidence_file or milestone.evidence_file)
            if upload_error:
                messages.error(request, upload_error)
                return redirect(request.get_full_path())
            if evidence_file:
                milestone.evidence_file = evidence_file
        milestone.status = next_status
        milestone.completed_at = timezone.now() if next_status == "completed" else None
        update_fields = ["status", "completed_at"]
        if evidence_file:
            update_fields.append("evidence_file")
        milestone.save(update_fields=update_fields)
        if next_status == "completed":
            data = dict(profile.profile_data or {})
            certification_label = certification.title
            if milestone.certificate_id:
                certification_label = f"{certification.title} (Certificate ID: {milestone.certificate_id})"
            certification_lines = [
                line.strip()
                for line in str(data.get("certifications", "") or "").splitlines()
                if line.strip()
            ]
            certification_lines = [
                line for line in certification_lines
                if line != certification.title
                and not line.startswith(f"{certification.title} (Certificate ID:")
            ]
            certification_lines.append(certification_label)
            data["certifications"] = "\n".join(certification_lines)
            profile.profile_data = data
            profile.save(update_fields=["profile_data"])
            sync_candidate_profile(request.user, data)
        redirect_url = reverse("candidate_learning")
        if job_id:
            redirect_url = f"{redirect_url}?job={job_id}"
        return redirect(redirect_url)
    return render(
        request,
        "candidates/learning.html",
        _context(
            request,
            profile_data=data,
            certifications=certifications,
            milestones=milestones,
            open_jobs=Job.objects.filter(status="open").select_related("company"),
            target_job=target_job,
            match=match,
            gap_recommendations=gap_recommendations,
            career_progress=progress,
            selected_directions=_career_interest_labels(interests),
        ),
    )


@candidate_required
def saved_jobs(request):
    if request.method == "POST":
        job = get_object_or_404(Job, pk=request.POST.get("job_id"))
        saved, created = SavedJob.objects.get_or_create(candidate=request.user, job=job)
        if not created:
            saved.delete()
        return redirect("candidate_saved_jobs")
    saved = SavedJob.objects.filter(candidate=request.user).select_related("job__company")
    has_pro = _current_profile(request).is_pro
    job_cards = []
    for item in saved:
        match = get_or_update_match(request.user, item.job) if has_pro else None
        ml_prediction = predict_suitability(request.user, item.job) if has_pro else None
        job_cards.append({
            "job": item.job,
            "match": match,
            "ml_prediction": ml_prediction,
            "overall_score": calculate_overall_suitability(
                match.score if match else None,
                ml_prediction["score"] if ml_prediction else None,
            ),
            "is_saved": True,
        })
    return render(request, "candidates/jobs.html", _context(request, form=JobFilterForm(), job_cards=job_cards, saved_page=True))


def dashboard_context(request):
    applications = JobApplication.objects.filter(candidate=request.user)
    interviews = Interview.objects.filter(application__candidate=request.user).select_related("application__job__company")
    now = timezone.now()
    profile = _current_profile(request)
    profile_data = (profile.profile_data if profile else {}) or {}
    interests = _selected_career_interests(profile_data)
    return {
        "role": "candidate",
        "has_pro": profile.is_pro if profile else False,
        "application_count": applications.count(),
        "interview_count": interviews.filter(scheduled_start__gte=now).count(),
        "saved_count": SavedJob.objects.filter(candidate=request.user).count(),
        "profile_completion": _completion_percent(profile) if profile else 0,
        "upcoming_interviews": interviews.filter(scheduled_start__gte=now)[:1],
        "recent_jobs": Job.objects.filter(status="open").select_related("company")[:3],
        "career_progress": career_progress(request.user, interests),
    }
