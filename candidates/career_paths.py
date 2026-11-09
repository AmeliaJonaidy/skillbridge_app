"""Explainable career-pathway progress for the candidate dashboard.

This module keeps the first version transparent. It compares skills in a
selected pathway with evidence from the profile, resume, and milestones. The
percentage is a readiness indicator, not a probability of being hired.
"""

from urllib.parse import quote_plus

from accounts.choices import CAREER_INTEREST_CHOICES, CAREER_STAGE_CHOICES
from accounts.models import UserProfile

from .models import CandidateMilestone
from .resume_parser import extract_resume_text


def _course(title, provider, url, covers):
    return {"title": title, "provider": provider, "url": url, "covers": covers}


def _stage(title, skills, activity, evidence):
    return {"title": title, "skills": skills, "activity": activity, "evidence": evidence}


CAREER_PATHS = {
    "marketing": {
        "label": "Marketing",
        "skills": ["marketing", "SEO", "content marketing", "analytics", "social media"],
        "milestone_plan": [
            _stage("Marketing foundations", ["marketing", "content marketing"], "Write a campaign brief for a real or imagined product and define its audience.", "Campaign brief, positioning statement, or content calendar."),
            _stage("Reach an audience", ["SEO", "social media"], "Plan and publish a small content experiment across one search or social channel.", "Content samples, campaign results, or a portfolio case study."),
            _stage("Measure and improve", ["analytics"], "Create a simple dashboard and explain which campaign decision the data supports.", "Analytics dashboard, report, or experiment write-up."),
        ],
        "courses": [
            _course("Google Digital Marketing & E-commerce Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-digital-marketing-ecommerce", ["marketing", "content marketing", "analytics"]),
            _course("Google Analytics learning and certification", "Google Skillshop", "https://skillshop.withgoogle.com/", ["analytics"]),
        ],
    },
    "machine-learning": {
        "label": "Machine learning",
        "skills": ["Python", "SQL", "statistics", "machine learning", "TensorFlow"],
        "milestone_plan": [
            _stage("Programming and data foundations", ["Python", "SQL"], "Clean a dataset, write a small Python analysis, and query a relational database.", "Git repository with a notebook, SQL file, and short explanation."),
            _stage("Statistics and modelling", ["statistics", "machine learning"], "Train and evaluate a baseline model; explain the metric and one limitation.", "Notebook or report showing data preparation, metric choice, and evaluation."),
            _stage("Applied ML engineering", ["TensorFlow"], "Turn a model into a reproducible experiment or small prediction service.", "README, model code, evaluation results, and a demo or API endpoint."),
        ],
        "courses": [
            _course("Google Advanced Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-advanced-data-analytics", ["Python", "SQL", "statistics", "machine learning", "analytics"]),
            _course("Machine Learning Engineer Learning Path", "Google Cloud Skills Boost", "https://www.cloudskillsboost.google/paths/17", ["machine learning", "TensorFlow", "Python"]),
            _course("TensorFlow learning resources", "Google for Developers", "https://www.tensorflow.org/resources/learn-ml", ["TensorFlow", "machine learning"]),
        ],
    },
    "ai-engineering": {
        "label": "AI engineering",
        "skills": ["Python", "machine learning", "APIs", "data engineering", "model evaluation", "TensorFlow"],
        "milestone_plan": [
            _stage("AI and programming foundations", ["Python", "machine learning"], "Build a small supervised-learning project and document the data and assumptions.", "Public repository with a reproducible notebook and evaluation notes."),
            _stage("Build usable AI systems", ["APIs", "data engineering"], "Wrap a model or AI workflow in an API and create a simple data pipeline.", "API demo, architecture diagram, and sample request/response."),
            _stage("Evaluate and deploy responsibly", ["model evaluation", "TensorFlow"], "Compare model versions and write a short risk, bias, and monitoring note.", "Evaluation table, monitoring plan, and model card."),
        ],
        "courses": [
            _course("Machine Learning Engineer Learning Path", "Google Cloud Skills Boost", "https://www.cloudskillsboost.google/paths/17", ["machine learning", "TensorFlow", "Python"]),
            _course("Google Cloud Machine Learning Engineer resources", "Google Cloud", "https://cloud.google.com/learn/certification/machine-learning-engineer", ["data engineering", "model evaluation"]),
            _course("AI and machine learning courses", "Coursera search", "https://www.coursera.org/search?query=ai%20engineering", ["APIs", "machine learning"]),
        ],
    },
    "software-engineering": {
        "label": "Software engineering",
        "skills": ["Python", "Git", "SQL", "Django", "JavaScript"],
        "milestone_plan": [
            _stage("Programming and collaboration", ["Python", "Git"], "Build a small command-line or web feature and commit it with a clear README.", "Git repository, README, and tests for the feature."),
            _stage("Backend foundations", ["SQL", "Django"], "Create a Django feature backed by a relational model, form, view, and test.", "Working Django project with migration and tests."),
            _stage("Complete user-facing features", ["JavaScript"], "Add a small progressive enhancement to a Django page without moving the app to a JS framework.", "Before/after screenshots and linked source code."),
        ],
        "courses": [
            _course("Google IT Automation with Python Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-it-automation", ["Python", "Git", "SQL"]),
            _course("Meta Back-End Developer Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/meta-back-end-developer", ["Python", "SQL", "Django"]),
        ],
    },
    "computer-science": {
        "label": "Computer science",
        "skills": ["programming", "algorithms", "data structures", "SQL", "computer systems"],
        "milestone_plan": [
            _stage("Programming foundations", ["programming", "data structures"], "Solve a small set of problems and explain the time and space trade-offs.", "Annotated solutions, tests, and a short complexity explanation."),
            _stage("Algorithms and systems", ["algorithms", "computer systems"], "Implement one algorithm and inspect how a program uses memory, files, or processes.", "Repository with benchmark notes or a systems mini-project."),
            _stage("Build a complete application", ["SQL"], "Design a relational schema and build a small application that uses it correctly.", "ERD, migrations, tests, and a working demo."),
        ],
        "courses": [
            _course("Computer Science courses", "Coursera search", "https://www.coursera.org/search?query=computer%20science", ["programming", "algorithms", "data structures"]),
            _course("CS50x Introduction to Computer Science", "Harvard / edX", "https://cs50.harvard.edu/x/", ["programming", "computer systems", "algorithms"]),
        ],
    },
    "data-science": {
        "label": "Data science / statistics",
        "skills": ["Python", "statistics", "SQL", "data analysis", "data visualisation", "machine learning"],
        "milestone_plan": [
            _stage("Statistics and data handling", ["statistics", "SQL"], "Describe a dataset, query it, and explain uncertainty in one finding.", "Analysis report with SQL queries and statistical reasoning."),
            _stage("Analysis and communication", ["Python", "data analysis", "data visualisation"], "Create a reproducible analysis and a visualisation for a non-technical audience.", "Notebook, dashboard, and one-page stakeholder summary."),
            _stage("Predictive modelling", ["machine learning"], "Compare a baseline with a stronger model and explain whether the improvement matters.", "Model comparison, metric choice, and limitations."),
        ],
        "courses": [
            _course("Google Advanced Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-advanced-data-analytics", ["Python", "statistics", "data analysis", "machine learning"]),
            _course("Google Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-data-analytics", ["SQL", "data analysis", "data visualisation"]),
        ],
    },
    "microbiology": {
        "label": "Microbiology",
        "skills": ["microbiology", "laboratory", "molecular biology", "research", "data analysis"],
        "milestone_plan": [
            _stage("Biology and laboratory foundations", ["microbiology", "laboratory"], "Describe a safe, reproducible laboratory workflow and the controls it needs.", "Lab report, protocol summary, or supervised practical evidence."),
            _stage("Molecular methods", ["molecular biology"], "Explain one molecular technique and how its results should be interpreted.", "Annotated method summary or practical report."),
            _stage("Research and evidence", ["research", "data analysis"], "Analyse a small biological dataset and communicate a cautious conclusion.", "Research poster, analysis notebook, or literature review."),
        ],
        "courses": [
            _course("Microbiology courses", "Coursera search", "https://www.coursera.org/search?query=microbiology", ["microbiology", "molecular biology", "research"]),
            _course("Biology and life sciences learning", "Course search", "https://www.google.com/search?q=recognised+microbiology+certificate+course", ["microbiology", "laboratory"]),
        ],
    },
    "biomedical-science": {
        "label": "Biomedical science",
        "skills": ["biology", "biomedical science", "laboratory", "research", "statistics", "data analysis"],
        "milestone_plan": [
            _stage("Biomedical foundations", ["biology", "biomedical science"], "Summarise a disease mechanism and identify the evidence supporting it.", "Evidence-based literature summary."),
            _stage("Laboratory and research practice", ["laboratory", "research"], "Design a small experiment with controls, risks, and an analysis plan.", "Experiment plan, lab report, or supervised practical record."),
            _stage("Quantitative interpretation", ["statistics", "data analysis"], "Analyse experimental results and state what the data cannot prove.", "Statistical analysis and results discussion."),
        ],
        "courses": [
            _course("Biomedical science courses", "Coursera search", "https://www.coursera.org/search?query=biomedical%20science", ["biology", "biomedical science", "research"]),
            _course("Statistics for the life sciences", "Coursera search", "https://www.coursera.org/search?query=statistics%20life%20sciences", ["statistics", "data analysis"]),
        ],
    },
    "bioinformatics": {
        "label": "Bioinformatics / computational biology",
        "skills": ["biology", "statistics", "Python", "SQL", "data analysis", "bioinformatics", "research"],
        "milestone_plan": [
            _stage("Biology and research foundations", ["biology", "research"], "Read a biological research paper and explain its question, method, and limitation.", "Structured paper critique or literature review."),
            _stage("Statistics and coding", ["statistics", "Python", "SQL"], "Clean and analyse a small biological dataset using code and reproducible queries.", "Notebook, scripts, SQL, and a reproducible README."),
            _stage("Computational biology project", ["data analysis", "bioinformatics"], "Complete a small sequence, expression, or biological data analysis project.", "Capstone repository, methods, results, and limitations."),
        ],
        "courses": [
            _course("Bioinformatics courses", "Coursera search", "https://www.coursera.org/search?query=bioinformatics", ["bioinformatics", "biology", "research"]),
            _course("Python for Everybody", "Coursera", "https://www.coursera.org/specializations/python", ["Python", "data analysis"]),
            _course("Statistics for data science", "Coursera search", "https://www.coursera.org/search?query=statistics%20data%20science", ["statistics", "SQL"]),
        ],
    },
    "clinical-research": {
        "label": "Clinical research",
        "skills": ["clinical research", "research", "statistics", "study design", "ethics", "data analysis"],
        "milestone_plan": [
            _stage("Research and ethics foundations", ["clinical research", "ethics"], "Explain informed consent, participant safety, and the purpose of a protocol.", "Ethics or protocol case-study write-up."),
            _stage("Study design", ["study design", "research"], "Draft a research question, outcome measure, inclusion criteria, and analysis plan.", "Mock protocol or registered study plan."),
            _stage("Evidence and analysis", ["statistics", "data analysis"], "Interpret a clinical dataset without overstating causality.", "Statistical report, evidence table, or journal-club presentation."),
        ],
        "courses": [
            _course("Clinical research courses", "Coursera search", "https://www.coursera.org/search?query=clinical%20research", ["clinical research", "study design", "research"]),
            _course("Good Clinical Practice resources", "Google search", "https://www.google.com/search?q=Good+Clinical+Practice+training+certificate", ["ethics", "clinical research"]),
        ],
    },
    "scientific-research": {
        "label": "Scientific research",
        "skills": ["research", "statistics", "study design", "data analysis", "scientific writing", "literature review"],
        "milestone_plan": [
            _stage("Find and frame a question", ["literature review", "research"], "Compare sources and turn a broad interest into a researchable question.", "Annotated bibliography and research question."),
            _stage("Design and analyse", ["study design", "statistics", "data analysis"], "Create an analysis plan and interpret a dataset with appropriate uncertainty.", "Research plan, notebook, and results section."),
            _stage("Communicate evidence", ["scientific writing"], "Write a concise report that separates findings, limitations, and next steps.", "Poster, paper-style report, or presentation."),
        ],
        "courses": [
            _course("Research methods courses", "Coursera search", "https://www.coursera.org/search?query=research%20methods", ["research", "study design", "literature review"]),
            _course("Statistics with Python", "Coursera search", "https://www.coursera.org/search?query=statistics%20python", ["statistics", "data analysis"]),
        ],
    },
    "medicine-technology": {
        "label": "Medicine + technology",
        "skills": ["biology", "healthcare", "Python", "statistics", "data analysis", "research", "ethics"],
        "milestone_plan": [
            _stage("Health and biological context", ["biology", "healthcare"], "Map a healthcare problem, its users, and the evidence needed to solve it.", "Problem brief, stakeholder map, and literature summary."),
            _stage("Computational and statistical tools", ["Python", "statistics", "data analysis"], "Analyse a health-related dataset and explain privacy and data-quality risks.", "Notebook, data dictionary, and responsible-use notes."),
            _stage("Responsible applied project", ["research", "ethics"], "Build or evaluate a small health-technology prototype with clear limitations.", "Prototype, evaluation plan, and ethics/risk statement."),
        ],
        "courses": [
            _course("Digital health courses", "Coursera search", "https://www.coursera.org/search?query=digital%20health", ["healthcare", "research", "ethics"]),
            _course("Google Advanced Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-advanced-data-analytics", ["Python", "statistics", "data analysis"]),
        ],
    },
    "finance": {
        "label": "Finance",
        "skills": ["finance", "financial analysis", "Excel", "SQL", "analytics"],
        "milestone_plan": [
            _stage("Finance foundations", ["finance", "financial analysis"], "Read a set of financial statements and explain a decision supported by the numbers.", "Financial analysis memo or spreadsheet model."),
            _stage("Tools for analysis", ["Excel", "SQL"], "Build a clean model and query a small financial dataset.", "Spreadsheet model, SQL file, and data dictionary."),
            _stage("Communicate insights", ["analytics"], "Present a recommendation with assumptions, sensitivity, and risk.", "Dashboard or finance presentation."),
        ],
        "courses": [_course("Google Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-data-analytics", ["Excel", "SQL", "analytics", "financial analysis"])],
    },
    "investment": {
        "label": "Investment / portfolio analysis",
        "skills": ["finance", "financial analysis", "portfolio management", "valuation", "Excel", "statistics"],
        "milestone_plan": [
            _stage("Markets and financial statements", ["finance", "financial analysis"], "Write an evidence-based company or asset overview.", "Investment memo with sources and assumptions."),
            _stage("Valuation and portfolio thinking", ["valuation", "portfolio management"], "Compare two assets and explain risk, return, and diversification.", "Valuation model and portfolio rationale."),
            _stage("Quantitative decision-making", ["Excel", "statistics"], "Back-test a simple rule carefully and discuss why historical performance may mislead.", "Spreadsheet or notebook, results, and limitations."),
        ],
        "courses": [
            _course("Investment and portfolio management courses", "Coursera search", "https://www.coursera.org/search?query=investment%20portfolio%20management", ["portfolio management", "valuation", "finance"]),
            _course("Google Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-data-analytics", ["Excel", "statistics", "financial analysis"]),
        ],
    },
    "audit-accounting": {
        "label": "Audit / accounting",
        "skills": ["accounting", "audit", "financial statements", "Excel", "risk assessment", "data analysis"],
        "milestone_plan": [
            _stage("Accounting foundations", ["accounting", "financial statements"], "Prepare and review a basic set of financial statements.", "Workbook and explanation of accounting treatment."),
            _stage("Audit and risk", ["audit", "risk assessment"], "Create an audit planning memo with assertions, risks, and proposed procedures.", "Audit planning memo or case-study workpaper."),
            _stage("Evidence and analytics", ["Excel", "data analysis"], "Use spreadsheet analysis to identify exceptions and document follow-up.", "Working paper, exception log, and conclusion."),
        ],
        "courses": [
            _course("Accounting and audit courses", "Coursera search", "https://www.coursera.org/search?query=accounting%20audit", ["accounting", "audit", "financial statements"]),
            _course("Data analysis with Excel", "Coursera search", "https://www.coursera.org/search?query=excel%20data%20analysis", ["Excel", "data analysis"]),
        ],
    },
    "fintech": {
        "label": "Fintech",
        "skills": ["finance", "Python", "SQL", "APIs", "data analysis"],
        "milestone_plan": [
            _stage("Finance and product context", ["finance", "data analysis"], "Map a financial user problem and define a measurable product outcome.", "Product brief, user journey, and metric definition."),
            _stage("Build financial data features", ["Python", "SQL"], "Build a small data-driven feature with validation and a relational data model.", "Repository, ERD, tests, and sample output."),
            _stage("Integrate responsibly", ["APIs"], "Integrate a sandbox API and document security, privacy, and failure handling.", "API integration demo and risk notes."),
        ],
        "courses": [
            _course("Google Data Analytics Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-data-analytics", ["SQL", "data analysis"]),
            _course("Fintech courses", "Coursera", "https://www.coursera.org/search?query=fintech", ["finance", "Python", "APIs"]),
        ],
    },
    "business-analysis": {
        "label": "Business analysis",
        "skills": ["business analysis", "requirements", "SQL", "Excel", "stakeholder management"],
        "milestone_plan": [
            _stage("Understand a business problem", ["business analysis", "stakeholder management"], "Interview or simulate stakeholders and write a problem statement.", "Stakeholder map, problem statement, and interview notes."),
            _stage("Specify the solution", ["requirements"], "Turn the problem into prioritised user stories and acceptance criteria.", "Backlog, process map, or requirements specification."),
            _stage("Validate with data", ["SQL", "Excel"], "Use a small dataset to test a recommendation and explain its limitations.", "Analysis workbook, queries, and recommendation."),
        ],
        "courses": [_course("Google Project Management Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-project-management", ["requirements", "stakeholder management", "business analysis"])],
    },
    "ux-ui": {
        "label": "UX / UI design",
        "skills": ["UX", "UI", "Figma", "user research", "prototyping"],
        "milestone_plan": [
            _stage("Research users", ["UX", "user research"], "Conduct a small interview or usability review and identify a clear user need.", "Research plan, notes, and synthesised insights."),
            _stage("Design and prototype", ["UI", "Figma", "prototyping"], "Create and test a low-to-high fidelity flow for the selected need.", "Figma file, prototype, and usability findings."),
        ],
        "courses": [_course("Google UX Design Professional Certificate", "Coursera", "https://www.coursera.org/professional-certificates/google-ux-design", ["UX", "UI", "user research", "prototyping"])],
    },
    "cloud-devops": {
        "label": "Cloud / DevOps",
        "skills": ["Docker", "Kubernetes", "AWS", "Git", "Linux"],
        "milestone_plan": [
            _stage("Systems and collaboration", ["Linux", "Git"], "Deploy a small service locally and document commands and recovery steps.", "README, shell notes, and version-controlled configuration."),
            _stage("Package and automate", ["Docker"], "Containerise the service and add a repeatable test or build step.", "Dockerfile, compose file, and build output."),
            _stage("Operate a service", ["AWS", "Kubernetes"], "Deploy a safe sandbox workload and describe health, logs, and rollback.", "Architecture diagram, deployment notes, and monitoring evidence."),
        ],
        "courses": [
            _course("Cloud and DevOps courses", "Coursera", "https://www.coursera.org/search?query=cloud%20devops", ["Docker", "Kubernetes", "AWS", "Git"]),
            _course("Cloud Engineer and DevOps learning paths", "Google Cloud Skills Boost", "https://www.cloudskillsboost.google/paths", ["Kubernetes", "Git", "Linux"]),
        ],
    },
}


SKILL_ALIASES = {
    "machine learning": ("ml", "machine-learning", "machine learning"),
    "ai engineering": ("ai engineer", "artificial intelligence", "ai/ml"),
    "data visualisation": ("data visualization", "visualisation", "visualization"),
    "data analysis": ("data analytics", "analytics"),
    "programming": ("coding", "software development", "development"),
    "computer systems": ("operating systems", "systems programming"),
    "bioinformatics": ("computational biology", "biological data"),
    "portfolio management": ("portfolio analysis", "asset management"),
    "risk assessment": ("risk analysis", "risk management"),
    "scientific writing": ("research writing", "technical writing"),
    "data engineering": ("data pipeline", "data pipelines", "etl"),
    "model evaluation": ("model validation", "evaluation metrics"),
}

CAREER_FIT_PROFILES = {
    "sales": {
        "label": "Sales and business development",
        "skills": ["sales", "business development", "communication", "negotiation", "client relationship"],
    },
    "product-management": {
        "label": "Product management",
        "skills": ["product management", "requirements", "stakeholder management", "user research", "analytics"],
    },
}


def _normalise(value):
    return " ".join(str(value or "").casefold().replace("_", " ").split())


def _contains(text, term):
    return bool(_normalise(term) and _normalise(term) in _normalise(text))


def _skill_matches(source, skill):
    terms = (skill, *SKILL_ALIASES.get(_normalise(skill), ()))
    return any(_contains(source, term) for term in terms)


def _candidate_source(candidate):
    profile = UserProfile.objects.filter(user=candidate).first()
    data = (getattr(profile, "profile_data", {}) or {}) if profile else {}
    # Choices such as ``career_interests`` describe the destination, not
    # evidence that the candidate already has that skill. Only include
    # evidence-bearing profile fields in the readiness calculation.
    evidence_fields = (
        "education",
        "institution",
        "experience",
        "certifications",
        "skills",
        "portfolio",
        "awards",
        "linkedin",
    )
    values = [str(data.get(key)) for key in evidence_fields if data.get(key)]
    for key in ("completed_career_skills", "completed_career_courses"):
        value = data.get(key, [])
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value if item)
    if profile and profile.resume:
        try:
            with profile.resume.open("rb") as resume_file:
                values.append(extract_resume_text(resume_file))
        except (OSError, ValueError):
            pass
    completed = CandidateMilestone.objects.filter(candidate=candidate, status="completed").select_related("certification")
    values.extend(milestone.certification.skills for milestone in completed)
    return " ".join(values), data


def _uploaded_resume_source(candidate):
    """Return the selected main resume, or uploaded resume text."""
    from resumes.models import TailoredResume

    main_resume = TailoredResume.objects.filter(candidate=candidate, is_main=True).first()
    if main_resume:
        return main_resume.content.split("SKILLS TO VERIFY BEFORE SUBMITTING", 1)[0]
    profile = UserProfile.objects.filter(user=candidate).first()
    if not profile or not profile.resume:
        return ""
    try:
        with profile.resume.open("rb") as resume_file:
            return extract_resume_text(resume_file)
    except (OSError, ValueError):
        return ""


def _milestones(path, missing, recommendations):
    """Build ordered pathway stages, with a skill-level fallback."""
    plan = path.get("milestone_plan") or []
    if not plan:
        plan = [
            _stage(
                f"Build {skill}",
                [skill],
                f"Develop {skill} as evidence for your {path['label']} direction, then update your profile or resume.",
                f"A project, work sample, or recognised course certificate demonstrating {skill}.",
            )
            for skill in missing
        ]

    milestones = []
    for order, stage in enumerate(plan, start=1):
        stage_skills = stage.get("skills", [])
        stage_missing = [skill for skill in stage_skills if skill in missing]
        courses = [
            course for course in recommendations
            if any(skill in course.get("covers_missing", []) for skill in stage_missing)
        ]
        is_complete = not stage_missing
        milestones.append(
            {
                "order": order,
                "skill": stage_missing[0] if stage_missing else (stage_skills[0] if stage_skills else ""),
                "skills": stage_skills,
                "missing": stage_missing,
                "percent": round((len(stage_skills) - len(stage_missing)) / len(stage_skills) * 100) if stage_skills else 0,
                "title": stage["title"],
                "description": "This stage is covered by your current evidence." if is_complete else f"Build {', '.join(stage_missing)} for your {path['label']} direction.",
                "activity": stage.get("activity", ""),
                "evidence": stage.get("evidence", ""),
                "status": "completed" if is_complete else "next",
                "courses": courses,
            }
        )
    return milestones


def career_progress(candidate, interests):
    """Return one explainable progress bar and roadmap per selected path."""
    source, data = _candidate_source(candidate)
    stage_labels = dict(CAREER_STAGE_CHOICES)
    results = []
    for interest in interests or []:
        path = CAREER_PATHS.get(interest)
        if not path:
            continue
        matched = [skill for skill in path["skills"] if _skill_matches(source, skill)]
        missing = [skill for skill in path["skills"] if skill not in matched]
        percent = round(len(matched) / len(path["skills"]) * 100)
        recommendations = []
        for course in path["courses"]:
            covered = [
                skill for skill in missing
                if any(_contains(skill, item) or _contains(item, skill) for item in course["covers"])
            ]
            if covered:
                recommendations.append({
                    **course,
                    "covers_missing": covered,
                    "reason": "Recommended because it can help build: " + ", ".join(covered) + ".",
                })
        covered_by_catalogue = {skill for course in recommendations for skill in course.get("covers_missing", [])}
        for skill in missing:
            if skill not in covered_by_catalogue:
                recommendations.append(
                    {
                        "title": f"Search recognised {path['label']} courses for {skill}",
                        "provider": "Coursera search",
                        "url": f"https://www.coursera.org/search?query={quote_plus(skill + ' ' + path['label'])}",
                        "covers_missing": [skill],
                        "reason": f"This search focuses on the missing {skill} skill.",
                    }
                )
        results.append(
            {
                "key": interest,
                "label": path["label"],
                "percent": percent,
                "matched": matched,
                "missing": missing,
                "recommendations": recommendations,
                "milestones": _milestones(path, missing, recommendations),
                "current_stage": data.get("career_stage", ""),
                "current_stage_label": stage_labels.get(data.get("career_stage", ""), "Not set"),
            }
        )
    return results


def resume_fit_matrix(candidate, interests):
    """Compare uploaded-resume evidence with each selected career direction."""
    source = _uploaded_resume_source(candidate)
    labels = dict(CAREER_INTEREST_CHOICES)
    results = []
    for interest in interests or []:
        path = CAREER_PATHS.get(interest) or CAREER_FIT_PROFILES.get(interest)
        if not path:
            continue
        required = path["skills"]
        matched = [skill for skill in required if _skill_matches(source, skill)]
        missing = [skill for skill in required if skill not in matched]
        score = round(len(matched) / len(required) * 100) if required else 0
        results.append(
            {
                "key": interest,
                "label": path.get("label", labels.get(interest, interest.replace("-", " ").title())),
                "score": score,
                "matched": matched,
                "missing": missing,
                "summary": (
                    f"Your uploaded resume shows {len(matched)} of {len(required)} "
                    f"tracked signals for this direction."
                ),
            }
        )
    return results
