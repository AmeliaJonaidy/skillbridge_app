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
    "experience": ("experience", "work experience", "professional experience", "employment", "employment history", "work history", "career history"),
    "education": ("education", "academic background", "academic qualifications", "qualifications"),
    "skills": ("skills", "technical skills", "technology stack", "core competencies", "competencies", "key skills"),
    "projects": ("projects", "project experience"),
    "certifications": ("certifications", "certificates", "professional certifications"),
    "awards": ("awards", "achievements", "honours", "honors"),
}


def assess_resume_suitability(text):
    """Check that extracted content resembles a resume before it is accepted."""
    text = (text or "").strip()
    if not text:
        return False, "We could not read any text from this file. Upload a text-based PDF, DOCX, or TXT resume."

    lower = text.casefold()
    word_count = len(re.findall(r"\b[\w'+-]+\b", text))
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = {line.casefold().rstrip(":") for line in raw_lines}
    present_sections = set()
    for section, aliases in RESUME_SECTIONS.items():
        if any(alias in lines for alias in aliases) or any(
            re.search(rf"(?:^|[\n|])\s*{re.escape(alias)}\s*:?\s*(?:$|[\n|])", text, flags=re.I)
            for alias in aliases
        ):
            present_sections.add(section)
    email_signal = bool(re.search(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", lower))
    linkedin_signal = "linkedin.com/in/" in lower
    phone_signal = bool(re.search(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)", text))
    contact_signal = email_signal or linkedin_signal or phone_signal
    date_signal = bool(re.search(r"\b(?:19|20)\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", lower))
    role_signal = any(term in lower for term in (
        "university", "polytechnic", "diploma", "bachelor", "master", "intern", "manager",
        "engineer", "developer", "analyst", "consultant", "executive", "assistant", "coordinator",
    ))
    editorial_markers = sum(bool(re.search(pattern, lower, flags=re.M)) for pattern in (
        r"^\s*by\s+[a-z]", r"\bpublished\s+(?:on\s+)?(?:19|20)\d{2}\b", r"\babstract\b",
        r"\bintroduction\b", r"\bconclusion\b", r"\breferences\b", r"\bthis article\b",
    ))
    has_core_sections = (
        "experience" in present_sections and bool({"education", "skills", "projects"} & present_sections)
    ) or {"education", "skills"}.issubset(present_sections)

    is_resume = all((
        25 <= word_count <= 1500,
        contact_signal,
        len(present_sections) >= 2,
        has_core_sections,
        role_signal,
        date_signal,
        editorial_markers < 2,
    ))
    if not is_resume:
        missing = []
        if not contact_signal:
            missing.append("contact details")
        if len(present_sections) < 2 or not has_core_sections:
            missing.append("recognisable resume sections")
        if not role_signal or not date_signal:
            missing.append("dated education or work history")
        if editorial_markers >= 2:
            missing.append("content that reads like an article rather than a resume")
        detail = ", ".join(missing) or "enough structured resume information"
        return False, f"This document does not pass the resume structure check because we could not confirm {detail}. Check the file or complete the guided resume instead."
    return True, ""


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


def _resume_month(value):
    """Convert common resume year/month text to the HTML month input format."""
    match = re.search(r"\b((?:19|20)\d{2})(?:[-/](0?[1-9]|1[0-2]))?\b", value or "")
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2) or 1):02d}"


def _experience_entries(experience_text, detected_skills):
    """Create an editable guided entry from extracted experience text."""
    lines = [line.strip() for line in experience_text.splitlines() if line.strip()]
    if not lines:
        return []
    heading = lines[0]
    position = heading
    company = ""
    for separator in (" — ", " – ", " | ", " at ", " @ "):
        if separator in heading:
            position, company = (part.strip() for part in heading.split(separator, 1))
            break
    if not company and "," in heading and not re.search(r"\b(?:19|20)\d{2}\b", heading):
        position, company = (part.strip() for part in heading.split(",", 1))

    date_source = " ".join(lines[:3])
    dates = re.findall(r"\b(?:19|20)\d{2}(?:[-/](?:0?[1-9]|1[0-2]))?\b", date_source)
    current = bool(re.search(r"\b(?:present|current|now)\b", date_source, flags=re.I))
    detail_lines = lines[1:]
    if detail_lines and (dates or current) and re.search(r"\b(?:19|20)\d{2}|\bpresent\b|\bcurrent\b", detail_lines[0], flags=re.I):
        detail_lines = detail_lines[1:]
    return [{
        "position": position[:200],
        "company": company[:200],
        "start_date": _resume_month(dates[0]) if dates else "",
        "end_date": _resume_month(dates[1]) if len(dates) > 1 and not current else "",
        "current": current,
        "skills": ", ".join(detected_skills),
        "achievements": "\n".join(detail_lines)[:4000],
    }]


def autofill_profile_data(text, existing=None):
    """Return only fields that can be confidently inferred and are still blank."""
    existing = existing or {}
    lower = text.casefold()
    updates = {}
    email = re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", text)
    if email and not existing.get("email"):
        updates["email"] = email.group(0)
    phone = re.search(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)", text)
    if phone and not existing.get("phone"):
        updates["phone"] = re.sub(r"\s+", " ", phone.group(0)).strip()

    if not existing.get("name"):
        ignored = {alias for aliases in RESUME_SECTIONS.values() for alias in aliases} | {"resume", "curriculum vitae", "cv"}
        for line in (item.strip() for item in text.splitlines()[:10]):
            words = re.findall(r"[A-Za-z][A-Za-z'’-]*", line)
            if 2 <= len(words) <= 5 and line.casefold().rstrip(":") not in ignored and "@" not in line and "http" not in line.casefold() and not re.search(r"\d", line):
                updates["name"] = " ".join(words)
                break
    skills = [skill for skill in KNOWN_SKILLS if re.search(rf"(?<![a-z0-9]){re.escape(skill.casefold())}(?![a-z0-9])", lower)]
    if skills and not existing.get("skills"):
        updates["skills"] = ", ".join(skills)

    linkedin = re.search(r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_%-]+/?", text, flags=re.I)
    if linkedin and not existing.get("linkedin"):
        updates["linkedin"] = linkedin.group(0)
    portfolio = re.search(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|[A-Za-z0-9.-]+\.(?:dev|io))/[^\s,)]+", text, flags=re.I)
    if portfolio and not existing.get("portfolio"):
        updates["portfolio"] = portfolio.group(0).rstrip(".")

    experience = _section(text, set(RESUME_SECTIONS["experience"]))
    if experience and not existing.get("experience"):
        updates["experience"] = experience[:4000]
    if experience and not existing.get("experience_entries"):
        updates["experience_entries"] = _experience_entries(experience, skills)
    certifications = _section(text, {"certifications", "certificates", "professional certifications"})
    if certifications and not existing.get("certifications"):
        updates["certifications"] = certifications[:2000]
    awards = _section(text, set(RESUME_SECTIONS["awards"]))
    if awards and not existing.get("awards"):
        updates["awards"] = awards[:2000]

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

    if not existing.get("institution"):
        institutions = {
            "nus": ("national university of singapore", "nus"),
            "ntu": ("nanyang technological university", "ntu"),
            "smu": ("singapore management university", "smu"),
            "sutd": ("singapore university of technology and design", "sutd"),
            "sit": ("singapore institute of technology", "sit"),
            "suss": ("singapore university of social sciences", "suss"),
            "singapore-polytechnic": ("singapore polytechnic",),
            "ngee-ann-polytechnic": ("ngee ann polytechnic",),
            "temasek-polytechnic": ("temasek polytechnic",),
            "republic-polytechnic": ("republic polytechnic",),
            "nanyang-polytechnic": ("nanyang polytechnic",),
        }
        for value, names in institutions.items():
            if any(re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", lower) for name in names):
                updates["institution"] = value
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
