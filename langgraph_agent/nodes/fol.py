from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.llm_cache import get_cache

from langchain_core.messages import HumanMessage

from langgraph_agent.llm import DEFAULT_MODEL, get_llm
from langgraph_agent.state import FOLItem, PipelineState, RuleItem
from langgraph_agent.corpus_config import get_corpus_config

# Fine-tuning data collection
_TRAINING_DATA_PATH = (
    Path(__file__).parent.parent.parent / "data" / "fol_training_data.jsonl"
)
_TRAINING_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def _save_training_example(text: str, rule_type: str, parsed: dict) -> None:
    """
    Save successful FOL generation as training data for potential fine-tuning.
    Only saves examples that are not placeholders.
    """
    if _is_placeholder(parsed):
        return  # Don't save placeholder examples

    try:
        training_example = {
            "prompt": _FOL_PROMPT.format(text=text, rule_type=rule_type),
            "completion": json.dumps(parsed, indent=None),
            "metadata": {
                "text": text,
                "rule_type": rule_type,
                "timestamp": str(Path(__file__).stat().st_mtime),
            },
        }

        # Append to JSONL file
        with open(_TRAINING_DATA_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(training_example) + "\n")
    except Exception:
        # Silently fail if we can't save training data
        pass


_cache = get_cache()
_llm_instance = None


def _get_llm():
    """Lazy LLM initialization — avoids import-time hangs and allows config changes."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm()
    return _llm_instance

_FOL_PROMPT = """\
You are a formal logician specialising in deontic logic for institutional policy.

Convert the policy rule below into a First-Order Logic (FOL) formula using \
deontic operators:
  O(φ) — Obligation: the subject MUST perform φ
  P(φ) — Permission: the subject MAY perform φ
  F(φ) — Prohibition (Forbidden): the subject MUST NOT perform φ

Rule type: {rule_type}
Rule text: "{text}"

DOMAIN VOCABULARY — When choosing a predicate name for the action, you MUST \
prefer one from this list of known institutional policy properties. Pick the \
one that BEST matches the rule's main action or constraint:
{vocabulary_hint}

If NO property in the list is a reasonable match, you may create a new \
camelCase predicate — but this should be rare.

EXAMPLES OF GOOD FORMALIZATIONS:
Rule: "Students must submit their thesis by the deadline."
Good: {{"deontic_type": "obligation", "deontic_formula": "O(submittitlepage(student))", "fol_expansion": "∀x (Student(x) → O(submittitlepage(x)))", "predicates": {{"subject": "student", "action": "submittitlepage", "condition": ""}}, "shacl_hint": "submittitlepage property"}}

Rule: "Faculty may attend meetings with prior approval."
Good: {{"deontic_type": "permission", "deontic_formula": "P(attendHearing(faculty))", "fol_expansion": "∀x (Faculty(x) → P(attendHearing(x)))", "predicates": {{"subject": "faculty", "action": "attendHearing", "condition": "with prior approval"}}, "shacl_hint": "attendHearing property"}}

Rule: "Students must not disturb fellow students in residential areas."
Good: {{"deontic_type": "prohibition", "deontic_formula": "F(disturbFellowStudentsInResidentialAreas(student))", "fol_expansion": "∀x (Student(x) → F(disturbFellowStudentsInResidentialAreas(x)))", "predicates": {{"subject": "student", "action": "disturbFellowStudentsInResidentialAreas", "condition": ""}}, "shacl_hint": "disturbFellowStudentsInResidentialAreas property"}}

EXAMPLES OF BAD FORMALIZATIONS TO AVOID:
Bad: {{"deontic_type": "obligation", "deontic_formula": "O(Action(x))", "fol_expansion": "...", "predicates": {{"subject": "...", "action": "Action", ...}}}}
Bad: {{"deontic_type": "prohibition", "deontic_formula": "F(Predicate(y))", "fol_expansion": "...", "predicates": {{"action": "Predicate", ...}}}}
Bad: {{"deontic_type": "permission", "deontic_formula": "P(Condition(z))", "fol_expansion": "...", "predicates": {{"action": "Condition", ...}}}}

Output ONLY a JSON object (no markdown):
{{
  "deontic_type": "obligation"/"permission"/"prohibition",
  "deontic_formula": "O/P/F(predicate(subject))",
  "fol_expansion": "∀x (Subject(x) ∧ Condition(x) → O/P/F(Action(x)))",
  "predicates": {{"subject": "...", "action": "...", "condition": "..."}},
  "shacl_hint": "brief hint for SHACL translation"
}}"""


def _get_vocabulary_hint() -> str:
    """Load vocabulary hint from corpus config (cached inside config object)."""
    cfg = get_corpus_config()
    return cfg.vocabulary_hint()


FOL_PROMPT_VERSION = 3  # v3: ontology vocabulary injection for property path alignment

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


def _extract_predicates_from_text(text: str) -> Dict[str, str]:
    """
    Extract semantic predicates from rule text using simple NLP techniques.
    Returns a dictionary with subject, action, and condition predicates.
    """
    # Convert to lowercase for processing
    text_lower = text.lower().strip()

    # Initialize result
    result = {"subject": "", "action": "", "condition": ""}

    # Common subject patterns in policy documents
    subject_patterns = [
        (r"^(students?|student)\b", "student"),
        (r"^(faculty|professor|instructor|teacher|staff)\b", "faculty"),
        (r"^(employees?|employee|worker|staff)\b", "employee"),
        (r"^(researchers?|researcher)\b", "researcher"),
        (r"^(applicants?|applicant|candidates?|candidate)\b", "applicant"),
        (r"^(tenants?|tenant|residents?|resident)\b", "resident"),
        (r"^(guests?|guest|visitors?|visitor)\b", "guest"),
        (r"^(persons?|person|individuals?|individual)\b", "person"),
        (r"^(members?|member|committee|board|team|group)s?\b", "member"),
        (r"^(departments?|department|office|unit|division)s?\b", "department"),
        (
            r"^(administrators?|administrator|manager|director|coordinator)s?\b",
            "administrator",
        ),
    ]

    # Extract subject
    for pattern, replacement in subject_patterns:
        match = re.search(pattern, text_lower)
        if match:
            result["subject"] = replacement
            # Remove the matched subject from text for further processing
            text_lower = re.sub(pattern, "", text_lower, count=1).strip()
            break

    # If no specific subject found, use a generic one
    if not result["subject"]:
        result["subject"] = "person"

    # Extract action (main verb phrase)
    # Look for verb phrases after modal verbs (must, shall, may, should, etc.)
    action_patterns = [
        r"(?:must|shall|will|should)\s+(.+?)(?:\s+by\s+|\s+before\s+|\s+after\s+|\s+when\s+|\s+if\s+|\s+unless\s+|\.|$)",
        r"(?:may|can|could|is\s+allowed\s+to|is\s+permitted\s+to|is\s+entitled\s+to)\s+(.+?)(?:\s+by\s+|\s+before\s+|\s+after\s+|\s+when\s+|\s+if\s+|\s+unless\s+|\.|$)",
        r"(?:must\s+not|shall\s+not|cannot|is\s+prohibited\s+from|is\s+not\s+allowed\s+to)\s+(.+?)(?:\s+by\s+|\s+before\s+|\s+after\s+|\s+when\s+|\s+if\s+|\s+unless\s+|\.|$)",
        r"(?:is\s+required\s+to|are\s+required\s+to|has\s+to|have\s+to)\s+(.+?)(?:\s+by\s+|\s+before\s+|\s+after\s+|\s+when\s+|\s+if\s+|\s+unless\s+|\.|$)",
    ]

    action_found = False
    for pattern in action_patterns:
        match = re.search(pattern, text_lower)
        if match:
            action_phrase = match.group(1).strip()
            # Clean up the action phrase
            action_phrase = re.sub(r"\s+", " ", action_phrase)  # Normalize whitespace
            action_phrase = action_phrase.strip()
            # Convert to camelCase/predicate format
            if action_phrase:
                # Remove articles and prepositions at the beginning
                action_phrase = re.sub(
                    r"^(?:to\s+|the\s+|a\s+|an\s+)", "", action_phrase
                )
                # Split into words and convert to camelCase
                words = re.findall(r"\b[a-z]+", action_phrase)
                if words:
                    # First word lowercase, rest capitalized
                    result["action"] = words[0] + "".join(
                        w.capitalize() for w in words[1:]
                    )
                    action_found = True
                    break

    # If no action found via patterns, try to extract verb phrases
    if not action_found:
        # Simple verb extraction - look for common verbs in policy context
        verb_patterns = [
            r"\b(submit|submit(?:ting)?|file|pay|provide|send|bring|take|make|attend|participate|join|enroll|register|apply|request|obtain|access|use|utilize|employ|conduct|perform|complete|finish|obtain|acquire|receive|get|review|approve|authorize|permit|allow|prohibit|ban|restrict|limit|require|mandate|compel|oblige)\b",
            r"\b(terminate|expel|suspend|dismiss|remove|exclude|reject|deny|refuse|withhold|waive|reduce|increase|adjust|modify|change|alter|amend|revise|update|maintain|keep|preserve|protect|safeguard|secure|ensure|guarantee|warranty|certify|validate|verify|confirm|establish|create|found|set up|initiate|start|begin|commence|launch)\b",
            r"\b(disturb|interfere|disrupt|obstruct|impede|hinder|violate|breach|contravene|disobey|defy|ignore|neglect|overlook|disregard|fail|decline|refuse|resist|oppose|object|protest|challenge|appeal|contest|dispute|argue|contend|maintain|assert|declare|state|allege|claim|allege|allege)\b",
        ]

        for pattern in verb_patterns:
            match = re.search(pattern, text_lower)
            if match:
                verb = match.group(1)
                # Look for additional context around the verb
                start = max(0, match.start() - 10)
                end = min(len(text_lower), match.end() + 20)
                context = text_lower[start:end]

                # Extract a meaningful phrase around the verb
                words = re.findall(r"\b[a-z]+", context)
                if len(words) >= 2:
                    # Take the verb and up to 2 following words
                    action_words = [verb]
                    verb_index = words.index(verb) if verb in words else 0
                    for i in range(1, 3):
                        if verb_index + i < len(words):
                            action_words.append(words[verb_index + i])
                    result["action"] = "".join(w.capitalize() for w in action_words)
                    action_found = True
                    break

    # If still no action found, extract from the beginning
    if not action_found and not result["action"]:
        # Take first few meaningful words as action
        words = re.findall(r"\b[a-z]{3,}", text_lower)
        if len(words) >= 2:
            # Skip articles and prepositions
            meaningful_words = [
                w
                for w in words
                if w
                not in {
                    "the",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "with",
                    "by",
                }
            ]
            if meaningful_words:
                # Take first 2-3 meaningful words
                action_words = meaningful_words[: min(3, len(meaningful_words))]
                result["action"] = "".join(w.capitalize() for w in action_words)

    # Extract condition (what remains after removing subject and action)
    # This is a simplified approach - in reality, condition extraction is complex
    condition_text = text_lower

    # Remove subject mentions
    for pattern, replacement in subject_patterns:
        condition_text = re.sub(pattern, "", condition_text, flags=re.IGNORECASE)

    # Remove action mentions (simplified)
    if result["action"]:
        # Convert camelCase back to spaced words for matching
        action_spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", result["action"]).lower()
        condition_text = re.sub(
            re.escape(action_spaced), "", condition_text, flags=re.IGNORECASE
        )

    # Clean up condition text
    condition_text = re.sub(r"\s+", " ", condition_text)  # Normalize whitespace
    condition_text = condition_text.strip()

    # Remove common punctuation and articles at start/end
    condition_text = re.sub(
        r"^(?:the|a|an|to|of|for|in|on|at|by|with|\s)+", "", condition_text
    )
    condition_text = re.sub(
        r"(\s+|:|\.|,|;|\!|\?)+(?:the|a|an|to|of|for|in|on|at|by|with|\s)*$",
        "",
        condition_text,
    )

    # Limit condition length
    if len(condition_text) > 50:
        condition_text = condition_text[:50] + "..."

    result["condition"] = condition_text.strip()

    # Ensure we have at least something for action
    if not result["action"]:
        result["action"] = "action"  # Fallback

    return result


def _safe_str(val) -> str:
    """Coerce a predicate value to string. LLM sometimes returns lists."""
    if isinstance(val, list):
        return " ".join(str(v) for v in val)
    return str(val) if val else ""


def _is_placeholder(parsed: dict) -> bool:
    formula = parsed.get("deontic_formula", "")
    if _PLACEHOLDER_PREDS.search(formula):
        return True
    # Also check predicates dict if available
    preds = parsed.get("predicates") or {}
    if isinstance(preds, dict):
        action = _safe_str(preds.get("action", "")).lower()
        subject = _safe_str(preds.get("subject", "")).lower()
        condition = _safe_str(preds.get("condition", "")).lower()
        # Check for generic/placeholder values
        placeholder_indicators = {
            "action",
            "subject",
            "predicate",
            "condition",
            "thing",
            "entity",
            "x",
            "y",
            "z",
            "n",
            "m",
        }
        if action in placeholder_indicators or subject in placeholder_indicators:
            return True
        # Also check if action is too short (likely a single letter)
        if len(action) <= 1:
            return True
    return False


def _backfill_predicates(parsed: dict) -> dict:
    """Backfill generic predicates.action from deontic_formula.

    The LLM often generates a meaningful deontic_formula like
    ``O(payFee(student))`` but leaves predicates.action as ``"Action"``
    or empty.  This function extracts the inner predicate from
    deontic_formula and writes it back into predicates.action,
    improving both M3 (FOL quality) and downstream SHACL generation.

    GAP-2 fix from the gap analysis.
    """
    formula = parsed.get("deontic_formula", "")
    preds = parsed.get("predicates")
    if not isinstance(preds, dict):
        preds = {}
    parsed["predicates"] = preds  # Always ensure key exists

    # Check if predicates.action needs backfill
    current_action = _safe_str(preds.get("action", "")).strip()
    action_is_bad = (
        not current_action
        or len(current_action) <= 1
        or current_action.lower() in {
            "action", "subject", "predicate", "condition",
            "thing", "entity", "x", "y", "z", "n", "m",
        }
    )

    if action_is_bad and formula:
        # Extract predicate from deontic_formula: O(payFee(student)) -> payFee
        m = re.search(r"[OPF]\(([a-zA-Z_]\w*)", formula)
        if m:
            candidate = m.group(1)
            if (
                len(candidate) > 1
                and candidate.lower() not in {
                    "action", "subject", "predicate", "condition",
                    "thing", "entity", "x", "y", "z", "n", "m",
                }
            ):
                preds["action"] = candidate

    # Also try to backfill subject from formula
    current_subject = _safe_str(preds.get("subject", "")).strip()
    subject_is_bad = (
        not current_subject
        or len(current_subject) <= 1
        or current_subject.lower() in {
            "action", "subject", "predicate", "condition",
            "thing", "entity", "x", "y", "z",
        }
    )

    if subject_is_bad and formula:
        # Extract subject from deontic_formula: O(payFee(student)) -> student
        m = re.search(r"[OPF]\(\w+\(([a-zA-Z_]\w*)", formula)
        if m:
            candidate = m.group(1)
            if (
                len(candidate) > 1
                and candidate.lower() not in {
                    "action", "subject", "predicate", "condition",
                    "thing", "entity", "x", "y", "z",
                }
            ):
                preds["subject"] = candidate

    return parsed


_FOL_RETRY_PROMPT = """\
Your previous FOL formalization used placeholder predicates like "Action" or single letters.
That is not acceptable — use SEMANTIC predicates derived from the rule's actual action.

Rule type: {rule_type}
Rule text: "{text}"
Previous (BAD) formula: {bad_formula}

DOMAIN VOCABULARY — Pick from these known property names:
{vocabulary_hint}

Rules:
- Pick a predicate from the DOMAIN VOCABULARY list above that best captures the rule's main action
- If no vocabulary term fits, create a new camelCase predicate from the rule's main verb
- Do NOT use: Action, Subject, Predicate, Condition, Thing, Entity, or any single letter (x, y, z)
- The predicate must be SEMANTIC and meaningful in the policy domain

EXAMPLES:
Rule: "Students must pay fees before registration."
Good: "O(payFee(student))"    [payFee is in the vocabulary]
Bad: "O(Action(x))"

Rule: "Students must not cook in prohibited dormitory areas."
Good: "F(cookInProhibitedDormitory(student))"    [cookInProhibitedDormitory is in the vocabulary]
Bad: "F(Predicate(y))"

Output ONLY a JSON object:
{{
  "deontic_type": "obligation"/"permission"/"prohibition",
  "deontic_formula": "O/P/F(semanticPredicate(subject))",
  "fol_expansion": "...",
  "predicates": {{"subject": "...", "action": "...", "condition": "..."}}
}}"""


def _generate_with_retry(
    text: str, rule_type: str, max_retries: int = 2
) -> dict | None:
    """Generate FOL, retry with stricter prompt if placeholder detected.

    Retry budget increased from 1 to 2 (GAP-2 fix) to give the LLM
    one more chance at producing semantic predicates.
    """
    # §7 — Ablation: disable retry loop
    if os.getenv("ABLATION_NO_FOL_RETRY", "0") == "1":
        max_retries = 0
    llm = _get_llm()
    prompt = _FOL_PROMPT.format(
        text=text, rule_type=rule_type, vocabulary_hint=_get_vocabulary_hint()
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    parsed = _parse_fol(response.content)

    if not parsed:
        return None

    for attempt in range(max_retries):
        if not _is_placeholder(parsed):
            return parsed
        # Re-prompt with the bad example
        try:
            retry_prompt = _FOL_RETRY_PROMPT.format(
                text=text,
                rule_type=rule_type,
                bad_formula=parsed.get("deontic_formula", ""),
                vocabulary_hint=_get_vocabulary_hint(),
            )
            response = llm.invoke([HumanMessage(content=retry_prompt)])
            parsed = _parse_fol(response.content) or parsed
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "FOL retry %d/%d timed out for rule: %.60s... (%s)",
                attempt + 1, max_retries, text, exc,
            )
            break  # Stop retrying — use what we have

    # If still placeholder after retry, enhance with extracted predicates
    if _is_placeholder(parsed):
        # Extract semantic predicates from text to improve the formulation
        extracted_predicates = _extract_predicates_from_text(text)

        # Improve the parsed result with extracted predicates
        if isinstance(parsed.get("predicates"), dict):
            # Update predicates with extracted values where they're placeholders
            preds = parsed["predicates"]
            action_str = _safe_str(preds.get("action", "")).lower()
            if (
                action_str
                in ("action", "subject", "predicate", "condition", "thing", "entity")
                or len(action_str) <= 1
            ):
                preds["action"] = extracted_predicates["action"]
            subject_str = _safe_str(preds.get("subject", "")).lower()
            if (
                subject_str
                in ("action", "subject", "predicate", "condition", "thing", "entity")
                or len(subject_str) <= 1
            ):
                preds["subject"] = extracted_predicates["subject"]
            if not preds.get("condition"):
                preds["condition"] = extracted_predicates["condition"]

            # Update the deontic formula with improved predicate
            action = _safe_str(preds.get("action", "action"))
            subject = _safe_str(preds.get("subject", "subject"))
            deontic_type = parsed.get("deontic_type", rule_type)

            # Map deontic type to symbol
            deontic_symbol = {
                "obligation": "O",
                "permission": "P",
                "prohibition": "F",
            }.get(deontic_type, "O")

            # Construct improved formula
            parsed["deontic_formula"] = f"{deontic_symbol}({action}({subject}))"

            # Update fol_expansion accordingly
            condition_str = _safe_str(preds.get('condition', 'Condition'))
            parsed["fol_expansion"] = (
                f"∀x ({subject.capitalize()}(x) ∧ {condition_str}(x) → {deontic_symbol}({action}(x)))"
            )

            # Update shacl_hint
            parsed["shacl_hint"] = f"{action} property"

            # Remove placeholder flag since we've improved it
            if "_placeholder_flag" in parsed:
                del parsed["_placeholder_flag"]

        return parsed

    # --- GAP-2: Always attempt predicate backfill before returning ---
    parsed = _backfill_predicates(parsed)
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
        cached = _cache.get(
            text,
            model,
            "fol_generation",
            extra_params={"rule_type": rule_type, "prompt_version": FOL_PROMPT_VERSION},
        )
        if cached:
            parsed = cached
        else:
            try:
                parsed = _generate_with_retry(text, rule_type)
                if parsed:
                    _cache.set(
                        text,
                        model,
                        "fol_generation",
                        parsed,
                        extra_params={
                            "rule_type": rule_type,
                            "prompt_version": FOL_PROMPT_VERSION,
                        },
                    )
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

            # Save non-placeholder examples for potential fine-tuning
            if not _is_placeholder(parsed):
                _save_training_example(text, rule_type, parsed)
        else:
            fol_failed.append(rule)

    return {
        "fol_formulas": fol_formulas,
        "fol_failed": fol_failed,
        "current_step": "fol",
        "errors": errors,
    }
