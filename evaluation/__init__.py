"""
evaluation — D3-grounded IRR and thesis metrics package

ACTIVE scripts (D3 corpus, 50-item human-annotated sample):
  external_annotator_agreement.py  — Fleiss' κ + LLM accuracy
  confidence_intervals.py          — Bootstrap 95% CIs
  report.py                        — Metrics aggregator / CLI

RETIRED scripts (D1/D2-dependent, superseded by D3 study):
  align.py              — M1 extraction coverage
  per_rule_eval.py      — M4 shape correctness F1
  multi_llm_agreement.py — Multi-LLM IAA
  intra_annotator.py    — Single-annotator reliability (pre-IRR)
"""
