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
from langgraph_agent.state import FOLItem, PipelineState, RuleItem

_cache = get_cache()
_llm = get_llm()

_FOL_PROMPT = """\
You are a formal logician specialising in deontic logic for institutional policy.

Convert the policy rule below into a First-Order Logic (FOL) formula using \
deontic operators:
  O(φ) — Obligation: the subject MUST perform φ
  P(φ) — Permission: the subject MAY perform φ
  F(φ) — Prohibition (Forbidden): the subject MUST NOT perform φ

Rule type: {rule_type}
Rule text: "{text}"

Output ONLY a JSON object (no markdown):
{{
  "deontic_type": "obligation"/"permission"/"prohibition",
  "deontic_formula": "O/P/F(predicate(subject))",
  "fol_expansion": "∀x (Subject(x) ∧ Condition(x) → O/P/F(Action(x)))",
  "predicates": {{"subject": "...", "action": "...", "condition": "..."}},
  "shacl_hint": "brief hint for SHACL translation"
}}"""


FOL_PROMPT_VERSION = 2

_PLACEHOLDER_PREDS = re.compile(
    r"[OPF]\(\s*(Action|Subject|Predicate|Condition|Thing|Entity|x|y|z|\?\w)\s*[()]",
    re.IGNORECASE,
)


def _parse_fol(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        # Validate minimum required fields
        if "deontic_formula" in data and "fol_expansion" in data:
            return data
        return None
    except json.JSONDecodeError:
        return None


def _is_placeholder(parsed: dict) -> bool:
    formula = parsed.get("deontic_formula", "")
    if _PLACEHOLDER_PREDS.search(formula):
        return True
    # Also check predicates dict if available
    preds = parsed.get("predicates") or {}
    if isinstance(preds, dict):
        action = preds.get("action", "").lower()
        if action in ("action", "subject", "predicate", "condition", "thing", "entity"):
            return True
    return False


_FOL_RETRY_PROMPT = """\
Your previous FOL formalization used placeholder predicates like "Action" or single letters.
That is not acceptable — use SEMANTIC predicates derived from the rule's actual action.

Rule type: {rule_type}
Rule text: "{text}"
Previous (BAD) formula: {bad_formula}

Rules:
- The inner predicate must name the actual action (e.g., "payFee", "submitThesis", "attendMeeting").
- Use snake_case or camelCase derived from the rule's main verb phrase.
- Do NOT use: Action, Subject, Predicate, Condition, or any single letter.

Output ONLY a JSON object:
{{
  "deontic_type": "obligation"/"permission"/"prohibition",
  "deontic_formula": "O/P/F(semanticPredicate(subject))",
  "fol_expansion": "...",
  "predicates": {{"subject": "...", "action": "...", "condition": "..."}}
}}"""


def _generate_with_retry(text: str, rule_type: str, max_retries: int = 1) -> dict | None:
    """Generate FOL, retry with stricter prompt if placeholder detected."""
    # §7 — Ablation: disable retry loop
    if os.getenv("ABLATION_NO_FOL_RETRY", "0") == "1":
        max_retries = 0
    prompt = _FOL_PROMPT.format(text=text, rule_type=rule_type)
    response = _llm.invoke([HumanMessage(content=prompt)])
    parsed = _parse_fol(response.content)

    if not parsed:
        return None

    for attempt in range(max_retries):
        if not _is_placeholder(parsed):
            return parsed
        # Re-prompt with the bad example
        retry_prompt = _FOL_RETRY_PROMPT.format(
            text=text, rule_type=rule_type,
            bad_formula=parsed.get("deontic_formula", ""),
        )
        response = _llm.invoke([HumanMessage(content=retry_prompt)])
        parsed = _parse_fol(response.content) or parsed

    # If still placeholder after retry, tag it 
    if _is_placeholder(parsed):
        parsed["_placeholder_flag"] = True
    return parsed


def fol_node(state: PipelineState) -> PipelineState:
    rules: List[RuleItem] = state["rules"]
    model = DEFAULT_MODEL
    errors: List[str] = []

    fol_formulas: List[FOLItem] = []
    fol_failed: List[RuleItem] = []

    from tqdm import tqdm
    for rule in tqdm(rules, desc="Generating FOL", leave=False):
        text = rule["text"]
        rule_type = rule["rule_type"]

        # --- cache check ---
        cached = _cache.get(text, model, "fol_generation",
                            extra_params={"rule_type": rule_type,
                                          "prompt_version": FOL_PROMPT_VERSION})
        if cached:
            parsed = cached
        else:
            try:
                parsed = _generate_with_retry(text, rule_type)
                if parsed:
                    _cache.set(text, model, "fol_generation", parsed,
                               extra_params={"rule_type": rule_type,
                                             "prompt_version": FOL_PROMPT_VERSION})
            except Exception as exc:
                errors.append(f"fol[{rule['rule_id']}]: {exc}")
                parsed = None

        if parsed:
            # Note: We keep placeholder rules but tag them.
            # Downstream direct_shacl fallback can optionally route them if wanted.
            item = FOLItem(
                rule_id=rule["rule_id"],
                text=text,
                deontic_type=parsed.get("deontic_type", rule_type),
                deontic_formula=parsed.get("deontic_formula", ""),
                fol_expansion=parsed.get("fol_expansion", ""),
                parse_success=True,
            )
            item["predicates"] = parsed.get("predicates", {})
            fol_formulas.append(item)
        else:
            fol_failed.append(rule)

    return {
        "fol_formulas": fol_formulas,
        "fol_failed": fol_failed,
        "current_step": "fol",
        "errors": errors,
    }
