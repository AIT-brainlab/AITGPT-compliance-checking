"""
Intra-Annotator Reliability Study
==================================
Generates a blinded re-annotation questionnaire from the gold standard,
and computes Cohen's Kappa when re-annotation results are provided.

Usage:
    # Step 1: Generate questionnaire (do this now)
    python -m evaluation.intra_annotator --generate

    # Step 2: After re-annotating (2-3 weeks later), compute kappa
    python -m evaluation.intra_annotator --compute

The questionnaire is saved as a JSON file with rule texts in randomized
order, stripped of original labels. The annotator fills in deontic_type
for each entry.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "ait"


def _load_gold_rules() -> list[dict]:
    """Load gold standard rules with their deontic types from the TTL file."""
    gold_path = PROJECT_ROOT / "shacl" / "shapes" / "ait_policy_shapes.ttl"
    content = gold_path.read_text(encoding="utf-8")

    # Extract rule ID, deontic type, and comment (rule text)
    pattern = (
        r'rdfs:label\s+"(GS-\d+)"\s*;'
        r'\s*rdfs:comment\s+"([^"]+)"\s*;'
        r'\s*deontic:type\s+deontic:(\w+)'
    )
    matches = re.findall(pattern, content)

    rules = []
    for gs_id, text, dtype in matches:
        rules.append({
            "gs_id": gs_id,
            "text": text.strip(),
            "original_type": dtype.strip(),
        })
    return rules


def generate_questionnaire(n_sample: int = 50, seed: int = 42):
    """Generate a blinded re-annotation questionnaire."""
    rules = _load_gold_rules()
    print(f"Loaded {len(rules)} gold standard rules")

    rng = random.Random(seed)
    sample = rng.sample(rules, min(n_sample, len(rules)))

    # Shuffle to remove any ordering bias
    rng.shuffle(sample)

    # Create blinded questionnaire (no original labels)
    questionnaire = []
    answer_key = []
    for i, rule in enumerate(sample, 1):
        questionnaire.append({
            "item_id": i,
            "gs_id": rule["gs_id"],
            "text": rule["text"],
            "reannotation": ""  # Annotator fills: obligation/permission/prohibition
        })
        answer_key.append({
            "item_id": i,
            "gs_id": rule["gs_id"],
            "original_type": rule["original_type"],
        })

    # Save questionnaire (blinded)
    q_path = OUTPUT_DIR / "reannotation_questionnaire.json"
    q_path.write_text(json.dumps(questionnaire, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved blinded questionnaire: {q_path} ({len(questionnaire)} items)")

    # Save answer key (hidden from annotator during re-annotation)
    ak_path = OUTPUT_DIR / "reannotation_answer_key.json"
    ak_path.write_text(json.dumps(answer_key, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved answer key: {ak_path}")

    print("\nInstructions:")
    print("1. Wait 2-3 weeks before re-annotating")
    print("2. Open reannotation_questionnaire.json")
    print("3. For each item, fill the 'reannotation' field with:")
    print("   obligation / permission / prohibition")
    print("4. Run: python -m evaluation.intra_annotator --compute")


def compute_kappa():
    """Compute Cohen's Kappa between original and re-annotation."""
    q_path = OUTPUT_DIR / "reannotation_questionnaire.json"
    ak_path = OUTPUT_DIR / "reannotation_answer_key.json"

    if not q_path.exists() or not ak_path.exists():
        print("Error: Run --generate first to create the questionnaire.")
        return

    questionnaire = json.loads(q_path.read_text(encoding="utf-8"))
    answer_key = json.loads(ak_path.read_text(encoding="utf-8"))

    # Check if re-annotation is complete
    filled = [q for q in questionnaire if q.get("reannotation", "").strip()]
    if len(filled) < len(questionnaire):
        print(f"Warning: Only {len(filled)}/{len(questionnaire)} items re-annotated.")
        if len(filled) == 0:
            print("No re-annotations found. Fill the 'reannotation' field first.")
            return

    # Build paired labels
    ak_map = {a["item_id"]: a["original_type"] for a in answer_key}
    labels_original = []
    labels_reannotated = []

    for q in questionnaire:
        reannot = q.get("reannotation", "").strip().lower()
        if not reannot:
            continue
        original = ak_map.get(q["item_id"], "").lower()
        labels_original.append(original)
        labels_reannotated.append(reannot)

    n = len(labels_original)
    if n == 0:
        print("No valid paired annotations found.")
        return

    # Compute Cohen's Kappa
    categories = sorted(set(labels_original) | set(labels_reannotated))
    kappa = _cohens_kappa(labels_original, labels_reannotated, categories)

    # Agreement rate
    agree = sum(1 for a, b in zip(labels_original, labels_reannotated) if a == b)
    agree_rate = agree / n

    # Confusion matrix
    print(f"\n{'='*60}")
    print(f"Intra-Annotator Reliability (n={n})")
    print(f"{'='*60}")
    print(f"Raw agreement: {agree}/{n} = {agree_rate:.3f}")
    print(f"Cohen's Kappa: {kappa:.3f}")
    print()

    # Interpret kappa
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
    print(f"Interpretation (Landis & Koch, 1977): {interp}")

    # Print confusion matrix
    print(f"\nConfusion Matrix:")
    print(f"{'':20s}", end="")
    for c in categories:
        print(f"{c:>15s}", end="")
    print()
    for c1 in categories:
        print(f"{c1:20s}", end="")
        for c2 in categories:
            count = sum(1 for a, b in zip(labels_original, labels_reannotated)
                       if a == c1 and b == c2)
            print(f"{count:15d}", end="")
        print()

    # Save results
    results = {
        "n_items": n,
        "raw_agreement": round(agree_rate, 4),
        "cohens_kappa": round(kappa, 4),
        "interpretation": interp,
        "categories": categories,
    }
    out_path = OUTPUT_DIR / "intra_annotator_results.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved to: {out_path}")


def _cohens_kappa(labels1: list, labels2: list, categories: list) -> float:
    """Compute Cohen's Kappa coefficient."""
    n = len(labels1)
    if n == 0:
        return 0.0

    # Build confusion matrix
    matrix = {}
    for c1 in categories:
        for c2 in categories:
            matrix[(c1, c2)] = 0
    for a, b in zip(labels1, labels2):
        matrix[(a, b)] += 1

    # Observed agreement
    p_o = sum(matrix[(c, c)] for c in categories) / n

    # Expected agreement (by chance)
    p_e = 0.0
    for c in categories:
        row_sum = sum(matrix[(c, c2)] for c2 in categories)
        col_sum = sum(matrix[(c1, c)] for c1 in categories)
        p_e += (row_sum / n) * (col_sum / n)

    if p_e >= 1.0:
        return 1.0 if p_o >= 1.0 else 0.0
    return (p_o - p_e) / (1 - p_e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intra-Annotator Reliability")
    parser.add_argument("--generate", action="store_true", help="Generate questionnaire")
    parser.add_argument("--compute", action="store_true", help="Compute kappa")
    parser.add_argument("-n", type=int, default=50, help="Number of rules to sample")
    args = parser.parse_args()

    if args.generate:
        generate_questionnaire(n_sample=args.n)
    elif args.compute:
        compute_kappa()
    else:
        parser.print_help()
