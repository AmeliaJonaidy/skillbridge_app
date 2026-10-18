from .models import CandidateProfile


PROFILE_FIELD_MAP = {
    "career": "career_area",
    "specialisation": "specialisation",
    "education": "education_level",
    "institution": "institution",
    "certifications": "certifications",
    "linkedin": "linkedin_url",
    "experience": "work_experience",
    "portfolio": "portfolio_links",
    "awards": "awards",
    "skills": "technical_skills",
    "visa": "visa_status",
    "phone": "phone_number",
}


def sync_candidate_profile(user, data):
    candidate_profile, _ = CandidateProfile.objects.get_or_create(user=user)
    for data_key, model_field in PROFILE_FIELD_MAP.items():
        if data_key in data:
            setattr(candidate_profile, model_field, data.get(data_key, ""))
    tracked_fields = ["name", *PROFILE_FIELD_MAP.keys()]
    completed = sum(bool(data.get(field)) for field in tracked_fields)
    candidate_profile.profile_complete_percent = round(completed / len(tracked_fields) * 100)
    candidate_profile.save()
    return candidate_profile
