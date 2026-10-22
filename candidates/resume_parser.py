import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


KNOWN_SKILLS = [
    "Python", "Django", "Java", "JavaScript", "TypeScript", "React", "SQL", "PostgreSQL",
    "Git", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "TensorFlow", "PyTorch",
    "Tableau", "Excel", "Figma", "HTML", "CSS", "C++", "C#", "Go", "Rust",
]

RESUME_SECTIONS = {
    "experience": ("experience", "work experience", "employment"),
    "education": ("education", "academic background"),
    "skills": ("skills", "technical skills", "technology stack"),
    "projects": ("projects", "project experience"),
    "certifications": ("certifications", "certificates", "professional certifications"),
    "awards": ("awards", "achievements", "honours", "honors"),
}


def extract_resume_text(source):
    """Extract text from PDF/DOCX/plain text without making parsing mandatory."""
    if not source:
        return ""
    original_position = source.tell() if hasattr(source, "tell") else None
    try:
        if hasattr(source, "seek"):
            source.seek(0)
        raw = source.read()
        name = Path(getattr(source, "name", "")).suffix.lower()
    finally:
        if original_position is not None and hasattr(source, "seek"):
            source.seek(original_position)

    if name == ".pdf":
        try:
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages).strip()
        except Exception:
            return ""
    if name == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            return "\n".join(
                "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
                for paragraph in document.findall(".//w:p", namespace)
            ).strip()
        except Exception:
            return ""
    return raw.decode("utf-8", errors="ignore").strip()


def _section(text, headings):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headings = {heading.casefold() for heading in headings}
    capture = False
    collected = []
    for line in lines:
        normalised = line.casefold().rstrip(":")
        if normalised in headings:
            capture = True
            continue
        if capture and normalised in {
            "experience", "work experience", "education", "skills", "technical skills",
            "certifications", "certificates", "projects", "awards", "achievements",
        }:
            break
        if capture:
            collected.append(line)
    return "\n".join(collected)


def autofill_profile_data(text, existing=None):
    """Return only fields that can be confidently inferred and are still blank."""
    existing = existing or {}
    lower = text.casefold()
    updates = {}
    skills = [skill for skill in KNOWN_SKILLS if re.search(rf"(?<![a-z0-9]){re.escape(skill.casefold())}(?![a-z0-9])", lower)]
    if skills and not existing.get("skills"):
        updates["skills"] = ", ".join(skills)

    linkedin = re.search(r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_%-]+/?", text, flags=re.I)
    if linkedin and not existing.get("linkedin"):
        updates["linkedin"] = linkedin.group(0)
    portfolio = re.search(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|[A-Za-z0-9.-]+\.(?:dev|io))/[^\s,)]+", text, flags=re.I)
    if portfolio and not existing.get("portfolio"):
        updates["portfolio"] = portfolio.group(0).rstrip(".")

    experience = _section(text, {"experience", "work experience", "employment"})
    if experience and not existing.get("experience"):
        updates["experience"] = experience[:4000]
    certifications = _section(text, {"certifications", "certificates", "professional certifications"})
    if certifications and not existing.get("certifications"):
        updates["certifications"] = certifications[:2000]

    if not existing.get("career"):
        career_keywords = {
            "technology": ("technology", "software", "developer", "engineering", "cloud", "data", "backend", "frontend", "devops"),
            "finance": ("finance", "banking", "investment", "accounting"),
            "business": ("business", "operations", "strategy", "management"),
            "design": ("design", "ux", "ui", "creative"),
        }
        for career, keywords in career_keywords.items():
            if any(keyword in lower for keyword in keywords):
                updates["career"] = career
                break

    if not existing.get("specialisation"):
        specialisations = [
            ("backend", ("backend", "back-end", "server-side")),
            ("frontend", ("frontend", "front-end", "react")),
            ("fintech", ("fintech", "financial technology")),
            ("cloud-devops", ("devops", "kubernetes", "cloud")),
            ("ai-ml", ("machine learning", "tensorflow", "pytorch", "artificial intelligence")),
            ("data-analytics", ("data analyst", "analytics", "tableau")),
            ("cybersecurity", ("cybersecurity", "security analyst")),
        ]
        for specialisation, keywords in specialisations:
            if any(keyword in lower for keyword in keywords):
                updates["specialisation"] = specialisation
                break

    education = {
        "postgraduate": ("master's", "masters", "phd", "doctorate", "mba"),
        "undergraduate": ("bachelor", "bsc", "ba degree", "undergraduate"),
        "diploma": ("diploma",),
        "professional": ("professional qualification",),
        "bootcamp": ("bootcamp", "boot camp"),
    }
    if not existing.get("education"):
        for education_level, keywords in education.items():
            if any(keyword in lower for keyword in keywords):
                updates["education"] = education_level
                break

    return updates


def review_resume(text):
    """Return transparent, non-generative feedback for an uploaded resume."""
    text = (text or "").strip()
    lower = text.casefold()
    lines = {line.strip().casefold().rstrip(":") for line in text.splitlines() if line.strip()}
    present_sections = [
        section
        for section, aliases in RESUME_SECTIONS.items()
        if any(alias in lines for alias in aliases)
    ]
    missing_sections = [section for section in RESUME_SECTIONS if section not in present_sections]
    detected_skills = [
        skill
        for skill in KNOWN_SKILLS
        if re.search(rf"(?<![a-z0-9]){re.escape(skill.casefold())}(?![a-z0-9])", lower)
    ]
    word_count = len(re.findall(r"\b[\w'-]+\b", text))
    has_metrics = bool(re.search(r"\b\d+(?:\.\d+)?\s?(?:%|percent|users|clients|projects|months|years|ms|s)\b", lower))
    has_contact_link = bool(re.search(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", lower)) or "linkedin.com" in lower
    suggestions = []
    if missing_sections:
        suggestions.append("Consider adding: " + ", ".join(section.title() for section in missing_sections[:3]) + ".")
    if not has_metrics:
        suggestions.append("Add measurable outcomes to experience or project bullets, such as percentages, users, revenue, or time saved.")
    if not has_contact_link:
        suggestions.append("Add a professional email address or LinkedIn link so recruiters can contact you.")
    if word_count < 120:
        suggestions.append("Add more evidence of your work, especially projects, responsibilities, and outcomes.")
    elif word_count > 900:
        suggestions.append("Consider shortening the resume and prioritising the most relevant recent experience.")
    if not detected_skills:
        suggestions.append("List your technical skills and tools using the exact names used in the jobs you want.")
    return {
        "word_count": word_count,
        "detected_skills": detected_skills,
        "present_sections": present_sections,
        "missing_sections": missing_sections,
        "suggestions": suggestions,
        "has_metrics": has_metrics,
        "has_contact_link": has_contact_link,
    }
