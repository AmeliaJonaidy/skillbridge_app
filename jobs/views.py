from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import candidate_required
from applications.forms import ApplicationForm
from applications.models import JobApplication, SavedJob
from matching.services import get_or_update_match
from resumes.models import TailoredResume
from resumes.services import build_tailored_resume

from .models import Job


@candidate_required
def detail(request, job_id):
    job = get_object_or_404(Job.objects.select_related("company"), pk=job_id)
    application = JobApplication.objects.filter(candidate=request.user, job=job).first()
    is_saved = SavedJob.objects.filter(candidate=request.user, job=job).exists()
    match = get_or_update_match(request.user, job)
    form = ApplicationForm(request.POST or None)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            SavedJob.objects.get_or_create(candidate=request.user, job=job)
            messages.success(request, "Job saved to your shortlist.")
            return redirect("job_detail", job_id=job.id)
        if action == "unsave":
            SavedJob.objects.filter(candidate=request.user, job=job).delete()
            messages.success(request, "Job removed from your shortlist.")
            return redirect("job_detail", job_id=job.id)
        if action == "tailor":
            draft = TailoredResume.objects.create(
                candidate=request.user,
                job=job,
                title=f"Resume for {job.title}",
                content=build_tailored_resume(request.user, job),
            )
            return redirect("resume_detail", resume_id=draft.id)
        if action == "apply" and not application:
            if form.is_valid():
                application = form.save(commit=False)
                application.candidate = request.user
                application.job = job
                application.match_score = match.score
                application.matched_skills = match.matched_skills
                application.missing_skills = match.missing_skills
                application.save()
                messages.success(request, "Your application has been submitted.")
                return redirect("candidate_applications")

    return render(
        request,
        "jobs/detail.html",
        {
            "role": "candidate",
            "job": job,
            "application": application,
            "is_saved": is_saved,
            "match": match,
            "form": form,
        },
    )
