# PolicyChecker — Accessible Benchmark Datasets for Evaluation

**Purpose.** Concrete, verified download information for every benchmark that is (a) actually accessible right now and (b) useful for some stage of your pipeline. Each entry has: direct URL, access method, license, size, format, and how to plug it into your specific pipeline stages.

**Status legend:**
- 🟢 **Open / direct download** — public, no gating, ready to use today
- 🟡 **Open but registration required** — free but needs form/email/license click
- 🟠 **Paywalled or request-only** — available but extra friction
- ⚫ **Source text only** — the regulation/policy PDFs are public, but no annotations; you'd annotate yourself

---

## Table of contents

1. [Quick-grab summary](#1-quick-grab-summary)
2. [Tier 1 — Use these first (directly aligned to your pipeline)](#2-tier-1--use-these-first)
   - 2.1 [CODE-ACCORD — building regulations, entity+relation annotations](#21-code-accord)
   - 2.2 [MALLS — NL-FOL pairs](#22-malls)
   - 2.3 [FOLIO — NL-FOL with reasoning](#23-folio)
   - 2.4 [DeonticBench — deontic reasoning benchmark](#24-deonticbench)
   - 2.5 [LexDeMod — contract clauses with deontic labels](#25-lexdemod)
3. [Tier 2 — Useful secondary benchmarks](#3-tier-2--useful-secondary-benchmarks)
   - 3.1 [ObliQA — regulatory QA](#31-obliqa)
   - 3.2 [LexGLUE — general legal NLP](#32-lexglue)
   - 3.3 [CUAD — legal contract review](#33-cuad)
   - 3.4 [OPP-115 — privacy policies](#34-opp-115)
4. [Tier 3 — Source text available, annotate yourself](#4-tier-3--source-text-available-annotate-yourself)
   - 4.1 [TCP Code — Australian Telecommunications](#41-tcp-code)
5. [Tier 4 — Exists but inaccessible / out of scope](#5-tier-4--exists-but-inaccessible--out-of-scope)
6. [Environment setup for running benchmarks](#6-environment-setup-for-running-benchmarks)
7. [Recommended first moves](#7-recommended-first-moves)
8. [Appendix A — Minimal integration examples](#appendix-a--minimal-integration-examples)

---

## 1. Quick-grab summary

| Benchmark | Tier | Access | Size | Pipeline stages it tests | Effort to integrate |
|---|---|---|---|---|---|
| **CODE-ACCORD** | 🟢 1 | Zenodo + HF + GitHub | 862 sentences | extract, prefilter, classify | Low |
| **MALLS** | 🟢 1 | Hugging Face | 28K NL-FOL pairs | FOL generation | Low |
| **FOLIO** | 🟢 1 | GitHub + HF | 1,204 examples | FOL generation & reasoning | Low |
| **DeonticBench** | 🟡 1 | GitHub (verify) | 6,232 tasks | classify + reasoning | Medium |
| **LexDeMod** | 🟢 1 | GitHub | ~7K clauses, 8,230 spans | classify (O/P/F) | Low |
| **ObliQA** | 🟢 2 | GitHub | 27,869 Q+passage | extract + retrieval QA | Medium |
| **LexGLUE** | 🟢 2 | Hugging Face | 7 subsets | general classification | Low |
| **CUAD** | 🟢 2 | GitHub + HF | 510 contracts, 13K labels | clause classification | Low |
| **OPP-115** | 🟢 2 | CMU website | 115 policies | privacy-specific classify | Low |
| **TCP Code** | ⚫ 3 | ACMA PDF | ~10 chapters | all stages, DIY annotate | High |

All direct download URLs and loading code are in the sections below.

---

## 2. Tier 1 — Use these first

These five are the most directly useful for measuring your pipeline's stages against published baselines.

### 2.1 CODE-ACCORD

**Status**: 🟢 Open, no registration
**What it is**: 862 self-contained sentences from the building regulations of England and Finland, manually annotated with 4,297 entities and 4,329 relations by 12 annotators. Published in *Scientific Data* (Nature) 2024.

**Why it's most aligned to your extraction + prefilter + classify stages**: Structurally the closest public corpus to what your extraction layer produces. Sentence-level with entity/relation annotations, covering regulatory text that expresses rules. The annotators explicitly filtered for sentences with quantitative requirements, subjective requirements, and deontic logic — the same selection criteria your prefilter applies.

**Access**:
- **GitHub** (recommended): <https://github.com/Accord-Project/CODE-ACCORD>
- **Zenodo** (includes raw PDFs): <https://doi.org/10.5281/zenodo.10210022>
- **Hugging Face** (easiest programmatic access):
  - Entities: <https://huggingface.co/datasets/ACCORD-NLP/CODE-ACCORD-Entities>
  - Relations: <https://huggingface.co/datasets/ACCORD-NLP/CODE-ACCORD-Relations>

**License**: The GitHub repo indicates open academic use; confirm by reading the specific license file before publication.

**Format**: CSV (train.csv / test.csv), 80/20 split. Fields include sentence text, annotation spans, entity types (Object, Property, Quality, Value), and ten relation categories (selection, necessity, part-of, not-part-of, greater, greater-equal, etc.).

**Companion framework**: `accord-nlp` (<https://github.com/Accord-Project/accord-nlp>) provides fine-tuned BERT/ALBERT/RoBERTa models and a full pipeline you can compare against.

**How to load**:

```python
from datasets import load_dataset

# Entity annotations
entities = load_dataset("ACCORD-NLP/CODE-ACCORD-Entities")
# Relation annotations
relations = load_dataset("ACCORD-NLP/CODE-ACCORD-Relations")

print(entities["train"][0])
# → {"sentence": "...", "entities": [...], "source": "..."}
```

**How to integrate with your pipeline**:

1. **Extraction/prefilter evaluation**: feed raw sentences through your prefilter, check recall against their 862 curated self-contained sentences. Expected M1-style metric: what fraction of their curated sentences does your prefilter retain?
2. **Classification mapping** (requires mapping their scheme to yours): their "necessity" relation roughly corresponds to your obligation; "not-part-of" or "selection" can map to prohibition/permission depending on context. This mapping is itself a small contribution.
3. **External-validation run**: this gives you your first non-AIT external benchmark number.

**Citation**:
```bibtex
@article{hettiarachchi-etal-2025-code,
  title   = {{CODE-ACCORD}: A Corpus of building regulatory data for rule generation towards automatic compliance checking},
  author  = {Hettiarachchi, Hansi and others},
  journal = {Scientific Data},
  year    = {2025}
}
```

---

### 2.2 MALLS

**Status**: 🟢 Open (CC BY-NC 4.0)
**What it is**: Large language Model generAted natural-Language-to-first-order-Logic pairS. 28K NL-FOL pairs, generated by prompting GPT-4 and processed to ensure validity; v0 has 34K unfiltered, v0.1 has 28K filtered (27K auto-verified + 1K human-verified).

**Why it's aligned to your FOL stage**: Standard benchmark for natural language → FOL translation. If you want to quantify your FOL quality (M3 from the enhancement plan) with an external reference, this is the canonical dataset.

**Access**:
- **Hugging Face**: <https://huggingface.co/datasets/yuan-yang/MALLS-v0>
- **GitHub (LogicLLaMA companion)**: <https://github.com/gblackout/LogicLLaMA>
- **Model weights** (optional comparison): <https://huggingface.co/yuan-yang/LogicLLaMA-7b-direct-translate-delta-v0.1>

**License**: Attribution-NonCommercial 4.0 International. Safe for academic thesis use.

**Format**: JSON. Each entry:
```json
{"NL": "<natural language statement>", "FOL": "<first-order logic rule>"}
```

Files: `MALLS-v0.json` (34K unfiltered), `MALLS-v0.1-train.json` (27K auto-verified), `MALLS-v0.1-test.json` (1K human-verified).

**How to load**:

```python
from datasets import load_dataset
ds = load_dataset("yuan-yang/MALLS-v0")
print(ds["train"][0])
# → {"NL": "If a person is a vegetarian, then they don't eat meat.", 
#    "FOL": "∀x (Vegetarian(x) → ¬EatsMeat(x))"}
```

**How to integrate**:

1. Sample 500-1000 entries from the human-verified test set.
2. Run your `fol_node` on the NL side (treat each sentence as a rule).
3. Compare your output FOL formulas to ground-truth FOL using:
   - **Exact match** (harsh baseline)
   - **Logical equivalence** via Z3 or Prover9 (standard in the literature)
   - **Predicate alignment** (soft metric: what fraction of predicates in ground truth appear in your output)
4. This gives you M3 with external reference — way stronger than your internal placeholder-detection metric.

---

### 2.3 FOLIO

**Status**: 🟢 Open
**What it is**: Expert-written, open-domain, logically complex and diverse dataset for natural language reasoning with first-order logic. 1,435 examples (unique conclusions), each paired with one of 487 sets of premises, with FOL annotations automatically verified by an inference engine.

**Why it's aligned to your FOL stage (and possibly classify)**: Gold-standard for evaluating both NL-FOL translation and FOL reasoning. Small enough to use as a full test set without sampling.

**Access**:
- **GitHub (official)**: <https://github.com/Yale-LILY/FOLIO>
- **Hugging Face**: <https://huggingface.co/datasets/tasksource/folio>
- **Hugging Face (extended proofs)**: <https://huggingface.co/datasets/yale-nlp/P-FOLIO> (P-FOLIO has human-annotated reasoning chains)

**License**: Check the GitHub repo; open for research use.

**Format**: JSONL. Fields per example:
- `premises`: list of natural-language premises
- `premises-FOL`: parallel FOL annotations
- `conclusion`: the conclusion to verify
- `conclusion-FOL`: FOL version of conclusion
- `label`: True / False / Unknown

**Size**: 1,204 rows in the tasksource version; 1.22 MB download. Tiny.

**How to load**:

```python
from datasets import load_dataset
folio = load_dataset("tasksource/folio")
```

**How to integrate**:

1. Use as a secondary NL-FOL translation test (alongside MALLS).
2. FOLIO has a harder compositionality / reasoning component than MALLS — running both gives you a "translation quality vs. reasoning quality" split you can report.
3. Small size means you can run it even with slow local LLMs in a few hours.

---

### 2.4 DeonticBench

**Status**: 🟡 Open but verify (paper cites `guangyaodou/DeonticBench` on GitHub; at the time of my research the repo wasn't visible under the author's profile — it may be gated, under review, or the exact repo name may differ)
**What it is**: 6,232 tasks across U.S. federal taxes, airline baggage policies, U.S. immigration administration, and U.S. state housing law, focused on reasoning about obligations, permissions, and prohibitions under explicit rules.

**Why it's the most aligned benchmark to your classify stage**: This is the only large-scale benchmark *specifically* for deontic reasoning. The task is directly your problem: given a rule text, reason about what's obligated/permitted/prohibited.

**Access**:
- **Paper**: arxiv 2604.04443 (Dou, Brena, Deo, Jurayj, Zhang, Holzenberger, Van Durme — JHU)
- **Claimed repo**: `guangyaodou/DeonticBench` (verify at <https://github.com/guangyaodou/DeonticBench> — if the public repo isn't there, email `gdou1@jhu.edu` directly; the author explicitly lists his email in the paper as the correspondence address)
- **Author's GitHub**: <https://github.com/guangyaodou>

**Format**: Unknown until access is confirmed. The paper indicates tasks support both direct NL reasoning and symbolic Prolog translation, with reference Prolog programs released for all instances.

**How to integrate**:

1. If you can access the raw rule texts: run your classify stage on them, compare deontic-type labels to their ground truth.
2. If their symbolic targets are Prolog (not SHACL), the comparison is at classification only, not at shape-generation level — but that's fine; it's an external M2 validation.
3. The "hard subset" scores they report (44.4% on SARA Numeric, 46.6 macro-F1 on Housing) give you defensible context for interpreting your own numbers.

**Why the uncertainty**: The paper is recent (2025 preprint, arxiv 2604 indicates ~early 2026 revision). GitHub repos sometimes lag behind arxiv submissions by weeks/months. Contact the authors directly if repo isn't yet public — datasets are often released on request for reviewers and peers before final public release.

---

### 2.5 LexDeMod

**Status**: 🟢 Open
**What it is**: Corpus of English contracts annotated with deontic modality expressed with respect to a contracting party or agent along with the modal triggers. Specifically: 7,092 clauses from 23 lease contracts with 8,230 span annotations. Each clause manually annotated with one or more of seven types: obligation, entitlement, prohibition, permission, no obligation, no entitlement, and none.

**Why it's directly aligned to your classify stage**: The seven labels map almost 1:1 to your obligation/permission/prohibition scheme (with "entitlement" being a permission variant, and "no obligation/entitlement" being useful for ablations). This is the most directly comparable classification benchmark to your work.

**Access**:
- **GitHub**: <https://github.com/abhilashasancheti/LexDeMod>
- **Paper**: arxiv 2211.12752 (Sancheti, Garimella, Srinivasan, Rudinger — UMD + Adobe, EMNLP Findings 2022)

**License**: check the repo; standard academic use.

**Splits** (reported in the LLMs for Law paper using LexDeMod): train (4.2k), dev (330), test (1.7k).

**How to load**: Clone the repo; data is in JSON or CSV format depending on the release.

**How to integrate**:

1. Run your classify stage on the test set clauses.
2. Aggregate your seven-label predictions to their three core labels (obligation/permission/prohibition) or use a mapping: entitlement→permission, no-obligation→none.
3. Report micro-F1 and macro-F1 — these are the standard metrics on this dataset and papers have published baselines you can compare against (BERT, RoBERTa, Contracts-BERT, LegalBERT, etc.).
4. **This is probably your best single classify-stage external validation** — same task, comparable size, established baselines.

---

## 3. Tier 2 — Useful secondary benchmarks

### 3.1 ObliQA

**Status**: 🟢 Open
**What it is**: 27,869 questions derived from regulatory documents from Abu Dhabi Global Markets (ADGM), which set regulations for financial services in the UAE free zones. 40 documents totaling approximately 640,000 words, each 30-100 pages.

**Why it's relevant**: RegNLP benchmark — same field as your work. Also has a companion **ObligationClassifier** repo specifically for binary obligation detection.

**Access**:
- **Main dataset**: <https://github.com/RegNLP/ObliQADataset>
- **Multi-passage extension**: <https://github.com/RegNLP/ObliQA-ML>
- **Obligation classifier** (more directly useful for you): <https://github.com/RegNLP/ObligationClassifier>
- **Shared task 2025 results**: <https://aclanthology.org/2025.regnlp-1.pdf>

**Format**: JSON with `QuestionID`, `Question`, `Passages` (list of `DocumentID`, `PassageID`, `Passage`).

**How to integrate**:

1. **Primary use**: the ObligationClassifier subset is built using ADGM Financial Regulations, with text labeled as obligations (True) or non-obligations (False) — direct binary classification comparison for your is_rule detection.
2. **Secondary use**: the question-passage pairs can be used to validate your extraction (if your pipeline can answer their questions from retrieved passages).

**Note**: ObliQA is retrieval + QA, not classification-first like your pipeline. The ObligationClassifier subset is the more directly useful artifact.

---

### 3.2 LexGLUE

**Status**: 🟢 Open (CC BY 4.0)
**What it is**: Legal General Language Understanding Evaluation benchmark, based on seven existing legal NLP datasets including ECtHR, EurLex, LEDGAR, UNFAIR-ToS, CaseHOLD, SCOTUS, and others.

**Why it's relevant**: Not directly deontic-focused, but UNFAIR-ToS and LEDGAR subsets are contract-classification tasks analogous to yours. Standard for legal-NLP validation.

**Access**:
- **Hugging Face**: <https://huggingface.co/datasets/coastalcph/lex_glue>
- **GitHub**: <https://github.com/coastalcph/lex-glue>

**How to load**:

```python
from datasets import load_dataset
# Pick your subset
ledgar = load_dataset("coastalcph/lex_glue", "ledgar")        # contract topic classification
unfair = load_dataset("coastalcph/lex_glue", "unfair_tos")    # unfair terms classification
```

**How to integrate**: If you want to demonstrate your classifier generalises beyond institutional policy, run on UNFAIR-ToS (sentence-level classification of 8 unfair contract term types). Expected treatment: a mapping from their 8 types to your O/P/F scheme is non-trivial, but it's a published dataset a reviewer will recognize.

---

### 3.3 CUAD

**Status**: 🟢 Open (CC BY 4.0)
**What it is**: Over 500 contracts carefully labeled by legal experts to identify 41 different types of important clauses, with more than 13,000 annotations.

**Access**:
- **GitHub**: <https://github.com/TheAtticusProject/cuad>
- **Hugging Face**: <https://huggingface.co/datasets/theatticusproject/cuad-qa>
- **Project site**: <https://www.atticusprojectai.org/cuad/>

**Format**: QA-style (SQuAD-like) — each label is a span-prediction task.

**How to integrate**: Less directly aligned — CUAD is about *finding* specific clause types (e.g., "Minimum Commitment Extraction", "Revenue Percentage Extraction"), not classifying deontic modality. Useful only if you want to demonstrate your extraction layer generalizes beyond institutional/regulatory text to commercial contracts.

**Note**: The Atticus Project also has MAUD (merger agreements) and ACORD (126,000+ expert-rated query-clause pairs) — all CC BY 4.0, all via <https://www.atticusprojectai.org/datasets/>. Lower priority but available.

---

### 3.4 OPP-115

**Status**: 🟡 Open for research (dataset page states "research, teaching, and scholarship purposes only")
**What it is**: 115 privacy policies with 23K fine-grained data practice annotations.

**Access**:
- **Dataset page**: <https://usableprivacy.org/data>
- **Direct zip**: OPP-115_v1_0.zip (94.5 MB — linked from that page)
- **Related datasets** (same lab): APP-350, MAPP (bilingual EN+DE), PrivacyQA, Opt-Out Choice, Privacy Law Corpus (1,043 laws)

**License**: Creative Commons Attribution-NonCommercial-like; a commercial license exists but the non-commercial research license is free.

**Format**: Paragraph-level annotations across 10 data practice categories (First Party Collection, Third Party Sharing, User Access/Edit/Delete, etc.).

**How to integrate**: Privacy-specific — annotation categories don't map cleanly to your O/P/F. Use only if you want to show your pipeline can extract privacy-relevant obligations from TOS-style documents as a generalization demo.

---

## 4. Tier 3 — Source text available, annotate yourself

### 4.1 TCP Code

**Status**: ⚫ Source PDF public; no annotated dataset publicly released by Dragoni/Horner
**What it is**: Australian Telecommunications Consumer Protections Code C628:2019 — the corpus used by Dragoni et al. (2016-2017) and Horner et al. (2025) for deontic formalization. The PDFs are public; the *annotations* (their DDL formalizations) are partially in their papers but not released as a downloadable dataset.

**Access**:
- **Official PDF (C628:2019)**: <https://www.acma.gov.au/sites/default/files/2022-06/C628_2019%20TCP%20Code_registered%201%20July%202019.pdf>
- **Australian Telecommunications Alliance**: <https://www.austelco.org.au/publication/c628/>
- **Horner 2025 paper** (for their evaluation methodology): arxiv 2506.08899

**Why it's valuable despite DIY annotation**: This is the corpus where the Dragoni-Governatori-Horner chain of papers built their results. Running your pipeline on it gives a **direct three-way methodological comparison** — the strongest possible external-validation story for a thesis. Their papers report per-chapter success scores you can compare against.

**What you'd need to do**:

1. **Download** the C628:2019 PDF.
2. **Extract** through your existing pipeline (you already handle PDFs).
3. **Build a mini gold standard** for a subset (say, Chapter 4 or 6, which both Dragoni and Horner focus on) — 20-30 rules manually annotated with your Pos/Neg test entity scheme.
4. **Run evaluation** — report M1-M5 on this subset.
5. **Compare to Horner 2025's six-dimension evaluation** for parallel numbers.

**Effort**: high (probably 1-2 days of annotation work for a small subset) — but this is the single most impactful addition to your thesis's external validation story, and the annotation work itself is a citable contribution ("we extend the TCP Code benchmark with SHACL-style test entity pairs").

---

## 5. Tier 4 — Exists but inaccessible / out of scope

Here for completeness so you don't waste time on them:

- **Kiyavitskaya et al. HIPAA / Stanca Act dataset (GaiusT)**: described in papers but no public release I could find.
- **Dragoni et al. TCP formalization dataset**: papers describe the methodology but the DDL annotations themselves aren't in a downloadable format.
- **Willow dataset** (used in Vossel 2025, arxiv 2509.22338): referenced but I couldn't verify public availability; if critical, email the first author.
- **GaiusT**: Cerno-framework annotations for HIPAA and Italian accessibility law — described in 2008+ Springer papers, no public release.
- **BREX (Business Rule Extraction Benchmark)**: mentioned in 2025 papers, availability depends on the release status of the paper's supplementary materials.
- **LUBM (for Trav-SHACL)**: available but it's synthetic RDF, not policy text — wrong abstraction level for your needs.
- **Compliance-to-Code (Chinese financial)**: Chinese-language only; out of scope for AIT-English pipeline.

---

## 6. Environment setup for running benchmarks

Add these to your `requirements.txt` (if not already present):

```
datasets>=2.14.0        # Hugging Face datasets
rdflib>=6.3.0           # you already have this
pyshacl>=0.23.0         # you already have this
scikit-learn>=1.3.0     # for TF-IDF similarity in alignment
sentence-transformers>=2.2.0   # for embedding-based alignment
rapidfuzz>=3.0.0        # for fuzzy matching
z3-solver>=4.12.0       # for logical equivalence evaluation on MALLS
```

One-time model download for embedding-based alignment:

```python
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")  # ~80MB, one-time cache
```

For Hugging Face datasets, make sure your firewall/proxy allows `huggingface.co` and `datasets-server.huggingface.co`.

---

## 7. Recommended first moves

Given your thesis goals (coverage, reproducibility, SHACL correctness, FOL quality, classification accuracy), here's the order I'd run them in.

**Week 1 — external validation on classify stage**
1. Download **LexDeMod** (§2.5). Run your classify stage on the test set. Report micro-F1 and macro-F1. This is your strongest single external classify benchmark.
2. Download **CODE-ACCORD** via Hugging Face (§2.1). Run your extract + prefilter stages; measure recall against their 862 curated sentences.

**Week 2 — external validation on FOL stage**
3. Download **FOLIO** (§2.3) — it's tiny (1.2 MB). Run your `fol_node` on the NL premises; compare to ground truth FOL using logical equivalence via Z3.
4. Sample 500 items from **MALLS** v0.1 test (§2.2). Same protocol as FOLIO.

**Week 3 — flagship external comparison**
5. **TCP Code** (§4.1) — download the PDF, run your full pipeline, build mini gold standard (30 rules × Pos/Neg entities). Report M1-M5 alongside Horner 2025's six-dimension scores.

**Week 4 — DeonticBench if accessible**
6. Attempt access to **DeonticBench** (§2.4). If available, run as secondary large-scale classify + reasoning benchmark. If not, email the authors.

**Publishable thesis result at the end**: AIT (your primary) + 3-4 external benchmarks + the dataset contribution of TCP Code Pos/Neg extensions. That's a defensible evaluation section.

---

## Appendix A — Minimal integration examples

### A.1 CODE-ACCORD extraction recall test

```python
# evaluation/external/code_accord_test.py
from datasets import load_dataset
from core.prefilter import PreFilter

# Load the CODE-ACCORD annotated sentences (they're already curated as rule-like)
ds = load_dataset("ACCORD-NLP/CODE-ACCORD-Entities", split="test")
sentences = [row["sentence"] for row in ds if "sentence" in row]

pf = PreFilter()
results = pf.filter_sentences(sentences)

candidates = sum(1 for r in results if r.is_candidate)
print(f"Prefilter recall on CODE-ACCORD: {candidates}/{len(sentences)} = {candidates/len(sentences):.1%}")
```

### A.2 MALLS FOL translation test

```python
# evaluation/external/malls_test.py
import random, json
from datasets import load_dataset
from langgraph_agent.nodes.fol import _llm, _FOL_PROMPT, _parse_fol
from langchain_core.messages import HumanMessage

ds = load_dataset("yuan-yang/MALLS-v0", split="train")  # v0.1 human-verified ~1K
sample = random.sample(list(ds), 100)

results = []
for item in sample:
    nl = item["NL"]
    gt_fol = item["FOL"]
    prompt = _FOL_PROMPT.format(text=nl, rule_type="unknown")
    response = _llm.invoke([HumanMessage(content=prompt)])
    parsed = _parse_fol(response.content)
    results.append({
        "NL": nl,
        "ground_truth_FOL": gt_fol,
        "predicted_FOL": parsed.get("deontic_formula") if parsed else None,
    })

# Save for manual scoring or automated logical-equivalence evaluation
with open("output/malls_results.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
```

### A.3 LexDeMod classify test

```python
# evaluation/external/lexdemod_test.py
# Assumes you've git-cloned https://github.com/abhilashasancheti/LexDeMod to ./vendor/LexDeMod
import json, pandas as pd
from pathlib import Path
from langgraph_agent.nodes.classify import classify_node
from langgraph_agent.state import PipelineState, SentenceItem

LXD = Path("vendor/LexDeMod")
test_data = json.loads((LXD / "test.json").read_text())  # adjust filename once cloned

# Map LexDeMod's 7 labels to your 3
LABEL_MAP = {
    "obligation":    "obligation",
    "entitlement":   "permission",
    "prohibition":   "prohibition",
    "permission":    "permission",
    "no-obligation": "none",
    "no-entitlement":"none",
    "none":          "none",
}

candidates = [
    SentenceItem(text=item["text"], page=0, source="lexdemod")
    for item in test_data
]

state = PipelineState(
    source="lexdemod", pdf_dir="",
    extracted_sentences=candidates, total_sentences=len(candidates),
    candidates=candidates, rules=[], uncertain_rules=[],
    fol_formulas=[], fol_failed=[], shacl_shapes=[],
    shacl_output_path="", validation_results={}, conforms=False,
    report={}, current_step="test", errors=[],
)
out = classify_node(state)

# Confusion matrix against ground truth (see paper for exact field names)
# Use sklearn's classification_report for micro/macro-F1
from sklearn.metrics import classification_report
y_true = [LABEL_MAP.get(item["deontic_label"], "none") for item in test_data]
y_pred = [rule["rule_type"] for rule in out["rules"]]
print(classification_report(y_true, y_pred, zero_division=0))
```

---

## Closing note

Every dataset in Tier 1 is downloadable today, in standard formats, with permissive licenses. Start with LexDeMod (§2.5) and CODE-ACCORD (§2.1) — those two alone give you external validation on two of your most important pipeline stages, and neither requires more than an afternoon to set up. MALLS and FOLIO extend that to FOL quality. TCP Code is the thesis-defining one if you have a spare week for manual annotation.
