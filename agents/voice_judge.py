"""
agents/voice_judge.py — Voice & Naturalness Judge

Input : ApplicationDraft
Output: VoiceJudgeResult pydantic model
"""
import json
import anthropic
from pydantic import BaseModel, Field

import config


# ── Output schema ─────────────────────────────────────────────────────────────

class VoiceJudgeResult(BaseModel):
    verdict: str = "approve"           # approve | revise
    feedback: list[str] = Field(default_factory=list)


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a senior recruiting advisor reviewing job application drafts for a
specific candidate. Your job is to detect AI smell, generic language, and
anything that violates the candidate's authentic voice.

The VOICE GUIDE (provided in the user message) defines the candidate's voice and the specific
words/phrases to avoid. It is the source of truth — judge the drafts against it, in whatever
language they are written. Flag any banned word/phrase from the guide and any wording that
clashes with the voice it describes.

Check each document for these violations:

HARD VIOLATIONS (always flag):
- Any word or phrase the VOICE GUIDE says to avoid
- A generic opener or performative enthusiasm ("excited/passionate to apply" and its equivalents
  in any language)
- Lists of adjectives describing the candidate (e.g. "collaborative, innovative, driven")
- Closing line is purely performative with no specific content
- Any paragraph that could apply to any other candidate at any company

STYLE VIOLATIONS (flag if pattern is strong):
- Excessive symmetry — every paragraph same length and structure (AI smell)
- Generic corporate language with no technical specificity
- Fake modesty or fake humility
- A tone that clashes with the voice guide
- No specific metric or system in a paragraph

WARMTH VIOLATIONS (flag if missing):
- Letter reads like a résumé with "I" prepended — no engagement with the company's
  actual problem or what the team is building
- No personal perspective or belief anywhere — only a list of things the candidate has done
- Nothing in the letter could not have been written without reading the JD

DOCUMENT-SPECIFIC CHECKS:
- Cover letter: does it open with something specific to this role/company?
- Cover letter: does each paragraph contain at least one specific metric or system?
- Recruiter pitch: is it 3-5 sentences? Does it lead with relevance not introduction?
- Referral message: is it 2-3 sentences? Is the ask specific?

Verdict:
- "approve": documents pass — ready for human review
- "revise": one or more violations found — list specific feedback

Return ONLY valid JSON — no markdown fences, no explanation.

Schema:
{
  "verdict": "approve",
  "feedback": [
    "Cover letter paragraph 2 has no specific metric",
    "Recruiter pitch opens with self-introduction instead of role relevance"
  ]
}
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

def judge_voice(draft: dict, parsed_job: dict, voice_guide: str = "") -> VoiceJudgeResult:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_msg = f"""
VOICE GUIDE (source of truth for tone and banned words/phrases):
{voice_guide}

Role: {parsed_job.get('title')} @ {parsed_job.get('company')}

Cover Letter:
{draft.get('cover_letter')}

Recruiter Pitch:
{draft.get('recruiter_pitch')}

Referral Message:
{draft.get('referral_message')}

Review these documents for voice, naturalness, and authenticity violations.
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

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[voice_judge] WARNING: malformed JSON — defaulting to approve")
        return VoiceJudgeResult(verdict="approve", feedback=["JSON parse error — manual review recommended"])

    return VoiceJudgeResult(**data)

# ── CLI helper ────────────────────────────────────────────────────────────────

def run_voice_judge(draft: dict, parsed_job: dict) -> VoiceJudgeResult:
    voice_guide = (config.CONTEXT_DIR / "writing_voice_guide.md").read_text()
    print(f"[voice_judge] reviewing drafts for {parsed_job.get('title')} @ {parsed_job.get('company')}…")
    result = judge_voice(draft, parsed_job, voice_guide)
    print(f"[voice_judge] verdict={result.verdict} feedback_count={len(result.feedback)}")
    return result
