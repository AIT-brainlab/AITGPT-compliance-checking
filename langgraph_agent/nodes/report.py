from __future__ import annotations

import json
import os
import platform
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from langgraph_agent.state import PipelineState

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Shapes that fire on more than this fraction of target entities are flagged
FALSE_POSITIVE_THRESHOLD = 0.80


def _capture_environment() -> dict:
    """Capture runtime environment for thesis reproducibility (§6.2)."""
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ollama_model": os.getenv("OLLAMA_MODEL", "mistral"),
        "ollama_second_model": os.getenv("OLLAMA_SECOND_MODEL", "mistral"),
        "seed": os.getenv("OLLAMA_SEED", "42"),
        "pipeline_version": os.getenv("PIPELINE_VERSION", "dev"),
        "extract_spacy": os.getenv("EXTRACT_SPACY", "0"),
    }
    # Ollama model digest (if Ollama is reachable)
    try:
        import requests
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        r = requests.get(f"{host}/api/tags", timeout=3)
        for m in r.json().get("models", []):
            if m["name"].startswith(env["ollama_model"]):
                env["ollama_model_digest"] = m.get("digest", "")[:12]
                break
    except Exception:
        pass
    # Git SHA
    try:
        env["git_sha"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()[:8]
    except Exception:
        env["git_sha"] = "unknown"
    return env


def report_node(state: PipelineState) -> PipelineState:
    source = state["source"]
    output_dir = PROJECT_ROOT / "output" / source
    output_dir.mkdir(parents=True, exist_ok=True)

    val = state.get("validation_results", {})
    shapes = state.get("shacl_shapes", [])
    violations = val.get("violations", [])

    # ── Build violation triage ────────────────────────────────────────────
    triage = _build_violation_triage(
        violations,
        entity_count=val.get("entity_count", 0),
    )

    report = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "pipeline_version": os.getenv("PIPELINE_VERSION", "dev"),
        "environment": _capture_environment(),
        "summary": {
            "sentences_extracted":  state.get("total_sentences", 0),
            "candidates_prefiltered": len(state.get("candidates", [])),
            "rules_classified":     len(state.get("rules", [])),
            "fol_formulas_ok":      len(state.get("fol_formulas", [])),
            "fol_formulas_failed":  len(state.get("fol_failed", [])),
            "shacl_shapes_total":   len(shapes),
            "shacl_shapes_valid":   sum(1 for s in shapes if s["syntax_valid"]),
            "shacl_shapes_fol_mediated": sum(1 for s in shapes if s["generation_method"] == "fol_mediated"),
            "shacl_shapes_direct_nl":    sum(1 for s in shapes if s["generation_method"] == "direct_nl"),
            "shacl_shapes_fol_fallback": sum(1 for s in shapes if s["generation_method"] == "fol_fallback"),
            "validation_conforms":  state.get("conforms", False),
            "violations":           val.get("violation_count", 0),
            "likely_false_positives": triage.get("likely_false_positive_count", 0),
            "actionable_violations":  triage.get("actionable_violation_count", 0),
            "total_errors":         len(state.get("errors", [])),
        },
        "violation_triage": triage,
        "rule_type_distribution": _count_by_type(state.get("rules", [])),
        "errors": state.get("errors", []),
    }

    # Save main report
    report_path = output_dir / "pipeline_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save intermediate outputs
    _save(output_dir / "classified_rules.json",  state.get("rules", []))
    _save(output_dir / "fol_formulas.json",       state.get("fol_formulas", []))

    # Print summary to console
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"  PIPELINE SUMMARY — {source.upper()}")
    print(f"{'='*60}")
    print(f"  Sentences extracted    : {s['sentences_extracted']}")
    print(f"  Pre-filter candidates  : {s['candidates_prefiltered']}")
    print(f"  Rules classified       : {s['rules_classified']}")
    print(f"  FOL formulas ok/fail   : {s['fol_formulas_ok']} / {s['fol_formulas_failed']}")
    print(f"  SHACL shapes generated : {s['shacl_shapes_total']} ({s['shacl_shapes_valid']} valid)")
    print(f"    - FOL-mediated       : {s['shacl_shapes_fol_mediated']}")
    print(f"    - Direct NL fallback : {s['shacl_shapes_direct_nl']}")
    if s["shacl_shapes_fol_fallback"]:
        print(f"    - FOL recovery       : {s['shacl_shapes_fol_fallback']}")
    print(f"  Validation conforms    : {s['validation_conforms']}")
    viol_line = f"  Violations found       : {s['violations']}"
    if triage.get("likely_false_positive_count"):
        fp = triage["likely_false_positive_count"]
        act = triage["actionable_violation_count"]
        viol_line += f" (est. ~{fp} false positives, {act} actionable)"
    print(viol_line)
    if s["total_errors"]:
        print(f"  Pipeline errors        : {s['total_errors']}")

    # Print triage severity breakdown
    sev = triage.get("by_severity", {})
    if sev:
        sev_parts = [f"{k}: {v}" for k, v in sev.items()]
        print(f"  Severity breakdown     : {', '.join(sev_parts)}")

    # Print top offending shapes
    top_shapes = triage.get("by_source_shape", [])[:5]
    if top_shapes:
        print(f"  Top-5 triggered shapes :")
        for entry in top_shapes:
            fp_tag = " ⚠ likely false positive" if entry.get("likely_false_positive") else ""
            print(f"    {entry['shape']}: {entry['count']} violations "
                  f"({entry['pct_entities']:.0f}% of entities){fp_tag}")

    print(f"{'='*60}")
    print(f"  Output dir: {output_dir}")
    print(f"{'='*60}\n")

    return {
        "report": report,
        "current_step": "report",
    }


# ── Violation triage logic ─────────────────────────────────────────────────

def _build_violation_triage(violations: list, entity_count: int) -> dict:
    """Analyse violations: group by shape, rank, flag false positives."""
    if not violations:
        return {
            "by_severity": {},
            "by_source_shape": [],
            "likely_false_positive_count": 0,
            "actionable_violation_count": 0,
        }

    # ── Severity breakdown ─────────────────────────────────────────────
    by_severity: dict[str, int] = defaultdict(int)
    for v in violations:
        sev_uri = v.get("severity", "")
        sev_label = sev_uri.rsplit("#", 1)[-1] if "#" in sev_uri else sev_uri
        by_severity[sev_label] += 1

    # ── Group by source shape ──────────────────────────────────────────
    shape_groups: dict[str, list] = defaultdict(list)
    for v in violations:
        shape = v.get("source_shape", "unknown")
        shape_groups[shape].append(v)

    by_shape = []
    fp_count = 0
    for shape, group in sorted(shape_groups.items(),
                                key=lambda x: len(x[1]), reverse=True):
        count = len(group)
        # Count distinct focus nodes hit by this shape
        distinct_entities = len({v.get("focus_node") for v in group})
        pct = (distinct_entities / entity_count * 100) if entity_count else 0

        # Shapes firing on >80% of entities are likely false positives
        # (the test data probably doesn't have the required property)
        is_fp = pct >= (FALSE_POSITIVE_THRESHOLD * 100)
        if is_fp:
            fp_count += count

        sample_msg = group[0].get("result_message", "")[:150] if group else ""

        by_shape.append({
            "shape": shape,
            "count": count,
            "distinct_entities": distinct_entities,
            "pct_entities": round(pct, 1),
            "likely_false_positive": is_fp,
            "sample_message": sample_msg,
        })

    total = len(violations)
    return {
        "by_severity": dict(by_severity),
        "by_source_shape": by_shape[:20],  # top 20
        "likely_false_positive_count": fp_count,
        "actionable_violation_count": total - fp_count,
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _save(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _count_by_type(rules: list) -> dict:
    dist: dict[str, int] = {}
    for r in rules:
        t = r.get("rule_type", "unknown")
        dist[t] = dist.get(t, 0) + 1
    return dist
