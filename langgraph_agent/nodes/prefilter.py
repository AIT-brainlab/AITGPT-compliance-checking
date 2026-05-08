from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.prefilter import PreFilter

from langgraph_agent.state import PipelineState, SentenceItem

_prefilter = PreFilter()


def prefilter_node(state: PipelineState) -> PipelineState:
    sentences: List[SentenceItem] = state["extracted_sentences"]
    errors: List[str] = []

    # §7 — Ablation: skip prefilter entirely, pass all sentences through
    import os
    if os.getenv("ABLATION_SKIP_PREFILTER", "0") == "1":
        return {
            "candidates": list(sentences),
            "current_step": "prefilter",
            "errors": ["ablation: prefilter skipped"],
        }

    # Group sentences by their source PDF so the PreFilter can use page context
    from collections import defaultdict
    by_source: dict[str, List[SentenceItem]] = defaultdict(list)
    for s in sentences:
        by_source[s["source"]].append(s)

    candidates: List[SentenceItem] = []

    for source, items in by_source.items():
        texts = [i["text"] for i in items]
        try:
            results = _prefilter.filter_sentences(texts)
            for item, result in zip(items, results):
                if result.is_candidate:
                    enriched: SentenceItem = {
                        **item,
                        "deontic_strength": result.deontic_strength,
                        "speech_act": result.speech_act,
                        "section_context": result.section_context,
                        "section_weight": result.section_weight,
                        "confidence_boost": result.confidence_boost,
                    }
                    candidates.append(enriched)
        except Exception as exc:
            errors.append(f"prefilter: error processing {source}: {exc}")
            # On error, pass all sentences through to avoid losing data
            candidates.extend(items)

    return {
        "candidates": candidates,
        "current_step": "prefilter",
        "errors": errors,
    }
