"""
Shared state definitions for the job search LangGraph pipeline.

GraphState is passed between every node in the graph. JobPosting is the
shape each scraper agent must return postings in, so the curator agent
can work with a consistent structure regardless of source.
"""

from typing import TypedDict, Annotated, Literal
import operator


SourceName = Literal["linkedin", "workday", "naukri", "indeed"]


class JobPosting(TypedDict):
    id: str                # stable unique id, e.g. hash of (source, url)
    source: SourceName
    title: str
    company: str
    location: str
    url: str
    posted_date: str       # ISO 8601, e.g. "2026-09-19"
    raw_description: str


class CuratedPosting(TypedDict):
    id: str
    source: SourceName
    title: str
    company: str
    location: str
    url: str
    posted_date: str
    match_score: int        # 0-100, set by the curator agent
    match_reason: str        # short explanation of why it scored this way


class GraphState(TypedDict):
    # Set once by profile_agent, reused on every run
    profile_summary: str

    # Each scraper agent branch appends its results here.
    # operator.add means LangGraph merges parallel branches by concatenation
    # instead of overwriting — required for the Send() fan-out pattern.
    raw_postings: Annotated[list[JobPosting], operator.add]

    # Set once by curator_agent, deduped + scored + sorted best-first
    curated: list[CuratedPosting]

    # Set by the human after the interrupt() pause in human_review.
    # Only postings whose id appears here are eligible for auto_apply.
    approved_ids: list[str]