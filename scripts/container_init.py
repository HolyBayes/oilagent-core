"""Idempotent preparation of the domain Git and public report index."""

from analyst.config import evolution_repo, workspace
from analyst.evolution import Evolution
from analyst.rag import ReportIndex

Evolution(workspace(), evolution_repo())
index = ReportIndex()
index.download()
index.ingest()
print("Domain Git and report index prepared; no LLM calls.")
