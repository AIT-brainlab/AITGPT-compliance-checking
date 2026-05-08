#!/usr/bin/env python3
"""
PolicyChecker - LangGraph Pipeline CLI

Usage:
    python -m langgraph_agent.run --source ait
    python -m langgraph_agent.run --source ait --verbose
    python -m langgraph_agent.run --source ait --ablation no-hints
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Suppress rdflib's verbose tracebacks for ISO8601 parsing on failed literals
logging.getLogger("rdflib.term").setLevel(logging.ERROR)

from langgraph_agent.graph import build_graph
from langgraph_agent.state import PipelineState

SOURCES = {
    "ait": {
        "name": "AIT - Asian Institute of Technology",
        "pdf_dir": str(PROJECT_ROOT / "institutional_policy" / "AIT"),
    },
}

# ── Ablation configurations (§7) ──────────────────────────────────────────
ABLATIONS = {
    "baseline":           {},
    "no-prefilter":       {"ABLATION_SKIP_PREFILTER": "1"},
    "no-hints":           {"ABLATION_NO_HINTS": "1"},
    "no-reclassify":      {"ABLATION_SKIP_RECLASSIFY": "1"},
    "no-fallback":        {"ABLATION_SKIP_DIRECT_SHACL": "1"},
    "no-fol-retry":       {"ABLATION_NO_FOL_RETRY": "1"},
    "no-may-disambig":    {"ABLATION_NO_MAY_DISAMBIG": "1"},
}


def _print_environment(ablation: str = "baseline") -> None:
    """Print active configuration at the top of every run (§6.1)."""
    print(f"\n{'='*60}")
    print(f"Environment:")
    print(f"  Model:     {os.getenv('OLLAMA_MODEL', 'mistral')}")
    print(f"  Second:    {os.getenv('OLLAMA_SECOND_MODEL', 'mistral')}")
    print(f"  Seed:      {os.getenv('OLLAMA_SEED', '42')}")
    print(f"  Version:   {os.getenv('PIPELINE_VERSION', 'dev')}")
    print(f"  Ablation:  {ablation}")
    if os.getenv("EXTRACT_SPACY", "0") == "1":
        print(f"  Extractor: spaCy")
    print(f"{'='*60}")


def _initial_state(source: str) -> PipelineState:
    cfg = SOURCES[source]
    return PipelineState(
        source=source,
        pdf_dir=cfg["pdf_dir"],
        extracted_sentences=[],
        total_sentences=0,
        candidates=[],
        rules=[],
        uncertain_rules=[],
        fol_formulas=[],
        fol_failed=[],
        shacl_shapes=[],
        shacl_output_path="",
        validation_results={},
        conforms=False,
        report={},
        current_step="init",
        errors=[],
    )


def run(source: str, verbose: bool = False, ablation: str = "baseline") -> dict:
    # Apply ablation environment variables
    if ablation in ABLATIONS:
        os.environ.update(ABLATIONS[ablation])

    # Print environment (§6.1)
    _print_environment(ablation)

    graph = build_graph()

    # Ablation output isolation (§7): output to output/ait_<ablation>/
    effective_source = source if ablation == "baseline" else f"{source}_{ablation}"
    state = _initial_state(source)
    # Override the source in state so output goes to the right directory
    if ablation != "baseline":
        state["source"] = effective_source

    print(f"\n{'='*60}")
    print(f"PolicyChecker - {SOURCES[source]['name']}")
    if ablation != "baseline":
        print(f"  Ablation: {ablation}")
    print(f"{'='*60}\n")

    for step in graph.stream(state):
        node_name = list(step.keys())[0]
        node_state = step[node_name]
        current = node_state.get("current_step", node_name)

        STEP_LABELS = {
            "extract":      "Step 1 - PDF Extraction",
            "prefilter":    "Step 2a - Heuristic Pre-filter",
            "classify":     "Step 2b - LLM Classification",
            "reclassify":   "Step 2c - Second-Opinion Reclassification",
            "fol":          "Step 3 - FOL Formalization",
            "shacl":        "Step 4a - SHACL Generation (FOL-mediated)",
            "direct_shacl": "Step 4b - SHACL Generation (Direct NL fallback)",
            "validate":     "Step 5 - SHACL Validation",
            "report":       "Step 6 - Report",
        }
        label = STEP_LABELS.get(current, current)
        print(f"  >> {label}")

        if verbose:
            # Show lightweight per-step stats
            stats = {
                "sentences":  len(node_state.get("extracted_sentences", [])),
                "candidates": len(node_state.get("candidates", [])),
                "rules":      len(node_state.get("rules", [])),
                "uncertain":  len(node_state.get("uncertain_rules", [])),
                "fol_ok":     len(node_state.get("fol_formulas", [])),
                "fol_fail":   len(node_state.get("fol_failed", [])),
                "shapes":     len(node_state.get("shacl_shapes", [])),
                "errors":     len(node_state.get("errors", [])),
            }
            # Only show non-zero entries
            active = {k: v for k, v in stats.items() if v}
            if active:
                print(f"     {active}")

        if node_state.get("errors"):
            for err in node_state["errors"]:
                print(f"  [WARN] {err}", file=sys.stderr)

    # Grab final state from last step
    final_state = node_state  # noqa: F821
    report = final_state.get("report", {})

    output_dir = PROJECT_ROOT / "output" / effective_source
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "pipeline_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"[DONE]  Pipeline complete - report: {report_path}")
    print(f"{'='*60}\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PolicyChecker LangGraph Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source", choices=list(SOURCES.keys()), default="ait",
        help="Institution to process (default: ait)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print per-step statistics",
    )
    parser.add_argument(
        "--ablation",
        choices=list(ABLATIONS.keys()),
        default="baseline",
        help="Run an ablation study (output goes to output/<source>_<ablation>/)",
    )
    args = parser.parse_args()
    run(args.source, verbose=args.verbose, ablation=args.ablation)


if __name__ == "__main__":
    main()
