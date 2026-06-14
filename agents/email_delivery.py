"""
agents/email_delivery.py — Email Delivery Agent

Input : list of review pack paths
Output: sends daily digest email via SMTP
"""
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import date

import config


def md_to_html(md: str) -> str:
    """Minimal markdown to HTML converter."""
    lines = md.split("\n")
    html = []
    for line in lines:
        if line.startswith("# "):
            html.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            html.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("- "):
            html.append(f"<li>{line[2:]}</li>")
        elif line.startswith("**") and line.endswith("**"):
            html.append(f"<strong>{line[2:-2]}</strong>")
        elif line.strip() == "---":
            html.append("<hr>")
        elif line.strip() == "":
            html.append("<br>")
        else:
            # inline bold
            import re
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            html.append(f"<p>{line}</p>")
    return "\n".join(html)

def extract_score(pack: Path) -> float:
    """Extract fit score from review pack markdown."""
    import re
    content = pack.read_text(encoding="utf-8")
    match = re.search(r'\*\*Score:\*\* ([\d.]+)/10', content)
    if match:
        return float(match.group(1))
    return 0.0


def load_discovery_stats() -> dict | None:
    stats_path = config.DB_DIR / "discovery_stats.json"
    if stats_path.exists():
        try:
            return json.loads(stats_path.read_text())
        except Exception:
            return None
    return None


def extract_company(pack: Path) -> str:
    """Extract company name from a review pack markdown."""
    import re
    content = pack.read_text(encoding="utf-8")
    match = re.search(r'\*\*Company:\*\*\s*(.+)', content)
    return match.group(1).strip() if match else "Unknown"


def extract_title(pack: Path) -> str:
    """Extract role title from a review pack markdown."""
    import re
    content = pack.read_text(encoding="utf-8")
    match = re.search(r'\*\*Title:\*\*\s*(.+)', content)
    return match.group(1).strip() if match else pack.stem


def pack_company_roles(review_packs: list[Path]) -> dict[str, list[str]]:
    """Map company -> list of role titles that passed all filters."""
    from collections import defaultdict
    roles: dict[str, list[str]] = defaultdict(list)
    for p in review_packs:
        roles[extract_company(p)].append(extract_title(p))
    return dict(roles)


def company_rows(stats: dict, passed_by_company: dict[str, list[str]]) -> list[dict]:
    """Merge discovery per-company stats with passed roles, ranked by passed desc."""
    rows = []
    matched = set()
    for entry in stats.get("companies", []):
        c = entry["company"]
        passed_roles: list[str] = []
        for comp, titles in passed_by_company.items():
            if c.lower() in comp.lower() or comp.lower() in c.lower():
                passed_roles.extend(titles)
                matched.add(comp)
        rows.append({
            "company": c,
            "fetched": entry.get("fetched", 0),
            "queued": entry.get("queued", 0),
            "passed": len(passed_roles),
            "roles": passed_roles,
        })
    # Packs whose company didn't map to any discovery entry (e.g. queued in a prior run)
    for comp, titles in passed_by_company.items():
        if comp not in matched:
            rows.append({"company": comp, "fetched": None, "queued": None,
                         "passed": len(titles), "roles": list(titles)})

    rows.sort(key=lambda r: (r["passed"], r["queued"] or 0, r["fetched"] or 0), reverse=True)
    return rows


def build_discovery_stats_html(stats: dict, passed_by_company: dict[str, list[str]]) -> str:
    rows = ""
    for r in company_rows(stats, passed_by_company):
        fetched = "—" if r["fetched"] is None else r["fetched"]
        queued = "—" if r["queued"] is None else r["queued"]
        passed = r["passed"]
        passed_cell = (
            f'<span style="font-weight:bold; color:#2563eb">{passed}</span>'
            if passed else '<span style="color:#bbb">0</span>'
        )
        rows += f"""
        <tr>
            <td style="padding:4px 12px 4px 0; color:#555; font-weight:bold">{r['company']}</td>
            <td style="padding:4px 8px; text-align:center">{fetched}</td>
            <td style="padding:4px 8px; text-align:center; color:#16a34a">{queued}</td>
            <td style="padding:4px 8px; text-align:center">{passed_cell}</td>
        </tr>"""
        for role in r["roles"]:
            rows += f"""
        <tr>
            <td colspan="4" style="padding:0 8px 4px 24px; color:#777; font-size:0.85em">↳ {role}</td>
        </tr>"""

    skipped_note = ""
    all_queries = set(q["query"] for q in stats.get("queries", []))
    # Mention blocked queries if any were skipped
    from agents.discovery import SEARCH_QUERIES
    skipped = [q for q in SEARCH_QUERIES if q not in all_queries]
    if skipped:
        skipped_note = f"<p style='color:#888; font-size:0.85em; margin-top:8px'>Skipped (blocked): {', '.join(skipped)}</p>"

    return f"""
    <div style="background:#f4f4f4; border-left:4px solid #888; padding:16px 20px; margin-bottom:24px; border-radius:4px;">
        <p style="margin:0 0 10px 0; font-weight:bold; color:#444">
            Discovery — {stats.get('date', '?')} &nbsp;·&nbsp;
            {stats['jsearch_calls']} queries &nbsp;·&nbsp;
            {stats['total_fetched']} fetched &nbsp;·&nbsp;
            {stats['total_queued']} queued &nbsp;·&nbsp;
            <span style="color:#16a34a">{stats['hit_rate']} hit rate</span>
            &nbsp;·&nbsp; {stats['results_per_query']} results/query
        </p>
        <table style="border-collapse:collapse; font-size:0.9em; width:100%">
            <thead>
                <tr style="border-bottom:1px solid #ddd; color:#888; font-size:0.85em">
                    <th style="padding:4px 12px 4px 0; text-align:left">Company</th>
                    <th style="padding:4px 8px">Fetched</th>
                    <th style="padding:4px 8px">Queued</th>
                    <th style="padding:4px 8px">Passed</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        {skipped_note}
    </div>"""


def build_discovery_stats_plain(stats: dict, passed_by_company: dict[str, list[str]]) -> str:
    lines = [
        f"Discovery — {stats.get('date', '?')} | {stats['jsearch_calls']} queries | "
        f"{stats['total_fetched']} fetched | {stats['total_queued']} queued | "
        f"{stats['hit_rate']} hit rate | {stats['results_per_query']} results/query",
        "-" * 60,
        f"  {'Company':<20} {'Fetched':>8} {'Queued':>8} {'Passed':>8}",
    ]
    for r in company_rows(stats, passed_by_company):
        fetched = "—" if r["fetched"] is None else r["fetched"]
        queued = "—" if r["queued"] is None else r["queued"]
        lines.append(f"  {r['company']:<20} {str(fetched):>8} {str(queued):>8} {r['passed']:>8}")
        for role in r["roles"]:
            lines.append(f"      ↳ {role}")
    lines.append("")
    return "\n".join(lines)


def sort_packs(review_packs: list[Path]) -> list[Path]:
    """Sort review packs by fit score descending."""
    return sorted(review_packs, key=extract_score, reverse=True)

def build_digest_html(review_packs: list[Path]) -> str:
    review_packs = sort_packs(review_packs)
    today = date.today().strftime("%Y-%m-%d")

    style = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 800px; margin: 0 auto; padding: 20px; color: #1a1a1a; }
        h1 { color: #1a1a1a; border-bottom: 2px solid #e5e5e5; padding-bottom: 10px; }
        h2 { color: #2d2d2d; margin-top: 30px; }
        h3 { color: #444; }
        hr { border: none; border-top: 1px solid #e5e5e5; margin: 30px 0; }
        li { margin: 4px 0; line-height: 1.6; }
        p { line-height: 1.7; }
        .score { font-size: 1.2em; font-weight: bold; color: #16a34a; }
        .concern { color: #dc2626; }
        .pack { background: #f9f9f9; border-left: 4px solid #2563eb;
                padding: 20px; margin: 20px 0; border-radius: 4px; }
        .header { background: #1a1a1a; color: white; padding: 20px;
                  border-radius: 8px; margin-bottom: 30px; }
        .header h1 { color: white; border-bottom: none; }
    </style>
    """

    stats = load_discovery_stats()
    passed_by_company = pack_company_roles(review_packs)
    stats_html = build_discovery_stats_html(stats, passed_by_company) if stats else ""

    packs_html = ""
    for pack in review_packs:
        content = pack.read_text(encoding="utf-8")
        packs_html += f'<div class="pack">{md_to_html(content)}</div>'

    return f"""
    <html><head>{style}</head><body>
    <div class="header">
        <h1>Career Agent Digest</h1>
        <p>{today} — {len(review_packs)} role(s) passed filters</p>
    </div>
    {stats_html}
    {packs_html}
    </body></html>
    """


def build_digest_plain(review_packs: list[Path]) -> str:
    review_packs = sort_packs(review_packs)
    today = date.today().strftime("%Y-%m-%d")
    lines = [f"Career Agent Digest — {today}\n"]
    lines.append(f"{len(review_packs)} role(s) passed filters today.\n")

    stats = load_discovery_stats()
    if stats:
        passed_by_company = pack_company_roles(review_packs)
        lines.append(build_discovery_stats_plain(stats, passed_by_company))

    lines.append("=" * 60 + "\n")
    for pack in review_packs:
        lines.append(pack.read_text(encoding="utf-8"))
        lines.append("\n" + "=" * 60 + "\n")
    return "\n".join(lines)


def send_digest(review_packs: list[Path]) -> bool:
    if not review_packs:
        print("[email] no roles passed filter today — skipping digest")
        return False

    if not config.SMTP_HOST or not config.SMTP_USER:
        print("[email] SMTP not configured — skipping delivery")
        return False

    today = date.today().strftime("%Y-%m-%d")
    subject = f"Career Agent — {len(review_packs)} role(s) for review | {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = config.EMAIL_TO

    msg.attach(MIMEText(build_digest_plain(review_packs), "plain", "utf-8"))
    msg.attach(MIMEText(build_digest_html(review_packs), "html", "utf-8"))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASS)
            server.sendmail(config.SMTP_USER, config.EMAIL_TO, msg.as_string())
        print(f"[email] digest sent to {config.EMAIL_TO} — {len(review_packs)} role(s)")
        return True
    except Exception as e:
        print(f"[email] failed to send — {e}")
        return False


def preview_digest(review_packs: list[Path]) -> None:
    if not review_packs:
        print("[email] no roles to preview")
        return
    print(build_digest_plain(review_packs))
