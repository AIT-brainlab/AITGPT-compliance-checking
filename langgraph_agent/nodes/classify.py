from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.llm_cache import get_cache

from langchain_core.messages import HumanMessage

from langgraph_agent.llm import DEFAULT_MODEL, get_llm
from langgraph_agent.state import PipelineState, RuleItem, SentenceItem

_cache = get_cache()
_llm = get_llm()

CONFIDENCE_HIGH = 0.6
CONFIDENCE_LOW = 0.4

_CLASSIFY_PROMPT = """\
You are a legal policy analyst specialising in institutional policy documents.

Classify whether the sentence below is a POLICY RULE — a deontic statement that \
creates a binding obligation, grants a permission, or imposes a prohibition.

IMPORTANT DISTINCTIONS:
- "may be X-ed" / "may have" / "may entail" = DESCRIPTIVE possibility, NOT a rule.
  Example: "Research may be sponsored by agencies." → NOT A RULE (describes what CAN happen).
- "may apply for" / "may request" / "may use" = PERMISSION (deontic rule).
  Example: "Students may apply for leave." → PERMISSION RULE (grants a right).
- "may not" = always a PROHIBITION.

Context hints:
- Deontic strength: {deontic_strength}
- Speech act: {speech_act}
- Section: {section}

Sentence:
"{text}"

Respond with ONLY a JSON object (no markdown, no explanation):
{{"is_rule": true/false, \
"rule_type": "obligation"/"permission"/"prohibition"/"none", \
"confidence": 0.0-1.0, \
"reasoning": "one concise sentence"}}"""


def _build_prompt(item: SentenceItem, hint: dict) -> str:
    return _CLASSIFY_PROMPT.format(
        text=item["text"],
        deontic_strength=hint.get("deontic_strength", "unknown"),
        speech_act=hint.get("speech_act", "unknown"),
        section=hint.get("section_context", "unknown"),
    )


def _parse_response(raw: str) -> dict:
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        return {"is_rule": False, "rule_type": "none", "confidence": 0.0,
                "reasoning": "parse_error"}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"is_rule": False, "rule_type": "none", "confidence": 0.0,
                "reasoning": "json_decode_error"}


def classify_node(state: PipelineState) -> PipelineState:
    candidates: List[SentenceItem] = state["candidates"]
    model = DEFAULT_MODEL
    errors: List[str] = []

    rules: List[RuleItem] = []
    uncertain: List[RuleItem] = []

    # Gather prefilter hints if available (prefilter stores them in candidates)
    # If not available, use empty dict — classify still works without hints
    from tqdm import tqdm
    for i, item in enumerate(tqdm(candidates, desc="Classifying", leave=False)):
        text = item["text"]

        # Read prefilter hints from the enriched SentenceItem
        hint = {
            "deontic_strength": item.get("deontic_strength", "unknown"),
            "speech_act":       item.get("speech_act", "unknown"),
            "section_context":  item.get("section_context", "unknown"),
        }
        boost = float(item.get("confidence_boost", 0.0))

        # §7 — Ablation: strip hints if no-hints ablation is active
        if os.getenv("ABLATION_NO_HINTS", "0") == "1":
            hint = {"deontic_strength": "unknown", "speech_act": "unknown",
                    "section_context": "unknown"}
            boost = 0.0

        # Include hints in cache key so hint changes invalidate stale entries
        cache_params = {
            "deontic_strength": hint["deontic_strength"],
            "speech_act": hint["speech_act"],
            "prompt_version": 2,
        }

        # --- cache check ---
        cached = _cache.get(text, model, "classification", extra_params=cache_params)
        if cached:
            result = cached
        else:
            try:
                prompt = _build_prompt(item, hint)
                response = _llm.invoke([HumanMessage(content=prompt)])
                result = _parse_response(response.content)
                _cache.set(text, model, "classification", result, extra_params=cache_params)
            except Exception as exc:
                errors.append(f"classify[{i}]: {exc}")
                result = {"is_rule": False, "rule_type": "none",
                          "confidence": 0.0, "reasoning": str(exc)}

        if not result.get("is_rule"):
            continue

        # Sanitise inconsistent LLM output: is_rule=True but rule_type missing
        if result.get("rule_type") in ("none", None, ""):
            result["rule_type"] = "obligation"  # conservative default
            result["confidence"] = max(float(result.get("confidence", 0.5)) - 0.1, 0.4)

        # Apply prefilter confidence boost (additive, clamped to [0, 1])
        raw_conf = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, raw_conf + boost))
        rule_id = f"AIT-{i:04d}"

        rule = RuleItem(
            rule_id=rule_id,
            text=text,
            source_document=item["source"],
            rule_type=result.get("rule_type", "obligation"),
            confidence=confidence,
            prefilter_strength=hint["deontic_strength"],
            section_context=hint["section_context"],
        )

        if confidence >= CONFIDENCE_HIGH:
            rules.append(rule)
        elif confidence >= CONFIDENCE_LOW:
            uncertain.append(rule)
        # below CONFIDENCE_LOW → discard

    return {
        "rules": rules,
        "uncertain_rules": uncertain,
        "current_step": "classify",
        "errors": errors,
    }
