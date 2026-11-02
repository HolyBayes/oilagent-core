from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetrievalPolicy(BaseModel):
    """Bounded selection strategy for ranked report evidence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    comparison_strategy: Literal["pooled", "per_publisher"] = "pooled"
    top_k_per_publisher: int = Field(default=2, ge=2, le=4)
    reranker: Literal["vector", "bm25"] = "vector"


class Route(BaseModel):
    """Classify an oil/gas request and whether it needs fresh evidence."""

    model_config = ConfigDict(extra="forbid")
    intent: Literal["domain_qa", "forecast", "scenario", "out_of_scope", "clarify"]
    freshness_required: bool
    horizon_months: int = 3
    as_of: str = ""
    instrument: str = "Brent"
    start_date: str = ""
    end_date: str = ""
    metric: str = ""
    geography: str = ""
    reference_period: str = ""
    publishers: list[str] = Field(default_factory=list)
    quote_requested: bool = False
    hybrid: bool = False
    report_query: str = ""
    compare: bool = False
    scenario_inputs: dict = Field(default_factory=dict)
    scenario_price: float = 0
    scenario_supply_mbd: float = 0
    scenario_cut_mbd: float = 0
    demand_elasticity_low: float = 0
    demand_elasticity_high: float = 0
    supply_elasticity_low: float = 0
    supply_elasticity_high: float = 0
    web_query: str = ""


class CriticVerdict(BaseModel):
    """Review an exact candidate diff and return findings with an admission verdict."""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["APPROVE", "REQUEST_CHANGES", "REJECT"]
    findings: list[str]


class ReportClaim(BaseModel):
    """A sourced fact with its source ID and a verbatim supporting passage."""

    text: str
    source_id: str
    quote: str
    kind: Literal["fact", "assumption"] = "fact"
    value: str = ""
    unit: str = ""
    period: str = ""
    metric: str = ""
    geography: str = ""
    vintage: str = ""
    observation_type: Literal["actual", "estimate", "forecast", "unspecified"] = "unspecified"


class ReportDraft(BaseModel):
    """Answer only with supported PDF or web claims; abstain when evidence is missing."""

    claims: list[ReportClaim] = Field(max_length=5)
    abstain: bool
    missing: list[str] = Field(default_factory=list)
