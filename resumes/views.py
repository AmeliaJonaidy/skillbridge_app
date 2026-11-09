from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import candidate_required

from .models import TailoredResume


@candidate_required
def detail(request, resume_id):
    tailored_resume = get_object_or_404(
        TailoredResume.objects.select_related("job__company"),
        pk=resume_id,
        candidate=request.user,
    )
    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if not content:
            messages.error(request, "Your resume cannot be empty.")
        else:
            tailored_resume.content = content
            tailored_resume.save(update_fields=["content", "updated_at"])
            messages.success(request, "Your resume changes were saved.")
            return redirect("resume_detail", resume_id=tailored_resume.id)
    return render(
        request,
        "resumes/detail.html",
        {"role": "candidate", "tailored_resume": tailored_resume},
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
