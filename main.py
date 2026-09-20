"""
Run this once to confirm the environment is healthy before writing real code.
    python main.py
"""

def check(name, fn):
    try:
        fn()
        print(f"[OK]   {name}")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")

def check_langgraph():
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import MemorySaver

def check_gemini():
    import os
    from google import genai

    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY not set in environment / .env")

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents="Reply with exactly one word: pong",
    )
    if "pong" not in response.text.lower():
        raise RuntimeError(f"Unexpected response from Gemini: {response.text!r}")

def check_crewai():
    from crewai import Agent, Task, Crew

def check_browser_use():
    from browser_use import Agent as BrowserAgent

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    check("langgraph imports", check_langgraph)
    check("gemini client + API key (live call)", check_gemini)
    check("crewai imports", check_crewai)
    check("browser-use imports", check_browser_use)