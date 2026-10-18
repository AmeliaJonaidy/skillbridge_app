from django.shortcuts import get_object_or_404, render

from accounts.decorators import candidate_required

from .models import TailoredResume


@candidate_required
def detail(request, resume_id):
    tailored_resume = get_object_or_404(
        TailoredResume.objects.select_related("job__company"),
        pk=resume_id,
        candidate=request.user,
    )
    return render(
        request,
        "resumes/detail.html",
        {"role": "candidate", "tailored_resume": tailored_resume},
    )
