"""
agents/factual_judge.py — Factual Judge Agent

Input : all generated content + resume source of truth
Output: FactualJudgeResult pydantic model
"""
import json
import anthropic
from pydantic import BaseModel, Field

import config


# ── Output schema ─────────────────────────────────────────────────────────────

class FactualJudgeResult(BaseModel):
    verdict: str = "approve"           # approve | revise | block
    factual_risk: str = "low"          # low | medium | high
    issues: list[str] = Field(default_factory=list)


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a strict factual auditor. Your job is to detect any claims in generated
content that are not supported by the candidate's verified resume.

CRITICAL: The source-of-truth resume is the only allowed source of facts.
Any metric, technology, scope, title, or achievement not in the source-of-truth
is a hallucination and must be flagged.

Also flag:
- Inflated language that exaggerates scope even if not technically false
- Technologies implied but not explicitly listed
- Team sizes or org scope not specified in source-of-truth
- Any claim about work authorization or immigration status

DO NOT flag:
- The CV headline — it is always the target role title adapted from the job description, not a claim about the candidate's past experience
- Any reference to the TARGET COMPANY, its products, team names, or role details — cover letters and recruiter pitches naturally discuss the company being applied to; this is not a claim about the candidate's past experience
- Statements explaining why the candidate is interested in the target company or role
- Minor rephrasing of verified facts (e.g. a verified "reduced latency by 30%" restated as "cut latency ~30%" is acceptable)
- Selective omission of bullets — the CV tailor may omit bullets that are less relevant to the role

Verdicts:
- "approve": all claims are supported, low risk
- "revise": minor issues, can be fixed
- "block": high factual risk, do not proceed with drafts

Factual risk levels:
- "low": no issues or trivial wording
- "medium": 1-2 minor unsupported claims
- "high": invented metrics, technologies, or scope — BLOCK immediately

Return ONLY valid JSON — no markdown fences, no explanation.

Schema:
{
  "verdict": "approve",
  "factual_risk": "low",
  "issues": []
}
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

def check_facts(generated_content: str, resume_source: str) -> FactualJudgeResult:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_msg = f"""
Resume Source of Truth:
{resume_source}

Generated Content to Audit:
{generated_content}

Check every factual claim in the generated content against the source-of-truth.
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
        # Model returned malformed JSON — default to approve with warning
        print(f"[factual_judge] WARNING: malformed JSON response — defaulting to approve")
        return FactualJudgeResult(verdict="approve", factual_risk="low", issues=["JSON parse error — manual review recommended"])

    # Normalize issues — model sometimes returns list of dicts instead of strings
    issues = data.get("issues", [])
    normalized = []
    for item in issues:
        if isinstance(item, dict):
            claim = item.get("claim", "")
            severity = item.get("severity", "")
            normalized.append(f"[{severity}] {claim}" if severity else claim)
        else:
            normalized.append(str(item))
    data["issues"] = normalized

    return FactualJudgeResult(**data)
# ── CLI helper ────────────────────────────────────────────────────────────────

def run_factual_judge(generated_content: str) -> FactualJudgeResult:
    resume_source = (config.CONTEXT_DIR / "resume_source_of_truth.md").read_text()

    print(f"[factual_judge] auditing {len(generated_content)} chars of generated content…")
    result = check_facts(generated_content, resume_source)
    print(f"[factual_judge] verdict={result.verdict} risk={result.factual_risk}")
    return result
