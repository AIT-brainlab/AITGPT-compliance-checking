from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pdfplumber

from langgraph_agent.state import PipelineState, SentenceItem

# Minimum / maximum token counts for a sentence to be worth keeping
_MIN_WORDS = 5
_MAX_WORDS = 250

# Patterns that indicate non-sentence noise (page numbers, headers, footers)
_NOISE = re.compile(
    r"^(page\s+\d+|\d+\s*$|www\.|http|©|\bait\b\s*\d{4}|_{3,}|-{3,})",
    re.IGNORECASE,
)


_LIST_MARKER = re.compile(r"\n\s*(\d+\.|\([a-z]\)|[a-z]\)|\*|\-)\s+")
_SOFT_WRAP = re.compile(r"(?<=[a-z,;:])\n(?=[a-z])")
_MULTI_NL = re.compile(r"\n{2,}")
_TRAILING_LIST_NUM = re.compile(r"\s*\n?\s*\d+\.\s*$")

import os
USE_SPACY = os.getenv("EXTRACT_SPACY", "0") == "1"

if USE_SPACY:
    import spacy
    _nlp = spacy.load("en_core_web_sm", disable=["ner", "tagger"])

def _normalise(raw: str) -> str:
    """Clean PDF extraction artifacts before sentence splitting."""
    # Rejoin soft-wrapped lines: "...to the\ncommittee..." -> "...to the committee..."
    raw = _SOFT_WRAP.sub(" ", raw)
    # Collapse blank lines
    raw = _MULTI_NL.sub("\n", raw)
    # Normalise whitespace (preserves newlines where untouched)
    raw = re.sub(r"[ \t]+", " ", raw)
    return raw

def _split_sentences(raw: str) -> List[str]:
    raw = _normalise(raw)
    if USE_SPACY:
        doc = _nlp(raw)
        return [s.text.strip() for s in doc.sents if s.text.strip()]

    # First pass: split on list markers (they always start a new item)
    items = _LIST_MARKER.split(raw)

    # Second pass: split each item on sentence boundaries
    sentences: list[str] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        # Split on . or ; followed by whitespace + capital letter
        parts = re.split(r"(?<=[.;])\s+(?=[A-Z])", item)
        for p in parts:
            # Strip trailing list markers that leaked through
            p = _TRAILING_LIST_NUM.sub("", p.strip())
            if p:
                sentences.append(p)

    return sentences


def _is_noise(text: str) -> bool:
    words = text.split()
    if len(words) < _MIN_WORDS or len(words) > _MAX_WORDS:
        return True
    if _NOISE.match(text):
        return True
    if text.isupper() and len(words) < 8:   # likely a section header in all-caps
        return True
    return False


def extract_node(state: PipelineState) -> PipelineState:
    pdf_dir = Path(state["pdf_dir"])
    pdf_files = sorted(pdf_dir.glob("*.pdf"))

    sentences: List[SentenceItem] = []
    errors: List[str] = []

    for pdf_path in pdf_files:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    raw_text = page.extract_text() or ""
                    for sent in _split_sentences(raw_text):
                        if not _is_noise(sent):
                            sentences.append(
                                SentenceItem(
                                    text=sent,
                                    page=page_num,
                                    source=pdf_path.name,
                                )
                            )
        except Exception as exc:
            errors.append(f"extract: failed to read {pdf_path.name}: {exc}")

    return {
        "extracted_sentences": sentences,
        "total_sentences": len(sentences),
        "current_step": "extract",
        "errors": errors,
    }
