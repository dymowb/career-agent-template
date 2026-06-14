"""
agents/revision.py — Revision Agent

Input : ApplicationDraft + VoiceJudgeResult feedback
Output: revised ApplicationDraft
"""
import json
import anthropic
from pydantic import BaseModel

import config


# ── Agent ─────────────────────────────────────────────────────────────────────

def revise_draft(
    draft: dict,
    feedback: list[str],
    parsed_job: dict,
    resume_source: str,
    voice_guide: str,
) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_msg = f"""
You are revising job application drafts based on specific feedback.

RULES:
- Apply each feedback item precisely
- Do NOT introduce new factual claims
- Do NOT invent metrics or technologies not in the resume source of truth
- Preserve what is already working
- Improve naturalness without overcorrecting into stiffness
- Every claim must remain supported by the resume source of truth

Resume Source of Truth:
{resume_source}

Voice Guide:
{voice_guide}

Role: {parsed_job.get('title')} @ {parsed_job.get('company')}

Current Drafts:
Cover Letter:
{draft.get('cover_letter')}

Recruiter Pitch:
{draft.get('recruiter_pitch')}

Referral Message:
{draft.get('referral_message')}

Feedback to address:
{chr(10).join(f"- {f}" for f in feedback)}

Return ONLY valid JSON — no markdown fences, no explanation.

Schema:
{{
  "cover_letter": "revised cover letter",
  "recruiter_pitch": "revised recruiter pitch",
  "referral_message": "revised referral message"
}}
"""

    message = client.messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[revision] WARNING: malformed JSON — returning original draft")
        return draft

    return data

# ── CLI helper ────────────────────────────────────────────────────────────────

def run_revision(draft: dict, feedback: list[str], parsed_job: dict) -> dict:
    resume_source = (config.CONTEXT_DIR / "resume_source_of_truth.md").read_text()
    voice_guide = (config.CONTEXT_DIR / "writing_voice_guide.md").read_text()

    print(f"[revision] applying {len(feedback)} feedback items…")
    result = revise_draft(draft, feedback, parsed_job, resume_source, voice_guide)
    print(f"[revision] done")
    return result
