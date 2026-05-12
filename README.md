# PolicyChecker — AI Policy Formalization System
 
An agentic LangGraph pipeline that extracts, classifies, and formalizes institutional
policy rules from PDF documents into validatable SHACL shapes.
 
> **Master's Thesis — Asian Institute of Technology (AIT), 2026**
 
---
 
## Table of Contents
 
1. [Project Structure](#1-project-structure)
2. [Pipeline Stages](#2-pipeline-stages)
3. [Local Environment Setup](#3-local-environment-setup)
4. [Dev Container Setup](#4-dev-container-setup)
5. [Running the Pipeline](#5-running-the-pipeline)
6. [Compliance Dashboard (Web UI)](#6-compliance-dashboard-web-ui)
7. [Running Evaluation](#7-running-evaluation)
---
 
## 1. Project Structure
 
```
.
├── data/                                   # All data files — input, reference, output
│   ├── institutional_policy/
│   │   └── AIT/                            # Source policy PDFs (pipeline input)
│   │       ├── AA-4-1-1 Academic Integrity...pdf
│   │       ├── FB-6-1-1 Credit Policy...pdf
│   │       ├── FS-1-1-1 Campus Accommodation...pdf
│   │       ├── PA-2-1-2 Ethical Behavior...pdf
│   │       └── Student-Handbook_August-2021.pdf
│   ├── shacl/
│   │   ├── ontology/
│   │   │   └── ait_policy_ontology.ttl     # AIT domain ontology (vocabulary definitions)
│   │   ├── shapes/
│   │   │   └── ait_policy_shapes.ttl       # 96 gold-standard SHACL shapes (hand-curated)
│   │   └── test_data/
│   │       └── tdd_test_data_fixed.ttl     # TDD test entities (Pos/Neg per rule)
│   ├── cache/                              # LLM response cache — gitignored
│   │   └── llm_cache.db
│   └── output/                             # Pipeline run artifacts — gitignored
│       └── ait/
│           ├── classified_rules.json       # Step 2 output
│           ├── fol_formulas.json           # Step 3 output
│           ├── shapes_generated.ttl        # Step 4 output
│           ├── validation_results.json     # Step 5 output
│           └── pipeline_report.json        # Step 6 final report
│
├── models/                                 # LangGraph agent (pipeline orchestrator)
│   └── langgraph_agent/
│       ├── state.py                        # Shared PipelineState (TypedDict)
│       ├── graph.py                        # Pipeline graph assembly (StateGraph)
│       ├── llm.py                          # Ollama LLM configuration
│       ├── run.py                          # CLI entry point
│       ├── _stubs.py                       # Fallback stubs for missing nodes
│       ├── edges/
│       │   └── route_classify.py           # Conditional routing after classification
│       └── nodes/                          # One file per pipeline stage
│           ├── extract.py                  # Step 1: PDF → sentences
│           ├── prefilter.py                # Step 2a: heuristic filter
│           ├── classify.py                 # Step 2b: LLM classification (O/P/F)
│           ├── reclassify.py               # Step 2c: second-opinion pass
│           ├── fol.py                      # Step 3: FOL formalization
│           ├── shacl.py                    # Step 4a: FOL → SHACL shapes
│           ├── direct_shacl.py             # Step 4b: NL → SHACL fallback
│           ├── validate.py                 # Step 5: pyshacl validation
│           └── report.py                   # Step 6: structured report
│
├── src/
│   └── policy_checker/                     # Main Python package
│       ├── __init__.py                     # Defines PROJECT_ROOT
│       ├── core/
│       │   ├── llm_cache.py                # SQLite-backed LLM response cache
│       │   ├── mcp_server.py               # JSON-RPC MCP server (5 tools)
│       │   └── prefilter.py                # Heuristic filter logic
│       ├── database/
│       │   ├── connection.py               # PostgreSQL connection handler
│       │   ├── rdf_converter.py            # SQL rows → RDF triples (data graph)
│       │   ├── schema.sql                  # Database schema
│       │   └── seed.py                     # Seed test student records
│       ├── evaluation/
│       │   ├── align.py                    # M1: pipeline vs gold-standard alignment
│       │   ├── per_rule_eval.py            # M4: per-rule pyshacl correctness
│       │   └── report.py                   # M1–M5 thesis metrics aggregator
│       └── web/
│           ├── app.py                      # FastAPI compliance dashboard (port 8000)
│           ├── static/                     # CSS + JS
│           └── templates/
│               └── index.html              # Dashboard UI
│
├── logs/                                   # Runtime logs — gitignored
├── dev-setup.sh                            # One-time setup script
├── docker-compose.yml                      # Dev + PostgreSQL services
├── dockerfile                              # Dev container image
├── pyproject.toml                          # Project config + dependencies
├── uv.lock                                 # Pinned dependency versions
├── .env                                    # Local secrets — never committed
└── .env.example                            # Environment variable template
```
 
### Key concepts
 
| Folder | Purpose |
|---|---|
| `data/` | Everything that flows IN or comes OUT of the pipeline |
| `data/shacl/` | SHACL reference files used by evaluation and TDD |
| `models/langgraph_agent/` | The AI agent that orchestrates the pipeline |
| `src/policy_checker/` | Shared utilities, database, evaluation, web UI |
 
---
 
## 2. Pipeline Stages
 
The pipeline runs as a LangGraph state machine. Each stage passes its output
to the next via a shared `PipelineState` object.
 
```
PDFs
 │
 ▼
Step 1 ── extract.py ──────────────────────────────────────────────────────
          Opens all PDFs with pdfplumber
          Splits text into sentences
          Filters out headers/footers
          Output: extracted_sentences[] (1,565 sentences)
          File written: none (stays in memory)
 │
 ▼
Step 2a ── prefilter.py ────────────────────────────────────────────────────
           Quick keyword scan — no LLM involved
           Keeps sentences with deontic markers:
             must / shall / required  → obligation candidate
             may / permitted          → permission candidate
             must not / cannot        → prohibition candidate
           Also disambiguates epistemic "may" vs deontic "may"
           Output: candidates[] (~450 sentences)
           File written: none
 │
 ▼
Step 2b ── classify.py ─────────────────────────────────────────────────────
           Sends each candidate to Mistral AI:
             "Is this a policy rule?"
             "If yes, is it Obligation / Permission / Prohibition?"
           Returns confidence score per classification
           Output: rules[]          (confidence ≥ 0.6 → confident)
                   uncertain_rules[] (confidence 0.4–0.6 → needs review)
           File written: data/output/ait/classified_rules.json
 │
 ├─ confident ──────────────────────────────────────────────────── Step 3
 │
 └─ uncertain ──────────────────────────────────────────────────────────────
    Step 2c ── reclassify.py
               Second-opinion pass using a configurable secondary model
               Adds few-shot examples to prompt for better accuracy
               Promotes uncertain rules to rules[] or discards them
               File written: updates classified_rules.json
               └──────────────────────────────────────────────── Step 3
 │
 ▼
Step 3 ── fol.py ───────────────────────────────────────────────────────────
          Converts each rule to First-Order Logic format
          Asks Mistral to produce:
            deontic_formula:  O(payFee(student))
            fol_expansion:    ∀x Student(x) → pay(x, fees)
            predicates:       [Student, pay, fees]
          Has placeholder-rejection retry:
            if Mistral returns O(Action(x)) → retries with stricter prompt
          Output: fol_formulas[]  (success)
                  fol_failed[]    (failed formalization → goes to Step 4b)
          File written: data/output/ait/fol_formulas.json
 │
 ├─ fol_formulas[] ─────────────────────────────────────────────────────────
 │  Step 4a ── shacl.py
 │             Translates FOL formula → SHACL NodeShape
 │             Mapping rules:
 │               O(φ) → sh:minCount 1   (must exist)
 │               P(φ) → sh:minCount 0   (may exist)
 │               F(φ) → sh:maxCount 0   (must not exist)
 │             Output: shacl_shapes[] (appended)
 │             File written: data/output/ait/shapes_generated.ttl
 │
 └─ fol_failed[] ───────────────────────────────────────────────────────────
    Step 4b ── direct_shacl.py
               Fallback: skips FOL, converts rule text → SHACL directly
               Has syntax repair loop: invalid SHACL → fix and retry
               Output: shacl_shapes[] (appended to Step 4a output)
               File written: updates shapes_generated.ttl
 │
 ▼ (both branches converge)
Step 5 ── validate.py ──────────────────────────────────────────────────────
          Runs pyshacl engine
          Merges generated shapes with gold-standard shapes
          Validates against TDD test data (Pos/Neg entities per rule)
          Finds which test entities violate which rules
          Output: validation_results{}
          File written: data/output/ait/validation_results.json
 │
 ▼
Step 6 ── report.py ────────────────────────────────────────────────────────
          Collects all stats from every stage
          Builds final summary with:
            sentences / candidates / rules / shapes / violations counts
            severity breakdown (Violation / Info)
            top-5 triggered shapes
            environment metadata (model, seed, version, git sha)
          File written: data/output/ait/pipeline_report.json
```
 
### Output files summary
 
| File | Written by | Contents |
|---|---|---|
| `classified_rules.json` | Step 2b + 2c | All sentences — deontic type, confidence, rule ID |
| `fol_formulas.json` | Step 3 | FOL formula, deontic formula, predicates per rule |
| `shapes_generated.ttl` | Step 4a + 4b | All generated SHACL shapes in Turtle syntax |
| `validation_results.json` | Step 5 | Which entities violated which shapes |
| `pipeline_report.json` | Step 6 | Full run summary with stats and environment info |
 
---
 
## 3. Local Environment Setup
 
Use this if you want to run the project directly on your machine without Docker.
 
### Prerequisites
 
| Tool | Version | Install |
|---|---|---|
| Python | 3.10+ | [python.org](https://python.org) |
| uv | latest | see below |
| Ollama | latest | [ollama.com/download](https://ollama.com/download) |
| PostgreSQL | 15+ | [postgresql.org](https://postgresql.org) — optional, see note |
 
> **Note:** PostgreSQL is only needed if you use `src/policy_checker/database/` to load
> student entity data. The core pipeline (`models/langgraph_agent/`) runs without it.
 
### Step 1 — Install uv
 
**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
 
# Add to PATH (current session):
$env:Path = "C:\Users\<you>\.local\bin;$env:Path"
 
# Add to PATH permanently:
[Environment]::SetEnvironmentVariable(
    "Path",
    "C:\Users\<you>\.local\bin;" + [Environment]::GetEnvironmentVariable("Path", "User"),
    "User"
)
```
 
**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
 
### Step 2 — Clone the repo
 
```bash
git clone <repo-url>
cd compliance-checker
```
 
### Step 3 — Install dependencies
 
```bash
uv python install    # installs Python from .python-version
uv sync              # installs all packages from pyproject.toml
```
 
### Step 4 — Set up environment
 
```bash
cp .env.example .env
```
 
Open `.env` and set these minimum required values:
 
```bash
OLLAMA_HOST=http://localhost:11434    # local Ollama
OLLAMA_MODEL=mistral                  # must match what you pulled
OLLAMA_SEED=42                        # fixed seed for reproducibility
PIPELINE_VERSION=2.1-hints            # bump to invalidate LLM cache after prompt changes
POSTGRES_HOST=localhost               # local PostgreSQL (optional)
```
 
To clear the LLM cache after changing prompts:
```bash
# Option A — bump PIPELINE_VERSION in .env
# Option B — delete cache file:
rm data/cache/llm_cache.db
```
 
### Step 5 — Install and start Ollama
 
Ollama must be running **before** the pipeline starts.
 
```bash
# Install from https://ollama.com/download
# Then pull the model (one-time, ~4GB download):
ollama pull mistral
```
 
**Windows:** Ollama runs automatically as a background service after install.
 
**macOS / Linux:** Start it manually:
```bash
ollama serve
```
 
Verify Ollama is running:
```bash
curl http://localhost:11434
# → Ollama is running ✓
 
ollama list
# → mistral:latest   4.4GB ✓
```
 
Check GPU is being used (faster inference):
```bash
ollama ps
# → mistral:latest   GPU 100%  ← good
# → mistral:latest   CPU 100%  ← slow, check GPU drivers
```
 
### Step 6 — Seed the database (optional)
 
Only needed if using the compliance dashboard database features:
 
```bash
uv run python -m policy_checker.database.seed
```
 
### Step 7 — Run the pipeline
 
```bash
uv run policy-checker --source ait --verbose
```
 
---
 
## 4. Dev Container Setup
 
Use this for a consistent, team-ready environment using Docker.
 
### Prerequisites
 
| Tool | Install |
|---|---|
| Docker Desktop | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| VS Code | [code.visualstudio.com](https://code.visualstudio.com/) |
| Dev Containers extension | VS Code Extensions: `ms-vscode-remote.remote-containers` |
| Ollama | [ollama.com/download](https://ollama.com/download) — installed on your machine, **not** in Docker |
 
### Why Ollama runs on your machine, not in Docker
 
Ollama automatically detects and uses your GPU when installed natively.
Running it inside Docker requires complex GPU passthrough that varies by OS and
GPU vendor. Installing it directly on your machine is simpler and faster for everyone.
 
### Step 1 — Install Ollama on your machine
 
Download and install from [ollama.com/download](https://ollama.com/download).
 
Pull the model (one-time, ~4GB):
```bash
ollama pull mistral
```
 
Verify:
```bash
curl http://localhost:11434
# → Ollama is running ✓
 
ollama list
# → mistral:latest   4.4GB ✓
```
 
### Step 2 — Clone the repo
 
```bash
git clone <repo-url>
cd compliance-checker
```
 
### Step 3 — Set up environment
 
```bash
cp .env.example .env
```
 
Open `.env` and set these minimum required values:
 
```bash
# Inside Dev Container, use host.docker.internal not localhost
OLLAMA_HOST=http://host.docker.internal:11434
 
OLLAMA_MODEL=mistral                  # must match what you pulled
OLLAMA_SEED=42                        # fixed seed for reproducibility
PIPELINE_VERSION=2.1-hints            # bump to invalidate LLM cache after prompt changes
 
# PostgreSQL runs as a Docker service named "postgres"
POSTGRES_HOST=postgres
```
 
To clear the LLM cache after changing prompts:
```bash
# Option A — bump PIPELINE_VERSION in .env
# Option B — delete cache file:
rm data/cache/llm_cache.db
```
 
### Step 4 — Open in Dev Container
 
1. Open VS Code
2. `File → Open Folder` → select the project folder
3. VS Code shows: *"Folder contains a Dev Container config"*
4. Click **Reopen in Container**
5. Wait for container to build (~2–3 minutes on first run)
### Step 5 — Run dev-setup.sh
 
Inside the VS Code terminal (you are now inside the container):
 
```bash
bash dev-setup.sh
```
 
This will:
- Fix volume permissions
- Load `.env`
- Install Python and all dependencies via `uv sync`
- Install CLI tab completion
### Step 6 — Verify everything works
 
```bash
# Ollama reachable from container
curl http://host.docker.internal:11434
# → Ollama is running ✓
 
# Environment variable is correct
echo $OLLAMA_HOST
# → http://host.docker.internal:11434 ✓
 
# Package imports work
uv run python -c "from policy_checker import PROJECT_ROOT; print(PROJECT_ROOT)"
# → /Projects/compliance-checker ✓
```
 
### Step 7 — Run the pipeline
 
```bash
uv run policy-checker --source ait --verbose
```
 
### Subsequent runs (every day after first setup)
 
```bash
# Windows: Ollama runs automatically — no action needed
# macOS/Linux: make sure ollama serve is running
 
# Start Docker services if stopped
docker compose up -d
 
# Open VS Code → Reopen in Container
# Run pipeline
uv run policy-checker --source ait --verbose
```
 
---
 
## 5. Running the Pipeline
 
 
### Basic run
 
```bash
uv run policy-checker --source ait
```
 
### Verbose — shows per-step stats
 
```bash
uv run policy-checker --source ait --verbose
```
 
### Ablation studies
 
Run these to measure the contribution of individual pipeline components
(used for thesis experiments):
 
```bash
uv run policy-checker --source ait --ablation no-hints
uv run policy-checker --source ait --ablation no-prefilter
uv run policy-checker --source ait --ablation no-reclassify
uv run policy-checker --source ait --ablation no-fallback
uv run policy-checker --source ait --ablation no-fol-retry
uv run policy-checker --source ait --ablation no-may-disambig
```
 
| Flag | What it disables |
|---|---|
| `no-prefilter` | Skips heuristic filter — all sentences go to classifier |
| `no-hints` | Strips prefilter hints from classifier prompt |
| `no-reclassify` | Skips second-opinion pass for uncertain rules |
| `no-fallback` | Skips direct NL→SHACL fallback (Step 4b) |
| `no-fol-retry` | Disables placeholder rejection retry in FOL step |
| `no-may-disambig` | Skips epistemic "may" disambiguation |
 
Output is isolated to `data/output/ait_<ablation>/` for side-by-side comparison.
 
### Expected terminal output
 
```
============================================================
Environment:
  Model:     mistral
  Seed:      42
  Version:   2.1-hints
  Ablation:  baseline
============================================================
 
  >> Step 1  - PDF Extraction          {'sentences': 1565}
  >> Step 2a - Heuristic Pre-filter    {'candidates': 450}
  >> Step 2b - LLM Classification      {'rules': 440}
  >> Step 2c - Second-Opinion          {'rules': 440}
  >> Step 3  - FOL Formalization       {'fol_ok': 371, 'fol_fail': 69}
  >> Step 4a - SHACL Generation        {'shapes': 371}
  >> Step 4b - SHACL NL Fallback       {'shapes': 69}
  >> Step 5  - SHACL Validation
  >> Step 6  - Report
 
[DONE] Pipeline complete - report: data/output/ait/pipeline_report.json
```
 
### MCP server (optional)
 
Exposes the pipeline as tools for MCP-compatible AI clients:
 
```bash
uv run policy-mcp    # stdio MCP mode — connect from Claude or other clients
```
 
Available tools: `verify_rule`, `check_status`, `list_rules`, `get_metrics`, `run_pipeline`.
 
---
 
## 6. Compliance Dashboard (Web UI)
 
An interactive web dashboard for browsing pipeline results and running live
SHACL validation against custom RDF data.
 
> **Important:** Run the pipeline at least once before starting the dashboard.
> The dashboard reads from `data/output/ait/` which is populated by the pipeline.
 
### Start the dashboard
 
```bash
uv run uvicorn policy_checker.web.app:app --host 0.0.0.0 --port 8000 --reload
```
 
Then open [http://localhost:8000](http://localhost:8000) in your browser.
 
If running inside Dev Container, port 8000 is forwarded automatically.
Open [http://localhost:8000](http://localhost:8000) from your Windows browser.
 
### Dashboard features
 
| Feature | Description |
|---|---|
| **Pipeline Stats** | Summary of extraction, classification, and shape generation metrics from the latest run |
| **Rule Browser** | Browse and search all classified rules — filter by type (obligation / permission / prohibition) |
| **Rule Detail** | Click any rule to see its original text, FOL formula, and generated SHACL shape side by side |
| **Compliance Check** | Paste RDF data in Turtle format and run live pyshacl validation against pipeline shapes |
| **Violation Report** | Severity-coded violations showing affected entities, source shapes, and violation messages |
 
### What the dashboard reads
 
| Data source | Used for |
|---|---|
| `data/output/ait/pipeline_report.json` | Pipeline stats on the home page |
| `data/output/ait/classified_rules.json` | Rule browser |
| `data/output/ait/fol_formulas.json` | FOL formula in rule detail view |
| `data/output/ait/shapes_generated.ttl` | SHACL shape in rule detail + live validation |
| `data/shacl/test_data/tdd_test_data_fixed.ttl` | Sample RDF data for compliance check |
| `data/shacl/ontology/ait_policy_ontology.ttl` | Domain ontology loaded during validation |
 
---
 
## 7. Running Evaluation
 
Run evaluation scripts **after** the pipeline completes to measure accuracy
against the 96 gold-standard shapes in `data/shacl/shapes/ait_policy_shapes.ttl`.
 
```bash
# M1 — extraction coverage
uv run python -m policy_checker.evaluation.align
 
# M4 — per-rule shape correctness
uv run python -m policy_checker.evaluation.per_rule_eval
 
# M1–M5 — full thesis metrics summary
uv run python -m policy_checker.evaluation.report
 
# Markdown table (for thesis document)
uv run python -m policy_checker.evaluation.report --md
 
# Save results to JSON
uv run python -m policy_checker.evaluation.report --save
```
 
### Metrics reference
 
| Metric | Definition |
|---|---|
| M1 | Extraction coverage — gold rules with an aligned pipeline rule (cosine ≥ 0.65) |
| M2 | Classification accuracy — correct deontic type (O/P/F) assignment |
| M3 | FOL quality — formulas with semantic (non-placeholder) predicates |
| M4 | Shape correctness — per-rule precision/recall against Pos/Neg test entities |
| M5 | Reproducibility — identical output across clean-cache runs with fixed seed |
 
### Evaluation output files
 
| File | Written by | Contents |
|---|---|---|
| `data/output/ait/gold_alignment.json` | `align.py` | M1 alignment results — matched, missed, false positives |
| `data/output/ait/per_rule_eval.json` | `per_rule_eval.py` | M4 per-rule verdicts (PASS/FAIL, too_strict/too_permissive) |
| `data/output/ait/thesis_metrics.json` | `report.py --save` | M1–M5 summary for thesis |
