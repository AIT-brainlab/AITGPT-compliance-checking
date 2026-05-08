"""
MCP Server — Policy Rule Verification & Pipeline Management
Exposes pipeline tools via JSON-RPC over STDIO for MCP-compatible clients.

Tools:
    verify_rule       — Check if a text is a policy rule via local Ollama
    check_status      — Check Ollama availability and list models
    list_rules        — List classified rules from the latest pipeline run
    get_metrics       — Return M1–M5 thesis metrics from the latest run
    run_pipeline      — Trigger a pipeline run for a given source

Usage:
    python -m core.mcp_server --mcp
    python -m core.mcp_server          # interactive mode
"""

import json
import os
import re
import sys
from pathlib import Path

import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
JSONRPC_VERSION = "2.0"
PROJECT_ROOT = Path(__file__).parent.parent

TOOLS = [
    {
        "name": "verify_rule",
        "description": (
            "Classify whether a text is a policy rule (obligation, permission, or prohibition) "
            "using a local Ollama LLM."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to classify"},
                "model": {
                    "type": "string",
                    "description": f"Ollama model to use (default: {DEFAULT_MODEL})",
                    "default": DEFAULT_MODEL,
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "check_status",
        "description": "Check if Ollama is reachable and list available models.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_rules",
        "description": (
            "List classified rules from the latest pipeline run. "
            "Returns rule_id, text, rule_type, and confidence for each rule."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Institution source (default: ait)",
                    "default": "ait",
                },
                "rule_type": {
                    "type": "string",
                    "description": "Filter by rule type: obligation, permission, prohibition, or all",
                    "default": "all",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of rules to return (default: 50)",
                    "default": 50,
                },
            },
        },
    },
    {
        "name": "get_metrics",
        "description": (
            "Return M1–M5 thesis metrics from the latest pipeline run. "
            "Requires that the evaluation has been run previously."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Institution source (default: ait)",
                    "default": "ait",
                },
            },
        },
    },
    {
        "name": "run_pipeline",
        "description": (
            "Trigger a full pipeline run for the given source institution. "
            "Returns the pipeline report on completion."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Institution source (default: ait)",
                    "default": "ait",
                },
                "ablation": {
                    "type": "string",
                    "description": "Ablation study name (default: baseline)",
                    "default": "baseline",
                },
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _query_ollama(prompt: str, model: str) -> str:
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.0, "seed": 42, "num_predict": 512}},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def verify_rule(text: str, model: str = DEFAULT_MODEL) -> dict:
    prompt = (
        "You are a legal policy analyst. Classify whether the following sentence is a "
        "POLICY RULE (a binding obligation, permission, or prohibition) or NOT A RULE.\n\n"
        f'Sentence: "{text}"\n\n'
        'Respond ONLY with a JSON object:\n'
        '{"is_rule": true/false, "rule_type": "obligation"/"permission"/"prohibition"/null, '
        '"confidence": 0.0-1.0, "reasoning": "one sentence"}'
    )
    try:
        raw = _query_ollama(prompt, model)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"is_rule": False, "rule_type": None, "confidence": 0.0,
                "reasoning": "Failed to parse LLM response", "raw": raw[:200]}
    except Exception as exc:
        return {"is_rule": False, "rule_type": None, "confidence": 0.0, "error": str(exc)}


def check_status() -> dict:
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return {"ollama_running": True, "available_models": models, "host": OLLAMA_HOST}
    except Exception:
        return {"ollama_running": False, "available_models": [], "host": OLLAMA_HOST}


def list_rules(source: str = "ait", rule_type: str = "all", limit: int = 50) -> dict:
    """List classified rules from the latest pipeline output."""
    rules_path = PROJECT_ROOT / "output" / source / "classified_rules.json"
    if not rules_path.exists():
        return {"success": False, "error": f"No classified_rules.json found for source '{source}'"}
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    if rule_type != "all":
        rules = [r for r in rules if r.get("rule_type") == rule_type]
    total = len(rules)
    rules = rules[:limit]
    return {
        "success": True,
        "source": source,
        "filter": rule_type,
        "total_matching": total,
        "returned": len(rules),
        "rules": rules,
    }


def get_metrics(source: str = "ait") -> dict:
    """Return thesis metrics from the latest run."""
    metrics_path = PROJECT_ROOT / "output" / source / "thesis_metrics.json"
    if metrics_path.exists():
        return {
            "success": True,
            "source": source,
            "metrics": json.loads(metrics_path.read_text(encoding="utf-8")),
        }
    # Fall back to computing live if evaluation module is available
    try:
        from evaluation.report import build_report, format_console
        from dataclasses import asdict
        report = build_report(source)
        return {
            "success": True,
            "source": source,
            "metrics": asdict(report),
            "note": "Computed live (not cached)",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def run_pipeline(source: str = "ait", ablation: str = "baseline") -> dict:
    """Trigger a pipeline run and return the report."""
    try:
        from langgraph_agent.run import run
        report = run(source, verbose=False, ablation=ablation)
        return {"success": True, "source": source, "ablation": ablation, "report": report}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# MCP dispatch
# ---------------------------------------------------------------------------

def _handle(tool_name: str, arguments: dict) -> dict:
    if tool_name == "verify_rule":
        text = arguments.get("text", "")
        model = arguments.get("model", DEFAULT_MODEL)
        return {"success": True, "result": verify_rule(text, model)}

    if tool_name == "check_status":
        return {"success": True, **check_status()}

    if tool_name == "list_rules":
        return list_rules(
            source=arguments.get("source", "ait"),
            rule_type=arguments.get("rule_type", "all"),
            limit=arguments.get("limit", 50),
        )

    if tool_name == "get_metrics":
        return get_metrics(source=arguments.get("source", "ait"))

    if tool_name == "run_pipeline":
        return run_pipeline(
            source=arguments.get("source", "ait"),
            ablation=arguments.get("ablation", "baseline"),
        )

    return {"success": False, "error": f"Unknown tool: {tool_name}"}


def run_mcp_server() -> None:
    print(json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "policy-rule-verifier", "version": "2.0.0"},
            "capabilities": {"tools": {}},
        },
    }), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            method = request.get("method")
            params = request.get("params", {})
            rid = request.get("id")

            if method == "tools/list":
                response = {"jsonrpc": JSONRPC_VERSION, "id": rid,
                            "result": {"tools": TOOLS}}
            elif method == "tools/call":
                result = _handle(params.get("name", ""), params.get("arguments", {}))
                response = {
                    "jsonrpc": JSONRPC_VERSION, "id": rid,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
                }
            else:
                response = {
                    "jsonrpc": JSONRPC_VERSION, "id": rid,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            continue
        except Exception as exc:
            print(json.dumps({"jsonrpc": JSONRPC_VERSION,
                               "error": {"code": -32603, "message": str(exc)}}), flush=True)


def interactive_mode() -> None:
    status = check_status()
    if not status["ollama_running"]:
        print(f"❌ Ollama not reachable at {OLLAMA_HOST}. Start with: ollama serve")
        return
    print(f"✅ Ollama running at {OLLAMA_HOST}. Models: {status['available_models']}")

    while True:
        text = input("\nEnter rule text (or 'q' to quit): ").strip()
        if text.lower() == "q":
            break
        result = verify_rule(text)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if "--mcp" in sys.argv:
        run_mcp_server()
    else:
        interactive_mode()
