from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

# import sys
# sys.path.insert(0, str(Path(__file__).parent.parent.parent))
# from core.llm_cache import get_cache
 
from policy_checker.core.llm_cache import get_cache, prompt_key
from policy_checker.langgraph_agent.llm import DEFAULT_MODEL, get_llm
from policy_checker.langgraph_agent.nodes.common import cached_or_generate, invoke_text
from policy_checker.langgraph_agent.state import PipelineState, RuleItem, SHACLShape
from policy_checker.langgraph_agent.corpus_config import get_corpus_config

_cache = get_cache()
_llm_instance = None


def _get_llm():
    """Lazy LLM initialization."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm()
    return _llm_instance

MAX_REPAIR_ATTEMPTS = 2
DIRECT_SHACL_PROMPT_VERSION = "v1"

def _get_shacl_prefixes() -> str:
    """Generate SHACL prefixes from corpus config."""
    cfg = get_corpus_config()
    return (
        f"@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        f"@prefix sh:   <http://www.w3.org/ns/shacl#> .\n"
        f"@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .\n"
        f"@prefix {cfg.prefix}:  <{cfg.namespace}> .\n"
    )



_DIRECT_PROMPT = """\
Translate this policy rule DIRECTLY into a valid SHACL NodeShape in Turtle syntax.

Rule type: {rule_type}
Rule text: "{text}"

Requirements:
- Use the namespace prefix {ns_prefix}: <{namespace}>  and  sh: <http://www.w3.org/ns/shacl#>
- The shape MUST be a sh:NodeShape with sh:targetClass, sh:severity, sh:property
- Obligations  -> sh:minCount 1  and sh:severity sh:Violation
- Prohibitions -> sh:maxCount 0  and sh:severity sh:Violation
- Permissions  -> sh:severity sh:Info

Shape name: {ns_prefix}:{shape_id}Shape

Return ONLY the Turtle block for this shape. No explanations, no markdown fences."""

_REPAIR_PROMPT = """\
The following SHACL Turtle has a syntax error. Fix it and return ONLY the corrected Turtle.
Do NOT add markdown fences. Return raw Turtle only.

Original Turtle:
{turtle}

Error: {error}

Return ONLY valid Turtle. No explanations, no markdown fences."""

'''
def _validate_turtle(text: str) -> Tuple[bool, str]:
    """Validate Turtle syntax and basic SHACL rules. Returns (is_valid, error_message)."""
    try:
        from rdflib import Graph

        g = Graph()
        g.parse(data=_get_shacl_prefixes() + "\n" + text, format="turtle")
        return True, ""
    except Exception as exc:
        return False, str(exc)
'''

def _validate_turtle(text: str) -> Tuple[bool, str]:
    """Validate Turtle syntax and basic SHACL rules. Returns (is_valid, error_message)."""
    try:
        from rdflib import Graph

        g = Graph()
        g.parse(data=_get_shacl_prefixes() + "\n" + text, format="turtle")
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _strip_fences(text: str) -> str:
    """Strip markdown code fences if model wrapped the output."""
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


def _repair_turtle(turtle: str, error: str, rule_id: str) -> Tuple[str, bool]:
    """Attempt to repair invalid Turtle by re-prompting the LLM."""
    for _ in range(MAX_REPAIR_ATTEMPTS):
        try:
            prompt = _REPAIR_PROMPT.format(turtle=turtle, error=error)
            repaired = _strip_fences(invoke_text(_get_llm(), prompt).strip())
            valid, new_error = _validate_turtle(repaired)
            if valid:
                return repaired, True
            turtle = repaired
            error = new_error
        except Exception:
            break
    return turtle, False


def direct_shacl_node(state: PipelineState) -> PipelineState:
    import os
    if os.getenv("ABLATION_SKIP_DIRECT_SHACL", "0") == "1":
        return {"shacl_shapes": [], "errors": ["ablation: direct_shacl skipped"]}

    failed_rules: List[RuleItem] = state.get("fol_failed", [])
    errors: List[str] = []
    new_shapes: List[SHACLShape] = []

    from tqdm import tqdm

    for rule in tqdm(failed_rules, desc="Direct SHACL", leave=False):
        text = rule["text"]
        shape_id = rule["rule_id"].replace("-", "_")

        def _generate_direct_shape() -> dict:
            prompt = _DIRECT_PROMPT.format(
                text=text,
                rule_type=rule["rule_type"],
                shape_id=shape_id,
            )
            turtle = _strip_fences(invoke_text(_get_llm(), prompt).strip())
            valid, parse_error = _validate_turtle(turtle)

            if not valid and turtle:
                turtle, valid = _repair_turtle(turtle, parse_error, rule["rule_id"])

            return {"turtle": turtle, "valid": valid}

        try:
            cached = cached_or_generate(
                _cache,
                text,
                DEFAULT_MODEL,
                "direct_shacl",
                prompt_key(DIRECT_SHACL_PROMPT_VERSION),
                _generate_direct_shape,
            )
            turtle = cached.get("turtle", "")
            valid = cached.get("valid", False)
        except Exception as exc:
            errors.append(f"direct_shacl[{rule['rule_id']}]: {exc}")
            turtle = ""
            valid = False

        if turtle:
            new_shapes.append(SHACLShape(
                rule_id=rule["rule_id"],
                turtle_text=turtle,
                target_class="Unknown",
                deontic_type=rule["rule_type"],
                syntax_valid=valid,
                generation_method="direct_nl",
            ))

    return {
        "shacl_shapes": new_shapes,
        "errors": errors,
    }
