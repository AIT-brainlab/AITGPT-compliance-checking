from __future__ import annotations

from pathlib import Path
from typing import List

from pyshacl import validate
from rdflib import Graph, Namespace, RDF, SH, BNode

from langgraph_agent.state import PipelineState, SHACLShape
from langgraph_agent.corpus_config import get_corpus_config

PROJECT_ROOT = Path(__file__).parent.parent.parent


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
    from langgraph_agent.nodes.shacl import _get_ttl_prefixes

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

    # Run validation — with sanitization retry for duplicate sh:path errors
    def _sanitize_duplicate_paths(g: Graph) -> int:
        """Remove duplicate sh:path triples from implicit PropertyShapes (BNodes).
        Returns number of BNodes sanitized."""
        fixed = 0
        for bnode in set(g.subjects(SH.path)):
            if not isinstance(bnode, BNode):
                continue
            paths = list(g.objects(bnode, SH.path))
            if len(paths) > 1:
                # Keep only the first path, remove the rest
                for extra in paths[1:]:
                    g.remove((bnode, SH.path, extra))
                fixed += 1
        return fixed

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
        if "sh:path" in str(exc):
            # Sanitize and retry
            fixed = _sanitize_duplicate_paths(shapes_graph)
            errors.append(
                f"validate: sanitized {fixed} implicit PropertyShapes with "
                f"duplicate sh:path — retrying validation"
            )
            try:
                conforms, results_graph, results_text = _run_pyshacl(shapes_graph)
            except Exception as exc2:
                errors.append(f"validate: pyshacl error after sanitization: {exc2}")
                return {
                    "validation_results": {"error": str(exc2)},
                    "conforms": False,
                    "current_step": "validate",
                    "errors": errors,
                }
        else:
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
    output_dir = PROJECT_ROOT / "output" / state["source"]
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
