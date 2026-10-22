"""Shared choices used by onboarding and the candidate profile form."""

CAREER_CHOICES = [
    ("technology", "Technology"),
    ("business", "Business"),
    ("finance", "Finance"),
    ("design", "Design"),
    ("healthcare", "Healthcare"),
    ("other", "Other"),
]

SPECIALISATION_CHOICES = [
    ("software-engineering", "Software engineering"),
    ("backend", "Backend development"),
    ("frontend", "Frontend development"),
    ("fintech", "Fintech"),
    ("crypto", "Blockchain / crypto"),
    ("cloud-devops", "Cloud / DevOps"),
    ("ai-ml", "AI / machine learning"),
    ("data-analytics", "Data / analytics"),
    ("cybersecurity", "Cybersecurity"),
    ("product-management", "Product management"),
    ("business-analysis", "Business analysis"),
    ("finance-investment", "Finance / investment"),
    ("ux-ui", "UX / UI design"),
    ("other", "Other"),
]

CAREER_INTEREST_CHOICES = [
    ("marketing", "Marketing"),
    ("machine-learning", "Machine learning"),
    ("ai-engineering", "AI engineering"),
    ("software-engineering", "Software engineering"),
    ("computer-science", "Computer science"),
    ("data-science", "Data science / statistics"),
    ("microbiology", "Microbiology"),
    ("biomedical-science", "Biomedical science"),
    ("bioinformatics", "Bioinformatics / computational biology"),
    ("clinical-research", "Clinical research"),
    ("scientific-research", "Scientific research"),
    ("medicine-technology", "Medicine + technology"),
    ("finance", "Finance"),
    ("fintech", "Fintech"),
    ("investment", "Investment / portfolio analysis"),
    ("audit-accounting", "Audit / accounting"),
    ("business-analysis", "Business analysis"),
    ("ux-ui", "UX / UI design"),
    ("cloud-devops", "Cloud / DevOps"),
]

CAREER_STAGE_CHOICES = [
    ("exploring", "Exploring this direction"),
    ("beginner", "Beginner"),
    ("foundation", "Building foundations"),
    ("intermediate", "Intermediate"),
    ("advanced", "Advanced"),
    ("career-switcher", "Switching into this field"),
]

PHONE_COUNTRY_CODE_CHOICES = [
    ("+65", "Singapore (+65)"),
    ("+60", "Malaysia (+60)"),
    ("+62", "Indonesia (+62)"),
    ("+91", "India (+91)"),
    ("+86", "China (+86)"),
    ("+852", "Hong Kong (+852)"),
    ("+81", "Japan (+81)"),
    ("+82", "South Korea (+82)"),
    ("+61", "Australia (+61)"),
    ("+44", "United Kingdom (+44)"),
    ("+1", "United States / Canada (+1)"),
]

EDUCATION_CHOICES = [
    ("secondary", "Secondary school"),
    ("diploma", "Diploma"),
    ("undergraduate", "Undergraduate degree"),
    ("postgraduate", "Postgraduate degree"),
    ("professional", "Professional qualification"),
    ("bootcamp", "Bootcamp / skills programme"),
    ("other", "Other"),
]

INSTITUTION_CHOICES = [
    ("nus", "National University of Singapore (NUS)"),
    ("ntu", "Nanyang Technological University (NTU)"),
    ("smu", "Singapore Management University (SMU)"),
    ("sutd", "Singapore University of Technology and Design (SUTD)"),
    ("sit", "Singapore Institute of Technology (SIT)"),
    ("suss", "Singapore University of Social Sciences (SUSS)"),
    ("singapore-polytechnic", "Singapore Polytechnic (SP)"),
    ("ngee-ann-polytechnic", "Ngee Ann Polytechnic (NP)"),
    ("temasek-polytechnic", "Temasek Polytechnic (TP)"),
    ("republic-polytechnic", "Republic Polytechnic (RP)"),
    ("nanyang-polytechnic", "Nanyang Polytechnic (NYP)"),
    ("lasalle", "LASALLE College of the Arts"),
    ("nafa", "Nanyang Academy of Fine Arts (NAFA)"),
    ("ite", "Institute of Technical Education (ITE)"),
    ("overseas", "Overseas institution"),
    ("other", "Other institution"),
    ("none", "No formal institution"),
]

VISA_CHOICES = [
    ("citizen", "Singapore Citizen"),
    ("pr", "Singapore Permanent Resident"),
    ("ep", "Employment Pass"),
    ("s-pass", "S Pass"),
    ("student-pass", "Student Pass"),
    ("other", "Other work authorisation"),
    ("sponsorship", "Need employer sponsorship"),
    ("unsure", "Not sure yet"),
]
