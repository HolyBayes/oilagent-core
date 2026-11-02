import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from analyst import graph as pipeline
from analyst.contracts import ReportClaim, ReportDraft, Route
from analyst.evidence import render_answer, validate_claims
from analyst.evolution import WEB_ARTIFACT, Evolution
from analyst.web import normalize_results, search_web, source_policy, trusted_source

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
POLICY = {"official": ["eia.gov"], "news": ["reuters.com"]}


def item(url="https://reuters.com/oil", date="2026-11-01T09:00:00Z"):
    return {"url": url, "date": date, "title": "Oil news", "body": "Output stays at 10 units."}


@pytest.mark.parametrize(
    "url",
    [
        "https://eia.gov.evil.org",
        "https://noteia.gov",
        "https://eia.gov@evil.org",
        "https://user@eia.gov",
        "http://eia.gov",
        "https://eia.gov:8443",
    ],
)
def test_domain_boundary_and_url_credentials(url):
    assert trusted_source(url, POLICY) is None


def test_provenance_date_filter_and_official_priority():
    rows, warnings = normalize_results(
        [
            item(),
            item("https://www.eia.gov/news"),
            item("https://reuters.com/oil#duplicate"),
            item("https://eia.gov/old", "2025-01-01"),
            item("https://eia.gov/undated", ""),
            item("https://eia.gov/future", "2027-01-01"),
            item("https://fake.org"),
            item("https://eia.gov:bad/invalid"),
        ],
        freshness=True,
        now=NOW,
        policy=POLICY,
    )
    assert [r["publisher"] for r in rows] == ["eia.gov", "reuters.com"]
    assert rows[0]["published_at"] != rows[0]["retrieved_at"]
    assert rows[0]["date_origin"] == "search_provider"
    assert {
        "web_untrusted_source",
        "web_future_date",
        "web_missing_or_old_date",
        "web_invalid_result",
    } <= set(warnings)
    assert (
        normalize_results(
            [item(date="2026-10-31T10:00:00Z")], freshness=True, today=True, now=NOW, policy=POLICY
        )[0]
        == []
    )


def test_undated_sources_do_not_support_numbers_or_live_prices():
    rows, _ = normalize_results([item(date="")], freshness=False, now=NOW, policy=POLICY)
    draft = ReportDraft(
        claims=[ReportClaim(text="Объём 10", source_id="W1", quote="Output stays at 10 units.")],
        abstain=False,
    )
    assert validate_claims(draft, rows) == ([], ["unverified_number"])
    assert "дата неизвестна" in render_answer([draft.claims[0].model_dump()], rows)
    rows[0]["numeric_verified"] = True
    draft.claims[0].text = "Сейчас цена 10"
    assert validate_claims(draft, rows) == ([], ["unverified_live_fact"])


def test_committed_policy_and_bootstrap(tmp_path, monkeypatch):
    repo = tmp_path / "evolution"
    monkeypatch.setenv("EVOLUTION_REPO_PATH", str(repo))
    assert source_policy()[1].startswith("seed:") and not repo.exists()
    backend = Evolution(tmp_path / "runtime", repo)
    policy, sha, warnings = source_policy()
    assert not warnings and sha == backend.baseline()["base_sha"]
    (repo / WEB_ARTIFACT).write_text(json.dumps(POLICY))
    assert source_policy()[0] == policy  # Working edits do not activate themselves.
    backend.git("add", WEB_ARTIFACT)
    backend.git("commit", "-m", "Operator selects web sources")
    assert source_policy()[0] == POLICY
    backend.git("checkout", "-b", "candidate/bad-source-policy")
    (repo / WEB_ARTIFACT).write_text('{"official":["https://evil.org"],"news":[]}')
    backend.git("add", WEB_ARTIFACT)
    backend.git("commit", "-m", "Invalid policy fixture")
    assert source_policy()[0] == POLICY
    backend.git("branch", "-f", "main", "HEAD")
    with pytest.raises(ValueError):
        source_policy()


def test_network_disabled_and_errors_are_sanitized(monkeypatch):
    monkeypatch.setenv("WEB_ENABLED", "false")
    assert search_web("oil")["warnings"] == ["web_disabled"]
    monkeypatch.setenv("WEB_ENABLED", "true")
    monkeypatch.setattr("analyst.web.source_policy", lambda: (POLICY, "test", []))

    def broken(**kwargs):
        raise RuntimeError("private request details")

    monkeypatch.setattr("ddgs.DDGS", broken)
    assert search_web("oil")["warnings"] == ["web_error:RuntimeError"]


@pytest.mark.parametrize("freshness,abstain", [(True, False), (False, False), (False, True)])
def test_graph_web_once_and_report_priority(freshness, abstain, monkeypatch):
    sources, _ = normalize_results([item()], freshness=True, now=NOW, policy=POLICY)
    calls, invocations = [], []
    report = {
        "source_id": "R1",
        "text": "Report fact",
        "title": "Report",
        "url": "https://eia.gov/a",
        "published_at": "2025-10-07",
        "page": 1,
        "numeric_verified": True,
    }
    monkeypatch.setattr(pipeline, "model_ready", lambda: True)
    monkeypatch.setattr(
        pipeline, "ReportIndex", lambda: SimpleNamespace(search=lambda *a, **k: [report])
    )

    def web(query, freshness):
        calls.append(query)
        return {"evidence": sources, "warnings": []}

    def invoke(schema, messages):
        invocations.append(schema)
        if schema is Route:
            return Route(intent="domain_qa", freshness_required=False), {"total_tokens": 10}
        rows = json.loads(messages[1][1])["reports"]
        source = next((r for r in rows if r["source_id"].startswith("W")), rows[0])
        return ReportDraft(
            abstain=abstain,
            claims=[
                ReportClaim(
                    text="Издатель сообщает факт",
                    source_id=source["source_id"],
                    quote=source["text"],
                )
            ],
        ), {"total_tokens": 20}

    monkeypatch.setattr(pipeline, "search_web", web)
    monkeypatch.setattr(pipeline, "invoke_structured", invoke)
    result = pipeline.answer_question("Oil news today" if freshness else "Oil report fact")
    assert len(calls) == int(freshness or abstain)
    assert len(invocations) <= 3
    if abstain:
        assert result["status"] == "partial"
        assert "extractive_fallback" in result["warnings"]
        assert result["usage"]["web_synthesis"]["total_tokens"] == 20
    else:
        assert result["status"] == "answered"
        assert ("W1" if freshness else "R1") in result["answer"]


def test_official_rss_topic_filter_does_not_match_publisher_boilerplate(monkeypatch):
    from contextlib import nullcontext

    from analyst.feeds import official_news

    xml = b"""<rss><channel><item><title>Solar storage</title>
    <description>EIA reports solar battery additions.</description>
    <pubDate>Thu, 29 Oct 2026 09:00:00 -0500</pubDate></item>
    <item><title>LNG imports</title><description>Natural gas imports increased.</description>
    <pubDate>Thu, 29 Oct 2026 09:00:00 -0500</pubDate></item></channel></rss>"""
    response = SimpleNamespace(raise_for_status=lambda: None, iter_bytes=lambda: iter([xml]))
    monkeypatch.setattr("analyst.feeds.httpx.stream", lambda *a, **k: nullcontext(response))
    rows = official_news("EIA latest natural gas news")
    assert rows and {r["title"] for r in rows} == {"LNG imports"}
