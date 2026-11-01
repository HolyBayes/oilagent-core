from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetrievalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    comparison_strategy: Literal["pooled", "per_publisher"] = "pooled"
    top_k_per_publisher: int = Field(default=2, ge=2, le=4)


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["domain_qa", "forecast", "scenario", "out_of_scope", "clarify"]
    freshness_required: bool


class CriticVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["APPROVE", "REQUEST_CHANGES", "REJECT"]
    findings: list[str]
