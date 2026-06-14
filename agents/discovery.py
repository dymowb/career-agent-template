"""
agents/discovery.py — Job Discovery Agent

Input : search terms, target companies
Output: list of jobs saved to inputs/queue/
"""
import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import anthropic
import httpx

import config


# ── Search config ─────────────────────────────────────────────────────────────

# EDIT THESE — the free-text queries sent to the JSearch API (role + company).
# Mix titles and companies you care about. The example below targets EM roles;
# change the titles for IC / staff / director / other tracks.
SEARCH_QUERIES = [
    "Senior Engineering Manager Google",
    "Director of Engineering Microsoft",
    "Engineering Manager Anthropic",
    "Engineering Manager Netflix",
    "Engineering Manager Databricks",
]

# EDIT THIS — only jobs whose employer matches one of these names are kept.
TARGET_COMPANIES = [
    "Google", "Microsoft", "Anthropic", "Netflix", "Databricks",
]

# OPTIONAL — per-company title requirements: the role title must contain at least one
# of the listed keywords. Useful when a company's lower-level roles aren't worth it.
# Key on a lowercase company-name fragment, e.g.:
#   "snowflake": ["senior", "principal", "staff", "director"],
COMPANY_TITLE_REQUIREMENTS: dict[str, list[str]] = {}

NEGATIVE_TITLE_KEYWORDS = [
    "tpm", "technical program manager", "program manager",
    "gtm", "customer success", "delivery manager",
    "sales", "marketing", "operations manager",
    "support engineering", "product manager",
    "firmware", "hardware", "manufacturing", "test engineering",
    "planner", "recruiter", "finance", "legal",
    "field engineering", "forward deployed",
]

MAX_RESULTS_PER_QUERY = 10
NUM_PAGES_PER_QUERY = 3

_EM_CLASSIFIER_SYSTEM = """\
You are a job title classifier. Answer only YES or NO — no explanation.

Answer YES if the role manages software engineers or engineering teams — including engineering \
managers, senior managers, directors of engineering, or tech leads who manage engineers or \
engineering managers as direct reports.
Answer NO for: individual contributors, VPs and above, program/project managers, TPMs, \
product managers, operations managers, or roles without engineering direct reports.\
"""


# ── Deduplication ─────────────────────────────────────────────────────────────

def job_id(job: dict) -> str:
    key = f"{job.get('job_title', '')}{job.get('employer_name', '')}{job.get('job_city', '')}"
    return hashlib.md5(key.encode()).hexdigest()


def load_seen_ids() -> set:
    seen_path = config.DB_DIR / "seen_jobs.json"
    if seen_path.exists():
        return set(json.loads(seen_path.read_text()))
    return set()


def save_seen_ids(seen: set) -> None:
    seen_path = config.DB_DIR / "seen_jobs.json"
    seen_path.write_text(json.dumps(list(seen)))


# OPTIONAL — for companies whose names are ambiguous substrings, match on these exact
# fragments instead of the bare name, e.g.:
#   "Block": ["block, inc", "square, inc", "cash app"],
COMPANY_EXACT_FRAGMENTS: dict[str, list[str]] = {}


# ── Filtering ─────────────────────────────────────────────────────────────────

def _company_fragments(name: str) -> list[str]:
    """Return the match fragments to use for a target company name."""
    return COMPANY_EXACT_FRAGMENTS.get(name, [name.lower()])


def is_target_company(job: dict) -> bool:
    employer = job.get("employer_name", "").lower()
    return any(
        any(frag in employer for frag in _company_fragments(c))
        for c in TARGET_COMPANIES
    )


def canonical_company(job: dict) -> str | None:
    """Map a job's employer to its canonical target-company name, if any."""
    employer = job.get("employer_name", "").lower()
    for c in TARGET_COMPANIES:
        if any(frag in employer for frag in _company_fragments(c)):
            return c
    return None


def has_negative_title(job: dict) -> bool:
    title = job.get("job_title", "").lower()
    return any(kw in title for kw in NEGATIVE_TITLE_KEYWORDS)


def fails_company_title_requirement(job: dict) -> bool:
    employer = job.get("employer_name", "").lower()
    title = job.get("job_title", "").lower()
    for company_frag, required_keywords in COMPANY_TITLE_REQUIREMENTS.items():
        if company_frag in employer:
            return not any(kw in title for kw in required_keywords)
    return False


def is_em_role(job: dict) -> bool:
    """Lightweight Haiku classifier: is this an EM role with software engineering direct reports?"""
    title = job.get("job_title", "")
    description = job.get("job_description", "")
    snippet = ". ".join(description.split(".")[:3]).strip()

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            system=_EM_CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": f"Title: {title}\n\nSnippet: {snippet}"}],
        )
        return msg.content[0].text.strip().upper().startswith("YES")
    except Exception as e:
        print(f"[discovery] classifier error for '{title}': {e} — letting through")
        return True


# ── JD formatter ──────────────────────────────────────────────────────────────

def format_jd(job: dict) -> str:
    salary = ""
    min_s = job.get("job_min_salary")
    max_s = job.get("job_max_salary")
    currency = job.get("job_salary_currency", "USD")
    period = job.get("job_salary_period", "")
    if min_s and max_s:
        salary = f"{currency} {int(min_s):,} – {int(max_s):,} {period}"
    elif min_s:
        salary = f"{currency} {int(min_s):,}+ {period}"

    remote = job.get("job_is_remote", False)
    location = f"{job.get('job_city', '')}, {job.get('job_state', '')}".strip(", ")
    if remote:
        location = f"Remote ({location})" if location else "Remote"

    return f"""{job.get('job_title', '')}
{job.get('employer_name', '')} — {location}
{f'Salary: {salary}' if salary else ''}
Apply: {job.get('job_apply_link', '')}

{job.get('job_description', '')}
""".strip()


# ── API call ──────────────────────────────────────────────────────────────────

def search_jobs(query: str) -> list[dict]:
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": query,
        "page": "1",
        "num_pages": str(NUM_PAGES_PER_QUERY),
        "num_results": str(MAX_RESULTS_PER_QUERY),
        "employment_types": "FULLTIME",
        "country": "us",
        "date_posted": "week",
    }

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"[discovery] API error for query '{query}': {e}")
        return []


def get_job_details(job_id: str) -> dict | None:
    url = "https://jsearch.p.rapidapi.com/job-details"
    headers = {
        "X-RapidAPI-Key": config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    try:
        resp = httpx.get(url, headers=headers, params={"job_id": job_id}, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("data", [])
        return items[0] if items else None
    except Exception as e:
        print(f"[discovery] job-details error for {job_id}: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def save_discovery_stats(stats: dict) -> None:
    stats_path = config.DB_DIR / "discovery_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))


def run_discovery(
    queries: list[str] = None,
    target_companies_only: bool = True,
    dry_run: bool = False,
) -> list[Path]:
    queries = queries or SEARCH_QUERIES
    queue_dir = config.BASE_DIR / "inputs" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)

    seen = load_seen_ids()
    saved_paths = []

    from datetime import date as _date
    today_str = _date.today().isoformat()
    blocked_companies = (
        {frag for frag, until in config.COMPANY_BLOCK_UNTIL.items() if _date.today() < until}
        | config.COMPANY_SKIP
    )

    query_stats = []   # per-query breakdown
    company_stats = defaultdict(lambda: {"fetched": 0, "queued": 0})  # per-company breakdown
    total_fetched = 0
    total_queued = 0

    for query in queries:
        # Skip queries that are solely for a blocked company (saves API calls)
        if any(frag in query.lower() for frag in blocked_companies):
            print(f"[discovery] skipping blocked-company query: {query}")
            continue

        print(f"[discovery] searching: {query}...")
        jobs = search_jobs(query)

        q = {
            "query": query,
            "fetched": len(jobs),
            "deduped": 0,
            "company_filtered": 0,
            "blocked": 0,
            "title_filtered": 0,
            "classifier_rejected": 0,
            "salary_filtered": 0,
            "queued": 0,
        }
        total_fetched += len(jobs)

        for job in jobs:
            jid = job_id(job)
            canon = canonical_company(job)
            if canon:
                company_stats[canon]["fetched"] += 1

            if jid in seen:
                q["deduped"] += 1
                continue

            if target_companies_only and not is_target_company(job):
                q["company_filtered"] += 1
                seen.add(jid)
                continue

            # Company block gate — before paid classifier call
            employer_lower = job.get("employer_name", "").lower()
            if any(frag in employer_lower for frag in blocked_companies):
                q["blocked"] += 1
                seen.add(jid)
                print(f"[discovery] blocked: {job.get('employer_name')} (application limit)")
                continue

            if has_negative_title(job):
                q["title_filtered"] += 1
                seen.add(jid)
                continue

            if fails_company_title_requirement(job):
                q["title_filtered"] += 1
                seen.add(jid)
                print(f"[discovery] title requirement not met: {job.get('job_title')} @ {job.get('employer_name')}")
                continue

            if not is_em_role(job):
                q["classifier_rejected"] += 1
                seen.add(jid)
                print(f"[discovery] classifier rejected: {job.get('job_title')} @ {job.get('employer_name')}")
                continue

            # Filter by minimum salary ($250k annual)
            min_salary = job.get("job_min_salary") or 0
            max_salary = job.get("job_max_salary") or 0
            period = job.get("job_salary_period", "")
            if min_salary or max_salary:
                # Normalize to annual
                multiplier = 1
                if period == "HOUR":
                    multiplier = 2080
                elif period == "MONTH":
                    multiplier = 12
                annual = max(min_salary, max_salary) * multiplier
                if annual < 250000:
                    q["salary_filtered"] += 1
                    seen.add(jid)
                    continue

            seen.add(jid)
            q["queued"] += 1
            if canon:
                company_stats[canon]["queued"] += 1

            if not dry_run:
                details = get_job_details(job.get("job_id", ""))
                if details:
                    job = {**job, **details}

            company = re.sub(r"[^a-z0-9]", "_", job.get("employer_name", "unknown").lower())
            title = re.sub(r"[^a-z0-9]", "_", job.get("job_title", "role").lower())[:40]
            filename = f"{company}_{title}_{jid[:8]}.txt"
            out_path = queue_dir / filename

            if not dry_run:
                out_path.write_text(format_jd(job), encoding="utf-8")
                saved_paths.append(out_path)
                print(f"[discovery] queued -> {filename}")
            else:
                saved_paths.append(out_path)
                print(f"[discovery] dry-run -> {job.get('employer_name')} | {job.get('job_title')} | {job.get('job_city')}")

        total_queued += q["queued"]
        query_stats.append(q)
        time.sleep(1)

    if not dry_run:
        save_seen_ids(seen)

    hit_rate = f"{100 * total_queued / total_fetched:.0f}%" if total_fetched else "n/a"
    stats = {
        "date": today_str,
        "dry_run": dry_run,
        "jsearch_calls": len(query_stats),
        "results_per_query": MAX_RESULTS_PER_QUERY,
        "pages_per_query": NUM_PAGES_PER_QUERY,
        "total_fetched": total_fetched,
        "total_queued": total_queued,
        "hit_rate": hit_rate,
        "queries": query_stats,
        "companies": [
            {"company": c, "fetched": v["fetched"], "queued": v["queued"]}
            for c, v in sorted(company_stats.items())
        ],
    }
    if not dry_run:
        save_discovery_stats(stats)

    print(
        f"[discovery] done -- queries={len(query_stats)} fetched={total_fetched} "
        f"queued={total_queued} hit_rate={hit_rate}"
    )
    return saved_paths
