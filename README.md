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
6. [API Deployment](#6-api-deployment)

---

## 1. Project Structure

```
.
├── config/                                 # Corpus configuration files (one per domain)
│   └── ait.yaml                            # AIT corpus — paths, FOL examples, target classes
│
├── data/                                   # All data files — input, reference, output
│   ├── institutional_policy/
│   │   └── AIT/                            # Source policy PDFs (pipeline input)
│   │       └── Student-Handbook_August-2021.pdf
│   ├── shacl/
│   │   ├── ontology/
│   │   │   └── ait_policy_ontology.ttl     # AIT domain ontology (vocabulary definitions)
│   │   ├── shapes/
│   │   │   └── ait_policy_shapes.ttl       # 96 gold-standard SHACL shapes
│   │   ├── test_data/
│   │   │   └── tdd_test_data_fixed.ttl.ttl     # AIT domain ontology (vocabulary (hand-curated)
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
├── src/
│   └── policy_checker/                     # Main Python package
│       ├── __init__.py                     # Defines PROJECT_ROOT
│       ├── cli.py                          # Ollama management CLI (policy-ollama)
│       ├── core/
│       │   ├── llm_cache.py                # SQLite-backed LLM response cache
│       │   ├── mcp_server.py               # JSON-RPC MCP server (5 tools)
│       │   ├── prefilter.py                # Heuristic filter logic
│       │   └── turtle_utils.py             # Turtle/RDF utilities shared across nodes
│       ├── database/
│       │   ├── connection.py               # PostgreSQL connection handler
│       │   ├── rdf_converter.py            # SQL rows → RDF triples (data graph)
│       │   └── seed.py                     # Seed test student records
│       ├── langgraph_agent/                # LangGraph agent (pipeline orchestrator)
│       │   ├── state.py                    # Shared PipelineState (TypedDict)
│       │   ├── graph.py                    # Pipeline graph assembly (StateGraph)
│       │   ├── llm.py                      # Ollama LLM configuration
│       │   ├── run.py                      # CLI entry point
│       │   ├── corpus_config.py            # Corpus adapter — loads config/<corpus>.yaml
│       │   ├── _stubs.py                   # Fallback stubs for missing nodes
│       │   ├── edges/
│       │   │   └── route_classify.py       # Conditional routing after classification
│       │   └── nodes/                      # One file per pipeline stage
│       │       ├── common.py               # Shared node utilities
│       │       ├── extract.py              # Step 1: PDF → sentences
│       │       ├── prefilter.py            # Step 2a: heuristic filter
│       │       ├── classify.py             # Step 2b: LLM classification (O/P/F)
│       │       ├── reclassify.py           # Step 2c: second-opinion pass
│       │       ├── fol.py                  # Step 3: FOL formalization
│       │       ├── shacl.py                # Step 4a: FOL → SHACL shapes
│       │       ├── direct_shacl.py         # Step 4b: NL → SHACL fallback
│       │       ├── validate.py             # Step 5: pyshacl validation
│       │       └── report.py               # Step 6: structured report
│       └── api/
│           └── policy_checker.py           # API call (port 8000)
├── .gitignore                              # Files that git should never track
├── .gitattributes                          # Enforce LF line endings for shell scripts across all OS
├── dev-setup.sh                            # One-time setup script
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
| Python | 3.13+ |
| uv | latest |
| Node.js | 20 LTS (installed automatically by dev-setup.sh) |
| Ollama | latest |
| PostgreSQL | 15+ |

> **Note:** PostgreSQL is only needed if you use `src/policy_checker/database/` to load
> student entity data. The core pipeline (`src/policy_checker/langgraph_agent/`) runs without it.

### Step 1 — Clone the repo

```bash
git clone <repo-url>
cd compliance-checking
```

### Step 2 — Set up environment

```bash
cp .env.example .env
```

### Step 3 — Install and start Ollama

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

### Step 4 — Run dev-setup.sh

```bash
bash dev-setup.sh
```

This will:
- Install Python from `.python-version` via `uv python install`
- Install all Python dependencies via `uv sync`
- Install Node.js LTS 20 via `nodeenv` into the virtualenv
- Install frontend dependencies via `npm install`
- Pull the Ollama model specified in `.env`

### Step 5 — Run the pipeline

```bash
uv run policy-checker --source ait --verbose
```

### Step 6 — Seed the database (optional)

Only needed if using the compliance dashboard database features:

```bash
uv run policy-seed
```

---

## 4. Dev Container Setup

Use this for a consistent, team-ready environment using Docker.

### Step 1 — Install Ollama on your machine

Download and install from [ollama.com/download](https://ollama.com/download).

Pull the model (one-time, ~4GB):
```bash
ollama pull mistral
ollama serve
```

### Step 2 — Clone the repo

```bash
git clone <repo-url>
cd compliance-checking
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
3. `Ctrl + Shift + P` → select **Rebuild and Reopen in Container**
4. Select **Docker Outside of Docker**

### Step 5 — Run dev-setup.sh

Inside the VS Code terminal (you are now inside the container):

```bash
bash dev-setup.sh
```

This will:
- Fix container permissions
- Install Python, all Python dependencies, Node.js LTS 20, and frontend dependencies
- Pull the Ollama model specified in `.env`

### Step 6 — Run the pipeline

```bash
policy-checker
#or
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
policy-checker
#or
uv run policy-checker --source ait
```

### Verbose — shows per-step stats

```bash
uv run policy-checker --source ait --verbose
```

Each YAML file specifies PDF paths, ontology, gold shapes, FOL examples, and domain vocabulary.
See `config/ait.yaml` for a fully annotated example.

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

### Ollama management

```bash
policy-ollama load        # pull the model specified in .env
policy-ollama list        # list locally available models
policy-ollama host        # print the configured OLLAMA_HOST
policy-ollama chat <model>       # interactive chat with a model
```

### MCP server (optional)

Exposes the pipeline as tools for MCP-compatible AI clients:

```bash
uv run policy-mcp    # stdio MCP mode — connect from Claude or other clients
```

Available tools: `verify_rule`, `check_status`, `list_rules`, `get_metrics`, `run_pipeline`.

---

## 6. API Deployment

Status — In Development

Goal
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
| `/api/policy` | GET | Return policy path |
| `/api/policy` | POST | Replace policy file and change its path |
| `/api/policy` | DELETE | Delete current policy file |

### Build the backend

```bash
policy-api
```

Then to check the endpoint open swagger through [http://localhost:8000/docs]