import os
import re
from html import unescape
from dotenv import load_dotenv

try:
    from logsGenerator import writeToFile
except ImportError:
    def writeToFile(*args, **kwargs):
        pass

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

load_dotenv()

_missing_key_logged = False


def _format_output(answer: str, sources: list) -> str:
    parts = []
    if answer and answer.strip():
        parts.append(answer.strip())
    if sources:
        src_lines = ["Sources:"]
        for idx, s in enumerate(sources, start=1):
            line = f"{idx}. {s.get('title', 'Untitled')}"
            if s.get("snippet"):
                line += f" — {s['snippet']}"
            if s.get("url"):
                line += f"\n   URL: {s['url']}"
            src_lines.append(line)
        parts.append("\n".join(src_lines))
    return "\n\n".join(parts) if parts else "No relevant results found."


def _search_tavily(query: str) -> str | None:
    global _missing_key_logged
    api = os.getenv("TAVILY_SEARCH_API_KEY")
    if not api or TavilyClient is None:
        if not _missing_key_logged:
            writeToFile("Tavily API key or package missing -> falling back to DuckDuckGo.")
            _missing_key_logged = True
        return None

    client = TavilyClient(api_key=api)
    for attempt in range(2):
        try:
            response = client.search(
                query=query,
                search_depth="advanced",
                include_answer=True,
                include_raw_content=False,
                max_results=3,
            )
            sources = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": (r.get("content") or "")[:200] if not response.get("answer") else "",
                }
                for r in response.get("results", [])
                if r.get("url")
            ]
            return _format_output(response.get("answer", ""), sources)
        except Exception as e:
            writeToFile(f"Tavily attempt {attempt + 1} failed: {e}")
    return None


def _search_ddg(query: str) -> str | None:
    # 1. Try ddgs / duckduckgo_search library first
    if DDGS is not None:
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=4))
            if raw:
                sources = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": (r.get("body") or "").strip(),
                    }
                    for r in raw
                ]
                summary = " ".join(s["snippet"] for s in sources[:2] if s["snippet"])
                return _format_output(summary, sources)
        except Exception as e:
            writeToFile(f"DDGS library search failed: {e}")

    # 2. Zero-dependency HTML fallback via httpx/urllib if ddgs package isn't installed
    try:
        import httpx

        resp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=10.0,
        )
        blocks = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            resp.text,
            re.S,
        )
        sources = []
        for url, title, snip in blocks[:4]:
            clean_title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
            clean_snip = unescape(re.sub(r"<[^>]+>", "", snip)).strip()
            sources.append({"title": clean_title, "url": url, "snippet": clean_snip})
        if sources:
            summary = " ".join(s["snippet"] for s in sources[:2] if s["snippet"])
            return _format_output(summary, sources)
    except Exception as e:
        writeToFile(f"DuckDuckGo HTML fallback failed: {e}")

    return None


def searchOnline(search_query: str) -> str:
    query = (search_query or "").strip()
    if not query:
        writeToFile("Empty search query received.")
        return "Search Results: Empty search query."

    writeToFile(f"Search Query: {query}")

    # Primary: Tavily
    result = _search_tavily(query)
    provider = "Tavily"

    # Fallback: DuckDuckGo
    if not result:
        writeToFile("Switching to DuckDuckGo fallback...")
        result = _search_ddg(query)
        provider = "DuckDuckGo"

    if not result:
        msg = f"No search results found for '{query}' (all search providers unavailable)."
        writeToFile(f"Search Failed: {msg}")
        return f"Search Results: {msg}"

    formatted = f"Search Results ({provider}):\n{result}"
    writeToFile(formatted)
    return formatted


if __name__ == "__main__":
    print("Searching: Today's Latest News About AI")
    print(searchOnline("Today's latest news about AI"))