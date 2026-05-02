"""
Multi-LLM Annotation Agreement (Computational IAA)
====================================================
Runs multiple LLM models on a sample of gold-standard rules to classify
their deontic type, then computes Fleiss' Kappa across all annotators
(human + LLMs).

This is an accepted methodology in NLP research (2024-2026) for
validating annotation reliability when external human annotators
are not available.

Usage:
    # Run with available Ollama models
    python -m evaluation.multi_llm_agreement

    # Specify models explicitly
    python -m evaluation.multi_llm_agreement --models mistral llama3.1:8b

Requires: Ollama running locally with the specified models pulled.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "ait"

_CLASSIFY_PROMPT = """\
You are a legal/policy analyst. Classify the following institutional policy rule 
into exactly ONE of these deontic categories:

- obligation: The rule REQUIRES or MANDATES an action (must, shall, required to)
- prohibition: The rule FORBIDS or PROHIBITS an action (must not, shall not, prohibited)
- permission: The rule ALLOWS or PERMITS an action (may, can, is allowed to, is entitled to)

Rule: "{text}"

Respond with ONLY one word: obligation, permission, or prohibition.
"""


def _load_gold_sample(n: int = 50, seed: int = 42) -> list[dict]:
    """Load a sample of gold-standard rules."""
    gold_path = PROJECT_ROOT / "shacl" / "shapes" / "ait_policy_shapes.ttl"
    content = gold_path.read_text(encoding="utf-8")

    pattern = (
        r'rdfs:label\s+"(GS-\d+)"\s*;'
        r'\s*rdfs:comment\s+"([^"]+)"\s*;'
        r'\s*deontic:type\s+deontic:(\w+)'
    )
    matches = re.findall(pattern, content)

    import random
    rng = random.Random(seed)
    rules = [{"gs_id": m[0], "text": m[1], "gold_type": m[2]} for m in matches]
    return rng.sample(rules, min(n, len(rules)))


def _classify_with_model(text: str, model: str) -> Optional[str]:
    """Classify a rule using a specific Ollama model."""
    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage

        llm = ChatOllama(model=model, temperature=0, seed=42)
        prompt = _CLASSIFY_PROMPT.format(text=text)
        response = llm.invoke([HumanMessage(content=prompt)])
        result = response.content.strip().lower()

        # Normalize response
        for dtype in ["obligation", "prohibition", "permission"]:
            if dtype in result:
                return dtype
        return None
    except Exception as e:
        print(f"  Error with {model}: {e}", file=sys.stderr)
        return None


def _fleiss_kappa(annotations: list[list[str]], categories: list[str]) -> float:
    """Compute Fleiss' Kappa for multiple annotators.

    annotations: list of items, each item is a list of annotator labels
    categories: list of possible categories
    """
    n_items = len(annotations)
    n_raters = len(annotations[0]) if annotations else 0
    n_cats = len(categories)

    if n_items == 0 or n_raters <= 1:
        return 0.0

    cat_idx = {c: i for i, c in enumerate(categories)}

    # Build count matrix: n_items x n_categories
    counts = []
    for item_labels in annotations:
        row = [0] * n_cats
        for label in item_labels:
            if label in cat_idx:
                row[cat_idx[label]] += 1
        counts.append(row)

    # Proportion of ratings in each category
    p_j = [0.0] * n_cats
    for j in range(n_cats):
        p_j[j] = sum(counts[i][j] for i in range(n_items)) / (n_items * n_raters)

    # P_i for each item
    P_i = []
    for i in range(n_items):
        summed = sum(counts[i][j] ** 2 for j in range(n_cats))
        P_i.append((summed - n_raters) / (n_raters * (n_raters - 1)))

    P_bar = sum(P_i) / n_items
    P_e = sum(pj ** 2 for pj in p_j)

    if P_e >= 1.0:
        return 1.0 if P_bar >= 1.0 else 0.0

    return (P_bar - P_e) / (1 - P_e)


def main():
    parser = argparse.ArgumentParser(description="Multi-LLM Annotation Agreement")
    parser.add_argument("--models", nargs="+", default=["mistral", "llama3.1:8b"],
                       help="Ollama model names to use")
    parser.add_argument("-n", type=int, default=50, help="Number of rules to sample")
    args = parser.parse_args()

    print("=" * 60)
    print("Multi-LLM Annotation Agreement Study")
    print("=" * 60)

    rules = _load_gold_sample(n=args.n)
    print(f"Loaded {len(rules)} gold-standard rules")
    print(f"Models: {args.models}")
    print()

    # Classify with each model
    model_results = {}
    for model in args.models:
        print(f"Classifying with {model}...")
        results = []
        for i, rule in enumerate(rules):
            label = _classify_with_model(rule["text"], model)
            results.append(label or "unknown")
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(rules)} done")
        model_results[model] = results
        print(f"  Completed: {sum(1 for r in results if r != 'unknown')}/{len(rules)} valid")
        print()

    # Build annotations matrix: each item = [human, model1, model2, ...]
    categories = ["obligation", "permission", "prohibition"]
    annotations = []
    annotator_names = ["human"] + args.models

    for i, rule in enumerate(rules):
        item_labels = [rule["gold_type"]]  # Human annotation
        for model in args.models:
            item_labels.append(model_results[model][i])
        annotations.append(item_labels)

    # Compute Fleiss' Kappa
    kappa = _fleiss_kappa(annotations, categories)

    # Compute pairwise agreement between human and each model
    print("=" * 60)
    print("Results")
    print("=" * 60)

    for model in args.models:
        agree = sum(1 for i, rule in enumerate(rules)
                   if rule["gold_type"] == model_results[model][i])
        print(f"Human vs {model}: {agree}/{len(rules)} = {agree/len(rules):.3f}")

    print(f"\nFleiss' Kappa (all annotators): {kappa:.3f}")

    if kappa >= 0.81:
        interp = "Almost perfect agreement"
    elif kappa >= 0.61:
        interp = "Substantial agreement"
    elif kappa >= 0.41:
        interp = "Moderate agreement"
    elif kappa >= 0.21:
        interp = "Fair agreement"
    else:
        interp = "Slight agreement"
    print(f"Interpretation: {interp}")

    # Per-category breakdown
    print(f"\nPer-category agreement (Human gold standard):")
    for cat in categories:
        cat_rules = [i for i, r in enumerate(rules) if r["gold_type"] == cat]
        if not cat_rules:
            continue
        for model in args.models:
            agree = sum(1 for i in cat_rules
                       if model_results[model][i] == cat)
            print(f"  {cat:15s} | {model:10s}: {agree}/{len(cat_rules)} = {agree/len(cat_rules):.3f}")

    # Save results
    output = {
        "n_items": len(rules),
        "annotators": annotator_names,
        "fleiss_kappa": round(kappa, 4),
        "interpretation": interp,
        "pairwise_agreement": {},
        "per_item": [],
    }
    for model in args.models:
        agree = sum(1 for i, r in enumerate(rules)
                   if r["gold_type"] == model_results[model][i])
        output["pairwise_agreement"][f"human_vs_{model}"] = round(agree / len(rules), 4)

    for i, rule in enumerate(rules):
        item = {"gs_id": rule["gs_id"], "text": rule["text"][:80],
                "human": rule["gold_type"]}
        for model in args.models:
            item[model] = model_results[model][i]
        output["per_item"].append(item)

    out_path = OUTPUT_DIR / "multi_llm_agreement.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
