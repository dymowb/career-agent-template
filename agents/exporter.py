"""
agents/exporter.py — Review Pack Exporter

Input : all agent outputs
Output: review_pack.md inside the per-application directory
"""
from datetime import datetime
from pathlib import Path

import config


def export_review_pack(
    parsed_job: dict,
    scoring_result: dict,
    judge_result: dict,
    tailoring_notes: dict,
    draft: dict,
    factual_judge_result: dict,
    voice_judge_result: dict = None,
    cv_docx_path=None,
) -> Path:
    date = datetime.now().strftime("%Y%m%d")
    app_dir = config.application_dir(
        parsed_job.get("company", "Unknown"),
        parsed_job.get("title", "Unknown"),
    )
    out_path = app_dir / "review_pack.md"

    concerns = (
        judge_result.get("feedback", [])
        + factual_judge_result.get("issues", [])
        + (voice_judge_result.get("feedback", []) if voice_judge_result else [])
    )

    voice_verdict = voice_judge_result.get("verdict", "n/a") if voice_judge_result else "n/a"

    supplement_section = (
        f"## Company Supplement (application question)\n\n{draft.get('company_supplement')}\n"
        if draft.get("company_supplement")
        else ""
    )

    md = f"""# Review Pack — {parsed_job.get('company')} | {parsed_job.get('title')} | {date}

## Role Summary
- **Title:** {parsed_job.get('title')}
- **Company:** {parsed_job.get('company')}
- **Location:** {parsed_job.get('location')}
- **Remote:** {parsed_job.get('remote')}
- **Salary:** {parsed_job.get('salary_range', 'Not stated')}

## Fit Analysis
**Score:** {scoring_result.get('score')}/10 | **Recommendation:** {scoring_result.get('recommendation')}
**Estimated Level:** {scoring_result.get('estimated_level')} ({scoring_result.get('level_equivalent')})
**Voice Judge:** {voice_verdict}

### Reasons to Apply
{chr(10).join(f"- {r}" for r in scoring_result.get('reasons_to_apply', []))}

### Concerns
{chr(10).join(f"- {c}" for c in scoring_result.get('concerns', []))}

## Resume Tailoring Notes

**Narrative angle:** {tailoring_notes.get('narrative_angle')}

### Emphasize
{chr(10).join(f"- {e}" for e in tailoring_notes.get('emphasize', []))}

### De-emphasize
{chr(10).join(f"- {d}" for d in tailoring_notes.get('deemphasize', []))}

### Keyword Alignment
{chr(10).join(f"- {k}" for k in tailoring_notes.get('keyword_alignment', []))}

## Cover Letter

{draft.get('cover_letter')}

{supplement_section}

## Recruiter Pitch

{draft.get('recruiter_pitch')}

## Referral Message

{draft.get('referral_message')}

## Open Concerns
{chr(10).join(f"- {c}" for c in concerns) if concerns else "None flagged."}

## Tailored CV
{"**DOCX:** cv.docx (same folder as this file)" if cv_docx_path else "⚠ CV not generated (factual block or empty result)"}
"""

    out_path.write_text(md, encoding="utf-8")
    print(f"[exporter] saved review pack → {out_path}")
    return out_path
