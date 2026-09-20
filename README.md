# Job Search Multi-Agent System

An automated pipeline that reads your profile (resume, skills, experience),
scrapes job boards for postings from the last 24 hours, ranks them against
your profile, and gives you a curated shortlist to review — **you always
apply manually**. No agent ever submits an application without your
explicit, per-job approval.

## Status: in progress

| Component | Status |
|---|---|
| Environment setup (Python 3.12, LangGraph, CrewAI, browser-use) | ✅ Done |
| Profile agent (resume → structured summary) | ✅ Done |
| LinkedIn scraper agent | ✅ Working |
| Workday / Naukri / Indeed scraper agents | ⬜ Not started |
| Curator agent (dedupe + match scoring) | ⬜ Not started |
| Human review step (LangGraph `interrupt()`) | ⬜ Not started |
| Auto-apply (opt-in enhancement) | ⬜ Not started |

## Tech stack

| Piece | Tool | Why | Cost |
|---|---|---|---|
| Orchestration | [LangGraph](https://langchain-ai.github.io/langgraph/) | State machine controlling the whole pipeline; native support for parallel agent fan-out and pausing for human approval | Free (self-hosted) |
| Role-based sub-agent | [CrewAI](https://www.crewai.com/) | Used inside the curator node for multi-role ranking (dedupe → score → rank) | Free (self-hosted) |
| Browser automation | [browser-use](https://browser-use.com/) | Drives a real Chromium browser via an LLM instead of hand-written selectors — needed since LinkedIn/Naukri/Indeed don't offer usable public APIs | Free (self-hosted) |
| LLM | [Google Gemini](https://aistudio.google.com/) (`gemini-flash-latest`) | Free tier, no card required, used for all reasoning/extraction calls | **Free** |
| PDF parsing | [pypdf](https://pypdf.readthedocs.io/) | Extracts text from your resume | Free |
| Retry handling | [tenacity](https://tenacity.readthedocs.io/) | Automatic retry-with-backoff on transient API failures (e.g. Gemini 503s) | Free |

**No paid service is required anywhere in this stack.** This was a deliberate
requirement — see [Design decisions](#design-decisions) below.

## Project structure

```
job-search-agent/
├── venv/
├── main.py                      # environment smoke test
├── .env                         # API keys (gitignored)
├── data/
│   ├── profile_docs/            # your resume goes here
│   ├── auth/                    # exported browser sessions (gitignored — see Guardrails)
│   └── output/                  # cached profile summary, curated results
└── src/
    ├── state.py                 # GraphState / JobPosting schema shared across all nodes
    ├── graph.py                 # LangGraph wiring (not yet built)
    └── agents/
        ├── profile_agent.py     # resume → structured candidate summary
        ├── scraper_agents.py    # job board scrapers (LinkedIn done, others pending)
        └── curator_agent.py     # dedupe + match scoring (not yet built)
└── scripts/
    └── export_linkedin_auth.py  # one-time LinkedIn session export
```

## Setup

```powershell
# 1. Clone/create the project, then:
py -3.12 -m venv venv
venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install langgraph langgraph-checkpoint-sqlite crewai browser-use python-dotenv google-genai

# 3. Windows only: pywin32 needs a manual post-install step
python venv\Scripts\pywin32_postinstall.py -install

# 4. Get a free Gemini key at aistudio.google.com, then create .env:
#    GEMINI_API_KEY=your-key
#    GOOGLE_API_KEY=your-key      (browser-use reads this name specifically)

# 5. Verify everything works
python main.py
```

Expected output: 4/4 `[OK]` lines.

### Adding your profile

Place your resume at `data/profile_docs/Resume.pdf` (filename
configurable in `profile_agent.py`). Then:

```powershell
python -m src.agents.profile_agent
```

This prints a structured summary and caches it — it only re-runs the LLM
call if the resume file actually changes.

### Setting up LinkedIn scraping (one-time)

```powershell
# Close Chrome completely first, just for this one step
python -m scripts.export_linkedin_auth
```

This opens a browser window on your real Chrome profile, waits for you to
confirm you're logged into LinkedIn, then exports the session to
`data/auth/linkedin_auth.json`. Every scraper run after this loads that
file directly — **Chrome does not need to be closed for normal runs**,
only for this one-time export. Re-run this export only if LinkedIn
eventually invalidates the session.

```powershell
python -m src.agents.scraper_agents
```

## Design decisions

**Why free-only, all the way through.** This project intentionally avoids
any paid API. Every LLM call runs on Google Gemini's free tier rather than
Anthropic/OpenAI's paid APIs. This does mean occasional rate limits or
transient `503` errors under heavy Google traffic — handled via automatic
retry with exponential backoff (see `tenacity` usage in `profile_agent.py`
and `scraper_agents.py`).

**Why browser-use instead of official APIs.** LinkedIn, Naukri, and Indeed
don't offer public job-search APIs usable for this purpose (LinkedIn's
requires partnership approval; Naukri has none). Workday is per-company,
not a single board. browser-use drives a real browser via an LLM, adapting
to page layout instead of relying on brittle hand-written selectors.

**Why LangGraph + CrewAI together, not just one.** LangGraph owns the
overall control flow (parallel scraping, state, the human-approval pause).
CrewAI is used only inside the curator node, where role-based delegation
(dedupe → score → rank) is a natural fit. Keeping CrewAI scoped to one
node avoids mixing two orchestration philosophies across the whole system.

## Guardrails

This system is built with several deliberate safety boundaries:

1. **No auto-apply, ever, by default.** The pipeline always stops at a
   human review step. Nothing is submitted anywhere without you seeing
   the shortlist first. An opt-in auto-apply feature is planned as a
   future enhancement, but even then it will only touch job postings you
   individually mark as approved — never a blanket "apply to everything."

2. **Recency filtering happens at the source.** Each scraper filters to
   postings from the last 24 hours using the job board's own server-side
   filter (e.g. LinkedIn's `f_TPR=r86400` parameter), not by asking the
   LLM to judge recency — server-side filters are exact, LLM judgment
   of relative time text ("2 hours ago") is not.

3. **Stable, content-based caching, not blind re-computation.** The
   profile summary is cached by a hash of the resume file's actual bytes,
   so it only regenerates when the resume genuinely changes — reducing
   unnecessary LLM calls even on the free tier.
