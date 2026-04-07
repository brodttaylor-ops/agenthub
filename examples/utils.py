"""Robust JSON extraction from Claude responses.

Claude doesn't always return clean JSON even when prompted for it.
This runs on every job grading response (hundreds per week) and every
email classification. The fallback chain:

1. Strip markdown code fences and parse the content inside
2. Try parsing the raw text directly
3. Regex for the first {...} or [...] block and parse that

In production, this eliminated ~5% of grading failures that were caused
by Claude wrapping valid JSON in conversational text or markdown.
"""

import json
import re


def extract_json(text: str) -> dict | list | None:
    """Best-effort JSON extraction from LLM responses."""

    # Strategy 1: Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts[1::2]:  # odd-indexed parts are inside fences
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue

    # Strategy 2: Try the raw text
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 3: Regex for first JSON-like block
    for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue

    return None
