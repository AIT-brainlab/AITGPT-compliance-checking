"""
LexDeMod External Validation
=============================
Evaluates the pipeline's deontic classifier against the LexDeMod benchmark
(Sancheti et al., EMNLP 2022) to provide external, domain-independent validation.

LexDeMod is a multi-label dataset of lease-contract sentences annotated with
agent-specific deontic modalities. The label vector has 7 positions:
  [tenant_obl, tenant_ent, tenant_pro, landlord_obl, landlord_ent, landlord_pro, none]

We collapse this to a 4-way classification that mirrors our pipeline's schema:
  Obligation   ← tenant_obl OR landlord_obl  (pos 0 or 3)
  Permission   ← tenant_ent OR landlord_ent  (pos 1 or 4)
  Prohibition  ← tenant_pro OR landlord_pro  (pos 2 or 5)
  None         ← only pos 6 is 1 (no deontic modality)

Multi-label sentences (e.g., obligation + entitlement) receive the dominant label
(first match in the priority order: obligation > prohibition > permission > none).

Usage:
    python scripts/lexdemod_eval.py
    python scripts/lexdemod_eval.py --sample 200   # run on a random subsample
"""

import argparse
import ast
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage
from langgraph_agent.llm import get_llm

_llm = get_llm()

# ── Label schema ────────────────────────────────────────────────────────────

# Position indices in the 7-element LexDeMod label vector
_OBL_IDXS = {0, 3}   # tenant_obl, landlord_obl
_ENT_IDXS = {1, 4}   # tenant_ent, landlord_ent
_PRO_IDXS = {2, 5}   # tenant_pro, landlord_pro
_NONE_IDX = 6


def decode_label(label_str: str) -> str:
    """Convert a 7-element LexDeMod label vector to a single deontic class.

    Priority: obligation > prohibition > permission > none.
    This mirrors the typical severity ordering in deontic logic.
    """
    vec = ast.literal_eval(label_str)
    active = {i for i, v in enumerate(vec) if v == 1}
    if active & _OBL_IDXS:
        return "obligation"
    if active & _PRO_IDXS:
        return "prohibition"
    if active & _ENT_IDXS:
        return "permission"
    return "none"


# ── Prompt ──────────────────────────────────────────────────────────────────

PROMPT = """\
You are a legal NLP classifier specialising in contract law.

Classify the deontic modality of the sentence below using EXACTLY one of:
  - obligation   : a party MUST / SHALL / IS REQUIRED TO perform an action
  - permission   : a party MAY / IS ENTITLED TO perform an action
  - prohibition  : a party MUST NOT / SHALL NOT / IS PROHIBITED FROM an action
  - none         : the sentence is descriptive, definitional, or procedural

The sentence may include a party tag such as [tenant] or [landlord]. Ignore the tag
when deciding the modality—classify the underlying deontic force of the clause itself.

EXAMPLES:
1. "[tenant] Tenant shall pay rent on the first of each month." → obligation
2. "[tenant] Tenant may install fixtures with prior written consent." → permission
3. "[tenant] Tenant shall not sublet the premises without approval." → prohibition
4. "[landlord] Any work Tenant performs shall constitute Alterations." → none

Sentence:
"{text}"

Respond with ONLY a JSON object (no markdown, no explanation):
{{"label": "obligation"/"permission"/"prohibition"/"none", "confidence": 0.0-1.0, \
"reasoning": "one concise sentence"}}"""


# ── Data loading ─────────────────────────────────────────────────────────────

def load_test_set(sample_size: int | None = None) -> list[dict]:
    """Load LexDeMod test split and decode labels to 4-way deontic class."""
    csv_path = (
        PROJECT_ROOT
        / "research" / "LexDeMod" / "deontic_data" / "test_annotated_data.csv"
    )
    with open(csv_path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("split") == "test"]

    # Decode labels
    records = []
    for r in rows:
        records.append({
            "id": r["id"],
            "text": r["text"].strip(),
            "gold_label": decode_label(r["label"]),
            "raw_label": r["label"],
        })

    if sample_size and sample_size < len(records):
        random.seed(42)
        records = random.sample(records, sample_size)

    return records


# ── LLM inference ────────────────────────────────────────────────────────────

def _parse_response(raw: str) -> dict:
    """Extract JSON from LLM response."""
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        return {"label": "none", "confidence": 0.0, "reasoning": "parse error"}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"label": "none", "confidence": 0.0, "reasoning": "json error"}


def run_inference(records: list[dict]) -> list[dict]:
    """Run LLM classification on all records."""
    try:
        from tqdm import tqdm
        iterator = tqdm(records, desc="LexDeMod eval")
    except ImportError:
        iterator = records

    results = []
    for rec in iterator:
        prompt = PROMPT.format(text=rec["text"])
        try:
            response = _llm.invoke([HumanMessage(content=prompt)])
            parsed = _parse_response(response.content)
        except Exception as exc:
            parsed = {"label": "none", "confidence": 0.0, "reasoning": f"error: {exc}"}

        results.append({
            "id": rec["id"],
            "text": rec["text"][:200],
            "gold_label": rec["gold_label"],
            "pred_label": parsed.get("label", "none"),
            "confidence": parsed.get("confidence", 0.0),
            "reasoning": parsed.get("reasoning", ""),
        })

    return results


# ── Metrics ──────────────────────────────────────────────────────────────────

CLASSES = ["obligation", "permission", "prohibition", "none"]


def compute_metrics(results: list[dict]) -> dict:
    """Compute per-class precision/recall/F1 and macro/micro averages."""
    gold = [r["gold_label"] for r in results]
    pred = [r["pred_label"] for r in results]
    n = len(gold)

    per_class = {}
    for cls in CLASSES:
        tp = sum(1 for g, p in zip(gold, pred) if g == cls and p == cls)
        fp = sum(1 for g, p in zip(gold, pred) if g != cls and p == cls)
        fn = sum(1 for g, p in zip(gold, pred) if g == cls and p != cls)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[cls] = {"precision": prec, "recall": rec, "f1": f1,
                          "support": tp + fn}

    # Macro average
    macro_f1   = sum(v["f1"]   for v in per_class.values()) / len(CLASSES)
    macro_prec = sum(v["precision"] for v in per_class.values()) / len(CLASSES)
    macro_rec  = sum(v["recall"]    for v in per_class.values()) / len(CLASSES)

    # Micro average (overall accuracy proxy)
    correct = sum(1 for g, p in zip(gold, pred) if g == p)
    accuracy = correct / n if n else 0.0

    # Label distributions
    gold_dist = dict(Counter(gold))
    pred_dist = dict(Counter(pred))

    return {
        "n": n,
        "accuracy": accuracy,
        "macro_precision": macro_prec,
        "macro_recall": macro_rec,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "gold_distribution": gold_dist,
        "pred_distribution": pred_dist,
    }


# ── Report ───────────────────────────────────────────────────────────────────

def format_report(metrics: dict, sample_size: int | None) -> str:
    scope = f"{metrics['n']} randomly sampled" if sample_size else f"all {metrics['n']}"
    pc = metrics["per_class"]

    lines = [
        "# LexDeMod External Validation Report",
        "",
        "## Experiment Design",
        "",
        "Evaluated the pipeline's deontic classifier (Mistral via Ollama) against",
        "the **LexDeMod** benchmark (Sancheti et al., EMNLP 2022).",
        "",
        "LexDeMod is a dataset of lease-contract sentences annotated with",
        "agent-specific deontic modalities (obligation / entitlement / prohibition / none).",
        "This provides **external, domain-independent validation** of the classifier.",
        "",
        f"- **Test set**: {scope} sentences from `test_annotated_data.csv`",
        "- **Label mapping**: 7-class agent-specific → 4-class deontic",
        "  (obligation > prohibition > permission > none, priority order)",
        "- **Model**: Mistral via Ollama (same model used in the AIT pipeline)",
        "",
        "## Overall Metrics",
        "",
        f"| Metric | Score |",
        f"|--------|-------|",
        f"| Accuracy | {metrics['accuracy']:.1%} |",
        f"| Macro Precision | {metrics['macro_precision']:.3f} |",
        f"| Macro Recall | {metrics['macro_recall']:.3f} |",
        f"| **Macro F1** | **{metrics['macro_f1']:.3f}** |",
        "",
        "## Per-Class Performance",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "|-------|-----------|--------|----|---------|",
    ]

    for cls in CLASSES:
        m = pc[cls]
        lines.append(
            f"| {cls.capitalize()} | {m['precision']:.3f} | {m['recall']:.3f} | "
            f"{m['f1']:.3f} | {m['support']} |"
        )

    lines.extend([
        "",
        "## Label Distribution",
        "",
        "| Class | Gold | Predicted |",
        "|-------|------|-----------|",
    ])
    for cls in CLASSES:
        g = metrics["gold_distribution"].get(cls, 0)
        p = metrics["pred_distribution"].get(cls, 0)
        lines.append(f"| {cls.capitalize()} | {g} | {p} |")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "The LexDeMod evaluation provides external evidence of the classifier's",
        "deontic detection capabilities on a **held-out, publicly available benchmark**",
        "from a different legal domain (lease contracts vs. AIT institutional policy).",
        "",
        "Key observations:",
        f"1. **Macro F1 = {metrics['macro_f1']:.3f}**: measures balanced performance across all 4 classes.",
        "2. **Domain transfer**: LexDeMod uses lease-contract language; the pipeline was",
        "   developed for institutional policy. Cross-domain performance demonstrates",
        "   (or limits) generalisability.",
        "3. **None-class bias**: if the model over-predicts 'none', this reflects the",
        "   stricter deontic filter observed in the AIT ablation study.",
        "",
        "*Results reported in thesis Chapter 5 (External Validation, Section 5.5).*",
    ])

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LexDeMod external validation")
    parser.add_argument("--sample", type=int, default=None,
                        help="Number of test sentences to sample (default: all 1777)")
    args = parser.parse_args()

    print("Loading LexDeMod test set...")
    records = load_test_set(sample_size=args.sample)
    print(f"  {len(records)} sentences loaded")

    from collections import Counter
    dist = Counter(r["gold_label"] for r in records)
    print(f"  Gold distribution: {dict(dist)}")

    print("\nRunning LLM inference...")
    results = run_inference(records)

    print("\nComputing metrics...")
    metrics = compute_metrics(results)

    out_dir = PROJECT_ROOT / "output" / "ait"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON (full)
    json_path = out_dir / "lexdemod_eval.json"
    json_path.write_text(
        json.dumps({"metrics": metrics, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nJSON saved: {json_path}")

    # Markdown report
    report = format_report(metrics, args.sample)
    md_path = out_dir / "lexdemod_eval.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"Report saved: {md_path}")

    # Summary
    print("\n=== Summary ===")
    print(f"  N              : {metrics['n']}")
    print(f"  Accuracy       : {metrics['accuracy']:.1%}")
    print(f"  Macro F1       : {metrics['macro_f1']:.3f}")
    print(f"  Macro Prec     : {metrics['macro_precision']:.3f}")
    print(f"  Macro Recall   : {metrics['macro_recall']:.3f}")
    print("\n  Per-class F1:")
    for cls in CLASSES:
        print(f"    {cls:12s}: F1={metrics['per_class'][cls]['f1']:.3f}  "
              f"(P={metrics['per_class'][cls]['precision']:.3f}, "
              f"R={metrics['per_class'][cls]['recall']:.3f}, "
              f"n={metrics['per_class'][cls]['support']})")


if __name__ == "__main__":
    main()
