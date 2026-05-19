"""
multi_llm_agreement.py — [RETIRED] Multi-LLM Inter-Annotator Agreement

STATUS: RETIRED
---------------
This script measured agreement between multiple LLMs (e.g., Mistral, Llama,
GPT-4) as proxy annotators, anchored against the D2 SHACL gold labels.

WHY RETIRED:
  - The D2 gold anchor (SHACL-derived labels) introduced circular dependency:
    the same model family was used for both generation and evaluation
  - Multi-LLM agreement overestimated true semantic accuracy (LLMs share biases)
  - Replaced by human-annotated IRR study: three independent human annotators
    (author, Kittipat, Mayuree) on a 50-item D3 stratified sample

SUPERSEDED BY:
  - evaluation/external_annotator_agreement.py (Fleiss' κ = 0.8436)
"""

raise RuntimeError(
    "multi_llm_agreement.py is RETIRED — multi-LLM IAA with D2 gold anchor is no "
    "longer computed. See evaluation/external_annotator_agreement.py for the D3 IRR study."
)
