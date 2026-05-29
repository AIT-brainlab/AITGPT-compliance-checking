"""
PolicyChecker — Compliance Dashboard (FastAPI)

A web-based demo that showcases the SHACL-based compliance checking pipeline.
Users can browse extracted rules, submit RDF data, and see live validation results.

Usage:
    pip install fastapi uvicorn jinja2 python-multipart
    cd web
    python app.py
    # Open http://localhost:3000
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

 
# PROJECT_ROOT = Path(__file__).parent.parent
# sys.path.insert(0, str(PROJECT_ROOT))
from policy_checker import PROJECT_ROOT
 

from policy_checker.core.turtle_utils import get_rule_block, prefix_block

app = FastAPI(title="PolicyChecker Compliance Dashboard", version="2.0.0")

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data paths ────────────────────────────────────────────────────────────
DEMO_DIR = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "ait"
SHAPES_FILE = OUTPUT_DIR / "shapes_generated.ttl"
RULES_FILE = OUTPUT_DIR / "classified_rules.json"
FOL_FILE = OUTPUT_DIR / "fol_formulas.json"
REPORT_FILE = OUTPUT_DIR / "pipeline_report.json"
TEST_DATA_FILE = PROJECT_ROOT / "data" / "shacl" / "test_data" / "tdd_test_data_fixed.ttl"
ONTOLOGY_FILE = PROJECT_ROOT / "data" / "shacl" / "ontology" / "ait_policy_ontology.ttl"
DIST_DIR = DEMO_DIR / "frontend" / "dist"


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
        if path == SHAPES_FILE:
            text = _sanitize_turtle(text)
        return text
    return ""


def _sanitize_turtle(text: str) -> str:
    """Fix broken Turtle syntax in generated shapes."""
    import re
    lines = text.split('\n')
    result = []
    in_fol_comment = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# FOL:'):
            in_fol_comment = True
            result.append(line)
            continue
        if in_fol_comment:
            if (stripped == '' or stripped.startswith('#') or
                stripped.startswith('@') or stripped.startswith('ait:') or
                stripped.startswith('sh:') or stripped.startswith('rdf') or
                stripped.startswith('deontic:')):
                in_fol_comment = False
            else:
                result.append('# ' + stripped)
                continue
        if not stripped.startswith('#') and '?' in line:
            line = re.sub(r'\?[a-zA-Z_]\w*', 'ait:Thing', line)
        result.append(line)
    return '\n'.join(result)


def _invalidate_cache():
    """Clear cached data so fresh pipeline output is loaded."""
    _cache.clear()


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
    return get_rule_block(shapes_text, rule_id) if shapes_text else ""


# ── API Routes ────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    """Pipeline summary statistics."""
    report = _get_report()
    summary = report.get("summary", {})
    rules = _get_rules()
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
    if rule_type and rule_type != "all":
        rules = [r for r in rules if r.get("rule_type") == rule_type]
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

    fol_formulas = _get_fol()
    fol = next((f for f in fol_formulas if f["rule_id"] == rule_id), None)
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
        from policy_checker.database.connection import db_health
        return db_health()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/db-entities")
async def list_db_entities():
    """List all entities in the database (name, type, property count)."""
    try:
        from policy_checker.database.rdf_converter import list_entities
        entities = list_entities()
        return {"entities": entities, "total": len(entities)}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "detail": "Failed to list DB entities"},
        )


@app.post("/api/load-from-db")
async def load_from_db(request: Request):
    """Convert selected (or all) DB entities to RDF Turtle."""
    try:
        from policy_checker.database.rdf_converter import convert_db_to_turtle

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
    selected_shapes = body.get("shapes", "all")

    if not data_turtle.strip():
        raise HTTPException(status_code=400, detail="No RDF data provided")

    try:
        from rdflib import Graph, Namespace, URIRef
        from pyshacl import validate

        data_graph = Graph()
        data_graph.parse(data=data_turtle, format="turtle")

        if str(SHAPES_FILE) in _cache:
            del _cache[str(SHAPES_FILE)]
        shapes_text = _load_text(SHAPES_FILE)
        prefix = prefix_block(shapes_text)

        if selected_shapes != "all" and isinstance(selected_shapes, list):
            # Extract only selected shape blocks
            blocks = [prefix] if prefix.strip() else []
            for rid in selected_shapes:
                block = _get_shapes_for_rule(rid)
                if block:
                    blocks.append(block)
            shapes_text = "\n\n".join(blocks)
            prefix = prefix_block(shapes_text)

        shapes_graph = Graph()
        skipped = 0
        shape_blocks = shapes_text.split("# Rule:")
        for i, block in enumerate(shape_blocks):
            if i == 0:
                try:
                    shapes_graph.parse(data=block, format="turtle")
                except Exception:
                    pass
                continue
            turtle_block = prefix + "\n# Rule:" + block
            try:
                shapes_graph.parse(data=turtle_block, format="turtle")
            except Exception:
                skipped += 1

        # ── Filter to curated shapes only ──
        # Instead of validating against all 443 auto-generated shapes
        # (many of which share paths with wrong semantics), we use a
        # hand-picked set — one per DB property, correct target class.
        AIT = Namespace("http://example.org/ait-policy#")
        SH = Namespace("http://www.w3.org/ns/shacl#")
        RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

        _CURATED_SHAPES = {
            # Student fee obligations (minCount 1 + xsd:decimal)
            AIT.AIT_0007Shape,  # payFirstSemesterFee (Student, min1)
            AIT.AIT_0096Shape,  # payRentForStayOnCampus (Student, min1, NO datatype)
            AIT.AIT_0219Shape,  # feesPaid — best fee message (Student, min1)
            # Accommodation obligations
            AIT.AIT_0068Shape,  # confirmOfferMove (Student, min1)
            AIT.AIT_0056Shape,  # vacateRoom - vacate after graduation (Student, min1)
            AIT.AIT_0070Shape,  # maintainCleanlinessOfBedroomAndFacilities (Student, min1)
            AIT.AIT_0072Shape,  # maintainCleanlinessOfCommonAreaAndLandscape (Student, min1)
            # Conduct obligations
            AIT.AIT_0041Shape,  # bringConcernsToAttention (Student, min1)
            AIT.AIT_0150Shape,  # meetHighestStandardsOfPersonalEthicalAndMoralConduct (Student, min1)
            # Conduct prohibitions
            AIT.AIT_0086Shape,  # cookInProhibitedDormitory (Student, max0)
            AIT.AIT_0089Shape,  # petInStudentAccommodation (Student, max0)
            AIT.AIT_0079Shape,  # noisyGroupStudyOrPartyInStudentAccommodation (Student, max0)
            AIT.AIT_0077Shape,  # disturbingpeace (Student, max0)
            # Faculty obligations
            AIT.AIT_0005Shape,  # followProceduresForDisciplinaryActions (Faculty, min1)
            AIT.AIT_0142Shape,  # makeKnownCriteriaForGrading (Faculty, min1)
            AIT.AIT_0101Shape,  # disclose conflicts (Employee, min1)
            AIT.AIT_0100Shape,  # usesAuthorityEthically (Employee, min1)
            # Staff
            AIT.AIT_0029Shape,  # settled (Employee, min1)
        }

        # Remove all NodeShapes NOT in the curated set
        all_node_shapes = set(shapes_graph.subjects(RDF_TYPE, SH.NodeShape))
        to_remove = all_node_shapes - _CURATED_SHAPES
        for ns in to_remove:
            for prop_shape in shapes_graph.objects(ns, SH.property):
                for p2, o2 in list(shapes_graph.predicate_objects(prop_shape)):
                    shapes_graph.remove((prop_shape, p2, o2))
            for p2, o2 in list(shapes_graph.predicate_objects(ns)):
                shapes_graph.remove((ns, p2, o2))

        # Strip sh:datatype and sh:pattern from curated shapes to avoid
        # false positives (we use presence/absence for compliance checking,
        # not typed value validation)
        for ns in _CURATED_SHAPES:
            for prop_shape in shapes_graph.objects(ns, SH.property):
                for dt_val in list(shapes_graph.objects(prop_shape, SH.datatype)):
                    shapes_graph.remove((prop_shape, SH.datatype, dt_val))
                for pat_val in list(shapes_graph.objects(prop_shape, SH.pattern)):
                    shapes_graph.remove((prop_shape, SH.pattern, pat_val))

        conforms, results_graph, results_text = validate(
            data_graph,
            shacl_graph=shapes_graph,
            inference="none",
            abort_on_first=False,
            do_owl_imports=False,
        )

        violations = _parse_violations(results_graph)

        entities = set()
        for s in data_graph.subjects():
            entities.add(str(s))

        return {
            "conforms": conforms,
            "total_violations": len(violations),
            "total_entities": len(entities),
            "violations": violations[:200],
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


# Remediation suggestions keyed by property path fragment
_REMEDIATION_MAP = {
    "payFirstSemesterFee": "Pay the first semester tuition fee before the registration deadline.",
    "payFee": "Settle all outstanding tuition fees with the Finance Office.",
    "feesPaid": "Ensure all fees are paid in full within 30 days from semester start.",
    "fullPayment": "Complete the remaining tuition balance to avoid enrollment suspension.",
    "cookInProhibitedDormitory": "Remove all cooking equipment from the dormitory immediately. Use designated cooking areas.",
    "cookInUnit": "Cooking is prohibited in this accommodation category. Use shared kitchen facilities.",
    "petInStudentAccommodation": "Remove the pet from student accommodation. Pets are not allowed per housing policy.",
    "noisyGroupStudyOrPartyInStudentAccommodation": "Cease noisy activities in the dorm. Use designated study rooms for group work.",
    "disturbingpeace": "Refrain from disturbing other residents. A formal reprimand may be issued.",
    "disturbFellowStudentsInResidentialAreas": "Stop activities that disturb fellow residents, especially after 23:00.",
    "maintainCleanlinessOfBedroomAndFacilities": "Clean your room and maintain hygiene standards as required by housing policy.",
    "maintainCleanlinessOfCommonAreaAndLandscape": "Help maintain cleanliness of common areas and surrounding landscape.",
    "regularcleaningandhygieneoftheunit": "Perform regular cleaning and maintain unit hygiene standards.",
    "vacateRoom": "Vacate your room within 5 days after graduation/completion of studies.",
    "vacatesRoom": "Vacate the accommodation unit as required by the housing agreement.",
    "confirmOfferMove": "Confirm the accommodation offer within 5 working days or lose the allocation.",
    "makeKnownCriteriaForGrading": "Publish grading criteria to students at the beginning of each course.",
    "followProceduresForDisciplinaryActions": "Follow institutional disciplinary procedures as outlined in the staff handbook.",
    "disclose": "Disclose any actual or potential conflicts of interest to your supervisor.",
    "suspectCheatingDuringExamOrAssignmentOrResearchProject": "Report any suspected academic misconduct to the relevant committee.",
    "reported": "Report all gifts and benefits received as required by the ethics policy.",
    "settled": "Settle all outstanding travel authorizations and promissory notes by the due dates.",
    "usesAuthorityEthicallyWithRespectAndSensitivityAndInAccordanceWithInstitutesPolicies":
        "Exercise supervisory authority ethically, with respect and sensitivity.",
    "meetHighestStandardsOfPersonalEthicalAndMoralConduct":
        "Uphold the highest standards of personal ethical and moral conduct.",
    "bringConcernsToAttention": "Report any student welfare concerns to the Director of Student Affairs.",
    "correspondAsAuthorWithJournal": "Ensure the committee chair serves as corresponding author for journal submissions.",
    "multiAuthoredArticleWrittenByStudentShouldBeFirstAuthorUnlessJournalRequiresDifferentOrder":
        "Ensure student is listed as first author in multi-authored thesis-based articles.",
    "electsChair": "Hold an election to appoint a committee chair.",
}


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

        focus = v.get("focusNode", "")
        source = v.get("sourceShape", "")
        severity_raw = v.get("resultSeverity", "")
        message = v.get("resultMessage", "")
        path = v.get("resultPath", "")

        focus_label = focus.split("#")[-1] if "#" in focus else focus.split("/")[-1]
        source_label = source.split("#")[-1] if "#" in source else source.split("/")[-1]
        severity_label = severity_raw.split("#")[-1] if "#" in severity_raw else severity_raw
        path_label = path.split("#")[-1] if "#" in path else path.split("/")[-1]

        # Generate remediation suggestion
        suggestion = _REMEDIATION_MAP.get(path_label, "")
        if not suggestion and message:
            suggestion = "Review and address: " + message[:120]

        violations.append({
            "focus_node": focus_label,
            "focus_uri": focus,
            "source_shape": source_label,
            "source_uri": source,
            "severity": severity_label,
            "message": message[:300],
            "path": path_label,
            "suggestion": suggestion,
        })

    severity_order = {"Violation": 0, "Warning": 1, "Info": 2}
    violations.sort(key=lambda v: severity_order.get(v["severity"], 3))
    return violations


# ── Pipeline execution (SSE) ─────────────────────────────────────────────

@app.post("/api/run-pipeline")
async def run_pipeline(request: Request):
    """Run the full pipeline and stream progress via SSE."""
    body = await request.json()
    source = body.get("source", "ait")

    def generate():
        def send(event_data):
            return f"data: {json.dumps(event_data)}\n\n"

        steps = [
            ("extract", "PDF Extraction"),
            ("prefilter", "Heuristic Pre-filter"),
            ("classify", "LLM Classification"),
            ("fol", "FOL Formalization"),
            ("shacl_fol", "SHACL Generation (FOL)"),
            ("shacl_nl", "SHACL Generation (NL)"),
            ("validate", "SHACL Validation"),
            ("report", "Report Generation"),
        ]

        # ">> Step X" markers are printed AFTER each LangGraph node
        # completes (by run.py's graph.stream loop).  But tqdm bars
        # like "Generating FOL: 5%|█…" run DURING the node.  So we
        # use BOTH signals:
        #   - ">> Step X" → mark the PREVIOUS step as done
        #   - tqdm desc  → mark the CURRENT step as started (early)

        # Map ">> Step X" to the step index they represent.
        # When we see ">> Step 2b", it means classify just finished.
        step_done_markers = {
            "Step 1":  0,   # extract done
            "Step 2a": 1,   # prefilter done
            "Step 2b": 2,   # classify done
            "Step 2c": 2,   # reclassify done (same UI step)
            "Step 3":  3,   # fol done
            "Step 4a": 4,   # shacl_fol done
            "Step 4b": 5,   # shacl_nl done
            "Step 5":  6,   # validate done
            "Step 6":  7,   # report done
        }

        # Map tqdm desc substrings to the step they START.
        # These fire as soon as the node begins its work.
        tqdm_start_markers = {
            "Classifying":    2,   # classify step
            "Reclassifying":  2,   # same UI step
            "Generating FOL": 3,   # fol step
            "Direct SHACL":   5,   # shacl_nl step
        }

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            cmd = [sys.executable, "-u", "-m", "policy_checker.langgraph_agent.run", "--source", source]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
                env=env,
                bufsize=0,  # unbuffered binary
            )

            current_step_idx = -1
            last_progress_time = 0
            conn_refused_count = 0
            override_count = 0

            def transition_to(idx):
                """Move the step tracker to a new step."""
                nonlocal current_step_idx
                events = []
                if idx != current_step_idx:
                    # Mark all steps between current and target as done
                    if current_step_idx >= 0:
                        for i in range(current_step_idx, min(idx, len(steps))):
                            sid, _ = steps[i]
                            events.append(send({"type": "step_done", "step": sid}))
                    # Start the new step
                    if idx < len(steps):
                        sid, slabel = steps[idx]
                        events.append(send({"type": "step_start", "step": sid, "label": slabel}))
                    current_step_idx = idx
                return events

            import re

            def parse_tqdm_line(line):
                """Extract clean progress info from tqdm output.
                Input:  'Generating FOL:  27%|███████      | 120/443 [00:09<00:25, 12.97it/s]'
                Output: 'Generating FOL: 27% | 120/443 [00:09<00:25, 12.97it/s]'
                """
                m = re.match(
                    r'(.+?):\s*(\d+)%\|[^|]*\|\s*(\d+)/(\d+)\s*(\[.+\])',
                    line
                )
                if m:
                    desc, pct, cur, tot, timing = m.groups()
                    return f"{desc.strip()}: {pct}% | {cur}/{tot} {timing}"
                m2 = re.match(r'(.+?):\s*(\d+)%\|[^|]*\|\s*(\d+)/(\d+)', line)
                if m2:
                    desc, pct, cur, tot = m2.groups()
                    return f"{desc.strip()}: {pct}% | {cur}/{tot}"
                return line

            def process_line(line):
                """Process a single complete line and yield SSE events."""
                nonlocal current_step_idx, last_progress_time
                nonlocal conn_refused_count, override_count
                events = []

                # ── ">> Step X" done markers ──
                for marker, idx in step_done_markers.items():
                    if f">> {marker}" in line or f">>{marker}" in line:
                        # Only process if we haven't already passed this step
                        if idx >= current_step_idx:
                            events.extend(transition_to(idx))
                            sid, _ = steps[idx]
                            events.append(send({"type": "step_done", "step": sid}))
                            current_step_idx = idx + 1
                            if idx + 1 < len(steps):
                                nsid, nslabel = steps[idx + 1]
                                events.append(send({"type": "step_start", "step": nsid, "label": nslabel}))
                        return events  # Don't forward step markers as log text

                # ── tqdm progress bars ──
                is_progress = ("%" in line and "|" in line) or \
                              ("%" in line and ("it/s" in line or "s/it" in line))
                if is_progress:
                    for desc, idx in tqdm_start_markers.items():
                        if desc in line and idx > current_step_idx:
                            events.extend(transition_to(idx))
                            break
                    now = time.time()
                    if now - last_progress_time >= 0.5:
                        last_progress_time = now
                        events.append(send({"type": "log", "level": "info", "message": parse_tqdm_line(line)}))
                    return events

                # ── Warnings (deduplicated) ──
                if "[WARN]" in line:
                    if "Connection refused" in line:
                        conn_refused_count += 1
                        if conn_refused_count == 1:
                            events.append(send({"type": "warning", "message": line}))
                            events.append(send({"type": "log", "level": "warn",
                                                "message": "  (Ollama not reachable — using cached results for remaining rules)"}))
                        elif conn_refused_count % 50 == 0:
                            events.append(send({"type": "log", "level": "warn",
                                                "message": f"  ... {conn_refused_count} cache-miss rules skipped (Ollama offline)"}))
                    elif "override" in line:
                        override_count += 1
                        if override_count <= 3:
                            events.append(send({"type": "warning", "message": line}))
                        elif override_count == 4:
                            events.append(send({"type": "log", "level": "warn",
                                                "message": "  ... (more override warnings suppressed)"}))
                    else:
                        events.append(send({"type": "warning", "message": line}))
                    return events

                # ── Separators ──
                if line.startswith("=") or (line.startswith("-") and len(line) > 5 and line == line[0] * len(line)):
                    return events

                # ── Pipeline start ──
                if "PolicyChecker" in line and current_step_idx < 0:
                    events.extend(transition_to(0))
                    events.append(send({"type": "log", "level": "info", "message": line}))
                    return events

                # ── Everything else ──
                events.append(send({"type": "log", "level": "info", "message": line}))
                return events

            # ── Main read loop ──
            # Read in chunks, decode UTF-8 properly, buffer incomplete lines
            raw_buffer = b""     # undecoded bytes (partial UTF-8)
            text_buffer = ""     # decoded text waiting for a line ending

            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                raw_buffer += chunk

                # Decode as much UTF-8 as possible
                try:
                    decoded = raw_buffer.decode("utf-8")
                    raw_buffer = b""
                except UnicodeDecodeError:
                    # Find the last fully decodable prefix
                    for i in range(len(raw_buffer) - 1, max(len(raw_buffer) - 5, -1), -1):
                        try:
                            decoded = raw_buffer[:i].decode("utf-8")
                            raw_buffer = raw_buffer[i:]
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        continue

                text_buffer += decoded

                # Split into complete lines (\n or \r delimited)
                # Keep the last segment if it doesn't end with a delimiter
                parts = re.split(r'(\r\n|\r|\n)', text_buffer)

                # parts = [seg0, delim0, seg1, delim1, ..., last_seg]
                # If text_buffer ends with a delimiter, last_seg is ""
                # If not, last_seg is an incomplete line to carry forward
                if len(parts) >= 2 and parts[-1] != "":
                    # Last segment has no trailing delimiter — carry it forward
                    text_buffer = parts[-1]
                    parts = parts[:-1]
                else:
                    text_buffer = ""

                # Process complete lines
                for part in parts:
                    line = part.strip()
                    if not line:
                        continue
                    for ev in process_line(line):
                        yield ev

            # Flush any remaining text
            if text_buffer.strip():
                for ev in process_line(text_buffer.strip()):
                    yield ev
            if raw_buffer:
                try:
                    remaining = raw_buffer.decode("utf-8", errors="replace").strip()
                    if remaining:
                        for ev in process_line(remaining):
                            yield ev
                except Exception:
                    pass

            proc.wait()

            # Mark all remaining steps as done
            if current_step_idx >= 0:
                for i in range(current_step_idx, len(steps)):
                    sid, _ = steps[i]
                    yield send({"type": "step_done", "step": sid})

            # Check exit code
            if proc.returncode != 0:
                yield send({"type": "error", "message": f"Pipeline exited with code {proc.returncode}"})
            else:
                # Invalidate cache and load fresh report
                _invalidate_cache()
                report = _get_report()
                summary = report.get("summary", {})

                yield send({
                    "type": "summary",
                    "data": {
                        "sentences_extracted": summary.get("sentences_extracted", 0),
                        "rules_classified": summary.get("rules_classified", 0),
                        "fol_ok": summary.get("fol_formulas_ok", 0),
                        "fol_failed": summary.get("fol_formulas_failed", 0),
                        "shapes_valid": summary.get("shacl_shapes_valid", 0),
                        "violations": summary.get("violations_found", 0),
                    }
                })

        except Exception as exc:
            yield send({"type": "error", "message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Serve React build (production) ───────────────────────────────────────

# Try to mount the built React app
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="react-assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        """Serve React app for client-side routing."""
        # Don't catch API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        # Serve static file if it exists
        file_path = DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html for client-side routing
        return FileResponse(DIST_DIR / "index.html")


# ── Frontend helpers ──────────────────────────────────────────────────────

def _npm_env() -> dict:
    """Return an env dict with the nodeenv bin dir prepended to PATH."""
    import sys
    node_bin = Path(sys.prefix) / "node_env" / "bin"
    env = os.environ.copy()
    env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    return env


def run_frontend() -> None:
    """Start the Vite dev server (npm run dev)."""
    import subprocess
    frontend_dir = DEMO_DIR / "frontend"
    subprocess.run(["npm", "run", "dev"], cwd=frontend_dir, env=_npm_env(), check=True)


def build_frontend() -> None:
    """Build the React frontend for production (npm run build)."""
    import subprocess
    frontend_dir = DEMO_DIR / "frontend"
    env = _npm_env()
    if not (frontend_dir / "node_modules").exists():
        print("Installing npm dependencies...")
        subprocess.run(["npm", "install"], cwd=frontend_dir, env=env, check=True)
    print("Building React frontend...")
    subprocess.run(["npm", "run", "build"], cwd=frontend_dir, env=env, check=True)
    print(f"Build complete → {DIST_DIR}")


# ── Startup ───────────────────────────────────────────────────────────────

def main():
    import uvicorn
    print(f"\n{'='*60}")
    print(f"  PolicyChecker — Compliance Dashboard")
    print(f"  http://localhost:8000")
    if DIST_DIR.exists():
        print(f"  Serving React build from {DIST_DIR}")
    else:
        print(f"  React build not found — run: cd web/frontend && npm run build")
        print(f"  Dev mode: cd web/frontend && npm run dev (port 5173)")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
