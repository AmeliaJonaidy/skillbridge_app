from django.contrib import messages
<<<<<<< HEAD
from django.db import transaction
=======
from django.utils import timezone
>>>>>>> origin/model
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import candidate_required

from .models import TailoredResume
<<<<<<< HEAD
from .review import review_draft, without_legacy_notes
=======
from .forms import TailoredResumeForm
>>>>>>> origin/model


@candidate_required
def detail(request, resume_id):
    tailored_resume = get_object_or_404(
        TailoredResume.objects.select_related("job__company"),
        pk=resume_id,
        candidate=request.user,
    )
<<<<<<< HEAD
    if request.method == "POST":
        content = without_legacy_notes(request.POST.get("content", "").strip())
        if not content:
            messages.error(request, "Your resume cannot be empty.")
        else:
            tailored_resume.content = without_legacy_notes(content)
            tailored_resume.save(update_fields=["content", "updated_at"])
            messages.success(request, "Your resume changes were saved.")
            return redirect("resume_detail", resume_id=tailored_resume.id)
    return render(
        request,
        "resumes/detail.html",
        {"role": "candidate", "tailored_resume": tailored_resume,
         "editor_content": without_legacy_notes(tailored_resume.content),
         "review": review_draft(tailored_resume.content, tailored_resume.job)},
=======
    form = TailoredResumeForm(request.POST or None, instance=tailored_resume)
    if request.method == "POST" and form.is_valid():
        form.save()
        if request.POST.get("action") == "approve":
            tailored_resume.approved_at = timezone.now()
            tailored_resume.save(update_fields=["approved_at", "updated_at"])
            messages.success(request, "Your tailored resume was approved for submission.")
        else:
            tailored_resume.approved_at = None
            tailored_resume.save(update_fields=["approved_at", "updated_at"])
            messages.success(request, "Your tailored resume draft was saved. Review it before applying.")
        return redirect("resume_detail", resume_id=tailored_resume.id)
    return render(
        request,
        "resumes/detail.html",
        {"role": "candidate", "tailored_resume": tailored_resume, "form": form},
>>>>>>> origin/model
    )


@candidate_required
def set_main(request, resume_id):
    if request.method != "POST":
        return redirect("resume_detail", resume_id=resume_id)
    tailored_resume = get_object_or_404(
        TailoredResume,
        pk=resume_id,
        candidate=request.user,
    )
    with transaction.atomic():
        TailoredResume.objects.filter(candidate=request.user, is_main=True).update(is_main=False)
        tailored_resume.is_main = True
        tailored_resume.save(update_fields=["is_main", "updated_at"])
    messages.success(request, "This tailored resume is now your main resume.")
    return redirect("candidate_resume")
