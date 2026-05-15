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
8. [API Deployment](#8-api-deployment)
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
├── .gitignore                              # Files that git should never track
├── .gitattribute                           # Enforce LF line endings for shell scripts across all OS
├── dev-setup.sh                            # One-time setup script
├── docker-compose.yml                      # Dev + PostgreSQL services
├── dockerfile                              # Dev container image
├── pyproject.toml                          # Project config + dependencies
├── uv.lock                                 # Pinned dependency versions
├── .env                                    # Local secrets — never committed
└── .env.example                            # Environment variable template
```
 
## 2. Pipeline Stages
 
The pipeline runs as a LangGraph state machine. Each stage passes its output
to the next via a shared `PipelineState` object.
 
| Step | File | What it does |
|---|---|---|
| **Step 1** | `extract.py` | Opens all PDFs with pdfplumber, splits text into sentences, filters headers/footers |
| **Step 2a** | `prefilter.py` | Quick keyword scan — no LLM. Keeps sentences with deontic markers (must/shall/may/cannot). Disambiguates epistemic vs deontic "may" |
| **Step 2b** | `classify.py` | Asks Mistral AI: "Is this a rule? If yes, is it O/P/F?" Returns confidence score per classification |
| **Step 2c** | `reclassify.py` | Second-opinion pass for uncertain rules only. Adds few-shot examples to prompt. Promotes uncertain → rules or discards. **Skipped if no uncertain rules.** |
| **Step 3** | `fol.py` | Converts each rule to First-Order Logic. Asks Mistral to produce deontic formula, FOL expansion, predicates. Has placeholder-rejection retry. |
| **Step 4a** | `shacl.py` | Translates FOL → SHACL NodeShape. Mapping: O→minCount 1, P→minCount 0, F→maxCount 0 |
| **Step 4b** | `direct_shacl.py` | Fallback for FOL failures. Converts rule text → SHACL directly, skipping FOL. Has syntax repair loop. **Skipped if no FOL failures.** |
| **Step 5** | `validate.py` | Runs pyshacl engine. Merges generated shapes with gold-standard shapes. Validates against TDD test data. |
| **Step 6** | `report.py` | Collects all stats from every stage. Builds final summary with counts, severity breakdown, top-5 shapes, environment metadata. |
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
 
| Tool | Version |
|---|---|
| Python | 3.10+ |
| uv | latest |
| Ollama | latest |
| PostgreSQL | 15+ |
 
> **Note:** PostgreSQL is only needed if you use `src/policy_checker/database/` to load
> student entity data. The core pipeline (`models/langgraph_agent/`) runs without it.
  
### Step 1 — Clone the repo
 
```bash
git clone <repo-url>
cd compliance-checker
```
 
### Step 2 — Install dependencies
 
```bash
uv python install    # installs Python from .python-version
uv sync              # installs all packages from pyproject.toml
```
 
### Step 3 — Set up environment
 
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
 
### Step 4 — Install and start Ollama
 
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
 
### Step 5 — Run the pipeline
 
```bash
uv run policy-checker --source ait --verbose
```

### Step 6 — Seed the database (optional)
 
Only needed if using the compliance dashboard database features:
 
```bash
uv run python -m policy_checker.database.seed
```
 
---
 
## 4. Dev Container Setup
 
Use this for a consistent, team-ready environment using Docker.
 
### Step 1 — Install Ollama on your machine
 
Download and install from [ollama.com/download](https://ollama.com/download).
 
Pull the model (one-time, ~4GB):
```bash
ollama pull mistral
ollaa serve
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
 
POSTGRES_HOST=host.docker.internal
```
 
### Step 4 — Open in Dev Container
 
1. Open VS Code
2. `File → Open Folder` → select the project folder
3. `Ctrl + Shift + P` → select rebuild and reopen in container
4. Select docker outside docker

### Step 5 — Run dev-setup.sh
 
Inside the VS Code terminal (you are now inside the container):
 
```bash
bash dev-setup.sh
```
 
This will:
- Load `.env`
- Install uv and Python and all dependencies via `uv sync`
 
### Step 6 — Run the pipeline
 
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

### Step 6 — Seed the database (optional)
 
Only needed if using the compliance dashboard database features:
 
```bash
uv run python -m policy_checker.database.seed
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
uv run python -m uvicorn policy_checker.web.app:app --host 0.0.0.0 --port 8000 --reload
```
 
Then open [http://localhost:8000](http://localhost:8000) in your browser.
 
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

## 8. API Deployment
Status - In Development Progress

PolicyChecker exposes a REST API for integration with the AITGPT platform.

When a user logs into AITGPT, the platform calls PolicyChecker to check
whether that student is compliant with AIT institutional policies.
PolicyChecker validates the student profile against generated SHACL shapes
and returns any broken rules.

### How It Works

```
AITGPT (caller)                    PolicyChecker (this project)
───────────────                    ────────────────────────────
User logs in
        ↓
POST /check_compliance     →       validates student against SHACL shapes
{ student_profile: {...} }         returns violations
        ←
{ compliant: false,
  broken_rules: [...] }
        ↓
Show notification icon
User clicks → sees broken rules
```

### Available Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/validate` | POST | Validate RDF Turtle data against SHACL shapes — returns violations |
| `/api/rules` | GET | List all classified rules with filtering and pagination |
| `/api/rules/{rule_id}` | GET | Get single rule with FOL formula and SHACL shape |
| `/api/stats` | GET | Pipeline summary statistics |
| `/api/db-status` | GET | Check PostgreSQL connection and entity count |
| `/api/db-entities` | GET | List all entities in database |
| `/api/load-from-db` | POST | Convert database entities to RDF Turtle |

