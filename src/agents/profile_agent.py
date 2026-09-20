"""
Profile agent.

Reads your resume (and later: LinkedIn export, GitHub, LeetCode stats)
from data/profile_docs/, and produces a compact profile summary that the
curator agent uses to score job matches.

The summary is cached to disk and only regenerated when the source file
changes — no point burning an LLM call on every run if your resume hasn't
been touched.
"""

import os
import json
import hashlib
from pathlib import Path

from pypdf import PdfReader
from google import genai
from google.genai.errors import ServerError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DOCS_DIR = PROJECT_ROOT / "data" / "profile_docs"
CACHE_PATH = PROJECT_ROOT / "data" / "output" / "profile_summary_cache.json"

RESUME_FILENAME = "Saransh_Prabhu_9.pdf"


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(source_hash: str, summary: str) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({
        "source_hash": source_hash,
        "summary": summary,
    }, indent=2))


PROFILE_SUMMARY_PROMPT = """You are building a compact candidate profile from a resume, \
to be used later for matching against job postings.

Extract and organize the following, based only on what's actually in the resume text below \
(do not invent anything):

1. Core skills / technologies (grouped sensibly, e.g. languages, frameworks, tools)
2. Work experience: company, role, duration, and 1-2 line summary of impact per role
3. Notable projects or achievements
4. Education
5. A 2-3 sentence overall summary of what kind of role this person is suited for

Keep it dense and factual — this will be fed to another AI for job matching, not read by a human.

RESUME TEXT:
---
{resume_text}
---
"""


@retry(
    retry=retry_if_exception_type(ServerError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def _generate_profile_summary(resume_text: str) -> str:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=PROFILE_SUMMARY_PROMPT.format(resume_text=resume_text),
    )
    return response.text


def build_or_load_profile_summary(resume_filename: str = RESUME_FILENAME) -> str:
    resume_path = PROFILE_DOCS_DIR / resume_filename
    if not resume_path.exists():
        raise FileNotFoundError(
            f"Resume not found at {resume_path}. "
            f"Place your resume there (e.g. as '{RESUME_FILENAME}')."
        )

    current_hash = _file_hash(resume_path)
    cache = _load_cache()

    if cache and cache.get("source_hash") == current_hash:
        return cache["summary"]

    resume_text = _extract_pdf_text(resume_path)
    if not resume_text.strip():
        raise ValueError(
            f"Extracted no text from {resume_path}. "
            "It may be a scanned/image-based PDF — try re-exporting it as text-based."
        )

    summary = _generate_profile_summary(resume_text)
    _save_cache(current_hash, summary)
    return summary


def profile_agent(state: dict) -> dict:
    """LangGraph node. Ignores incoming state, returns the profile_summary field."""
    return {"profile_summary": build_or_load_profile_summary()}


if __name__ == "__main__":
    # Quick manual test: python -m src.agents.profile_agent
    from dotenv import load_dotenv
    load_dotenv()
    print(build_or_load_profile_summary())