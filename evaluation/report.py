"""
Thesis Metrics Report — M1 through M5
=======================================
Aggregates outputs from ``align.py`` and ``per_rule_eval.py`` into a single
metrics report suitable for inclusion in a thesis results section.

Usage:
    python -m evaluation.report           # pretty-print + JSON output
    python -m evaluation.report --md      # Markdown table for thesis
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).parent.parent


# ── Metric dataclasses ─────────────────────────────────────────────────────

@dataclass
class MetricsReport:
    """All five thesis metrics in one structure."""
    m1_extraction_coverage: float = 0.0
    m1_aligned: int = 0
    m1_total: int = 0

    m2_classification_coverage: float = 0.0
    m2_correct_type: int = 0
    m2_aligned_with_type: int = 0

    m3_fol_quality: float = 0.0
    m3_semantic: int = 0
    m3_total_fol: int = 0

    m4_precision: float = 0.0
    m4_recall: float = 0.0
    m4_f1: float = 0.0
    m4_correct: int = 0
    m4_too_strict: int = 0
    m4_too_permissive: int = 0
    m4_inverted: int = 0
    m4_skipped: int = 0

    m5_reproducible: bool = False

    pipeline_stats: dict = field(default_factory=dict)


# ── Metric computations ───────────────────────────────────────────────────

_PLACEHOLDER_PREDS = re.compile(
    r"[OPF]\(\s*(Action|Subject|Predicate|Condition|Thing|Entity|x|y|z|\?\w)\s*[()]",
    re.IGNORECASE,
)


def compute_m1(alignments: list[dict]) -> tuple[float, int, int]:
    """M1 — Extraction coverage: fraction of gold rules with an aligned pipeline rule."""
    total = len(alignments)
    aligned = sum(1 for a in alignments if a.get("aligned"))
    return (aligned / total if total else 0.0), aligned, total


def compute_m2(alignments: list[dict], gold_rules: list[dict],
               pipeline_rules: list[dict]) -> tuple[float, int, int]:
    """M2 — Classification coverage: fraction of aligned rules with correct deontic type."""
    # Build lookup maps
    gold_by_id = {g["gs_id"]: g for g in gold_rules}
    pipe_by_id = {r["rule_id"]: r for r in pipeline_rules}

    correct = 0
    evaluated = 0
    for a in alignments:
        if not a.get("aligned") or not a.get("ait_id"):
            continue
        gs = gold_by_id.get(a["gs_id"])
        pr = pipe_by_id.get(a["ait_id"])
        if not gs or not pr:
            continue
        evaluated += 1
        if gs.get("deontic_type", "").lower() == pr.get("rule_type", "").lower():
            correct += 1

    return (correct / evaluated if evaluated else 0.0), correct, evaluated


def compute_m3(fol_formulas: list[dict]) -> tuple[float, int, int]:
    """M3 — FOL quality rate: fraction of FOL formulas with non-placeholder predicates."""
    total = len(fol_formulas)
    placeholders = sum(
        1 for f in fol_formulas
        if _PLACEHOLDER_PREDS.search(f.get("deontic_formula", ""))
    )
    semantic = total - placeholders
    return (semantic / total if total else 0.0), semantic, total


def compute_m4(eval_results: list[dict]) -> dict:
    """M4 — Shape correctness from per-rule eval."""
    c = Counter(r["verdict"] for r in eval_results)
    correct = c.get("correct", 0)
    too_strict = c.get("too_strict", 0)
    too_perm = c.get("too_permissive", 0)
    inverted = c.get("inverted", 0)
    skipped = c.get("skipped", 0)

    precision = correct / (correct + too_strict) if (correct + too_strict) else 0
    recall = correct / (correct + too_perm) if (correct + too_perm) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "correct": correct,
        "too_strict": too_strict,
        "too_permissive": too_perm,
        "inverted": inverted,
        "skipped": skipped,
    }


# ── Aggregate report ──────────────────────────────────────────────────────

def build_report(source: str = "ait") -> MetricsReport:
    """Load all intermediate outputs and compute M1–M5."""
    out = PROJECT_ROOT / "output" / source

    # Load data
    alignments = _load_json(out / "gold_alignment.json", [])
    pipeline_rules = _load_json(out / "classified_rules.json", [])
    fol_formulas = _load_json(out / "fol_formulas.json", [])
    eval_results = _load_json(out / "per_rule_eval.json", [])
    pipeline_report = _load_json(out / "pipeline_report.json", {})

    # Load gold rules for M2
    from evaluation.align import load_gold_rules
    shapes_file = PROJECT_ROOT / "shacl" / "shapes" / "ait_policy_shapes.ttl"
    gold_rules = []
    if shapes_file.exists():
        gold = load_gold_rules(shapes_file)
        gold_rules = [{"gs_id": g.gs_id, "deontic_type": g.deontic_type} for g in gold]

    # Compute
    m1_val, m1_aligned, m1_total = compute_m1(alignments)
    m2_val, m2_correct, m2_eval = compute_m2(alignments, gold_rules, pipeline_rules)
    m3_val, m3_sem, m3_total = compute_m3(fol_formulas)
    m4 = compute_m4(eval_results)

    report = MetricsReport(
        m1_extraction_coverage=m1_val,
        m1_aligned=m1_aligned,
        m1_total=m1_total,
        m2_classification_coverage=m2_val,
        m2_correct_type=m2_correct,
        m2_aligned_with_type=m2_eval,
        m3_fol_quality=m3_val,
        m3_semantic=m3_sem,
        m3_total_fol=m3_total,
        m4_precision=m4["precision"],
        m4_recall=m4["recall"],
        m4_f1=m4["f1"],
        m4_correct=m4["correct"],
        m4_too_strict=m4["too_strict"],
        m4_too_permissive=m4["too_permissive"],
        m4_inverted=m4["inverted"],
        m4_skipped=m4["skipped"],
        m5_reproducible=False,  # computed separately by diffing two runs
        pipeline_stats=pipeline_report.get("summary", {}),
    )
    return report


def _load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


# ── Formatters ─────────────────────────────────────────────────────────────

def format_console(r: MetricsReport) -> str:
    lines = [
        "",
        "=" * 60,
        "  THESIS METRICS REPORT",
        "=" * 60,
        "",
        f"  M1 — Extraction Coverage :  {r.m1_extraction_coverage:.1%}  "
        f"({r.m1_aligned}/{r.m1_total} gold rules aligned)",
        "",
        f"  M2 — Classification Acc. :  {r.m2_classification_coverage:.1%}  "
        f"({r.m2_correct_type}/{r.m2_aligned_with_type} correct deontic type)",
        "",
        f"  M3 — FOL Quality Rate    :  {r.m3_fol_quality:.1%}  "
        f"({r.m3_semantic}/{r.m3_total_fol} semantic predicates)",
        "",
        f"  M4 — Shape Correctness   :  F1 = {r.m4_f1:.3f}  "
        f"(P = {r.m4_precision:.3f}, R = {r.m4_recall:.3f})",
        f"         correct = {r.m4_correct}, too_strict = {r.m4_too_strict}, "
        f"too_permissive = {r.m4_too_permissive}, inverted = {r.m4_inverted}, "
        f"skipped = {r.m4_skipped}",
        "",
        f"  M5 — Reproducibility     :  {'PASS' if r.m5_reproducible else 'NOT YET TESTED'}",
        "",
        "=" * 60,
    ]
    return "\n".join(lines)


def format_markdown(r: MetricsReport) -> str:
    return f"""## Thesis Metrics — Pipeline Evaluation Results

| Metric | Definition | Value |
|--------|-----------|-------|
| **M1** Extraction coverage | Gold rules with aligned pipeline rule (≥ 0.65 cosine) | **{r.m1_extraction_coverage:.1%}** ({r.m1_aligned}/{r.m1_total}) |
| **M2** Classification coverage | Aligned rules with correct deontic type | **{r.m2_classification_coverage:.1%}** ({r.m2_correct_type}/{r.m2_aligned_with_type}) |
| **M3** FOL quality rate | FOL formulas with semantic predicates | **{r.m3_fol_quality:.1%}** ({r.m3_semantic}/{r.m3_total_fol}) |
| **M4** Shape correctness | F1 score against Pos/Neg test entities | **F1 = {r.m4_f1:.3f}** (P={r.m4_precision:.3f}, R={r.m4_recall:.3f}) |
| **M5** Reproducibility | Identical output across clean-cache runs | {'✅ PASS' if r.m5_reproducible else '⏳ Not yet tested'} |

### M4 Breakdown

| Verdict | Count |
|---------|------:|
| Correct | {r.m4_correct} |
| Too strict (false violation) | {r.m4_too_strict} |
| Too permissive (missed violation) | {r.m4_too_permissive} |
| Inverted | {r.m4_inverted} |
| Skipped (missing test entity) | {r.m4_skipped} |
"""


# ── CLI entry point ───────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Compute thesis metrics M1–M5")
    parser.add_argument("--source", default="ait", help="Source institution (default: ait)")
    parser.add_argument("--md", action="store_true", help="Output Markdown table")
    parser.add_argument("--save", action="store_true", help="Save JSON to output dir")
    args = parser.parse_args()

    report = build_report(args.source)

    if args.md:
        print(format_markdown(report))
    else:
        print(format_console(report))

    if args.save:
        out_dir = PROJECT_ROOT / "output" / args.source
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "thesis_metrics.json"
        out_path.write_text(
            json.dumps(asdict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
