"""Explainable resume-to-job scoring for the MVP.

The score is deliberately deterministic so candidates and recruiters can see
why it changed. A TensorFlow model can replace the component calculators later
without changing the views or stored match shape.
"""

import re

from candidates.resume_parser import KNOWN_SKILLS, extract_resume_text

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


def _profile_data(candidate):
    profile = getattr(candidate, "profile", None)
    return (getattr(profile, "profile_data", {}) or {}) if profile else {}


def _resume_text(candidate):
    profile = getattr(candidate, "profile", None)
    resume = getattr(profile, "resume", None) if profile else None
    if not resume:
        return ""
    try:
        with resume.open("rb") as resume_file:
            return _normalise(extract_resume_text(resume_file))
    except (OSError, ValueError):
        return ""


def _coverage(profile_skills, skill_names, resume_text=""):
    normalised = {_normalise(skill): skill for skill in skill_names}
    matched_keys = {
        key
        for key in normalised
        if key in profile_skills
        or re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", resume_text)
    }
    return normalised, matched_keys


def _contains_skill(text, skill):
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(_normalise(skill))}(?![a-z0-9])",
            _normalise(text),
        )
    )


def _dedupe_skills(skills):
    """Keep the recruiter-provided spelling while removing duplicate skills."""
    result = []
    seen = set()
    for skill in skills:
        skill = str(skill or "").strip()
        key = _normalise(skill)
        if skill and key not in seen:
            result.append(skill)
            seen.add(key)
    return result


def _job_skill_sets(job):
    """Return explicit and job-description-derived skills for scoring.

    Recruiters should still fill in required/preferred skills. Description
    extraction is a safety net for MVP listings, not a replacement for clear
    recruiter input. When a listing has no explicit required skills, detected
    skills become required so the score is based on the actual job text.
    """
    explicit_required = _dedupe_skills(job.required_skill_list)
    explicit_preferred = _dedupe_skills(job.preferred_skill_list)
    job_text = " ".join(
        [
            job.title,
            job.description,
            job.required_skills,
            job.preferred_skills,
        ]
    )
    detected = [skill for skill in KNOWN_SKILLS if _contains_skill(job_text, skill)]

    if explicit_required:
        required = explicit_required
        preferred = _dedupe_skills(explicit_preferred + [
            skill
            for skill in detected
            if _normalise(skill) not in {
                _normalise(item) for item in required + explicit_preferred
            }
        ])
    else:
        required = _dedupe_skills(detected)
        preferred = explicit_preferred

    return required, preferred


def _experience_points(data, job):
    raw = " ".join(str(data.get(key, "")) for key in ("experience", "certifications", "education")).casefold()
    level = job.experience_level
    if level == "entry":
        return 10 if not raw or any(word in raw for word in ("intern", "student", "entry", "graduate")) else 8
    if level == "junior":
        return 10 if any(word in raw for word in ("junior", "intern", "1 year", "2 years", "associate")) else 5
    if level == "mid":
        return 10 if any(word in raw for word in ("mid", "3 years", "4 years", "5 years")) else 4
    return 10 if any(word in raw for word in ("senior", "lead", "manager", "6 years", "7 years", "8 years")) else 3


def _alignment_points(data, job):
    job_text = _normalise(" ".join((job.industry, job.title, job.description)))
    profile_terms = [data.get("career", ""), data.get("specialisation", "")]
    return 10 if any(_normalise(term).replace("-", " ") in job_text for term in profile_terms if term) else 0


def _evidence_points(candidate, data):
    evidence = [
        data.get("skills"),
        data.get("experience"),
        data.get("certifications"),
        data.get("portfolio"),
        _resume_text(candidate),
    ]
    return round(5 * sum(bool(item) for item in evidence) / len(evidence))


def _assessment(score):
    if score >= 80:
        return "Strong fit"
    if score >= 60:
        return "Good foundation"
    if score >= 40:
        return "Developing fit"
    return "Early-stage fit"


def calculate_match(candidate, job):
    data = _profile_data(candidate)
    candidate_skills = _profile_skills(candidate)
    resume_text = _resume_text(candidate)
    required_skills, preferred_skills = _job_skill_sets(job)

    # Do not imply a candidate is compatible when the recruiter has not
    # provided enough job information to compare against anything.
    if not required_skills and not preferred_skills:
        breakdown = {
            "required_skills": {"earned": 0, "max": 0},
            "preferred_skills": {"earned": 0, "max": 0},
            "job_data_quality": {"earned": 0, "max": 0},
        }
        return 0, [], [], breakdown, "Insufficient job data"

    required_normalised, required_matched = _coverage(candidate_skills, required_skills, resume_text)
    preferred_normalised, preferred_matched = _coverage(candidate_skills, preferred_skills, resume_text)
    required_points = round(60 * len(required_matched) / len(required_normalised)) if required_normalised else 0
    # Preferred skills are optional. If the recruiter leaves that field blank,
    # do not penalise the candidate for an omitted optional criterion.
    preferred_points = round(15 * len(preferred_matched) / len(preferred_normalised)) if preferred_normalised else 15
    alignment_points = _alignment_points(data, job)
    experience_points = _experience_points(data, job)
    evidence_points = _evidence_points(candidate, data)
    breakdown = {
        "required_skills": {"earned": required_points, "max": 60},
        "preferred_skills": {"earned": preferred_points, "max": 15},
        "career_alignment": {"earned": alignment_points, "max": 10},
        "experience_level": {"earned": experience_points, "max": 10},
        "profile_evidence": {"earned": evidence_points, "max": 5},
    }
    score = sum(component["earned"] for component in breakdown.values())
    matched = sorted(required_normalised[key] for key in required_matched)
    matched.extend(sorted(preferred_normalised[key] for key in preferred_matched if key not in required_matched))
    missing = sorted(required_normalised[key] for key in set(required_normalised).difference(required_matched))
    return score, matched, missing, breakdown, _assessment(score)


def get_or_update_match(candidate, job):
    score, matched, missing, breakdown, assessment = calculate_match(candidate, job)
    match, _ = JobMatch.objects.update_or_create(
        candidate=candidate,
        job=job,
        defaults={
            "score": score,
            "matched_skills": matched,
            "missing_skills": missing,
            "score_breakdown": breakdown,
            "assessment": assessment,
        },
    )
    return match


def recommend_certifications_for_gap(certifications, missing_skills):
    """Return recognised certifications that cover the missing job skills."""
    recommendations = []
    for certification in certifications:
        certification_text = _normalise(certification.skills or "")
        bridges = [
            skill
            for skill in missing_skills
            if re.search(
                rf"(?<![a-z0-9]){re.escape(_normalise(skill))}(?![a-z0-9])",
                certification_text,
            )
        ]
        if bridges:
            recommendations.append({
                "certification": certification,
                "bridges": bridges,
            })
    return sorted(
        recommendations,
        key=lambda item: (-len(item["bridges"]), item["certification"].cost, item["certification"].title),
    )
