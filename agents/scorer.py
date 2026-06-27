"""
agents/scorer.py — Fit Scoring Agent

Input : ParsedJob + candidate profile + career targets (loaded from context/)
Output: ScoringResult pydantic model
"""
import json
import anthropic
from pydantic import BaseModel, Field

import config


# ── Output schema ─────────────────────────────────────────────────────────────

class ScoringResult(BaseModel):
    score: float = 0.0
    recommendation: str = "skip"        # apply | skip | reject
    estimated_level: str = ""
    level_equivalent: str = ""    # the role's level mapped to YOUR current ladder
    reasons_to_apply: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    downlevel_risk: bool = False
    tpm_disguise_risk: bool = False
    deep_specialist_risk: bool = False
    fully_remote: bool = False    # set by the model; scored per config.REMOTE_PREFERENCE

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a senior recruiting advisor evaluating job fit for a specific candidate.
Return ONLY valid JSON — no markdown fences, no explanation.

Scoring dimensions (compute a weighted average for the final score):
1. role_fit (0-10): Does title and scope match target profile?
2. level_fit (0-10): Is this likely at target level or above?
3. domain_fit (0-10): Is the domain a good fit? Score against the domains the candidate
   prefers and avoids, as stated in their candidate profile and career targets.
   # EDIT: the lists below are EXAMPLES. Replace with the domains YOU want, e.g.:
   #   High (8-10): high-scale backend product, AI/LLM systems, payments/fintech, dev productivity
   #   Medium (5-7): pure infrastructure or data engineering without product ownership
   #   Low   (0-4): corporate IT, pure on-call/reliability, narrow regional scope
4. company_value (0-10): Is this a strategically valuable company for the candidate?
5. personal_interest (0-10): Does this align with long-term trajectory?

# ── EDIT: level calibration ────────────────────────────────────────────────────
# Tell the model YOUR current level and what counts as a step-up vs lateral, so it can
# fill level_fit and level_equivalent. Replace the example below with your own ladder.
Candidate's current level: <YOUR CURRENT TITLE / LEVEL>. Target is a step-up in scope, level,
or materially higher comp; a lateral is acceptable only with broader scope. Use this to
calibrate level_fit and to fill "level_equivalent" (the role mapped onto your own ladder).

Optionally provide a cross-company level reference table so the model maps titles consistently,
e.g. "Company X Senior <role> ≈ my level; Company X <next level up> ≈ one level up". Keep it
accurate to your situation.

EXTERNAL LEVELING REALITY: companies rarely hire external candidates two levels above their
current equivalent. Reflect that in the score — a 2-level reach is worth attempting but unlikely
to land at the stated level. This is a structural constraint, not a reflection of candidate quality.

Penalties (applied after weighted average):
- reach_level_risk: if the role maps to 2+ levels above the candidate's current level, cap
  level_fit at 4 and subtract 1.5 from the final score. Surface it in concerns as a structural
  external-leveling gap, not a skills gap.
- downlevel_risk: subtract 2 points if the role manages a single small team (<8 engineers) with
  no cross-org scope and is not a clear lateral with broader scope.
- tpm_disguise_risk: subtract 5 points if the role is really a TPM/program manager in disguise.
- deep_specialist_risk: subtract 3 points if the role requires very deep specialist expertise the
  manager must personally have (e.g. kernel/GPU programming, ML framework internals). This is
  about required personal depth, not domain_fit. (Remove this penalty if it doesn't apply to you.)
- generic_company_bonus: do NOT inflate the score just because the company is a top target.
  Score the role itself — a weak role at a great company is still a weak role.
__REMOTE_CLAUSE__

Weights: role_fit=25%, level_fit=25%, domain_fit=25%, company_value=15%, personal_interest=10%

Return this schema:
{
  "score": 8.4,
  "recommendation": "apply",
  "estimated_level": "Senior <role>",
  "level_equivalent": "one level above current (step-up)",
  "reasons_to_apply": ["reason 1", "reason 2"],
  "concerns": ["concern 1"],
  "downlevel_risk": false,
  "tpm_disguise_risk": false,
  "deep_specialist_risk": false,
  "fully_remote": false
}

Minimum score to recommend "apply": 6.5
Below 6.5: recommendation = "skip"
If tpm_disguise_risk is true: recommendation = "reject"
"""

# ── Agent ─────────────────────────────────────────────────────────────────────

def _remote_clause() -> str:
    """Build the fully-remote scoring directive from config.REMOTE_PREFERENCE."""
    pref = getattr(config, "REMOTE_PREFERENCE", "neutral")
    adj = getattr(config, "REMOTE_ADJUSTMENT", 1.5)
    if pref == "penalize":
        return (f"- fully_remote: set true if the role is FULLY REMOTE (work-from-anywhere, no office "
                f"attendance expected), then SUBTRACT {adj} points and add a concern. Apply ONLY to "
                f"genuinely fully-remote roles — never penalize hybrid or onsite. (Remote preference: penalize.)")
    if pref == "prefer":
        return (f"- fully_remote: set true if the role is FULLY REMOTE (work-from-anywhere), then ADD "
                f"{adj} points. Apply ONLY to genuinely fully-remote roles. (Remote preference: prefer.)")
    return ("- fully_remote: set true if the role is fully remote, but do NOT change the score for it "
            "(remote, hybrid, and onsite are scored equally). (Remote preference: neutral.)")


def score_job(parsed_job: dict, candidate_profile: str, career_targets: str, judge_feedback: list[str] = None) -> ScoringResult:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    feedback_note = ""
    if judge_feedback:
        feedback_note = "\n\nNote from reviewing judge — address these issues in your scoring:\n" + "\n".join(f"- {fb}" for fb in judge_feedback)

    user_msg = f"""
Candidate Profile:
{candidate_profile}

Career Targets:
{career_targets}

Parsed Job:
{json.dumps(parsed_job, indent=2)}

Score this job for this candidate.{feedback_note}
"""

    message = client.messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=SYSTEM.replace("__REMOTE_CLAUSE__", _remote_clause()),
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
        data.setdefault("deep_specialist_risk", False)
    except json.JSONDecodeError:
        print(f"[scorer] WARNING: malformed JSON — returning score 0")
        return ScoringResult(score=0.0, recommendation="skip", concerns=["JSON parse error — manual review recommended"])

    return ScoringResult(**data)

# ── CLI helper ────────────────────────────────────────────────────────────────

def run_scorer(parsed_job: dict, judge_feedback: list[str] = None) -> ScoringResult:
    candidate_profile = (config.CONTEXT_DIR / "candidate_profile.md").read_text()
    career_targets = (config.CONTEXT_DIR / "career_targets.md").read_text()

    print(f"[scorer] scoring {parsed_job.get('title')} @ {parsed_job.get('company')}…")
    result = score_job(parsed_job, candidate_profile, career_targets, judge_feedback=judge_feedback)
    print(f"[scorer] score={result.score} recommendation={result.recommendation}")
    return result
