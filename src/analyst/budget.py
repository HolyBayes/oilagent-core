import math
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

current_budget = ContextVar("oilagent_budget", default=None)


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    started: float = field(default_factory=time.monotonic)
    llm_calls: int = 0
    tool_calls: int = 0
    input_bytes: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    events: list = field(default_factory=list)
    accounted_calls: int = 0
    repairs: int = 0
    held_cost: float = 0
    pending_reservations: list = field(default_factory=list)

    def check(self):
        if time.monotonic() - self.started > float(os.getenv("REQUEST_TIMEOUT_SEC", "120")):
            raise BudgetExceeded("request_time")

    def tool(self, name):
        self.check()
        if self.tool_calls >= int(os.getenv("REQUEST_MAX_TOOLS", "6")):
            raise BudgetExceeded("tool_calls")
        self.tool_calls += 1
        self.events.append({"tool": name, "at_sec": round(time.monotonic() - self.started, 4)})

    def repair(self):
        self.check()
        if self.repairs >= 1:
            raise BudgetExceeded("repair_limit")
        self.repairs += 1

    def reserve_llm(self, messages):
        self.check()
        size = sum(len(text.encode()) for _, text in messages)
        if self.llm_calls >= int(os.getenv("REQUEST_MAX_LLM_CALLS", "4")):
            raise BudgetExceeded("llm_calls")
        # UTF-8 bytes conservatively bound text tokens; schemas are bounded separately.
        if self.input_bytes + size > int(os.getenv("REQUEST_MAX_INPUT_BYTES", "96000")):
            raise BudgetExceeded("input_bytes")
        cap = float(os.getenv("REQUEST_MAX_COST", "0"))
        reserve = 0
        if cap:
            incoming = os.getenv("LLM_INPUT_PRICE_PER_MILLION")
            outgoing = os.getenv("LLM_OUTPUT_PRICE_PER_MILLION")
            bound = os.getenv("LLM_MAX_OUTPUT_TOKENS", "").strip()
            if not incoming or not outgoing or not bound.isdigit():
                raise BudgetExceeded("money_cap_requires_prices_and_explicit_output_bound")
            if any(not math.isfinite(float(v)) or float(v) < 0 for v in (incoming, outgoing)):
                raise BudgetExceeded("invalid_price_config")
            spent = (
                self.input_tokens * float(incoming) + self.output_tokens * float(outgoing)
            ) / 1e6
            reserve = (size * float(incoming) + int(bound) * float(outgoing)) / 1e6
            if spent + self.held_cost + reserve > cap:
                raise BudgetExceeded("money_reservation")
        self.held_cost += reserve
        self.pending_reservations.append(reserve)
        self.llm_calls += 1
        self.input_bytes += size

    def account(self, usage):
        if "input_tokens" not in usage or "output_tokens" not in usage:
            self.check()
            return
        self.accounted_calls += 1
        if self.pending_reservations:
            # Calls are serialized; failed calls retain their reservation until request end.
            self.held_cost -= self.pending_reservations.pop()
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        if self.input_tokens > int(os.getenv("REQUEST_MAX_INPUT_TOKENS", "24000")):
            raise BudgetExceeded("input_tokens")
        self.check()

    def summary(self):
        incoming, outgoing = (
            os.getenv("LLM_INPUT_PRICE_PER_MILLION"),
            os.getenv("LLM_OUTPUT_PRICE_PER_MILLION"),
        )
        cost = (
            (self.input_tokens * float(incoming) + self.output_tokens * float(outgoing)) / 1e6
            if incoming and outgoing
            else None
        )
        return {
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "repairs": self.repairs,
            "unknown_cost_reservation": self.held_cost,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "elapsed_sec": round(time.monotonic() - self.started, 4),
            "estimated_cost": cost,
            "cost_currency": os.getenv("LLM_PRICE_CURRENCY", "RUB") if cost is not None else None,
            "hard_money_guarantee": False,
            "reservation_enabled": bool(float(os.getenv("REQUEST_MAX_COST", "0"))),
            "usage_complete": self.accounted_calls == self.llm_calls,
            "unknown_usage_calls": self.llm_calls - self.accounted_calls,
            "events": self.events,
        }


def tool_call(name):
    budget = current_budget.get()
    if budget:
        budget.tool(name)
