from pathlib import Path
import re

from django.contrib import messages
from django.utils import timezone
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse

from accounts.models import UserProfile
from accounts.notification_helpers import notify
from accounts.choices import (
    CAREER_CHOICES,
    CAREER_INTERESTS_BY_AREA,
    CAREER_INTEREST_CHOICES,
    PHONE_COUNTRY_CODE_CHOICES,
    SPECIALISATION_CHOICES,
    SPECIALISATIONS_BY_AREA,
    choices_for_career,
)
from accounts.calendar import build_month_calendar
from accounts.decorators import candidate_required
from accounts.notification_helpers import notify
from applications.forms import CandidateInterviewForm
from applications.models import Interview, JobApplication, SavedJob
from jobs.forms import JobFilterForm
from jobs.models import Job
from matching.services import get_or_update_match, recommend_certifications_for_gap

from .forms import CandidateProfileForm
from .career_paths import CAREER_FIT_PROFILES, CAREER_PATHS, _candidate_source, _skill_matches, career_progress, resume_fit_matrix
from .certificate_verification import verify_certificate
from .models import CandidateMilestone, Certification
from .resume_parser import assess_resume_suitability, extract_resume_text, review_resume
from .services import add_verified_certificate_to_resume, autofill_from_resume, sync_candidate_profile
from resumes.models import TailoredResume
from resumes.services import build_interest_tailored_resume

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
    data = profile.profile_data or {}
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
        "experience_entries": data.get("experience_entries", []),
        "certifications": data.get("certifications", ""),
        "certification_entries": data.get("certification_entries", []),
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


def _certificate_id_error(certificate_id):
    value = (certificate_id or "").strip()
    if len(value) < 6:
        return "Certificate IDs must contain at least 6 characters."
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{4,148}[A-Za-z0-9]", value):
        return "Enter the certificate ID exactly as issued, using only letters, numbers, dots, slashes, underscores, or hyphens."
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
    applied_ids = set(JobApplication.objects.filter(candidate=request.user).values_list("job_id", flat=True))
    job_cards = []
    for job in job_queryset:
        job_cards.append({
            "job": job,
            "match": get_or_update_match(request.user, job),
            "is_saved": job.id in saved_ids,
            "has_applied": job.id in applied_ids,
        })
    sort = "match" if request.GET.get("sort") == "match" and request.user.profile.is_pro else "newest"
    if sort == "match":
        job_cards.sort(key=lambda card: (card["match"].score, card["job"].created_at, card["job"].pk), reverse=True)
    return render(request, "candidates/jobs.html", _context(request, form=form, job_cards=job_cards, sort=sort))


@candidate_required
def profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={"role": "candidate"})
    initial = _profile_initial(request, profile)
    form = CandidateProfileForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "save")
        if action == "autofill":
            uploaded_resume = form.cleaned_data.get("resume")
            source = uploaded_resume or profile.resume
            if not source:
                messages.error(request, "Upload a resume first, then use auto-fill.")
            else:
                data = dict(profile.profile_data or {})
                updates, extracted_text = autofill_from_resume(source, data)
                suitable, reason = assess_resume_suitability(extracted_text)
                if suitable:
                    if uploaded_resume:
                        profile.resume = uploaded_resume
                        profile.save(update_fields=["resume"])
                    data.update(updates)
                    data["resume"] = profile.resume.name
                    profile.profile_data = data
                    profile.save(update_fields=["profile_data"])
                    sync_candidate_profile(request.user, data)
                    notify(request.user, "Profile auto-filled", f"Sandy auto-filled {len(updates)} profile field(s) from your resume.", "profile")
                else:
                    messages.error(request, reason)
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
            elif field == "profile_photo":
                if value:
                    profile.profile_photo = value
                    changed_fields.append("profile_photo")
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
        notify(request.user, "Profile updated", "Your SkillBridge profile has been updated successfully.", "profile")
        profile.refresh_from_db()
        form = CandidateProfileForm(initial=_profile_initial(request, profile))
    career_choice_map = {
        career_area: {
            "label": dict(CAREER_CHOICES).get(career_area, career_area.title()),
            "interests": choices_for_career(CAREER_INTEREST_CHOICES, CAREER_INTERESTS_BY_AREA, career_area),
            "specialisations": choices_for_career(SPECIALISATION_CHOICES, SPECIALISATIONS_BY_AREA, career_area),
        }
        for career_area in CAREER_INTERESTS_BY_AREA
    }
    selected_interests = form["career_interests"].value() or []
    if isinstance(selected_interests, str):
        selected_interests = [selected_interests]
    return render(request, "candidates/profile.html", {
        **_context(request),
        "form": form,
        "profile": profile,
        "completion_percent": _completion_percent(profile),
        "career_choice_map": career_choice_map,
        "selected_interests": selected_interests,
        "guided_resume": request.GET.get("guided") == "1",
    })


@candidate_required
def resume(request):
    profile = getattr(request.user, "profile", None)
    data = (profile.profile_data if profile else {}) or {}
    feedback = None
    fit_matrix = resume_fit_matrix(request.user, _selected_career_interests(data))
    tailored_drafts = {
        draft.title: draft
        for draft in TailoredResume.objects.filter(candidate=request.user)
    }
    main_resume = TailoredResume.objects.filter(candidate=request.user, is_main=True).first()
    for fit in fit_matrix:
        draft = tailored_drafts.get(f"Resume for {fit['label']}")
        fit["tailored_resume_id"] = draft.id if draft else ""
    if profile and profile.resume:
        with profile.resume.open("rb") as resume_file:
            feedback = review_resume(extract_resume_text(resume_file))
    return render(request, "candidates/resume.html", _context(
        request,
        profile=profile,
        profile_data=data,
        feedback=feedback,
        fit_matrix=fit_matrix,
        main_resume=main_resume,
    ))


@candidate_required
def tailor_resume_for_interest(request, interest):
    profile = _current_profile(request)
    data = (profile.profile_data if profile else {}) or {}
    if interest not in _selected_career_interests(data):
        messages.error(request, "Select this career direction in your profile before tailoring a resume.")
        return redirect("candidate_resume")
    path = CAREER_PATHS.get(interest) or CAREER_FIT_PROFILES.get(interest)
    if not path:
        messages.error(request, "This career direction is not available for tailoring yet.")
        return redirect("candidate_resume")
    source, _ = _candidate_source(request.user)
    tracked_skills = path["skills"] if path else []
    matched = [skill for skill in tracked_skills if _skill_matches(source, skill)]
    skill_questions = [
        {"name": skill, "already_matched": skill in matched}
        for skill in tracked_skills
    ]
    if request.method == "POST":
        skill_evidence = {}
        errors = []
        if not request.POST.get("skip_missing"):
            for skill in tracked_skills:
                description = request.POST.get(f"description_{skill}", "").strip()
                duration = request.POST.get(f"duration_{skill}", "").strip()
                question = next(item for item in skill_questions if item["name"] == skill)
                question.update(description=description, duration=duration)
                if bool(description) != bool(duration):
                    errors.append(f"For {skill}, provide both your experience and duration, or leave both blank and follow the learning route.")
                if description and duration:
                    skill_evidence[skill] = {"description": description, "duration": duration}
        if errors:
            return render(
                request,
                "candidates/tailor_interest.html",
                _context(request, interest=interest, path=path, skill_questions=skill_questions, errors=errors),
            )
        draft = TailoredResume.objects.create(
            candidate=request.user,
            title=f"Resume for {path['label'] if path else interest.replace('-', ' ').title()}",
            content=build_interest_tailored_resume(request.user, interest, skill_evidence),
        )
        notify(request.user, "Tailored resume ready", f"Your {path['label']} resume draft is ready to review and edit.", "resume")
        return redirect("resume_detail", resume_id=draft.id)
    return render(request, "candidates/tailor_interest.html", _context(
        request, interest=interest, path=path, skill_questions=skill_questions, errors=[],
    ))


@candidate_required
def applications(request):
    application_list = JobApplication.objects.filter(candidate=request.user).select_related("job__company")
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
            notify(request.user, "Interview request sent", f"Your reschedule request for {interview.application.job.title} was sent to the recruiter.", "interview")
        else:
            notify(request.user, "Interview notes saved", f"Your notes for {interview.application.job.title} were saved.", "interview")
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
    course_submissions = {milestone.certification.title: milestone for milestone in milestones}
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
            submission = course_submissions.get(course["title"])
            course["certificate_id"] = submission.certificate_id if submission else ""
            course["pending_verification"] = bool(submission and submission.status == "pending_verification")
            course["submission"] = submission
        for milestone in goal["milestones"]:
            for course in milestone["courses"]:
                completed = completed_courses.get(course["title"])
                course["completed"] = bool(completed or course["title"] in legacy_completed_courses)
                submission = course_submissions.get(course["title"])
                course["certificate_id"] = submission.certificate_id if submission else ""
                course["pending_verification"] = bool(submission and submission.status == "pending_verification")
                course["submission"] = submission
        goal["pending_count"] = len({
            course["title"]
            for milestone in goal["milestones"]
            for course in milestone["courses"]
            if course.get("pending_verification")
        })
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
        if request.POST.get("action") == "unsubmit_course":
            milestone = get_object_or_404(
                CandidateMilestone,
                candidate=request.user,
                certification__title=request.POST.get("course_title", ""),
                status="pending_verification",
            )
            if milestone.evidence_file:
                milestone.evidence_file.delete(save=False)
            milestone.delete()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True, "message": "The verification submission was withdrawn."})
            notify(request.user, "Certificate submission withdrawn", "The verification submission was withdrawn. You can edit and submit it again.", "certificate")
            return redirect(request.get_full_path())

        if request.POST.get("action") == "complete_course":
            ajax_submission = request.headers.get("x-requested-with") == "XMLHttpRequest"

            def submission_error(message):
                if ajax_submission:
                    return JsonResponse({"ok": False, "message": message}, status=400)
                messages.error(request, message)
                return redirect(request.get_full_path())

            career_key = request.POST.get("career_key", "")
            course_title = request.POST.get("course_title", "")
            certificate_id = request.POST.get("certificate_id", "").strip()
            verification_url = request.POST.get("verification_url", "").strip()
            evidence_file = request.FILES.get("evidence_file")
            path = CAREER_PATHS.get(career_key)
            course = next(
                (item for item in (path or {}).get("courses", []) if item["title"] == course_title),
                None,
            )
            upload_error = _certificate_upload_error(evidence_file) if evidence_file else ""
            certificate_id_error = _certificate_id_error(certificate_id)
            if not course:
                return submission_error("That course milestone could not be found. Refresh the page and try again.")
            elif certificate_id_error:
                return submission_error(certificate_id_error)
            else:
                certification = _catalogue_certification(course, career_key)
                result = verify_certificate(certification, verification_url)
                if result.status == "rejected":
                    return submission_error(result.message)
                if result.status != "completed" and not evidence_file:
                    return submission_error("Automatic verification was unavailable. Upload certificate evidence for administrator review.")
                if upload_error:
                    return submission_error(upload_error)
                milestone, _ = CandidateMilestone.objects.get_or_create(
                    candidate=request.user,
                    certification=certification,
                )
                milestone.evidence_file = evidence_file
                milestone.certificate_id = certificate_id
                milestone.verification_url = verification_url
                milestone.verification_method = result.method
                milestone.verification_details = result.message
                milestone.status = result.status
                milestone.verified_at = timezone.now() if result.status == "completed" else None
                milestone.completed_at = milestone.verified_at
                milestone.notes = result.message
                update_fields = ["certificate_id", "verification_url", "verification_method", "verification_details", "verified_at", "status", "completed_at", "notes"]
                if evidence_file:
                    update_fields.append("evidence_file")
                milestone.save(update_fields=update_fields)
                if result.status == "completed":
                    add_verified_certificate_to_resume(request.user, milestone)

                response_message = (
                    f"{course_title} was verified automatically with {certification.provider}."
                    if result.status == "completed"
                    else f"{course_title} was submitted and is pending administrator verification."
                )
                notify(request.user, course_title, response_message, "certificate")
                if ajax_submission:
                    return JsonResponse({
                        "ok": True,
                        "status": result.status,
                        "status_label": milestone.get_status_display(),
                        "message": response_message,
                        "certificate_id": milestone.certificate_id,
                        "course_title": course_title,
                    })
                return redirect(f"{reverse('candidate_learning')}?direction={career_key}#verification-status")

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
            next_status = "pending_verification"
            notify(request.user, "Certificate submitted", "Certificate evidence was submitted for administrator verification.", "certificate")
        milestone.status = next_status
        milestone.completed_at = None
        update_fields = ["status", "completed_at"]
        if evidence_file:
            update_fields.append("evidence_file")
        milestone.save(update_fields=update_fields)
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
def verification_status(request):
    """Small polling endpoint used by the learning page after submission."""
    milestones = CandidateMilestone.objects.filter(candidate=request.user).select_related("certification")
    return JsonResponse({
        "certificates": [
            {
                "certification_id": milestone.certification_id,
                "title": milestone.certification.title,
                "status": milestone.status,
                "status_label": milestone.get_status_display(),
                "certificate_id": milestone.certificate_id,
                "details": milestone.verification_details,
            }
            for milestone in milestones
        ]
    })


@candidate_required
def saved_jobs(request):
    if request.method == "POST":
        job = get_object_or_404(Job, pk=request.POST.get("job_id"))
        saved, created = SavedJob.objects.get_or_create(candidate=request.user, job=job)
        if not created:
            saved.delete()
        return redirect("candidate_saved_jobs")
    saved = SavedJob.objects.filter(candidate=request.user).select_related("job__company")
    applied_ids = set(JobApplication.objects.filter(candidate=request.user).values_list("job_id", flat=True))
    return render(request, "candidates/jobs.html", _context(request, form=JobFilterForm(), job_cards=[{"job": item.job, "match": get_or_update_match(request.user, item.job), "is_saved": True, "has_applied": item.job_id in applied_ids} for item in saved], saved_page=True))


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
        "recent_jobs": Job.objects.filter(status="open").select_related("company").annotate(
            is_saved=Exists(SavedJob.objects.filter(candidate=request.user, job_id=OuterRef("pk"))),
            has_applied=Exists(JobApplication.objects.filter(candidate=request.user, job_id=OuterRef("pk"))),
        )[:3],
        "career_progress": career_progress(request.user, interests),
    }
