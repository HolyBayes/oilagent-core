import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

from analyst.capabilities import requires_skill
from analyst.config import CORE_ROOT, evolution_repo
from analyst.evolution import SEED_WEB, WEB_ARTIFACT
from analyst.feeds import official_news
from analyst.rag import digest

FRESH = r"\b(?:сейчас|сегодня|свеж\w*|последн\w*|актуальн\w*|today|latest|current|now)\b"


class WebSources(BaseModel):
    model_config = ConfigDict(extra="forbid")
    official: list[str] = Field(max_length=30)
    news: list[str] = Field(max_length=30)

    @field_validator("official", "news")
    @classmethod
    def hostnames(cls, values):
        label = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
        if any(not re.fullmatch(rf"{label}(?:\.{label})+", v) for v in values):
            raise ValueError("Source policy requires bare lowercase hostnames")
        return values


def source_policy():
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(evolution_repo()), *args],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()

    text = SEED_WEB.read_text()
    sha, warnings = "seed:" + digest(text.encode()), ["web_policy_seed_fallback"]
    if (evolution_repo() / ".git").exists() and git("for-each-ref", "refs/heads"):
        sha = git("rev-parse", "--verify", "refs/heads/main")
        if git("ls-tree", "--name-only", sha, "--", WEB_ARTIFACT):
            text, warnings = git("show", f"{sha}:{WEB_ARTIFACT}"), []
        else:
            sha = "seed:" + digest(text.encode())
    return WebSources.model_validate_json(text).model_dump(), sha, warnings


def web_enabled():
    load_dotenv(CORE_ROOT / ".env", override=False)
    return os.getenv("WEB_ENABLED", "true").lower() == "true"


def trusted_source(url, policy):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    for priority, domains in enumerate(policy.values()):
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return domain, priority
    return None


def normalize_results(items, *, freshness, now, policy, today=False, query=""):
    evidence, warnings, seen = [], set(), set()
    for item in items:
        try:
            url = item.get("url") or item.get("href", "")
            trusted = trusted_source(url, policy)
            if not trusted:
                warnings.add("web_untrusted_source")
                continue
            parsed = urlsplit(url)
            url = quote(urlunsplit(parsed._replace(fragment="")), safe=":/?=&%+,-._~")
            if url in seen:
                continue
            seen.add(url)
            text = " ".join((item.get("body") or "").split())[:1200]
            if not text:
                continue
            published = None
            try:
                published = datetime.fromisoformat(item.get("date") or "")
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            if published and published > now:
                warnings.add("web_future_date")
                continue
            if freshness and (
                not published
                or now - published > timedelta(days=int(os.getenv("WEB_MAX_AGE_DAYS", "7")))
                or (today and published.date() != now.date())
            ):
                warnings.add("web_missing_or_old_date")
                continue
            evidence.append(
                {
                    "kind": "web",
                    "publisher": trusted[0],
                    "priority": trusted[1],
                    "url": url,
                    "title": re.sub(r"[\r\n<>\[\]`]", " ", item.get("title") or trusted[0])[:200],
                    "published_at": published.isoformat() if published else None,
                    "retrieved_at": now.isoformat(),
                    "date_origin": "search_provider",
                    "text": text,
                    "content_hash": digest(text.encode()),
                    "numeric_verified": published is not None,
                }
            )
        except (ValueError, TypeError, AttributeError):
            warnings.add("web_invalid_result")
    from analyst.method_contracts import validate
    from analyst.method_runtime import run

    request = {
        "rows": [
            {"priority": r["priority"], "text": r["text"], "title": r["title"]} for r in evidence
        ],
        "query": query,
    }
    order = validate("search_strategy", request, run("search_strategy", request))
    evidence = [evidence[i] for i in order]
    return [{**e, "source_id": f"W{i}"} for i, e in enumerate(evidence[:5], 1)], sorted(warnings)


@requires_skill("web_research")
def search_web(query, freshness=True, publishers=None):
    if not 1 <= len(query) <= 4000:
        raise ValueError("Web query must contain 1..4000 characters")
    if not web_enabled():
        return {"evidence": [], "warnings": ["web_disabled"]}
    try:
        from ddgs import DDGS

        policy, sha, policy_warnings = source_policy()
        requested_eia = "EIA" in (publishers or []) or bool(re.search(r"\bEIA\b", query, re.I))
        if requested_eia:
            policy = {"official": [h for h in policy["official"] if h == "eia.gov"], "news": []}
        client = DDGS(timeout=10, verify=True)
        method = client.news if freshness else client.text
        backend_warnings = []
        try:
            items = (
                official_news(query)
                if requested_eia and freshness
                else method(
                    query,
                    backend="duckduckgo",
                    max_results=20,
                    timelimit="w" if freshness else None,
                )
            )
        except Exception as exc:
            items = []
            backend_warnings.append(f"web_backend_error:{type(exc).__name__}")
        if requested_eia and freshness:
            backend_warnings.append("web_official_rss")
        evidence, warnings = normalize_results(
            items,
            query=query,
            freshness=freshness,
            now=datetime.now(timezone.utc),
            policy=policy,
            today=bool(re.search(r"\b(?:сегодня|today)\b", query, re.I)),
        )
        if requested_eia and freshness:
            for row in evidence:
                row["date_origin"] = "official_rss"
        if not evidence and freshness and not requested_eia:
            evidence, feed_warnings = normalize_results(
                official_news(query),
                freshness=True,
                now=datetime.now(timezone.utc),
                policy=policy,
                query=query,
                today=bool(re.search(r"\b(?:сегодня|today)\b", query, re.I)),
            )
            warnings += feed_warnings
            if evidence:
                for e in evidence:
                    e["date_origin"] = "official_rss"
                backend_warnings.append("web_official_rss_fallback")
        return {
            "evidence": [{**e, "policy_revision": sha} for e in evidence],
            "warnings": policy_warnings + backend_warnings + warnings + ["web_search_snippets"],
        }
    except Exception as exc:
        return {"evidence": [], "warnings": [f"web_error:{type(exc).__name__}"]}
