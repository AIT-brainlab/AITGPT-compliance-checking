"""
PolicyChecker — Compliance Dashboard (FastAPI)

A web-based demo that showcases the SHACL-based compliance checking pipeline.
Users can browse extracted rules, submit RDF data, and see live validation results.

Usage:
    pip install fastapi uvicorn jinja2 python-multipart
    cd demo
    python app.py
    # Open http://localhost:8000
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = FastAPI(title="PolicyChecker Compliance Dashboard", version="1.0.0")

# Static files and templates
DEMO_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(DEMO_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(DEMO_DIR / "templates"))

# ── Data paths ────────────────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "output" / "ait"
SHAPES_FILE = OUTPUT_DIR / "shapes_generated.ttl"
RULES_FILE = OUTPUT_DIR / "classified_rules.json"
FOL_FILE = OUTPUT_DIR / "fol_formulas.json"
REPORT_FILE = OUTPUT_DIR / "pipeline_report.json"
TEST_DATA_FILE = PROJECT_ROOT / "shacl" / "test_data" / "tdd_test_data_fixed.ttl"
ONTOLOGY_FILE = PROJECT_ROOT / "shacl" / "ontology" / "ait_policy_ontology.ttl"


# ── Cached data loading ──────────────────────────────────────────────────
_cache: dict = {}

def _load_json(path: Path) -> dict | list:
    if str(path) not in _cache:
        if path.exists():
            _cache[str(path)] = json.loads(path.read_text(encoding="utf-8"))
        else:
            _cache[str(path)] = []
    return _cache[str(path)]


def _load_text(path: Path) -> str:
    if path.exists():
        text = path.read_text(encoding="utf-8")
        # Sanitise broken multi-line FOL comments in generated shapes
        if path == SHAPES_FILE:
            text = _sanitize_turtle(text)
        return text
    return ""


def _sanitize_turtle(text: str) -> str:
    """Fix broken Turtle syntax in generated shapes.

    Issues handled:
    1. Multi-line FOL comments where continuation lines lack '#' prefix
    2. SPARQL-style '?x' variables in Turtle (invalid)
    """
    import re
    lines = text.split('\n')
    result = []
    in_fol_comment = False
    for line in lines:
        stripped = line.strip()
        # Detect start of FOL comment
        if stripped.startswith('# FOL:'):
            in_fol_comment = True
            result.append(line)
            continue
        # If we're inside a FOL comment continuation
        if in_fol_comment:
            # Valid Turtle starts with a prefix, URI, or is blank
            if (stripped == '' or stripped.startswith('#') or
                stripped.startswith('@') or stripped.startswith('ait:') or
                stripped.startswith('sh:') or stripped.startswith('rdf') or
                stripped.startswith('deontic:')):
                in_fol_comment = False
            else:
                # This is a continuation of the FOL comment — fix it
                result.append('# ' + stripped)
                continue

        # Fix ?x variables in non-comment lines (invalid in Turtle)
        if not stripped.startswith('#') and '?' in line:
            line = re.sub(r'\?[a-zA-Z_]\w*', 'ait:Thing', line)

        result.append(line)
    return '\n'.join(result)


def _get_rules() -> list:
    return _load_json(RULES_FILE)


def _get_fol() -> list:
    return _load_json(FOL_FILE)


def _get_report() -> dict:
    data = _load_json(REPORT_FILE)
    return data if isinstance(data, dict) else {}


def _get_shapes_for_rule(rule_id: str) -> str:
    """Extract the SHACL shape block for a specific rule from the combined TTL."""
    shapes_text = _load_text(SHAPES_FILE)
    if not shapes_text:
        return ""
    # Find the block for this rule
    marker = f"# Rule: {rule_id}"
    start = shapes_text.find(marker)
    if start == -1:
        return ""
    # Find the next rule block or end
    next_marker = shapes_text.find("# Rule:", start + len(marker))
    if next_marker == -1:
        return shapes_text[start:].strip()
    return shapes_text[start:next_marker].strip()




# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/stats")
async def get_stats():
    """Pipeline summary statistics."""
    report = _get_report()
    summary = report.get("summary", {})
    rules = _get_rules()
    # Count by type
    type_dist = {}
    for r in rules:
        t = r.get("rule_type", "unknown")
        type_dist[t] = type_dist.get(t, 0) + 1

    return {
        "total_rules": len(rules),
        "type_distribution": type_dist,
        "sentences_extracted": summary.get("sentences_extracted", 0),
        "candidates_prefiltered": summary.get("candidates_prefiltered", 0),
        "fol_ok": summary.get("fol_formulas_ok", 0),
        "fol_failed": summary.get("fol_formulas_failed", 0),
        "shapes_total": summary.get("shacl_shapes_total", 0),
        "shapes_valid": summary.get("shacl_shapes_valid", 0),
        "pipeline_version": report.get("pipeline_version", "unknown"),
    }


@app.get("/api/rules")
async def get_rules(
    rule_type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
):
    """List classified rules with filtering and pagination."""
    rules = _get_rules()

    # Filter by type
    if rule_type and rule_type != "all":
        rules = [r for r in rules if r.get("rule_type") == rule_type]

    # Search
    if search:
        q = search.lower()
        rules = [r for r in rules if q in r.get("text", "").lower()
                 or q in r.get("rule_id", "").lower()
                 or q in r.get("source_document", "").lower()]

    total = len(rules)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "rules": rules[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


@app.get("/api/rules/{rule_id}")
async def get_rule_detail(rule_id: str):
    """Get a single rule with its SHACL shape and FOL formula."""
    rules = _get_rules()
    rule = next((r for r in rules if r["rule_id"] == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    # Find matching FOL
    fol_formulas = _get_fol()
    fol = next((f for f in fol_formulas if f["rule_id"] == rule_id), None)

    # Get SHACL shape
    shape = _get_shapes_for_rule(rule_id)

    return {
        "rule": rule,
        "fol": fol,
        "shacl_shape": shape,
    }


# ── Database-backed endpoints ────────────────────────────────────────────

@app.get("/api/db-status")
async def db_status():
    """Check if PostgreSQL is reachable and return entity count."""
    try:
        from db.connection import db_health
        return db_health()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/db-entities")
async def list_db_entities():
    """List all entities in the database (name, type, property count)."""
    try:
        from db.rdf_converter import list_entities
        entities = list_entities()
        return {"entities": entities, "total": len(entities)}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "detail": "Failed to list DB entities"},
        )


@app.post("/api/load-from-db")
async def load_from_db(request: Request):
    """
    Convert selected (or all) DB entities to RDF Turtle.

    Request body (JSON):
        { "entities": ["Somchai", "Priya"] }   <- specific entities
        { "entities": "all" }                   <- all entities (default)
        {}                                      <- all entities

    Returns:
        { "turtle": "...", "entity_count": N, "property_count": M }
    """
    try:
        from db.rdf_converter import convert_db_to_turtle

        body = await request.json()
        entity_names = body.get("entities", "all")

        if entity_names == "all" or not isinstance(entity_names, list):
            result = convert_db_to_turtle()
        else:
            result = convert_db_to_turtle(entity_names=entity_names)

        return result
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print(f"[load-from-db] ERROR: {exc}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "detail": "Failed to convert DB to RDF"},
        )


@app.post("/api/validate")
async def validate_data(request: Request):
    """Validate submitted RDF data against pipeline SHACL shapes."""
    body = await request.json()
    data_turtle = body.get("data", "")
    selected_shapes = body.get("shapes", "all")  # "all" or list of rule_ids

    if not data_turtle.strip():
        raise HTTPException(status_code=400, detail="No RDF data provided")

    try:
        from rdflib import Graph
        from pyshacl import validate

        # Load data graph
        data_graph = Graph()
        data_graph.parse(data=data_turtle, format="turtle")

        # Load shapes — clear cache to pick up sanitisation
        if str(SHAPES_FILE) in _cache:
            del _cache[str(SHAPES_FILE)]
        shapes_text = _load_text(SHAPES_FILE)

        if selected_shapes != "all" and isinstance(selected_shapes, list):
            # Extract only selected shape blocks
            blocks = []
            prefix_end = shapes_text.find("# Rule:")
            if prefix_end > 0:
                blocks.append(shapes_text[:prefix_end])
            for rid in selected_shapes:
                block = _get_shapes_for_rule(rid)
                if block:
                    blocks.append(block)
            shapes_text = "\n\n".join(blocks)

        # Parse shapes block-by-block — skip any LLM-generated invalid Turtle
        shapes_graph = Graph()
        prefix_block = shapes_text[:shapes_text.find("# Rule:")] if "# Rule:" in shapes_text else ""
        shape_blocks = shapes_text.split("# Rule:")
        skipped = 0
        for i, block in enumerate(shape_blocks):
            if i == 0:
                # This is the prefix block — always include
                try:
                    shapes_graph.parse(data=block, format="turtle")
                except Exception:
                    pass
                continue
            turtle_block = prefix_block + "\n# Rule:" + block
            try:
                shapes_graph.parse(data=turtle_block, format="turtle")
            except Exception:
                skipped += 1

        # Run pyshacl validation
        # Note: do NOT pass ont_graph — causes 'NoneType' error in some
        # pyshacl/rdflib version combinations. inference="none" is sufficient.
        conforms, results_graph, results_text = validate(
            data_graph,
            shacl_graph=shapes_graph,
            inference="none",
            abort_on_first=False,
            do_owl_imports=False,
        )

        # Parse violations from results graph
        violations = _parse_violations(results_graph)

        # Count entities
        entities = set()
        for s in data_graph.subjects():
            entities.add(str(s))

        return {
            "conforms": conforms,
            "total_violations": len(violations),
            "total_entities": len(entities),
            "violations": violations[:200],  # cap for UI
            "results_text": results_text[:5000] if results_text else "",
        }

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print(f"[validate] ERROR: {exc}\n{tb}")
        return JSONResponse(
            status_code=422,
            content={"error": str(exc), "detail": "Validation failed"},
        )


def _parse_violations(results_graph) -> list:
    """Extract structured violations from pyshacl results graph."""
    from rdflib import SH, RDF, Namespace
    SH_NS = Namespace("http://www.w3.org/ns/shacl#")

    violations = []
    for result in results_graph.subjects(RDF.type, SH_NS.ValidationResult):
        v = {}
        for p, o in results_graph.predicate_objects(result):
            pname = str(p).split("#")[-1]
            v[pname] = str(o)

        # Map to friendly names
        focus = v.get("focusNode", "")
        source = v.get("sourceShape", "")
        severity_raw = v.get("resultSeverity", "")
        message = v.get("resultMessage", "")
        path = v.get("resultPath", "")

        # Clean up URIs
        focus_label = focus.split("#")[-1] if "#" in focus else focus.split("/")[-1]
        source_label = source.split("#")[-1] if "#" in source else source.split("/")[-1]
        severity_label = severity_raw.split("#")[-1] if "#" in severity_raw else severity_raw
        path_label = path.split("#")[-1] if "#" in path else path.split("/")[-1]

        violations.append({
            "focus_node": focus_label,
            "focus_uri": focus,
            "source_shape": source_label,
            "source_uri": source,
            "severity": severity_label,
            "message": message[:300],
            "path": path_label,
        })

    # Sort: Violation > Warning > Info
    severity_order = {"Violation": 0, "Warning": 1, "Info": 2}
    violations.sort(key=lambda v: severity_order.get(v["severity"], 3))

    return violations


# ── Startup ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"\n{'='*60}")
    print(f"  PolicyChecker — Compliance Dashboard")
    print(f"  http://localhost:8000")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
