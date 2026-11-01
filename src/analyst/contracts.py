from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetrievalPolicy(BaseModel):
    """Bounded selection strategy for ranked report evidence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    comparison_strategy: Literal["pooled", "per_publisher"] = "pooled"
    top_k_per_publisher: int = Field(default=2, ge=2, le=4)


class Route(BaseModel):
    """Classify an oil/gas request and whether it needs fresh evidence."""

    model_config = ConfigDict(extra="forbid")
    intent: Literal["domain_qa", "forecast", "scenario", "out_of_scope", "clarify"]
    freshness_required: bool


class CriticVerdict(BaseModel):
    """Review an exact candidate diff and return findings with an admission verdict."""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["APPROVE", "REQUEST_CHANGES", "REJECT"]
    findings: list[str]


class ReportClaim(BaseModel):
    """A report fact with its source ID and a verbatim supporting passage."""

    text: str
    source_id: str
    quote: str


class ReportDraft(BaseModel):
    """Answer only with supported report claims; abstain when evidence is missing."""

    claims: list[ReportClaim] = Field(max_length=5)
    abstain: bool
