# Career Agent

A disciplined, multi-agent job-application assistant built on the Claude API. It finds
roles, decides which are worth your time, and—only for the ones that pass—drafts a tailored,
ATS-friendly CV and cover letter. Every draft is fact-checked by a separate agent so it can't
invent things about you. **You stay in the loop: it prepares applications; you review and send them.**

> This is a sanitized template. All personal data is replaced with placeholders and clearly
> marked extension points. Search the code for `EDIT`, `OPTIONAL:`, `you@example.com`, `Your`,
> and `<...>` to find what to change.

---

## What it does, and what you get

The pipeline runs as a chain of small agents, each one a single Claude call:

```
discover ─▶ parse ─▶ score ─▶ judge ─▶ tailor CV + draft letter ─▶ factual + voice judges ─▶ revise ─▶ export ─▶ digest email
```

For every role that scores above your threshold, it writes a folder under `outputs/` containing:

- **`cv.docx`** — a CV tailored to that specific job (bullets reordered and reworded to match
  the JD, never fabricated), in ATS-friendly Word format.
- **`review_pack.md`** — the human-readable summary you actually work from: the fit score and
  reasoning, concerns, the tailoring angle, plus the **cover letter**, **recruiter pitch**, and
  **referral message** drafts.

You read the review pack, tweak anything you want, and apply. Nothing is sent to an employer
automatically. (The only optional outbound step is an email digest **to yourself**.)

## How it stays honest (read this — it's the whole point)

A dedicated **factual judge** audits every generated document against one file you control:
`context/resume_source_of_truth.md`. Any metric, technology, title, scope, or achievement that
isn't in that file gets flagged, and high-risk drafts are **blocked** rather than shipped. A
**voice judge** separately catches AI-smell and generic filler.

The practical consequence: **the quality and honesty of your results are bounded by that one
file.** If an achievement isn't in your source of truth, the agent literally cannot use it. So
the highest-leverage thing you can do is make `resume_source_of_truth.md` complete, specific,
and true — real metrics, real scope, real systems. Everything good flows from that.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your keys (below)
python main.py init-db        # creates db/career_agent.db

# try it on a single job: paste a JD into a .txt file, then:
python main.py run --jd path/to/job.txt
# → look in outputs/ for the review pack and CV
```

### API keys (in `.env`)

| Key | Required? | Where |
|-----|-----------|-------|
| `ANTHROPIC_API_KEY` | **Yes** — every agent calls Claude | https://console.anthropic.com |
| `RAPIDAPI_KEY` | Only for auto-discovery | https://rapidapi.com → subscribe to **JSearch** (`jsearch.p.rapidapi.com`), free tier available |
| `SMTP_*` | Optional — emailed digest to yourself | e.g. a Gmail [App Password](https://myaccount.google.com/apppasswords); leave blank to disable |

Without `RAPIDAPI_KEY` you skip discovery and just run the pipeline on JDs you paste in yourself.

## Customizing it

**The key idea:** every box in the pipeline is one Claude call, and its instructions live in a
big `SYSTEM = """ ... """` string near the top of `agents/<name>.py`. **To change how a step
behaves, open that file and edit the prose.** No framework knowledge required — if you can edit
a paragraph, you can retune any agent. Here's the map, from "must do" to "advanced".

### Tier 1 — Make it about you (do this first)
- **`context/resume_source_of_truth.md`** — your real, verifiable facts. *Start here* (see above).
- **`context/candidate_profile.md`** — positioning, strengths, themes (used by scorer, tailor, drafter).
- **`context/career_targets.md`** — roles, levels, comp, location you want (used by the scorer).
- **`context/writing_voice_guide.md`** — how your letters should sound (enforced by the voice judge).
- **`config.py`** — `CANDIDATE_NAME` / `CANDIDATE_CONTACT` / `GITHUB_URL` (on every doc), `MODEL`,
  `MIN_SCORE` (fit bar), `MIN_BASE_COMP` (salary floor), `COMPANY_SKIP` / `COMPANY_BLOCK_UNTIL`.

### Tier 2 — Tune the judgment (prompts & rubric)
This is where most of the power is, and where the README of most tools stops short:
- **`agents/scorer.py`** — the decision brain. Edit the **scoring dimensions, their weights**, the
  **level calibration** (tell it your current level and what counts as a step-up), and the
  **penalties** (`tpm_disguise_risk`, `downlevel_risk`, `deep_specialist_risk`, etc.). These
  penalties are *opinions*, not law — keep, change, or delete them to match what you'll accept.
- **`agents/cv_tailor.py`** — the CV rules. There's an `OPTIONAL: candidate-specific narrative
  rules` block where you can **pin must-keep bullets** or enforce ordering, plus a fixed
  identity headline (rule 7) and the bullet-writing philosophy.
- **`agents/drafter.py`** — the letter writer. Edit the **VOICE RULES** and **WARMTH RULES**, and
  use **`COMPANY_SUPPLEMENTS`** to auto-generate extra application essays for specific companies
  (e.g. a "Why <Company>?" question), with paragraphs you can lock verbatim.
- **`agents/voice_judge.py` / `agents/factual_judge.py`** — what gets flagged or blocked. Loosen
  or tighten the bar here.
- **`config.py`** — `MAX_SCORING_ITERATIONS`, `MAX_REVISION_ITERATIONS` control how many times
  agents re-score / re-draft against judge feedback (more = higher quality, more API cost).

### Tier 3 — Change the targeting / scope (advanced)
- **`agents/discovery.py`** — `SEARCH_QUERIES` and `TARGET_COMPANIES` (what to search and keep),
  plus the role filters: `NEGATIVE_TITLE_KEYWORDS`, `COMPANY_TITLE_REQUIREMENTS`, and an LLM
  **EM-role classifier**. **Heads-up: discovery and the rubric are tuned for engineering-manager
  roles by default** — if you target IC / staff / director / non-EM roles, adjust the queries,
  the classifier, and the negative-keyword list accordingly.
- **`scripts/generate_base_cv.py`** — builds a base `.docx`; replace `build_base_cv()` with your data.
- Adding a whole new step is just a new `agents/<name>.py` with its own `SYSTEM` prompt, wired
  into `main.py`.

## A workflow that actually produces good results

1. Write a thorough `resume_source_of_truth.md` (the ceiling for everything).
2. Run on **one** job: `python main.py run --jd job.txt`.
3. Read `outputs/.../review_pack.md`. Look at the score reasoning and any judge concerns.
4. If the score or framing feels off, that's feedback about your **context files and rubric**,
   not the model — refine `candidate_profile.md` / `career_targets.md` / `scorer.py` and rerun.
5. Once one job looks great, turn on discovery and let it run.

## Running

```bash
python main.py run --jd path/to/job.txt   # full pipeline on one job description
python main.py discover                    # pull jobs via JSearch → inputs/queue/
python main.py parse  --jd job.txt         # individual stages for debugging
python main.py digest                      # send/preview the results email
./run.sh                                    # daily cron: discover → process queue → digest
```

## Notes
- **Cost:** a single job runs ~10+ Claude calls (more with retries/iterations). It's not free —
  start on cheaper models and a few jobs while you tune.
- `db/career_agent.db` and `db/*.json` (seen-jobs cache, stats) are gitignored; `db/schema.py` is tracked.
- This pipeline assumes Claude; swapping providers means rewriting the agent calls.
