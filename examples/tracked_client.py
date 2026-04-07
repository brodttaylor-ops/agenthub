"""Cost-tiered API routing — drop-in Anthropic client wrapper.

Wraps every messages.create() call with token counting and cost estimation.
Accumulates totals across the bot's lifetime. The bot exposes a !costs
command that reads from get_usage_summary().

Design choice: wrapping at the client level (not the agent level) means
every API call is tracked regardless of which agent makes it — including
one-off calls in the general router or the email classifier.
"""

import logging
import anthropic

log = logging.getLogger("agenthub.costs")

# Approximate costs per million tokens (as of April 2026)
MODEL_COSTS = {
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":   {"input": 15.00, "output": 75.00},
}

# Accumulate across the bot's lifetime (reset on restart)
_totals = {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "estimated_cost_usd": 0.0,
}


def get_usage_summary() -> dict:
    """Return a copy of accumulated usage stats."""
    return dict(_totals)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a single API call."""
    # Match model name to pricing (handle version suffixes)
    costs = None
    for key in MODEL_COSTS:
        if key in model:
            costs = MODEL_COSTS[key]
            break
    if costs is None:
        costs = MODEL_COSTS["claude-sonnet-4-6"]  # safe default

    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


class _TrackedMessages:
    """Wraps the messages API to log usage after each create() call."""

    def __init__(self, messages_api):
        self._api = messages_api

    def create(self, **kwargs):
        response = self._api.create(**kwargs)

        model = kwargs.get("model", "unknown")
        usage = response.usage
        input_t = getattr(usage, "input_tokens", 0)
        output_t = getattr(usage, "output_tokens", 0)
        cost = _estimate_cost(model, input_t, output_t)

        _totals["calls"] += 1
        _totals["input_tokens"] += input_t
        _totals["output_tokens"] += output_t
        _totals["estimated_cost_usd"] += cost

        log.debug(
            f"API call: model={model} in={input_t} out={output_t} "
            f"cost=${cost:.4f} total=${_totals['estimated_cost_usd']:.4f}"
        )

        return response


class TrackedClient:
    """Drop-in replacement for anthropic.Anthropic() with usage tracking.

    Usage:
        # Instead of: client = anthropic.Anthropic()
        client = TrackedClient()

        # Everything else works the same
        response = client.messages.create(model=..., messages=...)

        # Check accumulated costs
        print(get_usage_summary())
    """

    def __init__(self, **kwargs):
        self._client = anthropic.Anthropic(**kwargs)
        self.messages = _TrackedMessages(self._client.messages)

    def __getattr__(self, name):
        # Forward anything else (beta, completions, etc.) to the real client
        return getattr(self._client, name)
