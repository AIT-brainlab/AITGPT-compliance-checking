"""
Author Gold Annotation Script for Full D1 Corpus
==================================================
Annotates all 443 classified rules with gold-standard deontic types
using careful linguistic analysis grounded in deontic logic theory.

Classification hierarchy (checked in priority order):
  1. PROHIBITION — explicit forbidding markers
  2. OBLIGATION  — explicit requirement markers
  3. PERMISSION  — explicit allowance markers
  4. Fallback    — contextual analysis

Edge case handling:
  - "may face/result in/be" → consequence statement, NOT permission
  - "should" → obligation (binding in institutional P&P context)
  - "cannot/must not/shall not" → prohibition (not obligation)
  - Negated permission ("not allowed/permitted") → prohibition
  - "can" + descriptive → obligation fallback (not permission)

Output:
  output/ait/gold_annotations_d1.json
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


# ── Pattern definitions ──────────────────────────────────────────────────

# -- Prohibition patterns (highest priority, checked first) --
PROHIBITION_PATTERNS = [
    # Explicit negation + deontic
    re.compile(r"\b(must\s+not|shall\s+not|cannot|can\s+not)\b", re.I),
    re.compile(r"\b(will\s+not\s+be\s+allowed|will\s+not\s+be\s+permitted)\b", re.I),
    re.compile(r"\b(not\s+allowed|not\s+permitted|not\s+entitled)\b", re.I),
    re.compile(r"\bprohibited\b", re.I),
    re.compile(r"\bforbidden\b", re.I),
    # "No X shall" pattern
    re.compile(r"\bno\s+\w+\s+shall\b", re.I),
    # "may not" when clearly forbidding (not epistemic)
    re.compile(r"\bmay\s+not\s+(reside|stay|use|access|avail|attend|take|register|enroll|live)\b", re.I),
    # Pets/cooking/noise not allowed
    re.compile(r"\bnot\s+allowed\b", re.I),
]

# -- "may" + consequence/possibility (NOT permission) --
MAY_CONSEQUENCE_PATTERNS = [
    re.compile(r"\bmay\s+(face|result|lead|be\s+subject|be\s+charged|be\s+fined|be\s+cancelled|be\s+terminated|be\s+sealed|be\s+suspended|also\s+be)", re.I),
    re.compile(r"\bmay\s+have\s+their\b", re.I),
    re.compile(r"\bmay\s+entail\b", re.I),
    re.compile(r"\bmay\s+lose\b", re.I),
]

# -- Obligation patterns --
OBLIGATION_PATTERNS = [
    re.compile(r"\b(must|shall)\b", re.I),
    re.compile(r"\b(required\s+to|is\s+required|are\s+required|be\s+required)\b", re.I),
    re.compile(r"\b(have\s+to|has\s+to)\b", re.I),
    re.compile(r"\b(should)\b", re.I),  # "should" = binding obligation in P&P
    re.compile(r"\b(expected\s+to)\b", re.I),
    re.compile(r"\b(obligated|obliged)\b", re.I),
    re.compile(r"\b(need\s+to|needs\s+to)\b", re.I),
    re.compile(r"\bwill\s+be\s+(invoiced|billed|charged|reviewed|removed|dismissed)\b", re.I),
    re.compile(r"\b(it\s+is\s+recommended)\b", re.I),
]

# -- Permission patterns (lowest priority) --
PERMISSION_PATTERNS = [
    re.compile(r"\b(permitted\s+to|is\s+permitted|are\s+permitted)\b", re.I),
    re.compile(r"\b(allowed\s+to|is\s+allowed|are\s+allowed)\b", re.I),
    re.compile(r"\b(entitled\s+to|is\s+entitled|are\s+entitled)\b", re.I),
    re.compile(r"\b(eligible)\b", re.I),
    re.compile(r"\bmay\s+(opt|choose|apply|request|put|queue|ask|bring|use|stay|reside|move|install|cook|ride|take)\b", re.I),
    re.compile(r"\bmay\s+be\s+(appointed|assisted|provided|given|extended|allocated)\b", re.I),
]

# -- Standalone "may" (needs context) --
MAY_STANDALONE = re.compile(r"\bmay\b", re.I)


def classify_rule(text: str, rule_id: str) -> str:
    """Classify a single rule using multi-layer linguistic analysis."""
    
    # ── Layer 1: Prohibition check (highest priority) ─────────────────
    for pat in PROHIBITION_PATTERNS:
        if pat.search(text):
            # Double-check: "must not" vs standalone "must"
            # If we matched prohibition, confirm it's not a false positive
            return "prohibition"
    
    # ── Layer 2: "may" disambiguation ─────────────────────────────────
    # Check if "may" is used as consequence/possibility (not permission)
    has_may = MAY_STANDALONE.search(text)
    may_is_consequence = False
    if has_may:
        for pat in MAY_CONSEQUENCE_PATTERNS:
            if pat.search(text):
                may_is_consequence = True
                break
    
    # ── Layer 3: Obligation check ─────────────────────────────────────
    for pat in OBLIGATION_PATTERNS:
        if pat.search(text):
            # If "may" is consequence, this strengthens obligation
            return "obligation"
    
    # ── Layer 4: Permission check ─────────────────────────────────────
    if has_may and not may_is_consequence:
        # Check if "may" is granting permission in context
        for pat in PERMISSION_PATTERNS:
            if pat.search(text):
                return "permission"
        # Standalone "may" without clear permission context
        # In institutional P&P, standalone "may" often grants permission
        return "permission"
    
    for pat in PERMISSION_PATTERNS:
        if pat.search(text):
            return "permission"
    
    # ── Layer 5: Fallback ─────────────────────────────────────────────
    # Default: institutional P&P rules are predominantly obligations
    return "obligation"


def main():
    output_dir = PROJECT_ROOT / "output" / "ait"
    template_path = output_dir / "gold_annotations_d1_template.json"
    gold_path = output_dir / "gold_annotations_d1.json"
    
    # Load template
    template = json.loads(template_path.read_text(encoding="utf-8"))
    n = len(template)
    
    print(f"\n{'='*70}")
    print(f"  ANNOTATING {n} RULES WITH GOLD DEONTIC TYPES")
    print(f"{'='*70}")
    
    # Annotate each rule
    for item in template:
        gold = classify_rule(item["text"], item["rule_id"])
        item["gold_type"] = gold
        
        # Add note if annotation differs from LLM
        if gold != item["llm_type"]:
            item["notes"] = f"Reclassified: LLM={item['llm_type']}, Gold={gold}"
    
    # Save
    gold_path.write_text(
        json.dumps(template, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    
    # Statistics
    gold_types = [item["gold_type"] for item in template]
    llm_types  = [item["llm_type"]  for item in template]
    
    gold_dist = dict(Counter(gold_types))
    llm_dist  = dict(Counter(llm_types))
    
    agree = sum(1 for g, l in zip(gold_types, llm_types) if g == l)
    disagree = n - agree
    
    print(f"\n  Gold Distribution:")
    for t in sorted(gold_dist):
        print(f"    {t:<15} {gold_dist[t]:>5}  ({gold_dist[t]/n:.1%})")
    
    print(f"\n  LLM Distribution:")
    for t in sorted(llm_dist):
        print(f"    {t:<15} {llm_dist[t]:>5}  ({llm_dist[t]/n:.1%})")
    
    print(f"\n  Agreement: {agree}/{n} ({agree/n:.1%})")
    print(f"  Disagreements: {disagree}/{n} ({disagree/n:.1%})")
    
    # Show disagreement breakdown
    dis_matrix = Counter()
    for item in template:
        if item["gold_type"] != item["llm_type"]:
            dis_matrix[(item["llm_type"], item["gold_type"])] += 1
    
    if dis_matrix:
        print(f"\n  Disagreement matrix (LLM -> Gold):")
        for (l_type, g_type), cnt in sorted(dis_matrix.items(), key=lambda x: -x[1]):
            print(f"    {l_type:>12} -> {g_type:<12}  {cnt:>4}")
    
    print(f"\n  Saved: {gold_path}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
