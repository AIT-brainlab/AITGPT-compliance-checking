from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import List

from langgraph_agent.state import FOLItem, PipelineState, SHACLShape
from langgraph_agent.corpus_config import get_corpus_config
from langgraph_agent.nodes.common import invoke_text
from rdflib import Graph, Namespace, RDFS


def _safe_str(val) -> str:
    """Coerce a predicate value to a plain string.

    The LLM sometimes returns ``predicates.subject`` or ``predicates.action``
    as a ``dict`` or ``list`` instead of a plain string.  A non-empty
    collection is truthy, so the common ``(val or "").strip()`` idiom fails
    with ``AttributeError: 'dict'/'list' object has no attribute 'strip'``.
    """
    if isinstance(val, list):
        return " ".join(str(v) for v in val)
    if isinstance(val, dict):
        # Try to extract a meaningful string from common keys
        for key in ("value", "name", "text", "label"):
            if key in val:
                return str(val[key])
        # Fallback: join all string values
        return " ".join(str(v) for v in val.values() if isinstance(v, str))
    return str(val) if val else ""


PROJECT_ROOT = Path(__file__).parent.parent.parent

def _get_ttl_prefixes() -> str:
    """Generate Turtle prefix block from corpus config."""
    cfg = get_corpus_config()
    return (
        f"@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        f"@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .\n"
        f"@prefix sh:     <http://www.w3.org/ns/shacl#> .\n"
        f"@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .\n"
        f"@prefix {cfg.prefix}:    <{cfg.namespace}> .\n"
        f"@prefix deontic: <http://example.org/deontic#> .\n\n"
    )



# ── Subject → target class inference ───────────────────────────────────────
_SUBJECT_MAP = [
    (r"postgraduate|doctoral|phd|master", "PostgraduateStudent"),
    (r"graduate|alumni", "Graduate"),
    (r"resident|tenant", "Resident"),
    (r"sponsor", "Sponsor"),
    (r"advisor|adviser|supervisor", "Faculty"),
    (r"faculty|professor|instructor|lecturer|invigilator", "Faculty"),
    (r"employee|staff", "Employee"),
    (r"student|learner", "Student"),
    (r"committee|board|tribunal", "Committee"),
    (r"director|dean|registrar", "Administrator"),
    # Enhanced mappings based on gold standard analysis
    (r"contracted research|research", "Person"),
    (r"individuals? with|persons?|people", "Person"),
    (r"account(s?)", "Person"),
    (r"tenant", "Resident"),
    (r"visa", "Person"),
    (r"department|office|unit", "Department"),
    (r"faculty|instructor|teacher", "Faculty"),
    (r"guest", "Person"),
    (r"center|centre", "Person"),
    (r"assistant", "Person"),
    (r"traveler", "Person"),
    (r"complainant", "Person"),
    (r"employee|worker|staff", "Employee"),
    (r"examiner|invigilator", "Faculty"),
]


def _get_ontology_path() -> Path:
    return get_corpus_config().ontology_path

def _get_property_list_path() -> Path:
    return get_corpus_config().vocabulary_path

def _get_namespace() -> Namespace:
    return Namespace(get_corpus_config().namespace)

# Backward-compatible aliases (deprecated — use get_corpus_config() instead)
_ONTOLOGY_PATH = PROJECT_ROOT / "shacl" / "ontology" / "ait_policy_ontology.ttl"
_PROPERTY_LIST_PATH = PROJECT_ROOT / "shacl" / "ontology" / "property_list.txt"

# One-time load caches
_ontology_classes: set[str] | None = None
_ontology_properties: list[str] | None = None
_ontology_properties_lower: dict[str, str] | None = None  # lowercase -> original


def _load_ontology_classes() -> set[str]:
    global _ontology_classes
    if _ontology_classes is None:
        g = Graph()
        onto_path = _get_ontology_path()
        ns = _get_namespace()
        if onto_path.exists():
            g.parse(str(onto_path), format="turtle")
        _ontology_classes = {
            str(s).split("#")[-1] for s in g.subjects(RDFS.subClassOf, None)
        } | {
            str(s).split("#")[-1]
            for s, _, _ in g.triples((None, None, None))
            if str(s).startswith(str(ns))
        }
    return _ontology_classes


def _load_ontology_properties() -> list[str]:
    """Load the known property vocabulary from the corpus config.

    Returns a list of valid property names (without the namespace prefix).
    The list is loaded from the vocabulary file specified in the corpus config.
    """
    global _ontology_properties, _ontology_properties_lower
    if _ontology_properties is None:
        cfg = get_corpus_config()
        _ontology_properties = cfg.load_vocabulary()
        # Build lowercase lookup: lowercase_form -> original_form
        _ontology_properties_lower = {}
        for p in _ontology_properties:
            low = p.lower()
            if low not in _ontology_properties_lower:
                _ontology_properties_lower[low] = p
    return _ontology_properties


def _normalize_property_path(raw_path: str, rule_text: str = "") -> str:
    """Normalize a generated property path against the known ontology vocabulary."""
    props = _load_ontology_properties()
    if not props:
        return raw_path

    # 1. Exact match
    if raw_path in props:
        return raw_path

    # 2. Case-insensitive match
    global _ontology_properties_lower
    if _ontology_properties_lower is None:
        _load_ontology_properties()
    raw_lower = raw_path.lower()
    if raw_lower in _ontology_properties_lower:
        return _ontology_properties_lower[raw_lower]

    # 3. Fuzzy match (cutoff lowered from 0.6 to 0.55)
    all_lower = list(_ontology_properties_lower.keys())
    matches = difflib.get_close_matches(raw_lower, all_lower, n=1, cutoff=0.55)
    if matches:
        return _ontology_properties_lower[matches[0]]

    # 4. Keyword overlap match using rule text
    if rule_text:
        best_prop = _keyword_match_property(raw_lower, rule_text)
        if best_prop:
            return best_prop

    # 5. Fallback: return lowercased raw path
    return raw_lower


# -- Keyword-based property matching -----------------------------------------

def _get_stop_words() -> frozenset:
    """Load stop words from corpus config (universal + corpus-specific)."""
    return get_corpus_config().full_stop_words()

def _get_domain_words() -> list[str]:
    """Load domain words from corpus config, sorted by length for greedy matching."""
    return get_corpus_config().sorted_domain_words()

# Backward-compatible module-level references (lazily evaluated)
_STOP_WORDS = None
_DOMAIN_WORDS = None

def _ensure_word_lists():
    """Lazy-load word lists from config on first use."""
    global _STOP_WORDS, _DOMAIN_WORDS
    if _STOP_WORDS is None:
        _STOP_WORDS = _get_stop_words()
    if _DOMAIN_WORDS is None:
        _DOMAIN_WORDS = _get_domain_words()


def _extract_subwords(text):
    """Greedily extract known domain words from a concatenated string."""
    _ensure_word_lists()
    found = set()
    remaining = text.lower()
    for word in _DOMAIN_WORDS:
        if word in remaining:
            found.add(word)
            remaining = remaining.replace(word, " ", 1)
    leftovers = set(re.findall(r"[a-z]{4,}", remaining))
    found.update(leftovers - _STOP_WORDS)
    return found if len(found) >= 2 else set()


def _tokenize_to_keywords(text):
    """Extract meaningful keywords from text."""
    _ensure_word_lists()
    words = set(re.findall(r"[a-z]{3,}", text.lower()))
    return words - _STOP_WORDS


def _split_camel_and_snake(prop):
    """Split a camelCase or snake_case property name into keyword tokens."""
    _ensure_word_lists()
    parts = prop.replace("_", " ").strip()
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", parts)
    words = set(re.findall(r"[a-z]{3,}", parts.lower()))
    if len(words) <= 1 and len(prop) > 10:
        extracted = _extract_subwords(prop.lower())
        if extracted:
            words = extracted
    return words - _STOP_WORDS


def _keyword_match_property(raw_path, rule_text):
    """Find the best ontology property by keyword overlap with rule text."""
    global _ontology_properties_lower
    if not _ontology_properties_lower:
        return None

    rule_keywords = _tokenize_to_keywords(rule_text)
    raw_keywords = _split_camel_and_snake(raw_path)
    combined_keywords = rule_keywords | raw_keywords

    if not combined_keywords:
        return None

    best_score = 0
    best_prop = None

    for prop_lower, prop_canonical in _ontology_properties_lower.items():
        prop_keywords = _split_camel_and_snake(prop_lower)
        if not prop_keywords:
            continue
        overlap = prop_keywords & combined_keywords
        score = sum(len(kw) for kw in overlap) if overlap else 0
        if len(overlap) >= 2 or (len(overlap) == 1 and max(len(k) for k in overlap) >= 6):
            if score > best_score:
                best_score = score
                best_prop = prop_canonical

    if best_prop and best_score >= 8:
        return best_prop
    return None


def _candidates_from_subject(subj: str) -> list[str]:
    """Convert 'the postgraduate students' into ['PostgraduateStudent', 'Student']."""
    words = re.findall(r"[A-Za-z]+", subj.lower())
    # strip determiners
    words = [
        w
        for w in words
        if w not in {"the", "a", "an", "any", "all", "each", "every", "some"}
    ]
    # singularise trivially (drop trailing 's')
    words = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]
    if not words:
        return []
    # Candidates: full concat, pairwise, single
    joined = "".join(w.capitalize() for w in words)
    singles = [w.capitalize() for w in words]
    return [joined] + singles


def _infer_target_class(text: str, fol: FOLItem | None = None) -> str:
    """Infer a target class by (1) FOL subject, (2) enhanced regex map with section hints, (3) Person fallback."""
    # --- Strategy A: use FOL subject if it matches an ontology class ---
    if fol is not None:
        preds = fol.get("predicates") or {}
        if isinstance(preds, dict):
            subj = _safe_str(preds.get("subject", "")).strip()
            if subj:
                candidates = _candidates_from_subject(subj)
                classes = _load_ontology_classes()
                for c in candidates:
                    if c in classes:
                        return c

    # --- Strategy B: enhanced regex map on rule text with section hints ---
    t = text.lower()

    # First, check for explicit section headers in the text
    section_indicators = [
        (
            r"section\s+\d+|subsection\s+\d+|clause\s+\d+",
            None,
        ),  # Will be handled by specific patterns below
        (r"student.*research.*expense|sra", "Student"),
        (r"leave.*travel|travel.*leave", "Person"),
        (r"medical.*emergency|emergency.*medical", "Person"),
        (r"swim.*wear|wear.*swim", "Person"),
        (r"health.*declaration|declaration.*health", "Person"),
        (r"accommodation.*unit|unit.*accommodation", "Resident"),
        (r"visa.*extension|extension.*visa", "Student"),
        (r"financial.*management|management.*financial", "Person"),
        (r"grievance.*process|process.*grievance", "Person"),
        (r"intellectual.*property|property.*intellectual", "Person"),
        (r"confidentiality|non.?disclosure", "Person"),
        (r"exam.*invigilation|invigilation.*exam", "Faculty"),
        (r"grade.*assessment|assessment.*grade", "Faculty"),
        (r"course.*criteria|criteria.*course", "Faculty"),
    ]

    for pattern, cls in section_indicators:
        if cls and re.search(pattern, t):
            return cls
        elif pattern and re.search(pattern, t):
            # Handle special cases that need more context
            if "student.*research.*expense" in pattern or "sra" in pattern:
                return "Student"
            elif "leave.*travel" in pattern or "travel.*leave" in pattern:
                return "Person"
            elif "medical.*emergency" in pattern or "emergency.*medical" in pattern:
                return "Person"
            elif "swim.*wear" in pattern or "wear.*swim" in pattern:
                return "Person"
            elif "health.*declaration" in pattern or "declaration.*health" in pattern:
                return "Person"
            elif "accommodation.*unit" in pattern or "unit.*accommodation" in pattern:
                return "Resident"
            elif "visa.*extension" in pattern or "extension.*visa" in pattern:
                return "Student"
            elif (
                "financial.*management" in pattern or "management.*financial" in pattern
            ):
                return "Person"
            elif "grievance.*process" in pattern or "process.*grievance" in pattern:
                return "Person"
            elif (
                "intellectual.*property" in pattern
                or "property.*intellectual" in pattern
            ):
                return "Person"
            elif "confidentiality" in pattern or "non.?disclosure" in pattern:
                return "Person"
            elif "exam.*invigilation" in pattern or "invigilation.*exam" in pattern:
                return "Faculty"
            elif "grade.*assessment" in pattern or "assessment.*grade" in pattern:
                return "Faculty"
            elif "course.*criteria" in pattern or "criteria.*course" in pattern:
                return "Faculty"

    # --- Strategy B continued: regex map on rule text ---
    for pattern, cls in _SUBJECT_MAP:
        if re.search(pattern, t):
            return cls

    # --- Strategy B2: corpus config target class patterns ---
    try:
        cfg = get_corpus_config()
        for pattern, cls in cfg.target_class_patterns:
            if pattern.search(t):
                return cls
    except Exception:
        pass

    # --- Strategy C: fallback — but narrower than Person ---
    return "Person"


def _slugify(text: str, max_words: int = 4, first_lower: bool = False) -> str:
    """Turn rule text into a camelCase property-path slug."""
    # Normalise whitespace (PDF newlines etc.) before stripping
    text = re.sub(r"\s+", " ", text)
    words = re.sub(r"[^a-zA-Z0-9 ]", "", text).split()
    if not words:
        return "policyRule"
    selected = words[:max_words]
    result = "".join(w.capitalize() for w in selected)
    if first_lower and result:
        result = result[0].lower() + result[1:]
    return result


# Reserved/placeholder predicates to reject — these are logical variables
# or lazy LLM outputs that carry no semantic content
_PLACEHOLDER_PREDICATES = {
    "x",
    "y",
    "z",
    "n",
    "m",  # logical variables
    "action",
    "subject",
    "predicate",  # LLM lazy placeholders
    "condition",
    "thing",
    "entity",
}


def _property_path(fol: FOLItem) -> str:
    """Derive a SHACL property path from the FOL formula.

    Priority: deontic predicate > predicates.action > rule text slug.
    Rejects single-letter tokens and known placeholders.

    All outputs are **normalized** against the known ontology vocabulary
    (case-insensitive match → fuzzy match → lowercased fallback).
    """
    raw: str | None = None

    # --- Try deontic operator argument ---
    m = re.search(r"[OPF]\(([a-zA-Z_]+)", fol["deontic_formula"])
    if m:
        candidate = m.group(1)
        if len(candidate) > 1 and candidate.lower() not in _PLACEHOLDER_PREDICATES:
            # Convert snake_case or PascalCase to camelCase
            parts = re.sub(r"([A-Z])", r" \1", candidate).strip().split()
            raw = (
                parts[0][0].lower()
                + parts[0][1:]
                + "".join(p.capitalize() for p in parts[1:])
            )

    # --- Try predicates.action from FOL output ---
    if raw is None:
        predicates = fol.get("predicates") or {}
        action = _safe_str(predicates.get("action", "")) if isinstance(predicates, dict) else ""
        if action and action.lower() not in _PLACEHOLDER_PREDICATES:
            raw = _slugify(action, max_words=3, first_lower=True)

    # --- Fall back to slug from rule text ---
    if raw is None:
        raw = _slugify(fol["text"], max_words=4, first_lower=True)

    # --- Normalize against known ontology vocabulary (with rule text) ---
    return _normalize_property_path(raw, rule_text=fol.get("text", ""))


# Datatype mapping for common policy attributes
_DATATYPE_MAP = {
    # Fee/payment related
    "fee": "xsd:decimal",
    "payment": "xsd:decimal",
    "amount": "xsd:decimal",
    "cost": "xsd:decimal",
    "price": "xsd:decimal",
    "salary": "xsd:decimal",
    "stipend": "xsd:decimal",
    "deposit": "xsd:decimal",
    "fine": "xsd:decimal",
    "penalty": "xsd:decimal",
    # Date/time related
    "date": "xsd:date",
    "time": "xsd:time",
    "deadline": "xsd:date",
    "due date": "xsd:date",
    "expiry": "xsd:date",
    "expiration": "xsd:date",
    "period": "xsd:duration",
    "duration": "xsd:duration",
    "term": "xsd:duration",
    "semester": "xsd:string",  # Could be enum but keeping simple
    "year": "xsd:gYear",
    "month": "xsd:gMonth",
    "day": "xsd:gDay",
    # Identifier related
    "id": "xsd:string",
    "identifier": "xsd:string",
    "number": "xsd:string",
    "code": "xsd:string",
    "ref": "xsd:string",
    "reference": "xsd:string",
    "visa": "xsd:string",
    "passport": "xsd:string",
    "license": "xsd:string",
    "permit": "xsd:string",
    "certificate": "xsd:string",
    "document": "xsd:string",
    # Boolean related
    "approved": "xsd:boolean",
    "authorized": "xsd:boolean",
    "certified": "xsd:boolean",
    "completed": "xsd:boolean",
    "confirmed": "xsd:boolean",
    "eligible": "xsd:boolean",
    "enrolled": "xsd:boolean",
    "employed": "xsd:boolean",
    "licensed": "xsd:boolean",
    "permitted": "xsd:boolean",
    "qualified": "xsd:boolean",
    "registered": "xsd:boolean",
    "required": "xsd:boolean",
    "satisfied": "xsd:boolean",
    "valid": "xsd:boolean",
    # Text/String related (default)
    "name": "xsd:string",
    "title": "xsd:string",
    "description": "xsd:string",
    "details": "xsd:string",
    "information": "xsd:string",
    "reason": "xsd:string",
    "purpose": "xsd:string",
    "objective": "xsd:string",
    "goal": "xsd:string",
    "requirement": "xsd:string",
    "condition": "xsd:string",
    "constraint": "xsd:string",
    "policy": "xsd:string",
    "rule": "xsd:string",
    "guideline": "xsd:string",
    "procedure": "xsd:string",
    "process": "xsd:string",
}

# Pattern constraints for formatted data
_PATTERN_CONSTRAINTS = {
    # Email
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    # Phone numbers
    "phone": r"\b\+?[\d\s\-\(\)]{10,}\b",
    # Postal codes
    "postal": r"\b\d{5}(?:[-\s]\d{4})?\b",
    # Dates (various formats)
    "date": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    # Times
    "time": r"\b\d{1,2}:\d{2}(:\d{2})?\s*(?:AM|PM|am|pm)?\b",
    # Currency
    "currency": r"\$\d+(?:\.\d{2})?",
    # Percentages
    "percentage": r"\d+(?:\.\d+)?%",
    # Identification numbers
    "id": r"\b[A-Z0-9]{6,12}\b",
}

_DEONTIC_CONSTRAINT = {
    "obligation": "sh:minCount 1 ;",
    "prohibition": "sh:maxCount 0 ;",
    "permission": "sh:minCount 0 ;",
}


def _severity_for(rule_type: str, confidence: float = 1.0) -> str:
    """Confidence-weighted severity tiers (§5.2).

    - Permissions are always ``sh:Info``
    - High-confidence obligations/prohibitions → ``sh:Violation``
    - Medium-confidence → ``sh:Warning``
    - Low-confidence → ``sh:Info``
    """
    if rule_type == "permission":
        return "sh:Info"
    if confidence >= 0.85:
        return "sh:Violation"
    if confidence >= 0.6:
        return "sh:Warning"
    return "sh:Info"


def _fol_to_turtle(
    fol: FOLItem, confidence: float = 1.0
) -> tuple[str, str, str, str, bool]:
    """
    Returns (turtle_text, target_class, shape_id, prop_path, syntax_valid).

    Implements:
    - §4.4: ``sh:targetSubjectsOf`` fallback when target class is Person
    - §5.1: Named property shape URIs (``<prefix>:<id>Shape_prop1``)
    - §5.2: Confidence-weighted severity
    - §5.3: Datatype and pattern constraints based on property name
    """
    cfg = get_corpus_config()
    pfx = cfg.prefix  # e.g. "ait"

    shape_id = fol["rule_id"].replace("-", "_") + "Shape"
    prop_shape_id = shape_id + "_prop1"
    target_class = _infer_target_class(fol["text"], fol)
    deontic_type = fol["deontic_type"]
    constraint = _DEONTIC_CONSTRAINT.get(deontic_type, "sh:minCount 1 ;")
    severity = _severity_for(deontic_type, confidence)
    prop_path = _property_path(fol)

    # Enhance constraint with datatype and pattern information
    enhanced_constraint = _enhance_constraint_with_datatype(
        constraint, prop_path, deontic_type
    )

    # Sanitise message for Turtle string literal (no newlines, no unescaped quotes)
    message = fol["text"].replace("\n", " ").replace("\r", " ").replace('"', "'")[:200]

    # §4.4 — Use sh:targetSubjectsOf when target class is Person (weak inference)
    if target_class == "Person":
        target_clause = f"sh:targetSubjectsOf {pfx}:{prop_path}"
    else:
        target_clause = f"sh:targetClass {pfx}:{target_class}"

    turtle = (
        f"# Rule: {fol['rule_id']} | {deontic_type.upper()}\n"
        f"# FOL: {fol['deontic_formula']}\n"
        f"{pfx}:{shape_id} a sh:NodeShape ;\n"
        f"    {target_clause} ;\n"
        f"    sh:severity {severity} ;\n"
        f"    sh:property {pfx}:{prop_shape_id} .\n"
        f"\n"
        f"{pfx}:{prop_shape_id} a sh:PropertyShape ;\n"
        f"    sh:path {pfx}:{prop_path} ;\n"
        f"    {enhanced_constraint}\n"
        f'    sh:message "{message}" .\n'
    )
    return turtle, target_class, shape_id, prop_path, True


def _enhance_constraint_with_datatype(
    constraint: str, prop_path: str, deontic_type: str
) -> str:
    """
    Enhance SHACL property constraint with datatype and pattern information based on property name.
    """
    # Start with the base constraint
    enhanced = constraint.rstrip(" ;")

    # Determine datatype based on property name
    datatype = None
    prop_lower = prop_path.lower()

    # Check for known datatype mappings
    for key, dt in _DATATYPE_MAP.items():
        if key in prop_lower:
            datatype = dt
            break

    # If we found a datatype, add it to the constraint
    if datatype:
        enhanced += f"; sh:datatype {datatype}"

    # Check for pattern constraints
    pattern = None
    for key, pat in _PATTERN_CONSTRAINTS.items():
        if key in prop_lower:
            pattern = pat
            break

    # If we found a pattern, add it to the constraint
    if pattern:
        # Escape backslashes first, then quotes, for valid Turtle string literal.
        # sh:pattern requires an xsd:string literal — we must double-escape
        # backslashes so that rdflib sees them as literal '\' in the regex.
        escaped_pattern = pattern.replace("\\", "\\\\").replace('"', '\\"')
        enhanced += f'; sh:pattern "{escaped_pattern}"'

    # Close the constraint
    enhanced += " ;"

    return enhanced


# ── §5.3 — Permission-as-exception override detection ────────────────────


def _detect_overrides(
    shapes: list[dict],
) -> list[tuple[str, str]]:
    """Detect permission shapes that override obligation shapes.

    A permission *overrides* an obligation when they share:
    - the same (or compatible) target class, AND
    - the same property path.

    Returns a list of ``(permission_shape_id, obligation_shape_id)`` pairs.
    Following Governatori & Rotolo (2010).
    """
    # Index obligations by (target_class, prop_path)
    obligations: dict[tuple[str, str], str] = {}
    permissions: list[dict] = []

    for s in shapes:
        key = (s.get("target_class", ""), s.get("prop_path", ""))
        if s["deontic_type"] == "obligation":
            obligations[key] = s["shape_id"]
        elif s["deontic_type"] == "permission":
            permissions.append(s)

    overrides: list[tuple[str, str]] = []
    for p in permissions:
        pkey = (p.get("target_class", ""), p.get("prop_path", ""))
        if pkey in obligations:
            overrides.append((p["shape_id"], obligations[pkey]))

    return overrides


def _emit_override_triples(overrides: list[tuple[str, str]]) -> str:
    """Generate Turtle triples for deontic:overrides links."""
    if not overrides:
        return ""
    pfx = get_corpus_config().prefix
    lines = ["# ── Permission-as-exception overrides (§5.3) ──"]
    for perm_id, obl_id in overrides:
        lines.append(f"{pfx}:{perm_id} deontic:overrides {pfx}:{obl_id} .")
    lines.append("")
    return "\n".join(lines) + "\n"


# ── Inline NL fallback for FOL-to-Turtle failures ────────────────────────
def _try_direct_fallback(fol: FOLItem) -> SHACLShape | None:
    """When _fol_to_turtle fails, attempt direct NL-to-SHACL via LLM.
    Reuses the same prompt and repair logic as direct_shacl_node."""
    from langgraph_agent.nodes.direct_shacl import (
        _DIRECT_PROMPT,
        _strip_fences,
        _validate_turtle,
        _repair_turtle,
        _get_llm,
    )

    shape_id = fol["rule_id"].replace("-", "_")
    try:
        cfg = get_corpus_config()
        prompt = _DIRECT_PROMPT.format(
            text=fol["text"],
            rule_type=fol["deontic_type"],
            shape_id=shape_id,
            ns_prefix=cfg.prefix,
            namespace=cfg.namespace,
        )
        turtle = _strip_fences(invoke_text(_get_llm(), prompt).strip())
        valid, parse_error = _validate_turtle(turtle)

        # Attempt repair if invalid
        if not valid and turtle:
            turtle, valid = _repair_turtle(turtle, parse_error, fol["rule_id"])

        if turtle:
            return SHACLShape(
                rule_id=fol["rule_id"],
                turtle_text=turtle,
                target_class=_infer_target_class(fol["text"]),
                deontic_type=fol["deontic_type"],
                syntax_valid=valid,
                generation_method="fol_fallback",
            )
    except Exception:
        pass
    return None


def shacl_node(state: PipelineState) -> PipelineState:
    fol_formulas: List[FOLItem] = state["fol_formulas"]
    errors: List[str] = []

    new_shapes: List[SHACLShape] = []
    ttl_blocks: List[str] = [_get_ttl_prefixes()]
    # Track shape metadata for override detection (§5.3)
    shape_meta: list[dict] = []

    for fol in fol_formulas:
        try:
            turtle, target_class, shape_id, prop_path, valid = _fol_to_turtle(fol)
            ttl_blocks.append(turtle + "\n")
            new_shapes.append(
                SHACLShape(
                    rule_id=fol["rule_id"],
                    turtle_text=turtle,
                    target_class=target_class,
                    deontic_type=fol["deontic_type"],
                    syntax_valid=valid,
                    generation_method="fol_mediated",
                )
            )
            shape_meta.append(
                {
                    "shape_id": shape_id,
                    "target_class": target_class,
                    "prop_path": prop_path,
                    "deontic_type": fol["deontic_type"],
                }
            )
        except Exception as exc:
            errors.append(f"shacl[{fol['rule_id']}]: {exc} (attempting NL fallback)")
            # ── Inline NL fallback: recover via direct LLM prompt ──
            fallback = _try_direct_fallback(fol)
            if fallback:
                new_shapes.append(fallback)
                if fallback["turtle_text"]:
                    ttl_blocks.append(fallback["turtle_text"] + "\n")

    # §5.3 — Detect and emit permission-as-exception overrides
    overrides = _detect_overrides(shape_meta)
    if overrides:
        override_ttl = _emit_override_triples(overrides)
        ttl_blocks.append(override_ttl)
        pfx = get_corpus_config().prefix
        for perm_id, obl_id in overrides:
            errors.append(
                f"shacl[override]: {pfx}:{perm_id} deontic:overrides {pfx}:{obl_id}"
            )

    # Write combined TTL to output/
    output_dir = PROJECT_ROOT / "output" / state["source"]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / "shapes_generated.ttl")
    Path(output_path).write_text("".join(ttl_blocks), encoding="utf-8")

    return {
        "shacl_shapes": new_shapes,
        "shacl_output_path": output_path,
        "errors": errors,
    }
