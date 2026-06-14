"""
main.py — Career Agent CLI

Usage:
  python main.py init-db
  python main.py parse --jd path/to/job.txt
  python main.py score --jd path/to/job.parsed.json
  python main.py judge --jd path/to/job.parsed.json
  python main.py run --jd path/to/job.txt
  python main.py digest
  python main.py digest --preview
"""
import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.pretty import Pretty

app = typer.Typer(help="Career Agent — disciplined recruiting assistant")


@app.command()
def init_db():
    """Initialise the SQLite database."""
    from db.schema import init_db as _init
    _init()


@app.command()
def parse(
    jd: Path = typer.Option(..., "--jd", help="Path to raw job description .txt file"),
):
    """Parse a job description and print structured output."""
    if not jd.exists():
        rprint(f"[red]File not found:[/red] {jd}")
        raise typer.Exit(1)

    from agents.parser import run_parser
    result = run_parser(jd)

    rprint(Panel(Pretty(result.model_dump()), title="[bold green]Parsed Job[/bold green]"))

    out = jd.with_suffix(".parsed.json")
    out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    rprint(f"\n[dim]Saved to {out}[/dim]")


@app.command()
def score(
    jd: Path = typer.Option(..., "--jd", help="Path to .parsed.json file"),
):
    """Score a parsed job for fit against candidate profile."""
    if not jd.exists():
        rprint(f"[red]File not found:[/red] {jd}")
        raise typer.Exit(1)

    parsed_job = json.loads(jd.read_text())

    from agents.scorer import run_scorer
    result = run_scorer(parsed_job)

    color = "green" if result.score >= 6.5 else "red"
    rprint(Panel(Pretty(result.model_dump()), title=f"[bold {color}]Fit Score: {result.score}[/bold {color}]"))

    out = jd.with_suffix(".scored.json")
    out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    rprint(f"\n[dim]Saved to {out}[/dim]")


@app.command()
def judge(
    jd: Path = typer.Option(..., "--jd", help="Path to .parsed.json file"),
):
    """Run judge agent to validate scoring."""
    if not jd.exists():
        rprint(f"[red]File not found:[/red] {jd}")
        raise typer.Exit(1)

    parsed_job = json.loads(jd.read_text())
    scored_path = jd.with_suffix(".scored.json")

    if not scored_path.exists():
        rprint(f"[red]Score file not found:[/red] {scored_path} — run score first")
        raise typer.Exit(1)

    scoring_result = json.loads(scored_path.read_text())

    from agents.judge import run_judge
    result = run_judge(parsed_job, scoring_result)

    color = "green" if result.verdict == "approve" else "red"
    rprint(Panel(Pretty(result.model_dump()), title=f"[bold {color}]Judge: {result.verdict.upper()}[/bold {color}]"))

    out = jd.with_suffix(".judged.json")
    out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    rprint(f"\n[dim]Saved to {out}[/dim]")


@app.command()
def run(
    jd: Path = typer.Option(..., "--jd", help="Path to raw job description .txt file"),
    send: bool = typer.Option(False, "--send", help="Send email digest after run"),
):
    """Run full pipeline: parse → score → judge → tailor → factual check → draft → voice → revise → export."""
    if not jd.exists():
        rprint(f"[red]File not found:[/red] {jd}")
        raise typer.Exit(1)

    from agents.parser import run_parser
    from agents.scorer import run_scorer
    from agents.judge import run_judge
    from agents.tailoring import run_tailoring
    from agents.factual_judge import run_factual_judge
    from agents.drafter import run_drafter
    from agents.voice_judge import run_voice_judge
    from agents.revision import run_revision
    from agents.exporter import export_review_pack
    from agents.email_delivery import send_digest, preview_digest
    import config

    # 1. Parse
    parsed = run_parser(jd)
    parsed_dict = parsed.model_dump()

    # 1b. Comp gate — skip if stated salary floor is below threshold
    _salary = parsed_dict.get("salary_range", "") or ""
    _nums = [
        int(s.rstrip("k").replace(",", "")) * (1000 if s.endswith("k") else 1)
        for s in re.findall(r"\$?([\d,]+k?)", _salary.lower())
        if s
    ]
    if _nums and min(_nums) < config.MIN_BASE_COMP:
        rprint(f"\n[red]⛔ Comp below threshold (floor ${min(_nums):,} < ${config.MIN_BASE_COMP:,}) — discarded[/red]")
        return

    # 1c. Company block gate — permanent skips and time-limited application limits
    from datetime import date as _today_date
    _company_lower = (parsed_dict.get("company", "") or "").lower()
    if any(frag in _company_lower for frag in config.COMPANY_SKIP):
        rprint(f"\n[yellow]⛔ {parsed_dict.get('company')} permanently skipped (portal/access issue) — skipped[/yellow]")
        return
    for _blocked_fragment, _unblock_date in config.COMPANY_BLOCK_UNTIL.items():
        if _blocked_fragment in _company_lower and _today_date.today() < _unblock_date:
            rprint(f"\n[yellow]⛔ {parsed_dict.get('company')} blocked until {_unblock_date} (application limit) — skipped[/yellow]")
            return

    # 2. Score
    scoring = run_scorer(parsed_dict)
    scoring_dict = scoring.model_dump()

    # 3. Decision gate
    if scoring.score < config.MIN_SCORE:
        rprint(Panel(Pretty(scoring_dict), title=f"[bold red]Discarded — Score: {scoring.score}[/bold red]"))
        rprint(f"\n[red]⛔ Score {scoring.score} below threshold {config.MIN_SCORE} — discarded[/red]")
        return

    # 4. Judge loop (re-score on revise)
    judge_result = None
    for scoring_iter in range(1, config.MAX_SCORING_ITERATIONS + 1):
        judge_result = run_judge(parsed_dict, scoring_dict)

        if judge_result.verdict == "reject":
            rprint(f"\n[red]⛔ Judge rejected — {judge_result.blocking_issues}[/red]")
            return

        if judge_result.verdict == "approve":
            rprint(f"[green][judge] approved on iteration {scoring_iter}[/green]")
            break

        rprint(f"[yellow][judge] revise — re-scoring (iteration {scoring_iter}/{config.MAX_SCORING_ITERATIONS})[/yellow]")
        for fb in judge_result.feedback:
            rprint(f"[yellow]  · {fb}[/yellow]")

        if scoring_iter < config.MAX_SCORING_ITERATIONS:
            scoring = run_scorer(parsed_dict, judge_feedback=judge_result.feedback)
            scoring_dict = scoring.model_dump()
            if scoring.score < config.MIN_SCORE:
                rprint(f"\n[red]⛔ Re-scored below threshold after judge revision — discarded[/red]")
                return
        else:
            rprint(f"[yellow]⚠ Max scoring iterations reached — proceeding with judge concerns[/yellow]")

    judge_dict = judge_result.model_dump()

    # 5. Dedup — skip before expensive drafting if already applied or already packed
    from agents.dedup import is_already_applied, is_already_packed
    _company = parsed_dict.get('company', '')
    _title = parsed_dict.get('title', '')
    applied_match = is_already_applied(_company, _title)
    if applied_match:
        rprint(f"\n[yellow]⏭ Already applied — {applied_match} — skipping[/yellow]")
        return
    packed_match = is_already_packed(_company, _title)
    if packed_match:
        rprint(f"\n[yellow]⏭ Pack already exists — {packed_match} — skipping[/yellow]")
        return

    # 7. Tailoring
    tailoring = run_tailoring(parsed_dict)
    tailoring_dict = tailoring.model_dump()

    # 8. CV Tailor — ATS-optimized DOCX per role
    from agents.cv_tailor import run_cv_tailor
    cv_markdown, cv_docx_path = run_cv_tailor(parsed_dict, tailoring_dict)
    if cv_docx_path:
        rprint(f"[green][cv_tailor] DOCX → {cv_docx_path}[/green]")
    else:
        rprint(f"[yellow][cv_tailor] DOCX skipped (factual block or empty)[/yellow]")

    # 9. Draft
    draft = run_drafter(parsed_dict, tailoring_dict)
    draft_dict = draft.model_dump()

    # 7. Factual judge
    all_content = f"{draft.cover_letter}\n\n{draft.recruiter_pitch}\n\n{draft.referral_message}"
    factual = run_factual_judge(all_content)

    if factual.verdict == "block" or factual.factual_risk == "high":
        rprint(f"\n[red]⛔ Factual judge blocked — {factual.issues}[/red]")
        return

    if factual.verdict == "revise":
        rprint(f"[yellow][factual_judge] revise — fixing factual issues before voice loop[/yellow]")
        draft_dict = run_revision(draft_dict, factual.issues, parsed_dict)
        revised_content = f"{draft_dict.get('cover_letter')}\n\n{draft_dict.get('recruiter_pitch')}\n\n{draft_dict.get('referral_message')}"
        factual = run_factual_judge(revised_content)
        if factual.verdict == "block" or factual.factual_risk == "high":
            rprint(f"\n[red]⛔ Factual risk persists after revision — blocked[/red]")
            return

    factual_dict = factual.model_dump()

    # 8. Voice judge + revision loop
    current_draft = draft_dict
    voice_result = None

    for iteration in range(1, config.MAX_REVISION_ITERATIONS + 1):
        voice_result = run_voice_judge(current_draft, parsed_dict)

        if voice_result.verdict == "approve":
            rprint(f"[green][voice_judge] approved on iteration {iteration}[/green]")
            break

        rprint(f"[yellow][voice_judge] revise — iteration {iteration}/{config.MAX_REVISION_ITERATIONS}[/yellow]")

        if iteration < config.MAX_REVISION_ITERATIONS:
            current_draft = run_revision(current_draft, voice_result.feedback, parsed_dict)

            # Factual check after revision
            revised_content = f"{current_draft.get('cover_letter')}\n\n{current_draft.get('recruiter_pitch')}\n\n{current_draft.get('referral_message')}"
            factual_check = run_factual_judge(revised_content)
            if factual_check.factual_risk == "high":
                rprint(f"\n[red]⛔ Factual risk introduced during revision — stopping[/red]")
                current_draft = draft_dict
                break
        else:
            rprint(f"[yellow]⚠ Max revisions reached — surfacing as concern[/yellow]")

    voice_dict = voice_result.model_dump() if voice_result else {}

    # 8b. Optional reference translation (for review only — does not change what is submitted)
    from agents.translator import run_translator
    translation = run_translator(cv_markdown, current_draft)

    # 9. Export review pack
    pack_path = export_review_pack(
        parsed_dict, scoring_dict, judge_dict,
        tailoring_dict, current_draft, factual_dict,
        voice_dict, cv_docx_path=cv_docx_path, translation=translation,
    )

    rprint(f"\n[green]✅ Review pack ready → {pack_path}[/green]")

    # 10. Email
    if send:
        send_digest([pack_path])
    else:
        preview_digest([pack_path])


@app.command()
def discover(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview jobs without saving to queue"),
    all_companies: bool = typer.Option(False, "--all-companies", help="Search beyond target companies"),
):
    """Discover new jobs via JSearch API and add to queue."""
    from agents.discovery import run_discovery

    rprint("[dim]Starting job discovery…[/dim]")
    paths = run_discovery(
        target_companies_only=not all_companies,
        dry_run=dry_run,
    )

    if dry_run:
        rprint(f"\n[dim]Dry run complete — {len(paths)} jobs would be queued[/dim]")
    else:
        rprint(f"\n[green]✅ {len(paths)} job(s) added to queue[/green]")
        if paths:
            rprint("[dim]Run 'python main.py run --jd inputs/queue/FILE.txt' to process[/dim]")


@app.command()
def digest(
    preview: bool = typer.Option(False, "--preview", help="Preview digest without sending"),
):
    """Send or preview email digest of today's review packs."""
    import config
    from agents.email_delivery import send_digest, preview_digest
    from datetime import date

    today = date.today().strftime("%Y%m%d")
    packs = sorted(
        p / "review_pack.md"
        for p in config.APPLICATIONS_DIR.glob(f"{today}_*")
        if (p / "review_pack.md").exists()
    )

    if not packs:
        rprint(f"[yellow]No review packs found for today ({today})[/yellow]")
        raise typer.Exit(0)

    rprint(f"[dim]Found {len(packs)} review pack(s) for today[/dim]")

    if preview:
        preview_digest(packs)
    else:
        sent = send_digest(packs)
        if sent:
            rprint(f"[green]✅ Digest sent[/green]")
        else:
            rprint(f"[yellow]⚠ Digest not sent — check SMTP config in .env[/yellow]")


if __name__ == "__main__":
    app()
