"""
agents/drafter.py — Application Draft Agent

Input : ParsedJob + TailoringNotes + voice guide + candidate profile
Output: ApplicationDraft pydantic model
"""
import json
import re

import anthropic
from pydantic import BaseModel

import config


# ── Output schema ─────────────────────────────────────────────────────────────

class ApplicationDraft(BaseModel):
    cover_letter: str = ""
    recruiter_pitch: str = ""
    referral_message: str = ""
    company_supplement: str = ""  # populated only for companies configured below


# ── OPTIONAL: per-company supplemental application questions ────────────────────
# Some companies ask an extra essay (e.g. "Why <Company>?"). Configure them here,
# keyed by a lowercase company-name fragment. When a job's company matches, the drafter
# also produces a `company_supplement` field answering that question.
#
# `locked_paragraphs` are reproduced VERBATIM — use this for paragraphs you've already
# polished and want kept stable across applications. The model writes the remaining
# paragraph(s) fresh, grounded in the specific JD. Leave the dict empty to disable.
#
# Example:
#   COMPANY_SUPPLEMENTS = {
#       "acme": {
#           "question": "Why do you want to work at Acme?",
#           "word_range": "200-400 words",
#           "num_paragraphs": 3,
#           "locked_paragraphs": [
#               "A first paragraph you wrote and want reproduced exactly...",
#               "A closing paragraph you wrote and want reproduced exactly...",
#           ],
#       },
#   }
COMPANY_SUPPLEMENTS: dict[str, dict] = {}


def _build_supplement_instructions(entry: dict) -> str:
    locked = entry.get("locked_paragraphs", [])
    locked_block = "\n\n".join(
        f"LOCKED PARAGRAPH {i + 1} (reproduce VERBATIM — do not alter a single word):\n{p}"
        for i, p in enumerate(locked)
    )
    return f"""

--- EXTRA OUTPUT REQUIRED: company_supplement ---
In addition to the cover letter, recruiter pitch, and referral message, you MUST produce a
"company_supplement" field answering: "{entry.get('question', '')}" ({entry.get('word_range', '200-400 words')}).

Rules:
- {entry.get('num_paragraphs', 3)} paragraphs total.
- Reproduce every LOCKED PARAGRAPH below verbatim, in order.
- Write the remaining paragraph(s) fresh and specific to THIS role's team and responsibilities,
  grounded in the actual JD (team mission, technical scope, what the team owns). 3-5 sentences each.

{locked_block}
--- END EXTRA ---
"""


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a senior technical writing assistant helping a candidate write job application
materials. You write in the candidate's authentic voice — not yours.

VOICE RULES (non-negotiable):
- The VOICE GUIDE provided in the user message is the source of truth for tone, style, and the
  specific words/phrases to avoid. Match that voice and never use any phrase it bans.
- Write in the SAME LANGUAGE as the job description.
- Every paragraph must contain at least one specific metric or system reference.
- No lists of adjectives describing the candidate.
- No performative enthusiasm in closing lines.

WARMTH RULES (non-negotiable — cold letters get rejected by humans, not ATS):
- At least one paragraph must show genuine curiosity about what the company/team is
  building — not "your scale is impressive" but something specific: a product decision,
  a technical challenge, a stated direction in the JD worth engaging with
- Include at least one moment of personal perspective or belief — something the candidate
  actually thinks, not just what they've done ("I've found that X is the harder problem
  than most teams realize", "The interesting thing about this space is...")
- Vary paragraph length and rhythm — uniform paragraphs signal AI generation
- The letter should feel like it was written by someone who read the JD, not assembled
  from a template. Name the actual problem the role is solving when possible.


ACCURACY RULES (non-negotiable):
- Use ONLY facts present in the resume source of truth and candidate profile. Never invent
  systems, metrics, titles, or outcomes.
- Refer to systems and products by the exact names used in the source of truth.
# ── OPTIONAL: candidate-specific narrative rules ───────────────────────────────
# Add any "always say X this way" or "always surface this part of my story" rules here.
# The original author used this section to pin precise system names and to make sure every
# letter surfaced their commercial / P&L background. Example of the style:
#   - Always include one sentence about <the part of your background that's easy to miss>,
#     framed as <the angle you want>, not as a generic "career breadth" name-drop.
# Delete this block if you don't need custom narrative rules.

DOCUMENT SPECS:
Cover letter: 3-4 paragraphs, open with something specific to the role/company,
one concrete achievement per paragraph, end directly

Recruiter pitch: 3-5 sentences max, lead with role+relevance, one specific hook,
low-pressure CTA

Referral message: 2-3 sentences, specific ask, no overselling

Return ONLY valid JSON — no markdown fences, no explanation.

Schema:
{
  "cover_letter": "full cover letter text",
  "recruiter_pitch": "recruiter pitch text",
  "referral_message": "referral message text",
  "company_supplement": "only populated for configured companies; empty string otherwise"
}
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

def draft_application(
    parsed_job: dict,
    tailoring_notes: dict,
    voice_guide: str,
    candidate_profile: str,
    resume_source: str,
) -> ApplicationDraft:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    company = parsed_job.get("company", "").lower()
    supplement_entry = next(
        (entry for frag, entry in COMPANY_SUPPLEMENTS.items() if frag in company),
        None,
    )
    supplement_extra = _build_supplement_instructions(supplement_entry) if supplement_entry else ""

    user_msg = f"""
Candidate Profile:
{candidate_profile}

Resume Source of Truth (ONLY use facts from here):
{resume_source}

Voice Guide:
{voice_guide}

Job (parsed):
{json.dumps(parsed_job, indent=2)}

Tailoring Notes:
{json.dumps(tailoring_notes, indent=2)}
{supplement_extra}
Write the cover letter, recruiter pitch, and referral message for this specific role.
{"Also write the company_supplement field as instructed above." if supplement_entry else "Leave company_supplement as an empty string."}
Every claim must be supported by the resume source of truth.
"""

    message = client.messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    for attempt in range(1, 4):
        if attempt == 1:
            raw = message.content[0].text.strip()
        else:
            print(f"[drafter] retry {attempt - 1}/2 — re-requesting after malformed JSON")
            message = client.messages.create(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                system=SYSTEM,
                messages=[
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": message.content[0].text},
                    {"role": "user", "content": "Your response was not valid JSON. Return ONLY the JSON object, no markdown, no explanation."},
                ],
            )
            raw = message.content[0].text.strip()

        # strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        try:
            data = json.loads(raw)
            return ApplicationDraft(**data)
        except (json.JSONDecodeError, Exception) as e:
            if attempt == 3:
                print(f"[drafter] ERROR: malformed JSON after 3 attempts — {e}")
                raise
            print(f"[drafter] attempt {attempt} malformed JSON — will retry")

# ── CLI helper ────────────────────────────────────────────────────────────────

def run_drafter(parsed_job: dict, tailoring_notes: dict) -> ApplicationDraft:
    voice_guide = (config.CONTEXT_DIR / "writing_voice_guide.md").read_text()
    candidate_profile = (config.CONTEXT_DIR / "candidate_profile.md").read_text()
    resume_source = (config.CONTEXT_DIR / "resume_source_of_truth.md").read_text()

    print(f"[drafter] drafting application for {parsed_job.get('title')} @ {parsed_job.get('company')}…")
    result = draft_application(parsed_job, tailoring_notes, voice_guide, candidate_profile, resume_source)
    print(f"[drafter] done — cover letter {len(result.cover_letter)} chars")
    return result
