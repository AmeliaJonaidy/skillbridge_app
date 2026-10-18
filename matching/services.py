"""Small deterministic matching service for the first backend milestone.

The service deliberately has no external AI dependency. A TensorFlow model can
replace this calculation later without changing the JobMatch model or views.
"""

import re

from .models import JobMatch


def _normalise(value):
    return re.sub(r"\s+", " ", value.strip().casefold())


def _profile_skills(candidate):
    profile = getattr(candidate, "profile", None)
    data = getattr(profile, "profile_data", {}) or {}
    raw = data.get("skills", "")
    return {
        _normalise(skill)
        for skill in re.split(r"[,\n;|]", raw)
        if skill.strip()
    }


def calculate_match(candidate, job):
    candidate_skills = _profile_skills(candidate)
    required = job.required_skill_list
    required_normalised = {_normalise(skill): skill for skill in required}
    matched_keys = set(required_normalised).intersection(candidate_skills)
    missing_keys = set(required_normalised).difference(candidate_skills)
    score = round(len(matched_keys) / len(required_normalised) * 100) if required_normalised else 0

    matched = sorted(required_normalised[key] for key in matched_keys)
    missing = sorted(required_normalised[key] for key in missing_keys)
    return score, matched, missing


def get_or_update_match(candidate, job):
    score, matched, missing = calculate_match(candidate, job)
    match, _ = JobMatch.objects.update_or_create(
        candidate=candidate,
        job=job,
        defaults={
            "score": score,
            "matched_skills": matched,
            "missing_skills": missing,
        },
    )
    return match
