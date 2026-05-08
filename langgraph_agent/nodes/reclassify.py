from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.llm_cache import get_cache

from langchain_core.messages import HumanMessage

from langgraph_agent.llm import SECOND_MODEL, get_second_llm
from langgraph_agent.state import PipelineState, RuleItem

_cache = get_cache()
_llm = get_second_llm()

RECLASSIFY_PROMPT_VERSION = "v1"

# Reclassify uses a more directive prompt — no confidence band, just binary verdict
_RECLASSIFY_PROMPT = """\
You are a strict policy compliance expert. Your task is to make a FINAL \
determination on whether the sentence below is a binding policy rule.

A binding rule MUST:
1. Impose an obligation ("must", "shall", "is required to")
   OR grant a permission ("may", "is entitled to", "is allowed to")
   OR impose a prohibition ("must not", "cannot", "is prohibited from")
2. Have a clear subject (who it applies to)
3. Describe a specific action or condition

Sentence:
"{text}"

Respond with ONLY a JSON object:
{{"is_rule": true/false, \
"rule_type": "obligation"/"permission"/"prohibition"/"none", \
"confidence": 0.0-1.0, \
"reasoning": "one sentence"}}"""


def _parse(raw: str) -> dict:
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        return {"is_rule": False, "rule_type": "none", "confidence": 0.0}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"is_rule": False, "rule_type": "none", "confidence": 0.0}


def reclassify_node(state: PipelineState) -> PipelineState:
    uncertain: List[RuleItem] = state["uncertain_rules"]
    confirmed: List[RuleItem] = list(state["rules"])  # start with already-confident rules
    model = SECOND_MODEL
    errors: List[str] = []

    # §7 — Ablation: skip reclassify, drop uncertain rules
    import os
    if os.getenv("ABLATION_SKIP_RECLASSIFY", "0") == "1":
        return {
            "rules": confirmed,
            "uncertain_rules": [],
            "current_step": "reclassify",
            "errors": ["ablation: reclassify skipped"],
        }

    from tqdm import tqdm
    for rule in tqdm(uncertain, desc="Reclassifying", leave=False):
        text = rule["text"]

        cached = _cache.get(text, model, "reclassification",
                            extra_params={"prompt_version": RECLASSIFY_PROMPT_VERSION})
        if cached:
            result = cached
        else:
            try:
                prompt = _RECLASSIFY_PROMPT.format(text=text)
                response = _llm.invoke([HumanMessage(content=prompt)])
                result = _parse(response.content)
                _cache.set(text, model, "reclassification", result,
                           extra_params={"prompt_version": RECLASSIFY_PROMPT_VERSION})
            except Exception as exc:
                errors.append(f"reclassify[{rule['rule_id']}]: {exc}")
                result = {"is_rule": False}

        if result.get("is_rule") and float(result.get("confidence", 0)) > 0.5:
            confirmed.append(RuleItem(
                **{**rule,
                   "rule_type": result.get("rule_type", rule["rule_type"]),
                   "confidence": float(result.get("confidence", 0.5))}
            ))
        # else: drop the uncertain rule — second opinion says it's not a rule

    return {
        "rules": confirmed,
        "uncertain_rules": [],   # cleared — all decisions made
        "current_step": "reclassify",
        "errors": errors,
    }
