"""Load released methods by content; never import an evolved module into the host."""

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar

from analyst.code_packages import artifact, seed_source, validate_source
from analyst.config import configured_path

method_pin = ContextVar("method_pin", default=None)

method_overrides = ContextVar("method_overrides", default={})


def code_root():
    return configured_path("RELEASE_PATH", "workspace/releases") / "code"


def active_bundle():
    pointer = code_root() / "active.json"
    if not pointer.exists():
        return None
    from analyst.code_releases import read_bundle

    return read_bundle(json.loads(pointer.read_text())["release_id"])


def source_for(slot):
    overrides = method_overrides.get()
    if slot in overrides:
        return overrides[slot]
    pin = method_pin.get()
    if pin is not None:
        return pin[slot]
    bundle = active_bundle()
    return bundle["files"][artifact(slot)] if bundle else seed_source(slot)


def method_digest(slot):
    return validate_source(slot, source_for(slot))


def run_many(slot, inputs, source=None):
    from analyst.code_executor import run_many as execute

    if (code_root() / "maintenance.json").exists():
        raise ValueError("Capability release is being activated")
    source = source if source is not None else source_for(slot)
    validate_source(slot, source)
    results, _ = execute(source, inputs)
    return results


def run(slot, payload, source=None):
    return run_many(slot, [payload], source)[0]


@contextmanager
def method_session():
    if method_pin.get() is not None:
        yield
        return
    from analyst.code_packages import SLOTS

    bundle = active_bundle()
    sources = {
        slot: bundle["files"][artifact(slot)] if bundle else seed_source(slot) for slot in SLOTS
    }
    token = method_pin.set(sources)
    try:
        yield
    finally:
        method_pin.reset(token)


def native_source(default):
    for filename in ["prepared.json", "active.json"]:
        pointer = code_root() / filename
        if pointer.exists():
            release_id = json.loads(pointer.read_text())["release_id"]
            # Native has no evaluator or numerical data: verify the manifest's
            # content identity here; full evaluation identity is checked by core.
            raw = (code_root() / "bundles" / f"{release_id}.json").read_bytes()
            if hashlib.sha256(raw).hexdigest() != release_id:
                raise ValueError("Native package manifest corrupted")
            return code_root() / "packages" / release_id / "ouroboros_skills"
    return default
