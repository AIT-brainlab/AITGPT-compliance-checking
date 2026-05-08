from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.llm_cache import get_cache

from langchain_core.messages import HumanMessage

from langgraph_agent.llm import DEFAULT_MODEL, get_llm
from langgraph_agent.state import PipelineState, RuleItem, SHACLShape

_cache = get_cache()
_llm = get_llm()

MAX_REPAIR_ATTEMPTS = 2
DIRECT_SHACL_PROMPT_VERSION = "v1"

_SHACL_PREFIXES = """\
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix ait:  <http://example.org/ait-policy#> .
"""

_DIRECT_PROMPT = """\
Translate this policy rule DIRECTLY into a valid SHACL NodeShape in Turtle syntax.

Rule type: {rule_type}
Rule text: "{text}"

Requirements:
- Use these prefixes: ait: <http://example.org/ait-policy#>  sh: <http://www.w3.org/ns/shacl#>
- The shape MUST be a sh:NodeShape with sh:targetClass, sh:severity, sh:property
- Obligations  → sh:minCount 1  and sh:severity sh:Violation
- Prohibitions → sh:maxCount 0  and sh:severity sh:Violation
- Permissions  → sh:severity sh:Info

Shape name: ait:{shape_id}Shape

Return ONLY the Turtle block for this shape. No explanations, no markdown fences."""

_REPAIR_PROMPT = """\
The following SHACL Turtle has a syntax error. Fix it and return ONLY the corrected Turtle.
Do NOT add markdown fences. Return raw Turtle only.

Original Turtle:
{turtle}

Error: {error}

Return ONLY valid Turtle. No explanations, no markdown fences."""


def _validate_turtle(text: str) -> Tuple[bool, str]:
    """Validate Turtle syntax. Returns (is_valid, error_message)."""
    try:
        from rdflib import Graph
        g = Graph()
        g.parse(data=_SHACL_PREFIXES + "\n" + text, format="turtle")
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _strip_fences(text: str) -> str:
    """Strip markdown code fences if model wrapped the output."""
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


def _repair_turtle(turtle: str, error: str, rule_id: str) -> Tuple[str, bool]:
    """Attempt to repair invalid Turtle by re-prompting the LLM with the error.
    Returns (repaired_turtle, is_valid)."""
    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        try:
            prompt = _REPAIR_PROMPT.format(turtle=turtle, error=error)
            response = _llm.invoke([HumanMessage(content=prompt)])
            repaired = _strip_fences(response.content.strip())
            valid, new_error = _validate_turtle(repaired)
            if valid:
                return repaired, True
            # Update for next attempt
            turtle = repaired
            error = new_error
        except Exception:
            break  # LLM call failed, stop retrying
    return turtle, False


def direct_shacl_node(state: PipelineState) -> PipelineState:
    # §7 — Ablation: skip direct NL fallback entirely
    import os
    if os.getenv("ABLATION_SKIP_DIRECT_SHACL", "0") == "1":
        return {"shacl_shapes": [], "errors": ["ablation: direct_shacl skipped"]}

    failed_rules: List[RuleItem] = state.get("fol_failed", [])
    model = DEFAULT_MODEL
    errors: List[str] = []

    new_shapes: List[SHACLShape] = []

    from tqdm import tqdm
    for rule in tqdm(failed_rules, desc="Direct SHACL", leave=False):
        text = rule["text"]
        shape_id = rule["rule_id"].replace("-", "_")

        cached = _cache.get(text, model, "direct_shacl",
                            extra_params={"prompt_version": DIRECT_SHACL_PROMPT_VERSION})
        if cached:
            turtle = cached.get("turtle", "")
            valid = cached.get("valid", False)
        else:
            try:
                prompt = _DIRECT_PROMPT.format(
                    text=text,
                    rule_type=rule["rule_type"],
                    shape_id=shape_id,
                )
                response = _llm.invoke([HumanMessage(content=prompt)])
                turtle = _strip_fences(response.content.strip())
                valid, parse_error = _validate_turtle(turtle)

                # ── Repair loop: re-prompt LLM with the error ──
                if not valid and turtle:
                    turtle, valid = _repair_turtle(
                        turtle, parse_error, rule["rule_id"]
                    )

                _cache.set(text, model, "direct_shacl",
                           {"turtle": turtle, "valid": valid},
                           extra_params={"prompt_version": DIRECT_SHACL_PROMPT_VERSION})
            except Exception as exc:
                errors.append(f"direct_shacl[{rule['rule_id']}]: {exc}")
                turtle = ""
                valid = False

        if turtle:
            new_shapes.append(SHACLShape(
                rule_id=rule["rule_id"],
                turtle_text=turtle,
                target_class="Unknown",  # harder to infer from raw LLM output
                deontic_type=rule["rule_type"],
                syntax_valid=valid,
                generation_method="direct_nl",
            ))

    return {
        "shacl_shapes": new_shapes,
        "errors": errors,
    }
