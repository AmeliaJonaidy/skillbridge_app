from .models import CandidateProfile
from .resume_parser import autofill_profile_data, extract_resume_text


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
    tracked_fields = ["resume", "name", *PROFILE_FIELD_MAP.keys()]
    completed = sum(bool(data.get(field)) for field in tracked_fields)
    candidate_profile.profile_complete_percent = round(completed / len(tracked_fields) * 100)
    candidate_profile.save()
    return candidate_profile


def autofill_from_resume(resume_file, existing_data):
    text = extract_resume_text(resume_file)
    if not text:
        return {}, ""
    return autofill_profile_data(text, existing_data), text
