"""Idempotent preparation of the domain Git and public report index."""

from analyst.code_packages import SLOTS, artifact
from analyst.code_releases import read_bundle
from analyst.config import evolution_repo, workspace
from analyst.evolution import Evolution
from analyst.method_runtime import code_root, method_pin
from analyst.rag import ReportIndex

Evolution(workspace(), evolution_repo())
prepared = code_root() / "prepared.json"
token = None
if prepared.exists():
    import json

    bundle = read_bundle(json.loads(prepared.read_text())["release_id"])
    token = method_pin.set({slot: bundle["files"][artifact(slot)] for slot in SLOTS})
try:
    index = ReportIndex()
    index.download()
    index.ingest()
finally:
    if token is not None:
        method_pin.reset(token)
print("Domain Git and report index prepared; no LLM calls.")
