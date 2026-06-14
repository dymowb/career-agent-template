"""
agents/dedup.py — Application-level deduplication

Two checks before generating expensive drafts:
  1. Already applied — folder is prefixed "APPLIED - " in outputs/applications/
  2. Same-day duplicate — a review pack for this role already exists today

Uses fuzzy title matching to handle punctuation/wording variations
(e.g. "Agent Prompts & Evals" == "Agent Prompts & Evaluations").
"""
import re

import config

# Words that appear in nearly every EM title — strip before comparing
# so "Engineering Manager, Core Services" vs "Engineering Manager, Infrastructure"
# doesn't false-positive just because they share "engineering manager".
_BOILERPLATE = frozenset({
    'engineering', 'manager', 'senior', 'software', 'em', 'lead',
    'principal', 'staff', 'director', 'head', 'vp', 'group', 'sdm',
    'systems', 'services', 'solutions', 'products', 'platform',
    'and', 'the', 'of', 'for', 'in', 'a', 'at', 'ii', 'iii',
})


def _key_tokens(s: str) -> frozenset:
    """Lowercase alphanum tokens minus common EM-title boilerplate."""
    tokens = frozenset(re.sub(r'[^a-z0-9\s]', ' ', s.lower()).split())
    unique = tokens - _BOILERPLATE
    return unique if unique else tokens  # fallback: use all tokens if nothing left


def _company_match(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    return bool(a) and (a in b or b in a)


def _title_match(a: str, b: str) -> bool:
    ta, tb = _key_tokens(a), _key_tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    smaller = min(len(ta), len(tb))
    return (overlap / smaller) >= 0.6


def is_already_applied(company: str, title: str) -> str | None:
    """Return the folder name if a matching APPLIED role exists, or None.

    Scans outputs/applications/ for folders prefixed "APPLIED - " and reads
    the first line of their review_pack.md to extract company/title.
    Matches on company (substring) + fuzzy title (≥50% key-token overlap).
    """
    for applied_dir in config.APPLICATIONS_DIR.glob("APPLIED - *"):
        pack_file = applied_dir / "review_pack.md"
        if not pack_file.exists():
            continue
        try:
            first_line = pack_file.read_text(encoding="utf-8").split("\n")[0]
            content = re.sub(r'^#\s+Review Pack\s+[—\-]+\s*', '', first_line)
            parts = [p.strip() for p in content.split("|")]
            if len(parts) < 2:
                continue
            pack_company, pack_title = parts[0], parts[1]
            if _company_match(company, pack_company) and _title_match(title, pack_title):
                return applied_dir.name
        except Exception:
            continue

    return None


def is_already_packed(company: str, title: str) -> str | None:
    """Return the folder name if a review pack already exists for this role, or None.

    Scans all dates in outputs/applications/ so the same role is never re-processed
    on a subsequent run. Skips APPLIED folders (already handled by is_already_applied).
    """
    for pack in config.APPLICATIONS_DIR.glob("*/review_pack.md"):
        if pack.parent.name.startswith("APPLIED - "):
            continue
        try:
            first_line = pack.read_text(encoding="utf-8").split("\n")[0]
            content = re.sub(r'^#\s+Review Pack\s+[—\-]+\s*', '', first_line)
            parts = [p.strip() for p in content.split("|")]
            if len(parts) < 2:
                continue
            pack_company, pack_title = parts[0], parts[1]
            if _company_match(company, pack_company) and _title_match(title, pack_title):
                return pack.parent.name
        except Exception:
            continue

    return None
