from accounts.models import UserProfile


def build_tailored_resume(candidate, job):
    """Create a simple editable resume draft from stored profile data."""
    profile = UserProfile.objects.filter(user=candidate).first()
    data = (profile.profile_data if profile else {}) or {}
    name = data.get("name", candidate.get_full_name() or candidate.username)
    skills = data.get("skills", "")
    experience = data.get("experience", "")
    certifications = data.get("certifications", "")

    return "\n".join(
        part
        for part in [
            name,
            f"Target role: {job.title}",
            "",
            "PROFILE",
            f"Interested in {data.get('career', 'this role')} with a focus on {data.get('specialisation', 'relevant skills')}.",
            "",
            "SKILLS",
            skills,
            "",
            "EXPERIENCE",
            experience,
            "",
            "CERTIFICATIONS",
            certifications,
        ]
        if part is not None
    )
