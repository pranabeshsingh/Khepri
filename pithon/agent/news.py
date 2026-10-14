"""News aggregator for Khepri daily briefings (local, national, world)."""

import html
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Set

from pithon.agent.search import search_duckduckgo

logger = logging.getLogger("pithon.news")


def clean_headline(title: str) -> str:
    """Clean and strip source attribution suffixes if redundant."""
    if not title:
        return ""
    title = html.unescape(title).strip()
    title = re.sub(r"\s+", " ", title)
    return title


def _fetch_rss_items(url: str, limit: int = 10, timeout: float = 4.0) -> List[Dict[str, str]]:
    """Fetch headlines from a Google News RSS feed."""
    items: List[Dict[str, str]] = []
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Khepri/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                if title_elem is not None and title_elem.text:
                    cleaned = clean_headline(title_elem.text)
                    if cleaned:
                        items.append({
                            "title": cleaned,
                            "url": str(link_elem.text) if link_elem is not None and link_elem.text else ""
                        })
                if len(items) >= limit:
                    break
    except Exception as e:
        logger.warning(f"Failed to fetch RSS from {url}: {e}")
    return items


def _normalize_title(title: str) -> str:
    """Normalize title for fuzzy deduplication."""
    return re.sub(r"[^a-zA-Z0-9]", "", title.lower())


def fetch_news_headlines(city: str = "Kolkata", country_code: str = "IN") -> Dict[str, List[Dict[str, str]]]:
    """
    Fetch top 10 news items partitioned by:
    - 5 local/city headlines
    - 3 country/national headlines
    - 2 world headlines
    Ensures zero cross-category duplicate headlines.
    """
    seen_hashes: Set[str] = set()

    # 1. Local City News (5 items)
    local_encoded = urllib.parse.quote(city)
    local_url = f"https://news.google.com/rss/search?q={local_encoded}&hl=en-{country_code}&gl={country_code}&ceid={country_code}:en"
    raw_local = _fetch_rss_items(local_url, limit=10)

    if not raw_local:
        ddg_results = search_duckduckgo(f"{city} latest news headlines", max_results=7)
        for r in ddg_results:
            raw_local.append({"title": r.get("title", ""), "url": r.get("href", "")})

    local_items: List[Dict[str, str]] = []
    for it in raw_local:
        norm = _normalize_title(it["title"])
        if norm and norm not in seen_hashes:
            seen_hashes.add(norm)
            local_items.append(it)
        if len(local_items) >= 5:
            break

    # 2. National News (3 items)
    nat_url = f"https://news.google.com/rss/headlines/section/topic/NATION?hl=en-{country_code}&gl={country_code}&ceid={country_code}:en"
    raw_national = _fetch_rss_items(nat_url, limit=10)
    if not raw_national:
        nat_search_url = "https://news.google.com/rss/search?q=India+national+news&hl=en-IN&gl=IN&ceid=IN:en"
        raw_national = _fetch_rss_items(nat_search_url, limit=10)

    national_items: List[Dict[str, str]] = []
    for it in raw_national:
        norm = _normalize_title(it["title"])
        if norm and norm not in seen_hashes:
            seen_hashes.add(norm)
            national_items.append(it)
        if len(national_items) >= 3:
            break

    # 3. World News (2 items)
    world_url = "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en"
    raw_world = _fetch_rss_items(world_url, limit=10)
    if not raw_world:
        world_search_url = "https://news.google.com/rss/search?q=World+news+headlines&hl=en-US&gl=US&ceid=US:en"
        raw_world = _fetch_rss_items(world_search_url, limit=10)

    world_items: List[Dict[str, str]] = []
    for it in raw_world:
        norm = _normalize_title(it["title"])
        if norm and norm not in seen_hashes:
            seen_hashes.add(norm)
            world_items.append(it)
        if len(world_items) >= 2:
            break

    return {
        "local": local_items[:5],
        "national": national_items[:3],
        "world": world_items[:2]
    }


def format_news_section(news_data: Dict[str, List[Dict[str, str]]], city: str = "Kolkata") -> str:
    """Format news items into a numbered markdown section with clickable story links."""
    lines = ["📰 *Top 10 Curated Headlines:*"]

    def _format_item(idx: int, item: Dict[str, str]) -> str:
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()

        # Split source attribution if present (e.g. "Headline text - Publisher Name")
        if " - " in title:
            headline, source = title.rsplit(" - ", 1)
        else:
            headline, source = title, ""

        # Sanitize for Telegram legacy markdown
        headline = headline.replace("[", "(").replace("]", ")").replace("*", "").replace("_", "").strip()
        source = source.replace("[", "(").replace("]", ")").replace("*", "").replace("_", "").strip()

        source_tag = f" — _{source}_" if source else ""

        if url:
            return f"{idx}. [{headline}]({url}){source_tag}"
        else:
            return f"{idx}. {headline}{source_tag}"

    # Local
    lines.append(f"\n📍 *Local ({city}):*")
    local_items = news_data.get("local", [])
    if local_items:
        for idx, item in enumerate(local_items, 1):
            lines.append(_format_item(idx, item))
    else:
        lines.append("• No local headlines available at this moment.")

    # National
    lines.append("\n🇮🇳 *National (India):*")
    national_items = news_data.get("national", [])
    if national_items:
        for idx, item in enumerate(national_items, 6):
            lines.append(_format_item(idx, item))
    else:
        lines.append("• No national headlines available at this moment.")

    # World
    lines.append("\n🌐 *World:*")
    world_items = news_data.get("world", [])
    if world_items:
        for idx, item in enumerate(world_items, 9):
            lines.append(_format_item(idx, item))
    else:
        lines.append("• No world headlines available at this moment.")

    return "\n".join(lines)
