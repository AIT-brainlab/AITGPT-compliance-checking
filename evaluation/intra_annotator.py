"""
intra_annotator.py — [RETIRED] Single-Annotator Reliability (Pre-IRR)

STATUS: RETIRED
---------------
This script measured single-annotator reliability (the author re-labelling a
subset of sentences on two separate occasions) as an early sanity check on
the consistency of the gold labelling process.

WHY RETIRED:
  - Single-annotator reliability does not establish validity — it only shows
    internal consistency of one person's labels, not cross-annotator agreement
  - The preliminary κ = 0.635 (Moderate) from this script was used in an early
    draft but was superseded by the three-annotator IRR study
  - That early κ of 0.635 is NOT the thesis result; it should not appear anywhere
    in the published dashboard or documentation

SUPERSEDED BY:
  - evaluation/external_annotator_agreement.py (Fleiss' κ = 0.8436, 3 annotators)
"""

raise RuntimeError(
    "intra_annotator.py is RETIRED — single-annotator reliability (κ=0.635) has "
    "been superseded by the three-annotator D3 IRR study (κ=0.8436). "
    "See evaluation/external_annotator_agreement.py."
)
