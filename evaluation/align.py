"""
align.py — [RETIRED] M1 Extraction Coverage

STATUS: RETIRED
---------------
This script was used to compute M1 (Extraction Coverage) against the D1 gold
standard — a manually annotated set of 97 policy sentences drawn from a preliminary
corpus snapshot.

WHY RETIRED:
  - M1 required a D1 gold standard (97 sentences) that is no longer the primary
    evaluation anchor for the thesis
  - The D3 study (1,663 sentences, 50-item IRR sample) supersedes D1/D2 metrics
  - M1 scores (85.4%) were misleading because they measured recall against an
    earlier, narrower corpus definition

SUPERSEDED BY:
  - IRR Fleiss' κ = 0.8436 on D3 (evaluation/external_annotator_agreement.py)
  - LLM Accuracy = 84.0% on D3 majority-vote gold

INTERN NOTE:
  If you need to re-run M1 for legacy comparison, you need:
    1. The D1 gold CSV (97 sentences with gold labels)
    2. A fresh pipeline run to produce classified_rules.json
    3. Alignment logic: tokenize sentences, fuzzy-match by edit distance, compute
       precision/recall/F1 between extracted set and gold set
"""

raise RuntimeError(
    "align.py is RETIRED — M1/D1-dependent metrics are no longer computed. "
    "See evaluation/external_annotator_agreement.py for the active D3 IRR study."
)
