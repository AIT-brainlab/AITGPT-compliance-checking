"""Run pyshacl per-rule: one pipeline shape against one gold Pos/Neg pair."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

from pyshacl import validate
from rdflib import Graph, Namespace, URIRef

PROJECT_ROOT = Path(__file__).parent.parent
AIT = Namespace("http://example.org/ait-policy#")

_PREFIXES = """
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh:     <http://www.w3.org/ns/shacl#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix ait:    <http://example.org/ait-policy#> .
@prefix deontic: <http://example.org/deontic#> .
"""

@dataclass
class RuleEvalResult:
    gs_id: str
    ait_id: str
    pos_passes: Optional[bool]    # None if test entity missing
    neg_fails: Optional[bool]
    verdict: str                  # "correct" | "too_strict" | "too_permissive" | "inverted" | "skipped"


def _entity_subgraph(full_data: Graph, entity_uri: URIRef) -> Graph:
    """Extract a single entity and its direct properties."""
    sub = Graph()
    for p, o in full_data.predicate_objects(entity_uri):
        sub.add((entity_uri, p, o))
    return sub


def evaluate_rule(gs_id: str,
                  ait_id: str,
                  pipeline_turtle: str,
                  test_data: Graph,
                  ontology: Graph) -> RuleEvalResult:
    gs_num = gs_id.replace("GS-", "").zfill(3)
    pos_uri = AIT[f"Pos_GS{gs_num}"]
    neg_uri = AIT[f"Neg_GS{gs_num}"]

    # Build single-shape graph
    shape_graph = Graph()
    try:
        shape_graph.parse(data=_PREFIXES + pipeline_turtle, format="turtle")
    except Exception:
        return RuleEvalResult(gs_id, ait_id, None, None, "skipped")

    pos_graph = _entity_subgraph(test_data, pos_uri)
    neg_graph = _entity_subgraph(test_data, neg_uri)

    pos_passes = None
    neg_fails = None

    if len(pos_graph) > 0:
        conforms, _, _ = validate(
            pos_graph, shacl_graph=shape_graph, ont_graph=ontology,
            inference="rdfs", abort_on_first=False, meta_shacl=False,
        )
        pos_passes = bool(conforms)

    if len(neg_graph) > 0:
        conforms, _, _ = validate(
            neg_graph, shacl_graph=shape_graph, ont_graph=ontology,
            inference="rdfs", abort_on_first=False, meta_shacl=False,
        )
        neg_fails = not bool(conforms)

    # 2x2 interpretation
    if pos_passes is None or neg_fails is None:
        verdict = "skipped"
    elif pos_passes and neg_fails:
        verdict = "correct"
    elif pos_passes and not neg_fails:
        verdict = "too_permissive"
    elif not pos_passes and neg_fails:
        verdict = "too_strict"
    else:
        verdict = "inverted"

    return RuleEvalResult(gs_id, ait_id, pos_passes, neg_fails, verdict)


def main() -> None:
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    alignment_file = PROJECT_ROOT / "output" / "ait" / "gold_alignment.json"
    shapes_file    = PROJECT_ROOT / "output" / "ait" / "shapes_generated.ttl"
    test_file      = PROJECT_ROOT / "shacl" / "test_data" / "tdd_test_data_fixed.ttl"
    onto_file      = PROJECT_ROOT / "shacl" / "ontology"  / "ait_policy_ontology.ttl"
    out_file       = PROJECT_ROOT / "output" / "ait" / "per_rule_eval.json"

    alignments = json.loads(alignment_file.read_text(encoding="utf-8"))
    test_data = Graph().parse(str(test_file), format="turtle")
    ontology  = Graph().parse(str(onto_file), format="turtle")

    # Parse the generated shapes file into a dict keyed by rule_id
    pipeline_shapes_text = shapes_file.read_text(encoding="utf-8")
    shape_blocks = _split_shape_blocks(pipeline_shapes_text)  # see utility below

    results: List[RuleEvalResult] = []
    for al in alignments:
        if not al["aligned"]:
            continue
        turtle = shape_blocks.get(al["ait_id"], "")
        if not turtle:
            continue
        r = evaluate_rule(al["gs_id"], al["ait_id"], turtle, test_data, ontology)
        results.append(r)

    out_file.write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _print_summary(results)


def _split_shape_blocks(ttl_text: str) -> dict[str, str]:
    """Parse the comment markers `# Rule: AIT-xxxx` to associate turtle blocks."""
    import re
    blocks: dict[str, str] = {}
    current_id = None
    current_lines: list[str] = []
    for line in ttl_text.splitlines():
        m = re.match(r"# Rule:\s+(AIT-\d+)", line)
        if m:
            if current_id and current_lines:
                blocks[current_id] = "\n".join(current_lines)
            current_id = m.group(1)
            current_lines = [line]
        elif current_id:
            current_lines.append(line)
    if current_id and current_lines:
        blocks[current_id] = "\n".join(current_lines)
    return blocks


def _print_summary(results: List[RuleEvalResult]) -> None:
    from collections import Counter
    c = Counter(r.verdict for r in results)
    total = sum(c.values())
    correct = c.get("correct", 0)
    too_strict = c.get("too_strict", 0)
    too_perm = c.get("too_permissive", 0)

    precision = correct / (correct + too_strict) if (correct + too_strict) else 0
    recall    = correct / (correct + too_perm)   if (correct + too_perm) else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print(f"\nShape correctness (M4):")
    print(f"  Total evaluated: {total}")
    for v, n in c.most_common():
        print(f"    {v:16s}: {n}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall:    {recall:.3f}")
    print(f"  F1:        {f1:.3f}")


if __name__ == "__main__":
    main()
