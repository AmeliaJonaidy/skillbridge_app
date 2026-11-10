"""Writing suggestions and literal job coverage; never claims to verify experience."""
import re

from .services import _contains, _job_description_points, _job_skills
from .content import clean_resume_content


SECTIONS = {
    "TARGET ROLE", "TARGET DIRECTION", "PROFESSIONAL SUMMARY", "SUMMARY",
    "PROFESSIONAL PROFILE", "CORE SKILLS", "SKILLS", "EDUCATION", "EXPERIENCE",
    "WORK EXPERIENCE", "PROJECTS", "PROJECTS & PORTFOLIO", "CERTIFICATIONS",
    "AWARDS & ACHIEVEMENTS", "WORK AUTHORISATION", "EMPLOYER DETAILS USED",
    "JOB DESCRIPTION PRIORITIES",
}
ADVISORY_SECTIONS = {"TARGET ROLE", "TARGET DIRECTION", "EMPLOYER DETAILS USED", "JOB DESCRIPTION PRIORITIES"}
WORK_SECTIONS = {"EXPERIENCE", "WORK EXPERIENCE", "PROJECTS", "PROJECTS & PORTFOLIO"}
SUMMARY_SECTIONS = {"PROFESSIONAL SUMMARY", "SUMMARY", "PROFESSIONAL PROFILE"}


def without_legacy_notes(content):
    # Compatibility name for existing callers; cleanup covers all reference sections.
    return clean_resume_content(content)


def review_draft(content, job=None):
    section = ""
    lines = []
    evidence = []
    for number, text in enumerate(without_legacy_notes(content).splitlines(), start=1):
        stripped = text.strip()
        heading = stripped.upper().rstrip(":")
        is_heading = heading in SECTIONS
        if is_heading:
            section = heading
        suggestions = []
        if stripped and not is_heading:
            if section in SUMMARY_SECTIONS and re.search(
                r"candidate (?:targeting|preparing)|motivated|hard.?working|team player|results.?driven|review every statement",
                stripped, re.I,
            ):
                suggestions.append("Replace generic or instructional wording with your relevant experience, strengths, and one concrete example for this role.")
            is_work_statement = section in WORK_SECTIONS and (
                stripped.startswith(("-", "•", "*")) or len(stripped.split()) >= 6
            ) and not re.fullmatch(r"[\d\s/–—-]+", stripped)
            if is_work_statement:
                if len(stripped.split()) < 8 or re.search(r"\b(responsible for|helped|assisted|worked on|various tasks|duties included)\b", stripped, re.I):
                    suggestions.append("Describe your own action, the task or tool, and the result instead of a broad responsibility.")
                if not re.search(r"\d[\d,.]*\s*(?:%|percent\b|users\b|clients\b|customers\b|hours\b|minutes\b|seconds\b|records\b|reports\b|projects\b)|[$£€]\s*\d", stripped, re.I):
                    suggestions.append("Add a measurable outcome if one is meaningful and known, such as time saved, records processed, or people served. Do not invent numbers.")
            if section not in ADVISORY_SECTIONS:
                evidence.append(stripped)
        if is_heading and section in {"EMPLOYER DETAILS USED", "JOB DESCRIPTION PRIORITIES"}:
            suggestions.append("This is reference information from the job listing. Remove this section from the resume you submit; use it to guide your own examples.")
        lines.append({"number": number, "text": text, "heading": is_heading, "suggestions": suggestions})

    source = "\n".join(evidence)
    skills = _job_skills(job) if job else []
    missing = [skill for skill in skills if not _contains(source, skill)]
    mentioned = [skill for skill in skills if _contains(source, skill)]
    # Show recruiter text as context, rather than claiming semantic coverage from keyword counts.
    priorities = _job_description_points(job, skills) if job else []
    return {
        "lines": lines,
        "issue_count": sum(bool(line["suggestions"]) for line in lines),
        "missing_skills": missing,
        "mentioned_skills": mentioned,
        "priorities": priorities,
        "has_job": bool(job),
        "has_skill_requirements": bool(skills),
    }
