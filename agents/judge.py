"""
agents/judge.py — Judge Agent

Input : ScoringResult + ParsedJob
Output: JudgeResult pydantic model
"""
import json
import anthropic
from pydantic import BaseModel, Field

import config


# ── Output schema ─────────────────────────────────────────────────────────────

class JudgeResult(BaseModel):
    verdict: str = "approve"           # approve | revise | reject
    confidence: str = "high"          # high | medium | low
    feedback: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a skeptical but fair recruiting advisor reviewing a job fit assessment.
Your job is to validate the scoring quality and catch errors.

Return ONLY valid JSON — no markdown fences, no explanation.

The candidate's target field and level are defined by their profile and career targets —
they may be in ANY field (engineering, operations, design, etc.). Do NOT reject a role just
because it is outside software/engineering; judge fit against what the candidate is targeting.

Your responsibilities:
1. Validate that the score is consistent with the reasons given
2. Detect overconfidence (score >9.0 needs very strong justification)
3. Detect roles whose real function differs from the candidate's target, disguised by the title
   (e.g. a coordinator/analyst/program-management role dressed up as the target role)
4. Check for red flags missed by the parser
5. Validate level estimation is realistic

Verdicts:
- "approve": scoring looks solid, proceed
- "revise": scoring has issues, needs another pass (use feedback field)
- "reject": role is fundamentally wrong fit or TPM disguise (use blocking_issues field)

Return this schema:
{
  "verdict": "approve",
  "confidence": "high",
  "feedback": [],
  "blocking_issues": []
}
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

def judge_scoring(scoring_result: dict, parsed_job: dict) -> JudgeResult:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_msg = f"""
Review this job fit assessment:

Parsed Job:
{json.dumps(parsed_job, indent=2)}

Scoring Result:
{json.dumps(scoring_result, indent=2)}

Is this assessment accurate and well-reasoned?
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
        print(f"[judge] WARNING: malformed JSON — defaulting to approve")
        return JudgeResult(verdict="approve", confidence="low", feedback=["JSON parse error — manual review recommended"])

    return JudgeResult(**data)

# ── CLI helper ────────────────────────────────────────────────────────────────

def run_judge(parsed_job: dict, scoring_result: dict) -> JudgeResult:
    print(f"[judge] reviewing score for {parsed_job.get('title')} @ {parsed_job.get('company')}…")
    result = judge_scoring(scoring_result, parsed_job)
    print(f"[judge] verdict={result.verdict} confidence={result.confidence}")
    return result
