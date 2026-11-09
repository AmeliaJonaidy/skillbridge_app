from django.contrib import messages
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import candidate_required

from .models import TailoredResume
from .forms import TailoredResumeForm


@candidate_required
def detail(request, resume_id):
    tailored_resume = get_object_or_404(
        TailoredResume.objects.select_related("job__company"),
        pk=resume_id,
        candidate=request.user,
    )
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
    )
