"""Fixed official RSS fallback; no arbitrary URL fetch or provider key."""

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape

import httpx

FEEDS = ("https://www.eia.gov/rss/todayinenergy.xml", "https://www.eia.gov/rss/press_rss.xml")


def official_news(query):
    words = set(re.findall(r"[a-z]{3,}", query.lower()))
    for ru, en in [
        ("нефт", "oil"),
        ("добыч", "production"),
        ("опек", "opec"),
        ("газ", "gas"),
        ("цен", "price"),
        ("спрос", "demand"),
    ]:
        if ru in query.lower():
            words.add(en)
    rows = []
    for url in FEEDS:
        try:
            with httpx.stream("GET", url, timeout=15, follow_redirects=False) as response:
                response.raise_for_status()
                data = b""
                for chunk in response.iter_bytes():
                    data += chunk
                    if len(data) > 2_000_000:
                        raise ValueError("RSS too large")
            root = ET.fromstring(data)
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                body = re.sub("<[^>]+>", " ", unescape(item.findtext("description", "")))
                text = " ".join((title + ". " + body).split())
                score = sum(w in text.lower() for w in words)
                if not score:
                    continue
                published = parsedate_to_datetime(item.findtext("pubDate", "")).isoformat()
                rows.append(
                    {
                        "title": title,
                        "body": text,
                        "url": item.findtext("link", ""),
                        "date": published,
                        "rss_score": score,
                    }
                )
        except (httpx.HTTPError, ValueError, ET.ParseError, TypeError):
            continue
    return sorted(rows, key=lambda r: (r["rss_score"], r["date"]), reverse=True)
