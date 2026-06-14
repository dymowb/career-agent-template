"""
scripts/generate_base_cv.py — Generate context/Resume_<MM_YYYY>.docx (your base CV)

Run directly:  .venv/bin/python scripts/generate_base_cv.py
Auto-run via:  Claude Code PostToolUse hook on edits to resume_source_of_truth.md (optional)

NOTE: The data below is hardcoded placeholder content. Replace `build_base_cv()` with
your own experience/education/certs/projects (or adapt it to parse
context/resume_source_of_truth.md). It must mirror your source of truth exactly — the
factual judge validates every claim in tailored CVs against that file.
"""
import sys
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from agents.cv_tailor import CVTailorResult, CVExperience, CVEducation, CVProject, render_docx

from datetime import date
_today = date.today()
OUTPUT_PATH = config.CONTEXT_DIR / f"Resume_{_today.strftime('%m_%Y')}_EN.docx"


def build_base_cv() -> CVTailorResult:
    experience = [
        CVExperience(
            company="Current Company",
            title="Engineering Manager",
            period="2020 – Present",
            bullets=[
                "Action + outcome bullet — e.g. 'Led launch of X, enabling N teams to do Y, deprecating a legacy system'",
                "Grew engineering team from A to B; promoted N engineers",
                "Drove >20% infrastructure cost reduction through platform modernization",
            ],
        ),
        CVExperience(
            company="Previous Company",
            title="Senior Software Engineer",
            period="2016 – 2020",
            bullets=[
                "Designed and shipped <system>, handling <scale> at <reliability>",
                "Pair each action with its measurable outcome — standalone metrics or actions read as filler",
            ],
        ),
    ]

    education = [
        CVEducation(
            degree="BSc in Computer Science",
            institution="Your University",
            period="2008 – 2012",
            notes="optional honors / ranking note",
        ),
    ]

    certifications = [
        "Relevant Certification — Issuer (Year)",
    ]

    technical_projects = [
        CVProject(
            name=f"Project Name ({config.GITHUB_URL}/project)",
            bullets=[
                "What you built, the stack, and what it does",
            ],
        ),
    ]

    return CVTailorResult(
        headline="Engineering Manager — Platform & Distributed Systems",
        professional_summary=(
            "2–3 sentence summary built only from verifiable facts. Lead with your strongest, "
            "most relevant experience. Avoid vague aggregate claims like '15+ years'."
        ),
        experience=experience,
        education=education,
        certifications=certifications,
        technical_projects=technical_projects,
    )


if __name__ == "__main__":
    print("[base-cv] Building base CV…")
    cv = build_base_cv()
    print(f"[base-cv] Rendering DOCX → {OUTPUT_PATH}")
    ok = render_docx(cv, OUTPUT_PATH)
    if ok:
        print("[base-cv] Done.")
    else:
        print("[base-cv] FAILED — check python-docx installation")
        sys.exit(1)
