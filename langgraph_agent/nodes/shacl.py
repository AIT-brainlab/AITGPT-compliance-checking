from __future__ import annotations

import re
from pathlib import Path
from typing import List

from langgraph_agent.state import FOLItem, PipelineState, SHACLShape
from rdflib import Graph, Namespace, RDFS

PROJECT_ROOT = Path(__file__).parent.parent.parent

_TTL_PREFIXES = """\
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh:     <http://www.w3.org/ns/shacl#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix ait:    <http://example.org/ait-policy#> .
@prefix deontic: <http://example.org/deontic#> .

"""

# ── Subject → target class inference ───────────────────────────────────────
_SUBJECT_MAP = [
    (r"postgraduate|doctoral|phd|master", "PostgraduateStudent"),
    (r"graduate|alumni",                  "Graduate"),
    (r"resident|tenant",                  "Resident"),
    (r"sponsor",                          "Sponsor"),
    (r"advisor|adviser|supervisor",       "Faculty"),
    (r"faculty|professor|instructor|lecturer|invigilator", "Faculty"),
    (r"employee|staff",                   "Employee"),
    (r"student|learner",                  "Student"),
    (r"committee|board|tribunal",         "Committee"),
    (r"director|dean|registrar",          "Administrator"),
]


_ONTOLOGY_PATH = PROJECT_ROOT / "shacl" / "ontology" / "ait_policy_ontology.ttl"
AIT = Namespace("http://example.org/ait-policy#")

# One-time load
_ontology_classes: set[str] | None = None

def _load_ontology_classes() -> set[str]:
    global _ontology_classes
    if _ontology_classes is None:
        g = Graph()
        if _ONTOLOGY_PATH.exists():
            g.parse(str(_ONTOLOGY_PATH), format="turtle")
        _ontology_classes = {
            str(s).split("#")[-1] for s in g.subjects(RDFS.subClassOf, None)
        } | {str(s).split("#")[-1] for s, _, _ in g.triples((None, None, None))
             if str(s).startswith(str(AIT))}
    return _ontology_classes


def _candidates_from_subject(subj: str) -> list[str]:
    """Convert 'the postgraduate students' into ['PostgraduateStudent', 'Student']."""
    words = re.findall(r"[A-Za-z]+", subj.lower())
    # strip determiners
    words = [w for w in words if w not in {"the", "a", "an", "any", "all", "each", "every", "some"}]
    # singularise trivially (drop trailing 's')
    words = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]
    if not words:
        return []
    # Candidates: full concat, pairwise, single
    joined = "".join(w.capitalize() for w in words)
    singles = [w.capitalize() for w in words]
    return [joined] + singles


def _infer_target_class(text: str, fol: FOLItem | None = None) -> str:
    """Infer a target class by (1) FOL subject, (2) regex map, (3) Person fallback."""
    # --- Strategy A: use FOL subject if it matches an ontology class ---
    if fol is not None:
        preds = fol.get("predicates") or {}
        if isinstance(preds, dict):
            subj = (preds.get("subject") or "").strip()
            if subj:
                candidates = _candidates_from_subject(subj)
                classes = _load_ontology_classes()
                for c in candidates:
                    if c in classes:
                        return c

    # --- Strategy B: regex map on rule text ---
    t = text.lower()
    for pattern, cls in _SUBJECT_MAP:
        if re.search(pattern, t):
            return cls

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
    "x", "y", "z", "n", "m",           # logical variables
    "action", "subject", "predicate",  # LLM lazy placeholders
    "condition", "thing", "entity",
}


def _property_path(fol: FOLItem) -> str:
    """Derive a SHACL property path from the FOL formula.
    Priority: deontic predicate > predicates.action > rule text slug.
    Rejects single-letter tokens and known placeholders."""
    # --- Try deontic operator argument ---
    m = re.search(r"[OPF]\(([a-zA-Z_]+)", fol["deontic_formula"])
    if m:
        raw = m.group(1)
        if len(raw) > 1 and raw.lower() not in _PLACEHOLDER_PREDICATES:
            # Convert snake_case or PascalCase to camelCase
            parts = re.sub(r"([A-Z])", r" \1", raw).strip().split()
            return parts[0][0].lower() + parts[0][1:] + "".join(
                p.capitalize() for p in parts[1:]
            )

    # --- Try predicates.action from FOL output ---
    predicates = fol.get("predicates") or {}
    action = predicates.get("action", "") if isinstance(predicates, dict) else ""
    if action and action.lower() not in _PLACEHOLDER_PREDICATES:
        return _slugify(action, max_words=3, first_lower=True)

    # --- Fall back to slug from rule text ---
    return _slugify(fol["text"], max_words=4, first_lower=True)


_DEONTIC_CONSTRAINT = {
    "obligation":  "sh:minCount 1 ;",
    "prohibition": "sh:maxCount 0 ;",
    "permission":  "sh:minCount 0 ;",
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


def _fol_to_turtle(fol: FOLItem, confidence: float = 1.0) -> tuple[str, str, str, str, bool]:
    """
    Returns (turtle_text, target_class, shape_id, prop_path, syntax_valid).

    Implements:
    - §4.4: ``sh:targetSubjectsOf`` fallback when target class is Person
    - §5.1: Named property shape URIs (``ait:AIT_xxxxShape_prop1``)
    - §5.2: Confidence-weighted severity
    """
    shape_id = fol["rule_id"].replace("-", "_") + "Shape"
    prop_shape_id = shape_id + "_prop1"
    target_class = _infer_target_class(fol["text"], fol)
    deontic_type = fol["deontic_type"]
    constraint = _DEONTIC_CONSTRAINT.get(deontic_type, "sh:minCount 1 ;")
    severity = _severity_for(deontic_type, confidence)
    prop_path = _property_path(fol)
    # Sanitise message for Turtle string literal (no newlines, no unescaped quotes)
    message = fol["text"].replace("\n", " ").replace("\r", " ").replace('"', "'")[:200]

    # §4.4 — Use sh:targetSubjectsOf when target class is Person (weak inference)
    if target_class == "Person":
        target_clause = f"sh:targetSubjectsOf ait:{prop_path}"
    else:
        target_clause = f"sh:targetClass ait:{target_class}"

    turtle = (
        f"# Rule: {fol['rule_id']} | {deontic_type.upper()}\n"
        f"# FOL: {fol['deontic_formula']}\n"
        f"ait:{shape_id} a sh:NodeShape ;\n"
        f"    {target_clause} ;\n"
        f"    sh:severity {severity} ;\n"
        f"    sh:property ait:{prop_shape_id} .\n"
        f"\n"
        f"ait:{prop_shape_id} a sh:PropertyShape ;\n"
        f"    sh:path ait:{prop_path} ;\n"
        f"    {constraint}\n"
        f"    sh:message \"{message}\" .\n"
    )
    return turtle, target_class, shape_id, prop_path, True


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
    lines = ["# ── Permission-as-exception overrides (§5.3) ──"]
    for perm_id, obl_id in overrides:
        lines.append(f"ait:{perm_id} deontic:overrides ait:{obl_id} .")
    lines.append("")
    return "\n".join(lines) + "\n"


# ── Inline NL fallback for FOL-to-Turtle failures ────────────────────────
def _try_direct_fallback(fol: FOLItem) -> SHACLShape | None:
    """When _fol_to_turtle fails, attempt direct NL-to-SHACL via LLM.
    Reuses the same prompt and repair logic as direct_shacl_node."""
    from langgraph_agent.nodes.direct_shacl import (
        _DIRECT_PROMPT, _strip_fences, _validate_turtle, _repair_turtle, _llm,
    )
    shape_id = fol["rule_id"].replace("-", "_")
    try:
        prompt = _DIRECT_PROMPT.format(
            text=fol["text"],
            rule_type=fol["deontic_type"],
            shape_id=shape_id,
        )
        from langchain_core.messages import HumanMessage
        response = _llm.invoke([HumanMessage(content=prompt)])
        turtle = _strip_fences(response.content.strip())
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
    ttl_blocks: List[str] = [_TTL_PREFIXES]
    # Track shape metadata for override detection (§5.3)
    shape_meta: list[dict] = []

    for fol in fol_formulas:
        try:
            turtle, target_class, shape_id, prop_path, valid = _fol_to_turtle(fol)
            ttl_blocks.append(turtle + "\n")
            new_shapes.append(SHACLShape(
                rule_id=fol["rule_id"],
                turtle_text=turtle,
                target_class=target_class,
                deontic_type=fol["deontic_type"],
                syntax_valid=valid,
                generation_method="fol_mediated",
            ))
            shape_meta.append({
                "shape_id": shape_id,
                "target_class": target_class,
                "prop_path": prop_path,
                "deontic_type": fol["deontic_type"],
            })
        except Exception as exc:
            errors.append(
                f"shacl[{fol['rule_id']}]: {exc} (attempting NL fallback)"
            )
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
        for perm_id, obl_id in overrides:
            errors.append(f"shacl[override]: ait:{perm_id} deontic:overrides ait:{obl_id}")

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
