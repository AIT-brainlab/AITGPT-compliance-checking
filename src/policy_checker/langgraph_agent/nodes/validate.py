from __future__ import annotations

from pathlib import Path
from typing import List

from pyshacl import validate
from rdflib import Graph, Literal, Namespace, RDF, SH, BNode, XSD

from policy_checker.langgraph_agent.state import PipelineState, SHACLShape
from policy_checker.langgraph_agent.corpus_config import get_corpus_config

from policy_checker import PROJECT_ROOT


def _get_paths():
    """Resolve gold shapes, test data, and ontology paths from corpus config."""
    cfg = get_corpus_config()
    return cfg.gold_shapes_path, cfg.test_data_path, cfg.ontology_path


def _get_namespace() -> Namespace:
    return Namespace(get_corpus_config().namespace)


# Backward-compatible module-level aliases (deprecated)
SHACL_SHAPES_FILE  = PROJECT_ROOT / "shacl" / "shapes"   / "ait_policy_shapes.ttl"
SHACL_TEST_FILE    = PROJECT_ROOT / "shacl" / "test_data" / "tdd_test_data_fixed.ttl"
ONTOLOGY_FILE      = PROJECT_ROOT / "shacl" / "ontology"  / "ait_policy_ontology.ttl"


def _resolve_parent_shape(source_shape, shapes_graph: Graph) -> str:
    """Walk from a validation result's sourceShape back to its owning NodeShape.
    If source is a BNode (anonymous property shape), find the parent NodeShape."""
    if source_shape is None:
        return "unknown"
    # If source is already a named NodeShape, use it directly
    if not isinstance(source_shape, BNode):
        return str(source_shape)
    # If it's a NodeShape itself (unlikely for BNode, but check)
    if (source_shape, RDF.type, SH.NodeShape) in shapes_graph:
        return str(source_shape)
    # Otherwise, find the NodeShape that has sh:property pointing to this BNode
    for parent in shapes_graph.subjects(SH.property, source_shape):
        return str(parent)
    return str(source_shape)  # fallback

def _merge_shapes(pipeline_shapes: List[SHACLShape]) -> Graph:
    """Merge authoritative shapes with pipeline-generated shapes into one graph."""
    from policy_checker.langgraph_agent.nodes.shacl import _get_ttl_prefixes

    gold_shapes, _, _ = _get_paths()
    ttl_prefixes = _get_ttl_prefixes()

    g = Graph()

    # Load authoritative production shapes
    if gold_shapes.exists():
        g.parse(str(gold_shapes), format="turtle")

    # Append valid pipeline-generated shapes (prepend prefixes so ns resolves)
    skipped = 0
    for shape in pipeline_shapes:
        if not (shape["syntax_valid"] and shape["turtle_text"]):
            continue
        try:
            g.parse(data=ttl_prefixes + shape["turtle_text"], format="turtle")
        except Exception:
            skipped += 1

    if skipped:
        import logging
        logging.getLogger(__name__).warning(
            f"_merge_shapes: skipped {skipped}/{len(pipeline_shapes)} shapes (parse error)"
        )

    return g


def _sanitize_shapes_graph(g: Graph) -> list[str]:
    """Proactively fix known issues in the merged shapes graph before pyshacl.

    Two issues arise when pipeline shapes are merged with gold shapes:
      1) BNodes may acquire duplicate sh:path triples → pyshacl rejects
      2) sh:maxCount / sh:minCount may not have xsd:integer datatype → pyshacl rejects

    Returns a list of diagnostic messages for each fix applied.
    """
    msgs: list[str] = []

    # Fix 1: Deduplicate sh:path on BNodes
    dup_path_fixed = 0
    for bnode in set(g.subjects(SH.path)):
        if not isinstance(bnode, BNode):
            continue
        paths = list(g.objects(bnode, SH.path))
        if len(paths) > 1:
            for extra in paths[1:]:
                g.remove((bnode, SH.path, extra))
            dup_path_fixed += 1
    if dup_path_fixed:
        msgs.append(
            f"validate: sanitized {dup_path_fixed} implicit PropertyShapes "
            f"with duplicate sh:path"
        )

    # Fix 2: Ensure sh:maxCount and sh:minCount are xsd:integer literals
    count_fixed = 0
    for pred in (SH.maxCount, SH.minCount):
        for s, o in list(g.subject_objects(pred)):
            if isinstance(o, Literal) and o.datatype == XSD.integer:
                continue  # already correct
            try:
                int_val = int(o)
            except (ValueError, TypeError):
                int_val = 0  # fallback for unparseable values
            g.remove((s, pred, o))
            g.add((s, pred, Literal(int_val, datatype=XSD.integer)))
            count_fixed += 1
    if count_fixed:
        msgs.append(
            f"validate: fixed {count_fixed} sh:maxCount/sh:minCount literals "
            f"to xsd:integer datatype"
        )

    return msgs


def validate_node(state: PipelineState) -> PipelineState:
    shapes: List[SHACLShape] = state.get("shacl_shapes", [])
    errors: List[str] = []

    gold_shapes, test_data, ontology = _get_paths()

    if not test_data.exists():
        return {
            "validation_results": {"skipped": True, "reason": "test data not found"},
            "conforms": False,
            "current_step": "validate",
            "errors": [f"validate: test data not found at {test_data}"],
        }

    # Build shapes graph
    shapes_graph = _merge_shapes(shapes)
    shape_count = len(list(shapes_graph.subjects(RDF.type, SH.NodeShape)))

    # Load test data
    data_graph = Graph()
    data_graph.parse(str(test_data), format="turtle")
    entity_count = len(set(data_graph.subjects()))

    # ── Proactive sanitization before pyshacl ──────────────────────────
    errors.extend(_sanitize_shapes_graph(shapes_graph))

    # Run validation
    def _run_pyshacl(sg: Graph) -> tuple:
        return validate(
            data_graph,
            shacl_graph=sg,
            ont_graph=Graph().parse(str(ontology)) if ontology.exists() else None,
            inference="rdfs",
            abort_on_first=False,
            meta_shacl=False,
            advanced=True,
            debug=False,
        )

    try:
        conforms, results_graph, results_text = _run_pyshacl(shapes_graph)
    except Exception as exc:
        errors.append(f"validate: pyshacl error: {exc}")
        return {
            "validation_results": {"error": str(exc)},
            "conforms": False,
            "current_step": "validate",
            "errors": errors,
        }

    # Parse violations — resolve anonymous property shapes to parent NodeShape
    violations = []
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        source_shape = results_graph.value(result, SH.sourceShape)
        parent_shape = _resolve_parent_shape(source_shape, shapes_graph)
        violations.append({
            "focus_node":     str(results_graph.value(result, SH.focusNode)),
            "source_shape":   parent_shape,
            "source_path":    str(results_graph.value(result, SH.resultPath) or ""),
            "result_message": str(results_graph.value(result, SH.resultMessage)),
            "severity":       str(results_graph.value(result, SH.resultSeverity)),
        })

    validation_results = {
        "conforms":          conforms,
        "shape_count":       shape_count,
        "entity_count":      entity_count,
        "violation_count":   len(violations),
        "violations":        violations,   # full list for report triage
        "pipeline_shapes":   len(shapes),
        "valid_shapes":      sum(1 for s in shapes if s["syntax_valid"]),
    }

    # Save validation results (cap violations at 50 for JSON file size)
    output_dir = PROJECT_ROOT / "data" / "output" / state["source"]
    output_dir.mkdir(parents=True, exist_ok=True)
    import json
    save_results = {**validation_results, "violations": violations[:50]}
    (output_dir / "validation_results.json").write_text(
        json.dumps(save_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "validation_results": validation_results,
        "conforms": conforms,
        "current_step": "validate",
        "errors": errors,
    }
