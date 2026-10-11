"""DuckDuckGo web search engine and prompt context augmenter."""

import html
import re
import urllib.parse
import urllib.request
from typing import List, Dict, Any

SEARCH_INTENT_KEYWORDS = {
    "latest", "news", "today", "yesterday", "tomorrow", "current", "currently", "price", "stock", "score",
    "release", "happened", "who is", "who won", "what is happening",
    "breaking", "recent", "update"
}

def clean_html_text(raw_text: str) -> str:
    """Strip HTML tags and unescape HTML entities."""
    if not raw_text:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def should_search(query: str) -> bool:
    """Detect whether a query warrants a live web search."""
    clean = query.lower().strip()
    if clean.startswith("/search") or clean.startswith("/web"):
        return True

    words = set(re.findall(r"\b\w+\b", clean))
    if any(k in words for k in SEARCH_INTENT_KEYWORDS):
        return True

    phrases = ["who is", "who won", "what is happening", "what happened", "release date"]
    if any(p in clean for p in phrases):
        return True

    return False

def search_duckduckgo(query: str, max_results: int = 3, timeout: float = 5.0) -> List[Dict[str, str]]:
    """Perform a DuckDuckGo search via HTML endpoint and return top snippets."""
    if not query.strip():
        return []

    # Clean leading commands if present
    clean_q = re.sub(r"^/(search|web)\s+", "", query.strip(), flags=re.IGNORECASE)
    encoded_query = urllib.parse.urlencode({"q": clean_q})
    url = f"https://html.duckduckgo.com/html/?{encoded_query}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    results = []
    # Split by result container divs or match blocks
    raw_blocks = re.split(r'<div[^>]*class="[^"]*result\b', content)
    for block in raw_blocks[1:]:
        if len(results) >= max_results:
            break

        # Extract title & url
        title_match = re.search(r'<a[^>]*class="[^"]*(?:result__url|result__snippet|result__title)[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not title_match:
            title_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)

        raw_url = ""
        raw_title = ""
        if title_match:
            raw_url = title_match.group(1).strip()
            raw_title = title_match.group(2).strip()

        # Extract snippet
        snip_match = re.search(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not snip_match:
            snip_match = re.search(r'<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        raw_snip = snip_match.group(1).strip() if snip_match else ""

        # Decode actual URL from duckduckgo redirect if present
        actual_url = raw_url
        if "uddg=" in raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs and qs["uddg"]:
                actual_url = qs["uddg"][0]
        elif actual_url.startswith("//"):
            actual_url = "https:" + actual_url

        title = clean_html_text(raw_title)
        snippet = clean_html_text(raw_snip)

        if title or snippet:
            if len(snippet) > 220:
                snippet = snippet[:217] + "..."
            results.append({
                "title": title or "Source Result",
                "snippet": snippet or "No snippet provided.",
                "url": actual_url or ""
            })

    return results

def format_search_context(results: List[Dict[str, str]], query: str) -> str:
    """Format DuckDuckGo search results into a clean prompt context block."""
    if not results:
        return ""

    lines = [f'[Live Web Search Results for: "{query}"]']
    for idx, r in enumerate(results, 1):
        lines.append(f"{idx}. Title: {r['title']}")
        lines.append(f"   Snippet: {r['snippet']}")
        if r.get("url"):
            lines.append(f"   URL: {r['url']}")
    lines.append("[Instruction: Answer accurately using the search results above. Provide source references.]\n")
    return "\n".join(lines)
