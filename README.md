# PolicyChecker — AI Policy Formalization System

An agentic LangGraph pipeline for extracting, classifying, and formalizing institutional
policy rules from PDF documents into validatable SHACL shapes. Target use: academic
research on automated compliance verification over institutional corpora.

> **Master's Thesis — Asian Institute of Technology (AIT), 2026**

## 🎯 What it does

Given a folder of policy PDFs, PolicyChecker runs a nine-stage pipeline:

1. **Extract** — parses PDFs into sentences (`pdfplumber`, optional spaCy sentencizer)
2. **Prefilter** — heuristically filters non-rule content using deontic markers,
   section-aware weights (Brodie et al., 2006), Searle-style speech-act
   classification, and epistemic vs. deontic "may" disambiguation
3. **Classify** — uses a local LLM (Ollama/Mistral) to label each candidate as
   *obligation*, *permission*, or *prohibition*, enriched with prefilter hints
   (deontic strength, speech act, section context)
4. **Reclassify** — second-opinion pass for uncertain classifications using a
   configurable secondary model
5. **Formalize** — converts rules to First-Order Logic (FOL) formulas using deontic
   operators `O(φ)`, `P(φ)`, `F(φ)`, with placeholder rejection and retry
6. **Generate (FOL-mediated)** — translates FOL into SHACL `NodeShape`s with
   confidence-weighted severity, `sh:targetSubjectsOf` fallback, and named property shapes
7. **Generate (NL fallback)** — direct natural-language-to-SHACL for rules that
   resist FOL formalization, with syntax repair loop
8. **Validate** — merges pipeline shapes with gold-standard shapes and runs `pyshacl`
   against TDD test data, with false-positive triage
9. **Report** — generates a structured JSON report with pipeline stats, violation
   triage, environment metadata, and severity breakdown

The pipeline is orchestrated as a LangGraph state machine with conditional routing,
parallel fallback branches, and full ablation support for research measurement.

## 📊 Current pipeline output (AIT corpus)

Running the pipeline on the Asian Institute of Technology policy corpus
(`institutional_policy/AIT/`, 1,663 extracted sentences):

| Stage | Output |
|---|---:|
| Sentences extracted | 1,663 |
| Candidates after prefilter | 461 |
| Rules classified (confident) | 443 |
| FOL formulas generated | 353 (79.7% parse success) |
| FOL formulas failed | 90 (routed to NL fallback) |
| SHACL shapes produced | 443 (401 syntactically valid, 90.5%) |
| — FOL-mediated | 353 |
| — Direct NL fallback | 90 |
| Rule-type distribution | 326 obligations · 66 prohibitions · 50 permissions · 1 exemption |
| Validation violations | 11,522 |
| Pipeline errors | 12 (all override-relation warnings) |

## 📈 Evaluation

The project includes a gold-standard evaluation harness (`evaluation/`) that aligns
pipeline-generated rules to 96 curated SHACL shapes (`shacl/shapes/ait_policy_shapes.ttl`)
using multi-signal alignment (embedding similarity, TF-IDF, fuzzy matching) and
evaluates each pipeline shape against its corresponding `Pos_GSxxx` / `Neg_GSxxx`
test entities.

| Metric | Definition | Current |
|---|---|---:|
| **M1** Extraction coverage | Gold rules with aligned pipeline rule (cosine ≥ 0.65) | **85.4%** (82/96), 95% CI [78.1%, 91.7%] |
| **M2** Classification accuracy | Aligned rules with correct deontic type | **85.4%** (70/82), 95% CI [76.8%, 92.7%] |
| **M3** FOL quality | FOL formulas with semantic predicates | **100%** (353/353), 95% CI [100%, 100%] |
| **M4** Shape correctness (F1) | Per-rule precision/recall against Pos/Neg test entities | **F1 = 0.866** (P = 0.977, R = 0.778), 95% CI [0.791, 0.932] |
| **M5** Output stability | Identical SHACL output across clean-cache runs with fixed seed | **100%** on the frozen 10-run snapshot (hash `520a0fa9`) |

> [!NOTE]
> **M4 analysis:** Of 69 evaluated shapes, 42 are correct, 1 is `too_strict`, 12 are `too_permissive`, 8 are `inverted` (deontic-type mismatch), and 6 are skipped. Precision is 0.977 (when the pipeline flags a violation, it is right 97.7% of the time); recall is 0.778. The 8 inverted cases trace to upstream prohibition misclassification rather than vocabulary issues. The Corpus Adapter pattern (configuration-driven vocabulary injection) was the key intervention that moved M4 from F1 = 0.000 to F1 = 0.866.

> [!NOTE]
> **M3 analysis:** The 100% rate reflects the post-fix pipeline with retry-and-backfill of FOL `predicates.action` from the `deontic_formula` field. Earlier versions reported 29.8% (initial measurement bug, treating the empty `predicates.action` field as the only signal) and 68.7% (after the measurement fix). The current 100% is on the 353 FOL formulas that parsed successfully; the 90 formulas that failed parse are handled by the direct NL → SHACL fallback path and are not counted in M3.
>
> **M5 framing:** M5 measures *output stability* on a fixed-seed, clean-cache snapshot — i.e., whether the pipeline produces hash-identical SHACL shapes when re-run with the same seed and prompt version. This is distinct from *semantic correctness* (which is measured by M4). The current `evaluation/report.py` flag `m5_reproducible` may report `false` when the LLM cache is invalidated between runs; the 100% figure applies to the snapshot run reported in §5.1 of the thesis.
>
> **External Validation:** The pipeline's classification was also validated against the LexDeMod lease-contract benchmark (N=200). It achieved a Macro F1 of **0.370**, with strong obligation detection (F1=0.569) but degraded permission detection (F1=0.038) due to cross-domain vocabulary mismatch ("shall be entitled" vs "may").

### Running the evaluation

```bash
python -m evaluation.align          # M1 extraction coverage → gold_alignment.json
python -m evaluation.per_rule_eval  # M4 shape correctness → per_rule_eval.json
python -m evaluation.report         # All metrics M1–M5 → console summary
python -m evaluation.report --md    # Markdown table for thesis
python -m evaluation.report --save  # Save thesis_metrics.json
```

## 🧪 Ablation studies

### Large-Scale Prompt Ablation (N=100)

A controlled experiment tested four prompt variants on 100 corpus-wide classification disagreements:
- **V0 Baseline** (production prompt): 85.0% agreement, $\kappa$ = 0.101 (Optimal)
- **V1 Few-shot**: 83.0% agreement
- **V2 Negative instructions**: 81.0% agreement
- **V3 Combined**: 82.0% agreement

The baseline zero-shot prompt is empirically validated as optimal. The disagreements are dominated by asymmetric false negatives (LLM misses heuristic-labelled rules; never over-generates), confirming the gap reflects a schema-level annotation difference rather than prompt quality.

### Pipeline Component Ablations

The pipeline supports **7 component-level ablations** for measuring the contribution
of each enhancement:

| Ablation | Flag | What it disables |
|----------|------|------------------|
| Baseline | `baseline` | Full pipeline (control) |
| No prefilter | `no-prefilter` | Skips heuristic filter, all sentences pass |
| No hints | `no-hints` | Strips prefilter hints from classifier |
| No reclassify | `no-reclassify` | Skips second-opinion pass |
| No fallback | `no-fallback` | Skips direct NL→SHACL fallback |
| No FOL retry | `no-fol-retry` | Disables placeholder rejection retry |
| No may disambig | `no-may-disambig` | Skips epistemic "may" filter |

```bash
python -m langgraph_agent.run --source ait --ablation no-hints
python -m langgraph_agent.run --source ait --ablation no-reclassify
python -m langgraph_agent.run --source ait --ablation no-fallback
```

Output is isolated to `output/ait_<ablation>/` for side-by-side comparison.

## 🗂️ Project structure

```
Automatate_Compliance_Checking-v2/
├── core/                     # PreFilter, LLM cache (SQLite), MCP server
│   ├── prefilter.py          # Heuristic filter (600+ lines, may disambiguation)
│   ├── llm_cache.py          # SQLite cache with prompt versioning
│   └── mcp_server.py         # JSON-RPC MCP compatibility layer
├── db/                       # PostgreSQL data layer
│   ├── connection.py         # Connection manager (psycopg2)
│   ├── schema.sql            # Relational table definitions (students, fees, etc.)
│   ├── seed.py               # Populate DB with realistic AIT demo data
│   └── rdf_converter.py      # Relational DB → Turtle RDF converter
├── evaluation/               # Gold-standard alignment & thesis metrics
│   ├── align.py              # Multi-signal GS ↔ AIT alignment (M1)
│   ├── per_rule_eval.py      # Per-rule pyshacl evaluation (M4)
│   └── report.py             # M1–M5 thesis metrics aggregator
├── institutional_policy/     # Source PDFs (AIT corpus)
├── langgraph_agent/          # Pipeline orchestration
│   ├── nodes/                # 9 processing nodes
│   │   ├── extract.py        # PDF → sentences (pdfplumber + spaCy)
│   │   ├── prefilter.py      # Heuristic pre-filter wrapper
│   │   ├── classify.py       # LLM classification with hint injection
│   │   ├── reclassify.py     # Second-opinion reclassification
│   │   ├── fol.py            # FOL formalization with retry
│   │   ├── shacl.py          # FOL → SHACL (named shapes, severity tiers)
│   │   ├── direct_shacl.py   # NL → SHACL fallback with repair loop
│   │   ├── validate.py       # pyshacl validation with shape merging
│   │   └── report.py         # Structured report with env capture
│   ├── edges/                # Conditional routing (route_classify)
│   ├── graph.py              # Graph assembly (StateGraph)
│   ├── state.py              # Typed state schema (PipelineState)
│   ├── llm.py                # Ollama LLM configuration (seed, top_k)
│   └── run.py                # CLI with --ablation support
├── shacl/                    # Authoritative shapes, ontology, TDD test data
│   ├── shapes/               # 96 curated gold-standard shapes
│   ├── ontology/             # Domain ontology (Person, Student, Faculty, …)
│   └── test_data/            # 180 Pos/Neg test entities per rule
├── output/                   # Pipeline reports & intermediate artifacts
├── web/                     # Compliance Dashboard (FastAPI + HTML)
│   ├── app.py                # FastAPI backend with pyshacl validation
│   ├── templates/index.html  # Dashboard UI
│   └── static/               # CSS + JS
├── tests/                    # Pytest suite (121 tests)
│   ├── test_prefilter.py     # Core prefilter unit tests
│   ├── test_shacl_shapes.py  # Gold-standard SHACL shape validation
│   ├── test_may_disambiguation.py  # 45-sentence may eval set
│   ├── test_classify_hints.py      # Hint wiring & cache key tests
│   ├── test_align.py               # Alignment algorithm tests
│   ├── test_per_rule_eval.py       # Per-rule eval verdict tests
│   └── test_graph.py               # Graph structure tests
├── docker-compose.yml        # Postgres + App + optional GraphDB/Ollama
├── Dockerfile                # App container build
├── .env.example              # Environment configuration template
├── ARCHITECTURE.md           # Pipeline design & node walkthrough
└── POLICYCHECKER_ENHANCEMENT_PLAN.md   # Enhancement roadmap (completed)
```

## 🚀 Quick start

### 1. Dependencies

```bash
pip install -r requirements.txt
```

A local **Ollama** instance is required for LLM inference:

```bash
# macOS / Linux installer: https://ollama.com/download
ollama pull mistral
ollama serve   # leave running in a separate terminal
```

### 2. Environment

```bash
cp .env.example .env
```

Key settings (see `.env.example` for full list):

```bash
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=mistral
OLLAMA_SECOND_MODEL=mistral          # override with a different model for second-opinion
OLLAMA_SEED=42                       # required for reproducibility
PIPELINE_VERSION=2.1-final-defense    # bumped on any behavior-affecting change
```

### 3. Run the pipeline

```bash
python -m langgraph_agent.run --source ait --verbose
```

Outputs land in `output/ait/`:

- `pipeline_report.json` — summary stats, violation triage, and environment metadata
- `classified_rules.json` — all rules with deontic type and confidence
- `fol_formulas.json` — generated FOL formulas
- `shapes_generated.ttl` — pipeline-produced SHACL shapes
- `validation_results.json` — pyshacl output against test data

### 4. Run the tests

```bash
pytest                     # all 121 tests
pytest -m prefilter        # prefilter unit tests only
pytest -m shacl            # SHACL shape syntactic tests only
pytest tests/test_may_disambiguation.py  # May disambiguation eval set
```

## 🖥️ Compliance Dashboard (Demo)

An interactive web dashboard for demonstrating the practical application of the
generated SHACL shapes. Browse extracted rules, inspect FOL formulas and SHACL
shapes, load entity data from PostgreSQL, and visualize compliance violations
in real-time.

### Running the demo

```bash
# Option 1: Docker (recommended — starts Postgres + App together)
docker compose up -d
# Open http://localhost:8000

# Option 2: Local (requires Postgres already running)
pip install fastapi uvicorn jinja2 python-multipart
python web/app.py
```

### Features

| Feature | Description |
|---------|-------------|
| **Pipeline Stats** | Real-time display of extraction, classification, and shape generation metrics |
| **Rule Browser** | Search and filter 484 classified rules by type (obligation/prohibition/permission) |
| **Rule Detail** | Click any rule to see its text, FOL formula, and generated SHACL shape |
| **DB Entity Selector** | Select individual students, faculty, staff, and committees from the database |
| **Load from Database** | Convert selected DB entities to RDF Turtle with one click |
| **Compliance Check** | Submit RDF data (from DB or pasted) and run `pyshacl` validation |
| **Violation Report** | Entity-centric result cards with severity-coded violations and property details |

The dashboard loads pipeline outputs from `output/ait/` and validates against
all syntactically valid SHACL shapes. Invalid shape blocks (from the NL fallback)
are automatically skipped during parsing.

## 🗄️ Database Integration (PostgreSQL → RDF)

The dashboard supports loading entity data from a **PostgreSQL database** and
automatically converting it to RDF Turtle format for compliance validation. This
replaces the hardcoded sample data with live, editable data.

### Quick start with Docker

```bash
# Start PostgreSQL (and optionally the full stack)
docker compose up -d postgres

# Seed the database with demo entities (6 students, 3 faculty, 2 staff, 2 committees)
python -m db.seed

# Verify the data
python -m db.rdf_converter    # prints generated Turtle to stdout
```

To run the entire stack (Postgres + Web App):

```bash
docker compose up -d          # starts postgres + app
# Open http://localhost:8000
```

Optional services (GraphDB, Ollama) are available via profiles:

```bash
docker compose --profile graphdb up -d     # includes GraphDB
docker compose --profile ollama up -d      # includes Ollama (GPU)
```

### Without Docker

If you already have PostgreSQL running locally:

1. Set connection details in `.env`:
   ```env
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=ait_database
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=mysecretpassword
   ```

2. Seed the database:
   ```bash
   python -m db.seed          # create tables + insert demo data
   python -m db.seed --reset  # clear existing data first
   ```

### How it works

1. **Entity data** is stored in proper relational tables: `students`, `fee_records`,
   `accommodations`, `conduct_records`, `student_conduct`, `academic_records`,
   `faculty`, `staff`, and `committees`
2. The **`db.rdf_converter`** module queries these tables via `LEFT JOIN`s and
   maps relational fields to `ait:` ontology predicates (e.g., `payment_status = 'Paid'`
   → `ait:payFee true`)
3. The web dashboard's **"Load from Database"** button calls `/api/load-from-db`,
   which runs the converter and populates the Turtle editor
4. Users can **select specific entities** via checkboxes before loading
5. The converted RDF is validated against SHACL shapes as usual

### Database schema

```
students (PK: student_id)
  ├── fee_records        (FK → students, per-semester fees & payment status)
  ├── accommodations     (FK → students, dorm assignment & cleanliness flags)
  ├── conduct_records    (FK → students, incident log: cooking, noise, pet, cheating)
  ├── student_conduct    (FK → students, behavioral boolean flags)
  └── academic_records   (FK → students, registration & authorship flags)

faculty      (faculty_id, grading/disciplinary/disclosure flags)
staff        (staff_id, gifts/settlements/ethics flags)
committees   (committee_name, grievance/tribunal flags)
```

## ⚠️ Current limitations

Transparency about what the pipeline does *not* yet handle well:

- **Permission classification (50% type accuracy)** — the LLM struggles to distinguish
  normative permissions ("Students may request an extension") from factual descriptions
  ("Cultural differences may lead to misunderstanding"). Explicit-definition prompting
  improves accuracy from 0% to 70% on a 10-permission test set (p=0.023), but the
  challenge is fundamentally linguistic (deontic vs. epistemic modality).
- **M4 inverted cases (8/69)** — eight shapes have the wrong deontic constraint type
  (e.g., obligation encoded as prohibition). These trace to upstream deontic-type
  misclassification rather than vocabulary issues.
- **Single-annotator gold standard** — mitigated by intra-annotator κ=0.891 and
  multi-LLM Fleiss' κ=0.635, but no external human annotators were recruited.
- **Epistemic vs. deontic "may"** — disambiguation is implemented at the prefilter level
  with 80%+ accuracy on the eval set, but recall is not yet 100%.
- **Sentence boundary detection** — PDF extraction produces some cross-item
  contamination. An optional spaCy sentencizer is available via `EXTRACT_SPACY=1`.
- **Target-class inference** — fallback to `sh:targetSubjectsOf` for `Person`-class
  shapes reduces over-broadening but doesn't eliminate it entirely.

## 🔧 Additional tools

- **MCP server** (`core/mcp_server.py`) — exposes 5 tools over JSON-RPC for
  MCP-compatible clients:
  - `verify_rule` — classify a single text as policy rule
  - `check_status` — check Ollama availability
  - `list_rules` — browse classified rules from the latest run (filterable by type)
  - `get_metrics` — return M1–M5 thesis metrics
  - `run_pipeline` — trigger a full pipeline run with optional ablation

  ```bash
  python -m core.mcp_server --mcp          # stdio MCP mode
  python -m core.mcp_server                # interactive REPL
  ```

- **LLM cache** (`core/llm_cache.py`) — SQLite-backed deterministic cache for
  LLM responses. Cache keys include prompt version, so prompt edits invalidate
  stale entries automatically. Clear with:

  ```bash
  rm cache/llm_cache.db     # macOS/Linux
  Remove-Item cache\llm_cache.db   # Windows
  ```

## 📚 References

The pipeline design draws on:

- Goknil et al. (2024) — PAPEL: hierarchical filtering for policy extraction
- Brodie et al. (2006) — Section-aware classification for legal documents
- Searle (1969) — Speech Act Theory (directive / commissive / prohibitive / …)
- Governatori & Rotolo (2010) — Permission-as-exception in deontic logic
  (`deontic:overrides` in the ontology)

## 📝 License

Academic research project — AIT Master's Thesis.
