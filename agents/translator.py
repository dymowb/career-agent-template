"""
agents/translator.py — Reference Translation Agent

Produces a faithful translation of the finished application pack (CV + letters) into the
candidate's chosen review language (config.REVIEW_TRANSLATION_LANG), appended to the review
pack FOR REVIEW ONLY. The application is still written and submitted in the JD's language —
this just lets a non-native speaker double-check what they're about to send without pasting
it into an external translator.
"""
import anthropic

import config


SYSTEM = """\
You are a professional translator. Translate the job-application materials below into {lang},
faithfully and naturally.

Rules:
- Translate meaning and tone — not word-for-word, but do not embellish.
- Do NOT add, remove, or change any fact, metric, name, or claim.
- Keep proper nouns, company names, product names, and technologies as in the original.
  You may add a short parenthetical gloss only when a job title would otherwise be unclear.
- Preserve the markdown structure and section headers.
- This is for the candidate's review only and will not be submitted.

Return only the translated markdown — no preamble, no notes.
"""


def translate_pack(cv_markdown: str, draft: dict, lang: str) -> str:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    parts = [
        f"# CV\n\n{cv_markdown}",
        f"# Cover Letter\n\n{draft.get('cover_letter', '')}",
        f"# Recruiter Pitch\n\n{draft.get('recruiter_pitch', '')}",
        f"# Referral Message\n\n{draft.get('referral_message', '')}",
    ]
    if draft.get("company_supplement"):
        parts.append(f"# Company Supplement\n\n{draft['company_supplement']}")
    content = "\n\n".join(parts)

    message = client.messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=SYSTEM.format(lang=lang),
        messages=[{"role": "user", "content": content}],
    )
    return message.content[0].text.strip()


# ── CLI helper ────────────────────────────────────────────────────────────────

def run_translator(cv_markdown: str, draft: dict) -> str | None:
    """Return the translated pack, or None when no review language is configured."""
    lang = config.REVIEW_TRANSLATION_LANG
    if not lang:
        return None
    print(f"[translator] translating pack → {lang}…")
    return translate_pack(cv_markdown, draft, lang)
