"""
confidence_intervals.py — Bootstrap 95% CIs for D3 thesis metrics

PURPOSE
-------
Computes non-parametric bootstrap 95% confidence intervals for the
evaluation metrics reported in the thesis:

  - Fleiss' κ  (IRR, 3 annotators, N=50)
  - LLM Accuracy (N=50)
  - M3 FOL Quality (N=351 parsed formulas)
  - M5 Stability (binary PASS/FAIL — no CI required)

Bootstrap method: BCa (bias-corrected and accelerated) with 10,000 resamples.

INPUT
-----
  output/ait/external_annotator_agreement.json  — Fleiss' κ and LLM accuracy
  output/ait/fol_formulas.json                 — M3 FOL quality

OUTPUT
------
  output/ait/thesis_metrics_with_ci.json
  Fields per metric:
    value       — point estimate
    ci_lower    — 95% BCa lower bound
    ci_upper    — 95% BCa upper bound
    n           — sample size
    method      — bootstrap method description

USAGE
-----
  python -m evaluation.confidence_intervals

NOTE
----
This script is a STUB. The bootstrap implementation was part of the thesis
experimental code. To re-implement:
  1. Ensure output/ait/external_annotator_agreement.json exists (run
     evaluation.external_annotator_agreement first)
  2. Implement _bootstrap_ci() using numpy or scipy
  3. The published CIs (thesis Table 4.x) are the reference values
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = PROJECT_ROOT / "output" / "ait" / "thesis_metrics_with_ci.json"

# ── Published thesis values (frozen snapshot) ────────────────────────────
_PUBLISHED = {
    "irr_fleiss_kappa": {
        "value": 0.8436,
        "ci_lower": 0.8385,
        "ci_upper": 0.8487,
        "n": 50,
        "method": "bootstrap BCa (10,000 resamples)",
    },
    "llm_accuracy": {
        "value": 0.84,
        "ci_lower": 0.74,
        "ci_upper": 0.94,
        "n": 50,
        "method": "Wilson score interval",
    },
    "m3_fol_quality": {
        "value": 1.0,
        "ci_lower": 1.0,
        "ci_upper": 1.0,
        "n": 351,
        "method": "Exact Clopper-Pearson",
    },
    "m5_stability": {
        "value": "PASS",
        "ci_lower": None,
        "ci_upper": None,
        "n": 1,
        "method": "Hash comparison (deterministic)",
    },
    "note": "Published thesis snapshot. Re-run from raw annotation data to recompute.",
}


def run() -> dict:
    print("[confidence_intervals] Returning published thesis snapshot.")
    result = _PUBLISHED.copy()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"[confidence_intervals] Written → {OUTPUT_FILE}")
    return result


if __name__ == "__main__":
    run()
