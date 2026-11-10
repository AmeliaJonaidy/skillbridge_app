"""Keep generated reference material out of candidate resume content."""

REFERENCE_HEADINGS = {
    "EMPLOYER DETAILS USED", "JOB DESCRIPTION PRIORITIES",
    "TAILORING NOTES — REVIEW BEFORE SUBMITTING",
    "TAILORING NOTES – REVIEW BEFORE SUBMITTING",
    "TAILORING NOTES - REVIEW BEFORE SUBMITTING",
}
RESUME_HEADINGS = {
    "TARGET ROLE", "TARGET DIRECTION", "PROFESSIONAL SUMMARY", "SUMMARY",
    "PROFESSIONAL PROFILE", "CORE SKILLS", "SKILLS", "EDUCATION", "EXPERIENCE",
    "WORK EXPERIENCE", "PROJECTS", "PROJECTS & PORTFOLIO", "CERTIFICATIONS",
    "AWARDS & ACHIEVEMENTS", "AWARDS", "WORK AUTHORISATION",
}


def clean_resume_content(content):
    result = []
    skipping = False
    for line in (content or "").splitlines():
        heading = line.strip().upper().rstrip(":")
        if heading in REFERENCE_HEADINGS:
            skipping = True
            continue
        if heading in RESUME_HEADINGS:
            skipping = False
        if not skipping:
            result.append(line)
    text = "\n".join(result).replace(
        "Review every statement against the original resume before submitting.", "",
    )
    return text.strip()
