"""
agents/tailoring.py — Resume Tailoring Agent

Input : ParsedJob + resume source of truth + candidate profile
Output: TailoringNotes pydantic model
"""
import anthropic
from pydantic import BaseModel, Field

import config


# ── Output schema ─────────────────────────────────────────────────────────────

class TailoringNotes(BaseModel):
    company: str = ""
    role: str = ""
    emphasize: list[str] = Field(default_factory=list)
    deemphasize: list[str] = Field(default_factory=list)
    keyword_alignment: list[str] = Field(default_factory=list)
    narrative_angle: str = ""


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a senior technical recruiter helping tailor a resume for a specific role.
Your job is to identify which verified achievements to emphasize, which to de-emphasize,
and how to align vocabulary with the job description.

CRITICAL RULES:
- You may ONLY reference achievements and technologies from the source-of-truth resume
- You may NOT invent, inflate, or extrapolate any experience
- You may NOT add technologies not explicitly in the source-of-truth
- Reordering and emphasis are allowed — fabrication is not

Return ONLY valid JSON — no markdown fences, no explanation.

Schema:
{
  "company": "company name",
  "role": "role title",
  "emphasize": ["specific achievement or bullet to highlight"],
  "deemphasize": ["specific bullet to move down or omit"],
  "keyword_alignment": ["JD uses X → surface bullet Y"],
  "narrative_angle": "one sentence describing the core narrative angle for this application"
}
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

def tailor_resume(parsed_job: dict, resume_source: str, candidate_profile: str) -> TailoringNotes:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_msg = f"""
Resume Source of Truth (ONLY use claims from here):
{resume_source}

Candidate Profile:
{candidate_profile}

Job Description (parsed):
{parsed_job}

Generate tailoring notes for this specific role.
"""

    message = client.messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    import json
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[tailoring] WARNING: malformed JSON — returning empty notes")
        return TailoringNotes(company=parsed_job.get("company",""), role=parsed_job.get("title",""))

    return TailoringNotes(**data)

# ── CLI helper ────────────────────────────────────────────────────────────────

def run_tailoring(parsed_job: dict) -> TailoringNotes:
    resume_source = (config.CONTEXT_DIR / "resume_source_of_truth.md").read_text()
    candidate_profile = (config.CONTEXT_DIR / "candidate_profile.md").read_text()

    print(f"[tailoring] generating notes for {parsed_job.get('title')} @ {parsed_job.get('company')}…")
    result = tailor_resume(parsed_job, resume_source, candidate_profile)
    print(f"[tailoring] done — narrative: {result.narrative_angle[:60]}…")
    return result
