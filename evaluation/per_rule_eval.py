"""
per_rule_eval.py — [RETIRED] M4 Shape Correctness F1

STATUS: RETIRED
---------------
This script computed M4 (Shape Correctness F1) by comparing pipeline-generated
SHACL shapes against a D2 gold-standard set of manually verified shapes.

WHY RETIRED:
  - M4 required the D2 SHACL shape gold (a subset of curated shapes) as a
    structural reference, which is no longer the evaluation anchor
  - Shape-level structural F1 conflated syntactic correctness with semantic
    correctness; the metric was noisy and hard to interpret
  - Replaced by M3 (FOL Quality) which measures semantic predicate completeness,
    and M5 (Stability) which measures deterministic reproducibility

SUPERSEDED BY:
  - M3 FOL Quality = 100% (evaluation/confidence_intervals.py)
  - M5 Stability = PASS (hash-comparison in pipeline_report.json)

INTERN NOTE:
  If you need per-rule shape evaluation for a different purpose:
    1. Load output/ait/shapes_generated.ttl (pipeline output)
    2. Load shacl/shapes/*.ttl (curated gold shapes, 96 rules)
    3. Compare sh:path, sh:minCount/sh:maxCount, sh:targetClass
    4. Compute precision/recall/F1 at the property-shape level
"""

raise RuntimeError(
    "per_rule_eval.py is RETIRED — M4/D2-dependent shape F1 is no longer computed. "
    "See evaluation/confidence_intervals.py for M3 and M5 metrics."
)
