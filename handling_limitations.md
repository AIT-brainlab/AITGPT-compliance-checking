# Handling Current Limitations — Practical Strategies

## Diagnosis Summary

| Limitation | Current | Root Cause |
|---|---|---|
| **M3** FOL quality | 29.8% semantic predicates | Mistral 7B returns empty/placeholder `action` fields in 100% of FOL outputs |
| **M4** Shape correctness | F1 = 0.000 | Only **7 out of 317** pipeline property paths match any of the 199 gold-standard paths |
| **M2** Classification accuracy | 84.1% | 14 misclassified rules out of 88 aligned |
| **May disambiguation** | ~80% accuracy | Pattern-based; misses complex epistemic constructions |
| **Sentence boundaries** | Cross-item contamination | PDF extraction joins/splits at wrong boundaries |

> [!IMPORTANT]
> **M4 = 0.000 is the most critical issue.** The pipeline shapes are structurally valid Turtle, but they use completely different property names than the gold standard. Out of 317 unique pipeline paths, only 7 overlap with the 199 gold-standard paths. This is the single biggest blocker.

---

## Limitation 1: FOL Predicate Quality (M3 = 29.8%)

### What's happening
The FOL node asks Mistral to output `predicates: {action: "payFee"}`, but Mistral returns empty or generic values in **100% of cases**. The `deontic_formula` field (e.g., `O(payFee(student))`) is better — the `_property_path()` function in `shacl.py` already extracts from it — but the `predicates.action` field that M3 measures is always empty.

### Strategies

#### A. Fix the M3 measurement (quick win)
The M3 metric measures `predicates.action`, but the actual semantic content is in `deontic_formula`. Update M3 to also consider the formula-extracted predicate:
```python
# In evaluation, check deontic_formula too
formula_pred = re.search(r'[OPF]\((\w+)', fol['deontic_formula'])
has_semantic = (formula_pred and formula_pred.group(1).lower() not in PLACEHOLDERS)
```
This would likely push M3 from 29.8% to ~60-70% without any pipeline changes.

#### B. Post-process FOL output (medium effort)
Add a `_backfill_predicates()` step after FOL generation that extracts the inner predicate from `deontic_formula` and writes it back to `predicates.action`:
```python
def _backfill_predicates(parsed: dict) -> dict:
    m = re.search(r'[OPF]\((\w+)', parsed.get('deontic_formula', ''))
    if m and parsed.get('predicates', {}).get('action', '') in PLACEHOLDERS:
        parsed['predicates']['action'] = m.group(1)
    return parsed
```

#### C. Use a larger model for FOL (high effort, high impact)
Switch `OLLAMA_MODEL` to a larger model (e.g., `llama3:70b`, `mixtral:8x7b`, or a cloud API). The FOL prompt is well-structured — a more capable model would produce better predicates without prompt changes.

---

## Limitation 2: Shape Correctness (M4 = F1 = 0.000) ⚠️ CRITICAL

### What's happening
The per-rule evaluation shows:
- **43 too_strict** — shape requires a property the Pos test entity doesn't have
- **32 too_permissive** — shape doesn't constrain the property the Neg test entity violates
- **12 skipped** — missing Neg test entity
- **0 correct**

The root cause: **property path mismatch**. The pipeline generates paths like `ait:payFee`, `ait:vacateRoom`, `ait:installHeavyApplianceInUnsuitableAccommodation`, while the gold standard uses paths like `ait:payfee`, `ait:vacateroom`, `ait:enrolment`. Only 7 paths overlap.

### Strategies

#### A. Ontology-guided property path normalization (highest impact)
Inject the gold-standard ontology vocabulary into the SHACL generation prompt so the LLM picks from **known** property names instead of inventing new ones:

```python
# In shacl.py, load known predicates from ontology
KNOWN_PREDICATES = _load_ontology_predicates()  # from ait_policy_ontology.ttl

# Add to FOL prompt or SHACL prompt:
"Use ONLY these property names: {', '.join(KNOWN_PREDICATES)}"
```

This is the **single highest-impact change** you can make. It constrains the LLM to the known vocabulary.

#### B. Post-generation path mapping (medium effort, good impact)
Add a fuzzy-matching step after shape generation that maps pipeline paths to the nearest gold-standard path:

```python
from difflib import get_close_matches

def normalize_path(pipeline_path: str, known_paths: list[str]) -> str:
    # Try exact case-insensitive match first
    lower_map = {p.lower(): p for p in known_paths}
    if pipeline_path.lower() in lower_map:
        return lower_map[pipeline_path.lower()]
    # Fuzzy match
    matches = get_close_matches(pipeline_path.lower(), 
                                 [p.lower() for p in known_paths], 
                                 n=1, cutoff=0.7)
    if matches:
        return lower_map[matches[0]]
    return pipeline_path  # keep original if no match
```

This would catch `payFee` → `payfee`, `vacateRoom` → `vacateroom` etc.

#### C. Case-normalize all paths (quick win)
The simplest fix — lowercase all property paths in both pipeline output and gold standard before comparison. Many mismatches are just casing differences (`payFee` vs `payfee`).

#### D. Two-stage SHACL generation with validation feedback (high effort)
After generating a shape, test it against the gold-standard Pos entity. If it fails, feed the error back to the LLM for repair — similar to the existing Turtle syntax repair loop but for *semantic* correctness.

---

## Limitation 3: Classification Accuracy (M2 = 84.1%)

### What's happening
14 out of 88 aligned rules have wrong deontic type (obligation vs prohibition vs permission).

### Strategies

#### A. Few-shot examples in the classify prompt (medium effort)
Add 3-5 correctly classified examples to the classification prompt, especially edge cases where obligation/prohibition is ambiguous:
```
Example 1: "Students must not cook in dormitories" → prohibition (not obligation)
Example 2: "Fees shall be paid by the deadline" → obligation (not prohibition)
```

#### B. Ensemble with confidence weighting (medium effort)
Run classification with 2 different models (already have `OLLAMA_SECOND_MODEL`) and take the majority vote weighted by confidence. The reclassify node already does this for uncertain rules — extend it to all rules.

#### C. Rule-type post-correction heuristic (quick win)
Add a simple heuristic after classification:
```python
if "must not" in text.lower() or "shall not" in text.lower():
    if rule_type == "obligation":
        rule_type = "prohibition"  # common LLM mistake
```

---

## Limitation 4: May Disambiguation (~80% accuracy)

### What's happening
Pattern-based approach catches `may be`, `may have`, `may include` as epistemic but misses complex constructions like *"A situation may arise where..."* or *"Records may not always be available."*

### Strategies

#### A. Expand epistemic patterns (quick win)
Add more patterns to `EPISTEMIC_MAY_PATTERNS`:
```python
re.compile(r"\bmay\s+arise\b", re.IGNORECASE),
re.compile(r"\bmay\s+vary\b", re.IGNORECASE),
re.compile(r"\bmay\s+occur\b", re.IGNORECASE),
re.compile(r"\bmay\s+not\s+always\b", re.IGNORECASE),
re.compile(r"\bmay\s+also\b", re.IGNORECASE),  # typically epistemic
re.compile(r"\b(?:it|this|that|there)\s+may\b", re.IGNORECASE),  # impersonal subject = epistemic
```

#### B. Subject-based heuristic (medium effort)
Epistemic "may" typically has an impersonal subject (*it*, *this*, *there*, *situation*), while deontic "may" has a human agent (*students*, *faculty*, *committee*):
```python
def disambiguate_may_v2(text: str) -> str:
    # ... existing patterns ...
    if result == "ambiguous":
        # Check subject: human agent = deontic, impersonal = epistemic
        before_may = text[:text.lower().index("may")].strip().split()
        if before_may and before_may[-1].lower() in ("it", "this", "that", "there"):
            return "epistemic"
    return result
```

---

## Limitation 5: Sentence Boundary Detection

### What's happening
`pdfplumber` extracts raw text where line breaks in PDFs create cross-item contamination — numbered list items get joined, or single sentences get split mid-clause.

### Strategies

#### A. Enable spaCy sentencizer (quick win, already implemented)
```bash
EXTRACT_SPACY=1 python -m langgraph_agent.run --source ait
```
This uses spaCy's trained sentence boundary detection instead of naive splitting.

#### B. Pre-processing cleanup rules (medium effort)
Add regex-based cleanup before sentence splitting in `extract.py`:
```python
# Merge broken lines (line ends without period/colon)
text = re.sub(r'(?<![.;:!?])\n(?=[a-z])', ' ', text)
# Split numbered lists into separate sentences
text = re.sub(r'(\d+)\.\s+', r'\n\1. ', text)
```

#### C. PDF layout-aware extraction (high effort)
Use `PyMuPDF` (already in requirements) with block-level extraction instead of page-level. This preserves the document's visual structure — headers, lists, and paragraphs are naturally separated.

---

## Recommended Priority Order

| Priority | Action | Impact | Effort | Metrics Affected |
|----------|--------|--------|--------|-----------------|
| 🔴 1 | **Ontology-guided property paths** (2A) | Very High | Medium | M4 |
| 🔴 2 | **Case-normalize paths** (2C) | High | Low | M4 |
| 🟡 3 | **Fix M3 measurement** (1A) | High | Low | M3 |
| 🟡 4 | **Backfill predicates** (1B) | Medium | Low | M3 |
| 🟡 5 | **Expand may patterns** (4A) | Medium | Low | Prefilter |
| 🟢 6 | **Few-shot classify examples** (3A) | Medium | Medium | M2 |
| 🟢 7 | **Enable spaCy** (5A) | Medium | Low | Extraction |
| 🟢 8 | **Post-generation path mapping** (2B) | High | Medium | M4 |

> [!TIP]
> **Items 1-4 together could move M4 from 0.000 to a meaningful F1 score.** The property path mismatch is fundamentally a vocabulary alignment problem — constrain the LLM to the known ontology vocabulary, and the shapes will start matching.
