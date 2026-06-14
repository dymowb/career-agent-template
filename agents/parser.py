"""
agents/parser.py — Job Parser Agent

Input : raw job description text
Output: ParsedJob pydantic model
"""
import json
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

import config


# ── Output schema ─────────────────────────────────────────────────────────────

class ParsedJob(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    remote: bool = False
    salary_range: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a precise job description parser. Extract structured information from
job descriptions. Return ONLY valid JSON matching the schema below — no
markdown fences, no explanation, no extra keys.

Schema:
{
  "title": "exact job title from the posting",
  "company": "company name",
  "location": "city, state or 'Remote'",
  "remote": true | false,
  "salary_range": "e.g. $180k–$240k or '' if not stated",
  "requirements": ["list of required qualifications"],
  "responsibilities": ["list of key responsibilities"],
  "keywords": ["important technical/domain keywords from the JD"],
  "red_flags": ["any of: TPM, Program Manager, GTM, Customer Success, Delivery Manager, Sales, Marketing, Operations — only if present"]
}

Be literal and precise. Do not infer or add information not in the JD.
"""

# ── Agent ─────────────────────────────────────────────────────────────────────

def parse_job(raw_jd: str) -> ParsedJob:
    """Call Claude to parse a raw job description into structured data."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Parse this job description:\n\n{raw_jd}",
            }
        ],
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
        print(f"[parser] WARNING: malformed JSON — returning empty ParsedJob")
        return ParsedJob()

    return ParsedJob(**data)

# ── CLI helper ────────────────────────────────────────────────────────────────

def run_parser(jd_path: Path) -> ParsedJob:
    raw_jd = jd_path.read_text(encoding="utf-8")
    print(f"[parser] parsing {jd_path.name} ({len(raw_jd)} chars)…")
    result = parse_job(raw_jd)
    print(f"[parser] done — {result.title} @ {result.company}")
    return result
