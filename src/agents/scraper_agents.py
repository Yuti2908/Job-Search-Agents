"""
LinkedIn scraper agent.

Uses browser-use to drive your REAL, already-logged-in Chrome profile —
this reuses your existing LinkedIn session so there's no credential
handling and no separate login flow to automate.

Important: Chrome must be fully closed before running this, since
browser-use launches it in debug mode and a running instance will
conflict with that.

A reminder from earlier in the build: LinkedIn's ToS prohibits automated
scraping, and this can put your account at some risk even when reusing
a real session. You've already decided to proceed with this — just
flagging it stays true once here, at the point real code touches your
actual account, rather than repeating it every message from here on.
"""

import os
import hashlib
from datetime import date, datetime, timezone
from urllib.parse import quote

from pydantic import BaseModel
from browser_use import Agent, Browser, ChatGoogle, Controller
from tenacity import retry, stop_after_attempt, wait_exponential

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.state import JobPosting


SOURCE = "linkedin"

# f_TPR=r86400 -> posted in the last 24 hours (LinkedIn's own server-side filter)
# sortBy=DD -> sort by date, most recent first
SEARCH_URL_TEMPLATE = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords={keywords}&location={location}&f_TPR=r86400&sortBy=DD"
)


class LinkedInJobItem(BaseModel):
    title: str
    company: str
    location: str
    url: str
    posted_text: str  # e.g. "2 hours ago" — descriptive only, not parsed for filtering


class LinkedInJobList(BaseModel):
    jobs: list[LinkedInJobItem]


def _build_search_url(keywords: str, location: str) -> str:
    return SEARCH_URL_TEMPLATE.format(
        keywords=quote(keywords),
        location=quote(location),
    )


def _make_id(company: str, title: str) -> str:
    raw = f"{SOURCE}:{company}:{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@retry(
    stop=stop_after_attempt(2),  # browser runs are slow/costly — don't retry endlessly
    wait=wait_exponential(multiplier=5, min=5, max=20),
    reraise=True,
)
async def _run_scrape(keywords: str, location: str) -> LinkedInJobList:
    url = _build_search_url(keywords, location)

    controller = Controller(output_model=LinkedInJobList)
    browser = Browser.from_system_chrome()  # reuses your real, logged-in Chrome profile
    llm = ChatGoogle(model="gemini-flash-latest")

    task = (
        f"Go to {url} — this is a LinkedIn job search already filtered to "
        f"postings from the last 24 hours, sorted newest first. "
        f"Scroll down two or three times to load more results. "
        f"For each of the first 20 visible job listings, extract: "
        f"the job title, the company name, the location, the direct URL to "
        f"the job posting, and the posted-time text shown on the card "
        f"(e.g. '2 hours ago', '1 day ago'). "
        f"Do not open each job individually — only extract what's visible "
        f"on the search results list itself, to keep this fast."
    )

    agent = Agent(task=task, llm=llm, browser=browser, controller=controller)
    history = await agent.run()

    result = history.final_result()
    if not result:
        return LinkedInJobList(jobs=[])
    return LinkedInJobList.model_validate_json(result)


def scrape_linkedin(keywords: str, location: str = "") -> list[JobPosting]:
    """Sync entry point for use as a LangGraph node / scraper dispatch target."""
    import asyncio

    parsed = asyncio.run(_run_scrape(keywords, location))
    today = date.today().isoformat()

    postings: list[JobPosting] = []
    for job in parsed.jobs:
        postings.append(JobPosting(
            id=_make_id(job.company, job.title),
            source=SOURCE,
            title=job.title,
            company=job.company,
            location=job.location,
            url=job.url,
            posted_date=today,  # safe: search URL already filters to last 24h
            raw_description="",  # not fetched in this pass — listing fields only
        ))
    return postings


if __name__ == "__main__":
    # Manual test: python -m src.agents.scraper_agents
    from dotenv import load_dotenv
    load_dotenv()

    results = scrape_linkedin(keywords="backend engineer", location="Bengaluru")
    print(f"Found {len(results)} postings\n")
    for p in results:
        print(f"- {p['title']} @ {p['company']} ({p['location']}) — {p['url']}")