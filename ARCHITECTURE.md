# PolicyChecker — Pipeline Architecture

> **Master's Thesis — AIT 2026**  
> This document describes the internal design of the PolicyChecker pipeline for
> anyone reading or extending the codebase.

---

## Overview

PolicyChecker is a **9-node LangGraph state machine** that transforms institutional
policy PDFs into validatable SHACL shapes. The pipeline is deterministic
(fixed seed, caching) and fully ablation-controllable via environment flags.

```
PDF documents
     │
     ▼
┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ extract │──▶│ prefilter  │──▶│ classify │──▶│ reclassify  │
└─────────┘   └────────────┘   └──────────┘   └─────────────┘
                                    │ route_classify         │
                               ─────┴────────────────────────┘
                              ▼ (if confident only)   ▼ (if uncertain)
                           ┌─────┐              ┌─────────────┐
                           │ fol │◀─────────────│ reclassify  │
                           └─────┘              └─────────────┘
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
               ┌────────┐       ┌──────────────┐
               │  shacl │       │ direct_shacl │
               └────────┘       └──────────────┘
                    └─────────┬──────────┘
                              ▼
                        ┌──────────┐   ┌────────┐
                        │ validate │──▶│ report │
                        └──────────┘   └────────┘
```

---

## State Schema (`langgraph_agent/state.py`)

The `PipelineState` TypedDict flows through every node. Each node receives the
full state and returns a **partial dict** — LangGraph merges it back.

```
Source / Input
  source: str                     "ait" — corpus identifier
  pdf_dir: str                    path to institutional_policy/AIT/

After extract
  extracted_sentences: List[SentenceItem]   all sentences from PDFs
  total_sentences: int

After prefilter / classify
  candidates: List[SentenceItem]  passed the heuristic filter
  rules: List[RuleItem]           confident rules (confidence ≥ 0.6)
  uncertain_rules: List[RuleItem] borderline rules (0.4 ≤ conf < 0.6)

After fol
  fol_formulas: List[FOLItem]     successfully formalized rules
  fol_failed: List[RuleItem]      rules that failed FOL parsing

After shacl / direct_shacl  (accumulator — both branches add to it)
  shacl_shapes: List[SHACLShape]  generated SHACL NodeShapes

After validate
  validation_results: dict        full pyshacl output
  conforms: bool

After report
  report: dict                    final summary JSON

Meta (updated by each node)
  current_step: str
  errors: List[str]               accumulates errors across all nodes
```

`shacl_shapes` and `errors` use `Annotated[..., operator.add]` — LangGraph
concatenates them rather than overwriting. This is how the two parallel SHACL
branches (shacl + direct_shacl) both contribute shapes to the same list.

---

## Node-by-Node Description

### 1. `extract` — `langgraph_agent/nodes/extract.py`

**What it does:** Reads every `.pdf` in `pdf_dir`, extracts raw text with
`pdfplumber`, normalises soft-wraps and multi-newlines, then splits into
sentences. Optionally uses spaCy's `en_core_web_sm` sentencizer when
`EXTRACT_SPACY=1`.

**Key logic:**
- `_normalise()` rejoins soft-wrapped lines before splitting
- Sentences outside `[_MIN_WORDS=5, _MAX_WORDS=250]` token range are dropped
- `_NOISE` regex filters page numbers, headers, URLs, copyright marks
- Each sentence becomes a `SentenceItem` with `{text, page, source}`

**Output added to state:** `extracted_sentences`, `total_sentences`

---

### 2. `prefilter` — `langgraph_agent/nodes/prefilter.py` (wraps `core/prefilter.py`)

**What it does:** Heuristic pre-screen. Every `SentenceItem` is scored for
deontic content. Only sentences with non-trivial score become `candidates`.

**Core module `core/prefilter.py`** (600+ lines) implements:
- **Deontic marker detection** — regex patterns for obligation (`must`, `shall`,
  `is required to`), permission (`may`, `is entitled to`), prohibition (`must not`,
  `is prohibited`)
- **Epistemic "may" disambiguation** — `may be`, `may have`, `may lead to`,
  `may result in` are descriptive, not deontic. Filtered out.
- **Speech-act classification** — Searle-style labels: `directive`, `commissive`,
  `prohibitive`, `assertive`, `suggestive`
- **Section-aware weighting** — section headings matching policy keywords
  (`disciplinary`, `academic`, `financial`, `conduct`, etc.) get weight multipliers
  that boost their sub-sentences' scores (Brodie et al., 2006)

**Output added to state:** `candidates` (with deontic_strength, speech_act,
section_context, confidence_boost fields filled in)

---

### 3. `classify` — `langgraph_agent/nodes/classify.py`

**What it does:** Each candidate sentence is submitted to the LLM (Ollama/Mistral)
with a structured prompt asking for `{is_rule, rule_type, confidence, reasoning}`.
Results are cached. Confident rules (confidence ≥ 0.6) go to `rules`; borderline
(0.4–0.6) go to `uncertain_rules`.

**Key design decisions:**
- Prefilter hints (`deontic_strength`, `speech_act`, `section_context`) are
  injected into the prompt — this is what separates V0 from V1–V3 ablations
- Cache key includes hint values — hint changes invalidate stale cache entries
- `cached_or_generate()` pattern: always check SQLite cache before invoking LLM
- LLM uses `temperature=0, top_k=1, seed=42` — greedy/deterministic decoding
- Invalid `rule_type` values from LLM are sanitised to `"obligation"` (safe default)

**Routing after classify (`edges/route_classify.py`):**
- `has_uncertain` → go to `reclassify` first
- `not has_uncertain and has_confident` → skip to `fol` directly
- neither → `end` (no policy rules found)

---

### 4. `reclassify` — `langgraph_agent/nodes/reclassify.py`

**What it does:** Second-opinion pass for the `uncertain_rules`. Uses a
configurable `SECOND_MODEL` (defaults to Mistral with `seed=43`) with a
more directive prompt — binary verdict, no confidence band.

Rules that survive (second opinion says "yes, this is a rule") are merged
back into `rules`. Rules that fail the second opinion are dropped. After
reclassify, `uncertain_rules` is cleared.

**Ablation:** `ABLATION_SKIP_RECLASSIFY=1` drops uncertain rules entirely.

---

### 5. `fol` — `langgraph_agent/nodes/fol.py`

**What it does:** Each `RuleItem` is formalized into a `FOLItem` using deontic
logic: `O(φ)` (obligation), `P(φ)` (permission), `F(φ)` (prohibition).

**Retry logic (`_generate_with_retry`):**
1. First attempt: generate FOL with `_FOL_PROMPT` (includes vocabulary hint)
2. `_is_placeholder()` check — rejects generic predicates like `Action(x)`,
   `Predicate(y)`, single letters
3. If placeholder detected: retry up to 2× with `_FOL_RETRY_PROMPT` (shows the
   bad formula, insists on semantic predicates)
4. Post-retry: `_backfill_predicates()` — if predicates are still empty/placeholder,
   extracts subject/action/condition from rule text using regex heuristics

**Vocabulary hint:** `_get_vocabulary_hint()` loads the AIT ontology property
list from `langgraph_agent/corpus_config.py`. The LLM is instructed to prefer
known property names (`payFee`, `submitThesis`, etc.) from the ontology. This
directly improves M3 FOL Quality.

**Cache key:** includes `rule_type` and `FOL_PROMPT_VERSION=3` — changing either
invalidates all cached results.

**Output:** `fol_formulas` (successful), `fol_failed` (rules for NL fallback)

---

### 6. `shacl` — `langgraph_agent/nodes/shacl.py`

**What it does:** Translates `FOLItem`s into SHACL `NodeShape` Turtle blocks.

**Shape generation (`_fol_to_turtle`):**
- Extracts `predicates.subject` → `sh:targetClass`
- Obligation → `sh:minCount 1, sh:severity sh:Violation`
- Prohibition → `sh:maxCount 0, sh:severity sh:Violation`  
- Permission → `sh:severity sh:Info`
- Confidence-weighted severity: high-confidence violations get `sh:Violation`,
  medium get `sh:Warning`
- `sh:targetSubjectsOf` fallback for `Person`-typed generic subjects

**Inline NL fallback (`_try_direct_fallback`):** if `_fol_to_turtle` fails for a
specific rule (bad predicate, missing subject), it calls into `direct_shacl`
logic before routing the rule to `fol_failed`.

**Override triples:** Permission-as-exception rules get `deontic:overrides` links
(Governatori & Rotolo, 2010).

---

### 7. `direct_shacl` — `langgraph_agent/nodes/direct_shacl.py`

**What it does:** NL-to-SHACL fallback for `fol_failed` rules. Prompts the LLM
to produce Turtle directly from natural language.

**Repair loop:** If the generated Turtle fails to parse:
1. `_validate_turtle()` — parses with rdflib
2. `_repair_turtle()` — re-prompts LLM with the parse error, up to
   `MAX_REPAIR_ATTEMPTS=2` times

**Output:** `SHACLShape` items with `generation_method="direct_nl"`

Both `shacl` and `direct_shacl` append to the same `shacl_shapes` accumulator.

---

### 8. `validate` — `langgraph_agent/nodes/validate.py`

**What it does:**
1. Writes pipeline shapes to `output/ait/shapes_generated.ttl`
2. Merges with gold-standard curated shapes from `shacl/shapes/*.ttl`
3. Loads TDD test entity data from `shacl/test_data/` (180 pos/neg entities)
4. Runs `pyshacl` validation
5. Triages false positives: violations on intentionally non-conforming entities
   are expected

**Output:** `validation_results`, `conforms`

---

### 9. `report` — `langgraph_agent/nodes/report.py`

**What it does:** Assembles the final `pipeline_report.json` in `output/ait/`:
- Rule counts by type (obligation/permission/prohibition)
- Shape generation counts (FOL-mediated vs NL fallback)
- Syntax validity rates
- Violation counts and severity breakdown
- Environment metadata (model versions, pipeline version, timestamp)
- M5 stability hash

---

## Graph Assembly (`langgraph_agent/graph.py`)

```python
_NODE_SPECS = (
    ("extract",       "langgraph_agent.nodes.extract",       "extract_node"),
    ("prefilter",     "langgraph_agent.nodes.prefilter",     "prefilter_node"),
    ("classify",      "langgraph_agent.nodes.classify",      "classify_node"),
    ("reclassify",    "langgraph_agent.nodes.reclassify",    "reclassify_node"),
    ("fol",           "langgraph_agent.nodes.fol",           "fol_node"),
    ("shacl",         "langgraph_agent.nodes.shacl",         "shacl_node"),
    ("direct_shacl",  "langgraph_agent.nodes.direct_shacl", "direct_shacl_node"),
    ("validate",      "langgraph_agent.nodes.validate",      "validate_node"),
    ("report",        "langgraph_agent.nodes.report",        "report_node"),
)
```

Each module is loaded lazily via `_load_node()`. If an import fails, the node
falls back to a stub in `_stubs.py` that passes state through unchanged. This
allows partial pipeline runs when some dependencies (e.g., pdfplumber, spaCy)
are not installed.

**Fixed edges:**
```
extract → prefilter → classify
classify → [reclassify | fol]   (conditional: route_classify)
reclassify → fol
fol → shacl
fol → direct_shacl              (parallel branch)
shacl → validate
direct_shacl → validate
validate → report → END
```

---

## Caching (`core/llm_cache.py`)

Every LLM call is wrapped in `cached_or_generate()` from `langgraph_agent/nodes/common.py`.

Cache key = `hash(text + model + prompt_type + extra_params)`. The `extra_params`
dict includes `prompt_version` — bump the version constant to invalidate all
cached results for that node.

```
FOL_PROMPT_VERSION = 3          # in fol.py
RECLASSIFY_PROMPT_VERSION = "v1"  # in reclassify.py
DIRECT_SHACL_PROMPT_VERSION = "v1"
```

Storage: SQLite at `cache/llm_cache.db`. To flush:
```bash
rm cache/llm_cache.db
```

---

## Ablation Flags

All flags are environment variables, checked at runtime via `os.getenv(...)`.

| Flag | Effect |
|------|--------|
| `ABLATION_SKIP_RECLASSIFY=1` | Skip second-opinion pass; drop uncertain rules |
| `ABLATION_NO_HINTS=1` | Strip prefilter hints from classify prompt |
| `ABLATION_SKIP_DIRECT_SHACL=1` | Skip NL→SHACL fallback |
| `ABLATION_NO_FOL_RETRY=1` | Disable placeholder retry loop |
| `ABLATION_SKIP_MAY_DISAMBIG=1` | Disable epistemic-may filter in prefilter |
| `EXTRACT_SPACY=1` | Use spaCy sentencizer instead of regex splitter |

These flags are set by `langgraph_agent/run.py` when `--ablation <name>` is passed.

---

## Key File Index

| File | Role |
|------|------|
| `langgraph_agent/graph.py` | StateGraph assembly — start here to understand flow |
| `langgraph_agent/state.py` | `PipelineState` TypedDict — all data that flows between nodes |
| `langgraph_agent/llm.py` | Ollama LLM config (seed, timeout, model names) |
| `langgraph_agent/run.py` | CLI entry point |
| `langgraph_agent/nodes/common.py` | `invoke_text`, `cached_or_generate`, `parse_json_object` |
| `langgraph_agent/corpus_config.py` | AIT corpus settings, vocabulary hint, namespace |
| `core/prefilter.py` | Heuristic filter (600+ lines) — deontic markers, may disambiguation |
| `core/llm_cache.py` | SQLite cache with prompt-versioned keys |
| `core/turtle_utils.py` | `get_rule_block()`, `prefix_block()` — used by web/app.py |
| `web/app.py` | FastAPI server — compliance dashboard backend |
| `shacl/shapes/*.ttl` | 96 curated gold-standard SHACL shapes |
| `evaluation/external_annotator_agreement.py` | Active: Fleiss' κ + LLM accuracy |
| `evaluation/confidence_intervals.py` | Active: bootstrap 95% CIs |
| `evaluation/report.py` | Active: D3 metrics aggregator CLI |
