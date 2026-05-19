"""
external_annotator_agreement.py — Fleiss' κ (3 annotators) + LLM accuracy

PURPOSE
-------
Computes two key evaluation metrics from the D3 study:

  1. **IRR Fleiss' κ** — inter-rater reliability across three human annotators
     (author, Kittipat, Mayuree) on a stratified 50-item sample drawn from
     the full AIT D3 corpus (1,663 sentences).

     Result: κ = 0.8436 (Almost Perfect), 95% CI [0.8385, 0.8487]

  2. **LLM Accuracy** — agreement between the Mistral 7B pipeline output and
     the majority-vote human gold label for the same 50 items.

     Result: 84.0% (42/50 correct), Cohen's κ = 0.629 (Substantial)

INPUT
-----
  data/d3_annotator_sample.csv   (50 rows)
  Columns:
    sentence_id       — unique identifier
    sentence          — policy sentence text
    annotator_1       — label by annotator 1 (obligation/permission/prohibition/none)
    annotator_2       — label by annotator 2
    annotator_3       — label by annotator 3
    llm_label         — Mistral 7B pipeline label

OUTPUT
------
  output/ait/external_annotator_agreement.json
  Fields:
    fleiss_kappa           — float
    fleiss_kappa_ci_lower  — float (bootstrap 95%)
    fleiss_kappa_ci_upper  — float (bootstrap 95%)
    llm_accuracy           — float (fraction)
    llm_accuracy_n         — int
    llm_cohens_kappa       — float
    disagreements          — list of dicts (sentence_id, labels, llm_label)

USAGE
-----
  python -m evaluation.external_annotator_agreement
  python -m evaluation.external_annotator_agreement --data data/d3_annotator_sample.csv

NOTE
----
This script is a STUB. The annotator CSV and implementation were part of the
thesis experimental data. To re-implement:
  1. Place your annotator CSV at data/d3_annotator_sample.csv
  2. Implement _load_annotations(), _fleiss_kappa(), _llm_accuracy()
  3. Run the script and verify against the published thesis numbers
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = PROJECT_ROOT / "output" / "ait" / "external_annotator_agreement.json"

# ── Published thesis values (frozen snapshot) ────────────────────────────
_PUBLISHED = {
    "fleiss_kappa": 0.8436,
    "fleiss_kappa_ci_lower": 0.8385,
    "fleiss_kappa_ci_upper": 0.8487,
    "llm_accuracy": 0.84,
    "llm_accuracy_n": 50,
    "llm_cohens_kappa": 0.629,
    "note": (
        "Published thesis snapshot (D3 corpus, 50-item stratified sample, "
        "annotators: author, Kittipat, Mayuree). "
        "Re-run with --data to compute from raw annotations."
    ),
}


def _load_annotations(csv_path: Path) -> list[dict]:
    """Load annotator CSV.  Returns list of row dicts."""
    raise NotImplementedError(
        f"Annotator CSV not found or not implemented. "
        f"Expected: {csv_path}"
    )


def _fleiss_kappa(rows: list[dict]) -> dict:
    """Compute Fleiss' κ across annotator_1/2/3 columns."""
    raise NotImplementedError("Fleiss' κ computation not yet implemented.")


def _llm_accuracy(rows: list[dict]) -> dict:
    """Compute LLM accuracy vs. majority-vote gold."""
    raise NotImplementedError("LLM accuracy computation not yet implemented.")


def run(data_path: Path | None = None) -> dict:
    if data_path is None or not data_path.exists():
        print(f"[external_annotator_agreement] No annotator CSV found — "
              f"returning published thesis snapshot.")
        result = _PUBLISHED.copy()
    else:
        rows = _load_annotations(data_path)
        result = {**_fleiss_kappa(rows), **_llm_accuracy(rows)}

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"[external_annotator_agreement] Written → {OUTPUT_FILE}")
    print(f"  Fleiss' κ = {result['fleiss_kappa']}")
    print(f"  LLM Accuracy = {result['llm_accuracy']:.1%}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute IRR Fleiss' κ and LLM accuracy (D3 study)")
    parser.add_argument("--data", default=None, help="Path to annotator CSV file")
    args = parser.parse_args()
    data_path = Path(args.data) if args.data else None
    run(data_path)


if __name__ == "__main__":
    main()
