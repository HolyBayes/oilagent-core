"""Backend authorization from native skill state, independent of model instructions."""

import asyncio
import inspect
import json
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

import httpx
from dotenv import load_dotenv

from analyst.config import CORE_ROOT

_evaluation = ContextVar("trusted_capability_evaluation", default=False)


class CapabilityDisabled(ValueError):
    pass


def native_states():
    load_dotenv(CORE_ROOT / ".env", override=False)
    url = os.getenv("NATIVE_UI_URL") or "http://127.0.0.1:" + os.getenv("UI_PORT", "8765")
    with httpx.Client(trust_env=False, timeout=3) as client:
        response = client.get(url.rstrip("/") + "/api/extensions")
        response.raise_for_status()
        rows = response.json()["skills"]
    names = [row["name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("Ambiguous native skill identity")
    return {row["name"]: row for row in rows}


def require_skill(name):
    if _evaluation.get():
        return
    try:
        state = native_states().get(name, {})
    except Exception as exc:
        raise CapabilityDisabled("Состояние навыков недоступно; выполнение запрещено.") from exc
    if (
        state.get("enabled") is not True
        or state.get("executable_review") is not True
        or state.get("review_stale") is not False
    ):
        raise CapabilityDisabled(f"Навык {name} отключён или не имеет действующего review.")


def requires_skill(name):
    def decorate(function):
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def guarded_async(*args, **kwargs):
                await asyncio.to_thread(require_skill, name)
                return await function(*args, **kwargs)

            return guarded_async

        @wraps(function)
        def guarded(*args, **kwargs):
            require_skill(name)
            return function(*args, **kwargs)

        return guarded

    return decorate


@contextmanager
def trusted_evaluation():
    """Internal fixed evaluation/bootstrap only; never an MCP argument or environment flag."""
    token = _evaluation.set(True)
    try:
        yield
    finally:
        _evaluation.reset(token)


def owners_for(kind):
    owners = json.loads((CORE_ROOT / "config/capabilities.json").read_text())[kind]
    public = {("analyst", "health"), ("evolution", "get_status")}
    for name, owner in owners.items():
        if owner is None and (kind, name) in public:
            continue
        if not isinstance(owner, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", owner):
            raise ValueError(f"Invalid capability owner: {kind}/{name}")
    return owners


def tool_owner(kind, name):
    owners = owners_for(kind)
    if name not in owners:
        raise CapabilityDisabled(f"Module has no capability owner: {kind}/{name}")
    return owners[name]


def can_use(name):
    try:
        require_skill(name)
        return True
    except CapabilityDisabled:
        return False


def install_tool_gates(server, kind):
    owners = owners_for(kind)
    register = server.tool

    def tool(*args, **kwargs):
        def decorate(function):
            name = kwargs.get("name") or function.__name__
            if name not in owners:
                raise ValueError(f"MCP tool has no capability owner: {kind}/{name}")
            guarded = requires_skill(owners[name])(function) if owners[name] else function
            return register(*args, **kwargs)(guarded)

        return decorate

    server.tool = tool
