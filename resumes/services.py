import re

from accounts.models import UserProfile
from candidates.resume_parser import KNOWN_SKILLS, extract_resume_text
from matching.services import get_or_update_match


def _normalise(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _clean_lines(value):
    return [
        re.sub(r"^[•\-*\s]+", "", line).strip()
        for line in str(value or "").splitlines()
        if line.strip()
    ]


def _dedupe(values):
    result = []
    seen = set()
    for value in values:
        value = str(value or "").strip()
        key = _normalise(value)
        if value and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def _contains(text, term):
    text = _normalise(text)
    term = _normalise(term)
    if not text or not term:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))


def _uploaded_resume_text(profile):
    if not profile or not profile.resume:
        return ""
    try:
        with profile.resume.open("rb") as resume_file:
            return extract_resume_text(resume_file)
    except (OSError, ValueError):
        return ""


def _job_skills(job):
    """Combine recruiter-entered skills with skills found in the full job description."""
    job_text = " ".join(
        [
            job.title,
            job.description,
            job.required_skills,
            job.preferred_skills,
        ]
    )
    skills = list(job.required_skill_list) + list(job.preferred_skill_list)
    skills.extend(skill for skill in KNOWN_SKILLS if _contains(job_text, skill))
    return _dedupe(skills)


def _candidate_skills(data, resume_text):
    profile_skills = re.split(r"[,;|\n]", str(data.get("skills", "")))
    detected_skills = [skill for skill in KNOWN_SKILLS if _contains(resume_text, skill)]
    return _dedupe(profile_skills + detected_skills)


def _relevant_evidence(data, resume_text, job_skills):
    source_lines = []
    source_lines.extend(_clean_lines(data.get("experience", "")))
    source_lines.extend(_clean_lines(data.get("portfolio", "")))
    source_lines.extend(_clean_lines(data.get("awards", "")))
    source_lines.extend(_clean_lines(resume_text))
    source_lines = _dedupe(source_lines)
    if not source_lines:
        return []
    if not job_skills:
        return source_lines[:10]
    relevant = [
        line for line in source_lines
        if any(_contains(line, skill) for skill in job_skills)
    ]
    return relevant[:10] or source_lines[:10]


def _job_description_points(job, job_skills):
    description = str(job.description or "").strip()
    if not description:
        return []
    chunks = [
        chunk.strip(" •-*\t")
        for chunk in re.split(r"\n+|(?<=[.!?])\s+", description)
        if chunk.strip()
    ]
    relevant = [
        chunk for chunk in chunks
        if any(_contains(chunk, skill) for skill in job_skills)
    ]
    return _dedupe(relevant or chunks)[:5]


def _section(title, content):
    content = str(content or "").strip()
    return f"{title}\n{content}" if content else ""


def build_tailored_resume(candidate, job):
    """Build a truthful, job-aware resume draft from both sides of the marketplace.

    Recruiter input comes from the job title, company, description, required and
    preferred skills. Candidate input comes from profile fields and the uploaded
    resume. Missing skills are shown as review notes, never claimed as experience.
    """
    profile = UserProfile.objects.filter(user=candidate).first()
    data = (profile.profile_data if profile else {}) or {}
    resume_text = _uploaded_resume_text(profile)
    match = get_or_update_match(candidate, job)
    job_skills = _job_skills(job)
    candidate_source = " ".join(
        [
            resume_text,
            *(str(data.get(key, "")) for key in (
                "skills", "experience", "certifications", "portfolio", "awards",
                "career", "specialisation", "education",
            )),
        ]
    )
    candidate_skills = _candidate_skills(data, resume_text)
    verified_job_skills = _dedupe(
        [skill for skill in job_skills if _contains(candidate_source, skill)]
    )
    unverified_job_skills = _dedupe(
        [skill for skill in job_skills if not _contains(candidate_source, skill)]
    )
    relevant_evidence = _relevant_evidence(data, resume_text, job_skills)
    description_points = _job_description_points(job, job_skills)
    focus, focus_terms = _role_focus(job)
    focus_evidence = _cover_letter_evidence(data, resume_text, job_skills, focus_terms)
    prioritised_evidence = _dedupe(focus_evidence + relevant_evidence)

    name = data.get("name") or candidate.get_full_name() or candidate.username
    contact = _dedupe([
        data.get("email") or candidate.email,
        data.get("phone"),
        data.get("linkedin"),
    ])
    summary_parts = [
        f"Candidate targeting the {job.title} role at {job.company.name}.",
    ]
    if data.get("career") or data.get("specialisation"):
        summary_parts.append(
            "Background: " + ", ".join(
                value for value in (data.get("career"), data.get("specialisation")) if value
            ) + "."
        )
    if verified_job_skills:
        summary_parts.append(
            "Relevant evidence currently includes " + ", ".join(verified_job_skills) + "."
        )
    summary_parts.append(
        "Review every statement against the original resume before submitting."
    )

    all_skills = _dedupe(verified_job_skills + candidate_skills)
    employer_details = "\n".join(
        line for line in [
            f"Company: {job.company.name}",
            f"Industry: {job.get_industry_display() if job.industry else 'Not specified'}",
            f"Location: {job.location or 'Not specified'}",
            f"Employment type: {job.get_employment_type_display()}",
        ]
        if line
    )
    alignment_notes = [
        "Compatibility score: " + str(match.score) + "% (used for guidance, not a hiring decision).",
        "Verified matches: " + (", ".join(verified_job_skills) or "None found yet."),
        "Skills to verify before adding: " + (", ".join(unverified_job_skills) or "None."),
        "Evidence foregrounded for this role: " + focus + ".",
    ]

    experience_lines = _dedupe(_clean_lines(data.get("experience")) + prioritised_evidence)
    project_lines = _dedupe(_clean_lines(data.get("portfolio")) + focus_evidence)

    sections = [
        name,
        " | ".join(contact),
        _section("TARGET ROLE", f"{job.title} at {job.company.name}"),
        _section("PROFESSIONAL SUMMARY", " ".join(summary_parts)),
        _section("CORE SKILLS", ", ".join(all_skills)),
        _section("EDUCATION", "\n".join(_dedupe([data.get("education"), data.get("institution")])),),
        _section("EXPERIENCE", "\n".join(experience_lines)),
        _section("PROJECTS & PORTFOLIO", "\n".join(project_lines)),
        _section("CERTIFICATIONS", data.get("certifications")),
        _section("AWARDS & ACHIEVEMENTS", data.get("awards")),
        _section("WORK AUTHORISATION", data.get("visa")),
        _section("EMPLOYER DETAILS USED", employer_details),
        _section("JOB DESCRIPTION PRIORITIES", "\n".join(f"- {point}" for point in description_points)),
        _section("TAILORING NOTES — REVIEW BEFORE SUBMITTING", "\n".join(f"- {note}" for note in alignment_notes)),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def _role_focus(job):
    """Choose which evidence to foreground without inventing experience."""
    job_text = _normalise(" ".join((job.title, job.description, job.required_skills, job.preferred_skills)))
    business_terms = (
        "business", "marketing", "finance", "operations", "strategy", "sales",
        "stakeholder", "requirements", "consulting", "product", "analyst",
        "management", "economics", "accounting",
    )
    technical_terms = (
        "software", "engineer", "developer", "backend", "back-end", "frontend",
        "front-end", "data", "machine learning", "cloud", "devops", "python",
        "sql", "api", "technical", "cybersecurity", "database",
    )
    business_score = sum(_contains(job_text, term) for term in business_terms)
    technical_score = sum(_contains(job_text, term) for term in technical_terms)
    if business_score > technical_score:
        return "business", business_terms
    if technical_score > business_score:
        return "technical", technical_terms
    return "role-relevant", ()


def _cover_letter_evidence(data, resume_text, job_skills, focus_terms):
    """Return short, profile-backed evidence suitable for a cover letter."""
    labelled_lines = []
    for label, value in (
        ("project", data.get("portfolio", "")),
        ("experience", data.get("experience", "")),
        ("achievement", data.get("awards", "")),
        ("resume", resume_text),
    ):
        labelled_lines.extend((label, line) for line in _clean_lines(value))

    relevant = [
        (label, line)
        for label, line in labelled_lines
        if any(_contains(line, skill) for skill in job_skills)
    ]
    focused = [
        item
        for item in labelled_lines
        if any(_contains(item[1], term) for term in focus_terms)
    ]
    return _dedupe([line for _, line in focused + relevant])[:3]


def build_tailored_cover_letter(candidate, job):
    """Create an editable, job-specific cover letter from truthful evidence."""
    profile = UserProfile.objects.filter(user=candidate).first()
    data = (profile.profile_data if profile else {}) or {}
    resume_text = _uploaded_resume_text(profile)
    job_skills = _job_skills(job)
    match = get_or_update_match(candidate, job)
    focus, focus_terms = _role_focus(job)
    evidence = _cover_letter_evidence(data, resume_text, job_skills, focus_terms)
    display_name = data.get("name") or candidate.get_full_name() or candidate.username
    matched_skills = _dedupe(match.matched_skills)[:5]
    priorities = _job_description_points(job, job_skills)[:2]

    paragraphs = [
        f"Dear Hiring Team,\n\nI am writing to apply for the {job.title} position at {job.company.name}."
    ]
    background = ", ".join(
        value for value in (data.get("career"), data.get("specialisation")) if value
    )
    if background:
        paragraphs.append(f"My background in {background} gives me a relevant foundation for this role.")
    if priorities:
        paragraphs.append("The role particularly emphasises " + "; ".join(priorities) + ".")
    if evidence:
        focus_label = {
            "business": "business-facing projects and experience",
            "technical": "technical projects and experience",
            "role-relevant": "role-relevant projects and experience",
        }[focus]
        paragraphs.append(
            f"I would highlight my {focus_label}:\n"
            + "\n".join(f"- {line}" for line in evidence)
        )
    if matched_skills:
        paragraphs.append(
            "The skills from my current profile that align most closely with this position include "
            + ", ".join(matched_skills) + "."
        )
    paragraphs.append(
        "I would welcome the opportunity to discuss how my background can contribute to your team. "
        "Thank you for considering my application."
    )
    paragraphs.append(f"Kind regards,\n{display_name}")
    return "\n\n".join(paragraphs)
