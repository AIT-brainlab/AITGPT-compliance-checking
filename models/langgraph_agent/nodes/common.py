from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage

T = TypeVar("T")


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def invoke_text(llm: Any, prompt: str) -> str:
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


def cached_or_generate(
    cache: Any,
    text: str,
    model: str,
    prompt_type: str,
    extra_params: Mapping[str, Any],
    generate: Callable[[], T],
) -> T:
    cached = cache.get(text, model, prompt_type, extra_params=dict(extra_params))
    if cached is not None:
        return cached

    result = generate()
    if result is not None:
        cache.set(text, model, prompt_type, result, extra_params=dict(extra_params))
    return result


def first_json_object(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return the first valid JSON object embedded in model output."""
    decoder = json.JSONDecoder()
    saw_object_start = False

    for index, char in enumerate(raw):
        if char != "{":
            continue

        saw_object_start = True
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed, None

    return None, "json_decode_error" if saw_object_start else "parse_error"


def parse_json_object(
    raw: str,
    default: T = None,
    required: tuple[str, ...] = (),
) -> dict[str, Any] | T:
    parsed, reason = first_json_object(raw)
    if parsed is None or any(key not in parsed for key in required):
        fallback = copy.deepcopy(default)
        if isinstance(fallback, dict) and reason and fallback.get("reasoning"):
            fallback["reasoning"] = reason
        return fallback
    return parsed
