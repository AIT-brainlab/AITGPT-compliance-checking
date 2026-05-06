"""
Full D1 Deontic Type Classification Evaluation
================================================
Evaluates the LLM's deontic type assignments across the FULL D1 corpus
(443 classified rules) using two methods:

  1. Regex baseline comparison — heuristic deontic markers as silver standard
  2. Author gold annotation   — if gold_annotations_d1.json exists

When no gold file exists, the script generates a blank annotation template
(gold_annotations_d1_template.json) for the author to fill in.

Usage:
    python -m evaluation.full_d1_type_eval            # run evaluation
    python -m evaluation.full_d1_type_eval --generate  # generate annotation template only

Outputs:
    output/ait/full_d1_type_eval.json        — evaluation results
    output/ait/gold_annotations_d1_template.json — annotation template (if needed)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


# ── Regex Baseline Classifier ────────────────────────────────────────────

PROHIBITION_RE = re.compile(
    r"\b(cannot|must\s+not|shall\s+not|may\s+not|"
    r"prohibited|not\s+allowed|not\s+permitted|forbidden|"
    r"no\s+\w+\s+shall|will\s+not\s+be\s+allowed)\b",
    re.IGNORECASE,
)

OBLIGATION_RE = re.compile(
    r"\b(must|shall|required\s+to|is\s+required|are\s+required|"
    r"have\s+to|has\s+to|obligated|will\s+be\s+required|"
    r"should|expected\s+to|need\s+to)\b",
    re.IGNORECASE,
)

PERMISSION_RE = re.compile(
    r"\b(may|permitted\s+to|allowed\s+to|is\s+allowed|are\s+allowed|"
    r"can|entitled\s+to|eligible)\b",
    re.IGNORECASE,
)


def regex_classify(text: str) -> str:
    """Classify deontic type using regex markers (priority: prohibition > obligation > permission)."""
    if PROHIBITION_RE.search(text):
        return "prohibition"
    if OBLIGATION_RE.search(text):
        return "obligation"
    if PERMISSION_RE.search(text):
        return "permission"
    return "obligation"  # default fallback


# ── Metrics ──────────────────────────────────────────────────────────────

def per_class_metrics(labels_true: list[str], labels_pred: list[str]) -> dict:
    """Compute per-class precision, recall, F1 and overall accuracy."""
    categories = sorted(set(labels_true) | set(labels_pred))
    n = len(labels_true)
    agree = sum(1 for a, b in zip(labels_true, labels_pred) if a == b)

    per_class = {}
    for c in categories:
        tp = sum(1 for a, b in zip(labels_true, labels_pred) if a == c and b == c)
        fp = sum(1 for a, b in zip(labels_true, labels_pred) if a != c and b == c)
        fn = sum(1 for a, b in zip(labels_true, labels_pred) if a == c and b != c)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_class[c] = {
            "precision": round(prec, 4),
            "recall":    round(rec,  4),
            "f1":        round(f1,   4),
            "support":   tp + fn,
        }

    macro_p  = sum(v["precision"] for v in per_class.values()) / len(per_class) if per_class else 0
    macro_r  = sum(v["recall"]    for v in per_class.values()) / len(per_class) if per_class else 0
    macro_f1 = sum(v["f1"]        for v in per_class.values()) / len(per_class) if per_class else 0

    return {
        "n":              n,
        "accuracy":       round(agree / n, 4) if n else 0,
        "n_correct":      agree,
        "macro_precision": round(macro_p, 4),
        "macro_recall":   round(macro_r, 4),
        "macro_f1":       round(macro_f1, 4),
        "per_class":      per_class,
    }


def cohens_kappa(labels1: list[str], labels2: list[str]) -> float:
    """Cohen's Kappa between two label lists."""
    n = len(labels1)
    if n == 0:
        return 0.0
    categories = sorted(set(labels1) | set(labels2))
    matrix = {(c1, c2): 0 for c1 in categories for c2 in categories}
    for a, b in zip(labels1, labels2):
        matrix[(a, b)] += 1
    p_o = sum(matrix[(c, c)] for c in categories) / n
    p_e = sum(
        (sum(matrix[(c, c2)] for c2 in categories) / n)
        * (sum(matrix[(c1, c)] for c1 in categories) / n)
        for c in categories
    )
    if p_e >= 1.0:
        return 1.0 if p_o >= 1.0 else 0.0
    return round((p_o - p_e) / (1 - p_e), 4)


def interpret_kappa(k: float) -> str:
    if k >= 0.81: return "Almost perfect"
    if k >= 0.61: return "Substantial"
    if k >= 0.41: return "Moderate"
    if k >= 0.21: return "Fair"
    return "Slight"


# ── Template generation ──────────────────────────────────────────────────

def generate_annotation_template(rules: list[dict], out_path: Path) -> None:
    """Create a JSON template for author gold annotation."""
    template = []
    for r in rules:
        template.append({
            "rule_id":        r["rule_id"],
            "text":           r["text"],
            "source_document": r.get("source_document", ""),
            "llm_type":       r["rule_type"],
            "gold_type":      "",  # Author fills this in
            "notes":          "",
        })
    out_path.write_text(
        json.dumps(template, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Annotation template generated: {out_path}")
    print(f"  -> Fill in 'gold_type' for each rule (obligation/permission/prohibition)")
    print(f"  -> Save as 'gold_annotations_d1.json' in the same directory")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Full D1 deontic type evaluation")
    parser.add_argument("--generate", action="store_true",
                        help="Generate annotation template only")
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / "output" / "ait"
    rules_path = output_dir / "classified_rules.json"

    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    n = len(rules)

    print(f"\n{'='*70}")
    print(f"  FULL D1 DEONTIC TYPE CLASSIFICATION EVALUATION (N={n})")
    print(f"{'='*70}")

    # ── Generate template if requested ────────────────────────────────
    template_path = output_dir / "gold_annotations_d1_template.json"
    if args.generate:
        generate_annotation_template(rules, template_path)
        return

    # ── LLM labels ────────────────────────────────────────────────────
    llm_types  = [r["rule_type"] for r in rules]
    llm_dist   = dict(Counter(llm_types))
    print(f"\n  LLM Type Distribution (pipeline-assigned):")
    for t in sorted(llm_dist):
        print(f"    {t:<15} {llm_dist[t]:>5}  ({llm_dist[t]/n:.1%})")

    # ── Regex baseline ────────────────────────────────────────────────
    regex_types = [regex_classify(r["text"]) for r in rules]
    regex_dist  = dict(Counter(regex_types))
    print(f"\n  Regex Baseline Distribution:")
    for t in sorted(regex_dist):
        print(f"    {t:<15} {regex_dist[t]:>5}  ({regex_dist[t]/n:.1%})")

    # ── LLM vs Regex comparison ───────────────────────────────────────
    print(f"\n{'-'*70}")
    print(f"  LLM vs REGEX BASELINE AGREEMENT (N={n})")
    print(f"{'-'*70}")

    agree = sum(1 for a, b in zip(llm_types, regex_types) if a == b)
    print(f"\n  Raw Agreement: {agree}/{n} = {agree/n:.1%}")

    kappa_lr = cohens_kappa(llm_types, regex_types)
    print(f"  Cohen's Kappa: {kappa_lr:.4f}  [{interpret_kappa(kappa_lr)}]")

    metrics_lr = per_class_metrics(regex_types, llm_types)
    print(f"\n  Per-class (Regex as reference, LLM as prediction):")
    print(f"    {'Type':<15} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Support':>8}")
    for cls in sorted(metrics_lr["per_class"]):
        m = metrics_lr["per_class"][cls]
        print(f"    {cls:<15} {m['precision']:>10.4f} {m['recall']:>8.4f} {m['f1']:>8.4f} {m['support']:>8}")

    # ── Disagreement analysis ─────────────────────────────────────────
    disagreements = []
    for i, r in enumerate(rules):
        if llm_types[i] != regex_types[i]:
            disagreements.append({
                "rule_id":    r["rule_id"],
                "text":       r["text"][:100] + ("..." if len(r["text"]) > 100 else ""),
                "llm_type":   llm_types[i],
                "regex_type": regex_types[i],
            })

    print(f"\n  Disagreements: {len(disagreements)}/{n} ({len(disagreements)/n:.1%})")

    # Show disagreement breakdown
    dis_matrix = Counter()
    for d in disagreements:
        dis_matrix[(d["regex_type"], d["llm_type"])] += 1
    if dis_matrix:
        print(f"\n  Disagreement matrix (regex -> LLM):")
        for (r_type, l_type), cnt in sorted(dis_matrix.items(), key=lambda x: -x[1]):
            print(f"    {r_type:>12} -> {l_type:<12}  {cnt:>4}")

    # ── Check for author gold annotations ─────────────────────────────
    gold_path = output_dir / "gold_annotations_d1.json"
    results = {
        "n_rules": n,
        "llm_distribution": llm_dist,
        "regex_distribution": regex_dist,
        "llm_vs_regex": {
            "agreement": f"{agree}/{n}",
            "agreement_pct": round(agree / n, 4),
            "cohens_kappa": kappa_lr,
            "kappa_interpretation": interpret_kappa(kappa_lr),
            "per_class": metrics_lr["per_class"],
            "n_disagreements": len(disagreements),
        },
    }

    if gold_path.exists():
        print(f"\n{'-'*70}")
        print(f"  LLM vs AUTHOR GOLD STANDARD (N={n})")
        print(f"{'-'*70}")

        gold_data = json.loads(gold_path.read_text(encoding="utf-8"))
        gold_map = {g["rule_id"]: g["gold_type"].strip().lower() for g in gold_data
                     if g.get("gold_type", "").strip()}

        # Align
        matched_llm  = []
        matched_gold = []
        unmatched = 0
        for r in rules:
            if r["rule_id"] in gold_map:
                matched_llm.append(r["rule_type"])
                matched_gold.append(gold_map[r["rule_id"]])
            else:
                unmatched += 1

        n_matched = len(matched_llm)
        print(f"\n  Matched: {n_matched}/{n} rules ({unmatched} without gold annotation)")

        if n_matched > 0:
            gold_dist = dict(Counter(matched_gold))
            print(f"\n  Gold Type Distribution:")
            for t in sorted(gold_dist):
                print(f"    {t:<15} {gold_dist[t]:>5}  ({gold_dist[t]/n_matched:.1%})")

            metrics_gold = per_class_metrics(matched_gold, matched_llm)
            kappa_gold   = cohens_kappa(matched_gold, matched_llm)

            # Compute 3-class Macro F1 (exclude 'exemption' artifact)
            real_classes = [c for c in metrics_gold["per_class"] if c != "exemption"]
            macro_f1_3class = sum(
                metrics_gold["per_class"][c]["f1"] for c in real_classes
            ) / len(real_classes) if real_classes else 0

            print(f"\n  Overall Accuracy: {metrics_gold['accuracy']:.1%} ({metrics_gold['n_correct']}/{n_matched})")
            print(f"  Cohen's Kappa:    {kappa_gold:.4f}  [{interpret_kappa(kappa_gold)}]")
            print(f"  Macro F1 (3-class): {macro_f1_3class:.4f}")

            print(f"\n  Per-class (Gold as reference, LLM as prediction):")
            print(f"    {'Type':<15} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Support':>8}")
            for cls in sorted(metrics_gold["per_class"]):
                m = metrics_gold["per_class"][cls]
                print(f"    {cls:<15} {m['precision']:>10.4f} {m['recall']:>8.4f} {m['f1']:>8.4f} {m['support']:>8}")

            # ── Confusion Matrix ──────────────────────────────────────
            cm_classes = sorted(set(matched_gold) | set(matched_llm))
            cm = {g: {p: 0 for p in cm_classes} for g in cm_classes}
            for g, p in zip(matched_gold, matched_llm):
                cm[g][p] += 1

            print(f"\n  Confusion Matrix (rows=Gold, cols=LLM):")
            hdr_label = "Gold \\ LLM"
            header = f"    {hdr_label:<15}" + "".join(f" {c:>12}" for c in cm_classes) + f" {'Total':>8}"
            print(header)
            print(f"    {'-'*len(header)}")
            for g in cm_classes:
                row_total = sum(cm[g].values())
                row = f"    {g:<15}" + "".join(f" {cm[g][p]:>12}" for p in cm_classes) + f" {row_total:>8}"
                print(row)
            # Column totals
            col_totals = f"    {'Total':<15}" + "".join(
                f" {sum(cm[g][p] for g in cm_classes):>12}" for p in cm_classes
            ) + f" {n_matched:>8}"
            print(f"    {'-'*len(header)}")
            print(col_totals)

            # Serialize confusion matrix
            cm_serializable = {g: {p: cm[g][p] for p in cm_classes} for g in cm_classes}

            # Find LLM errors
            gold_errors = []
            for r in rules:
                if r["rule_id"] in gold_map and r["rule_type"] != gold_map[r["rule_id"]]:
                    gold_errors.append({
                        "rule_id":   r["rule_id"],
                        "text":      r["text"][:100] + ("..." if len(r["text"]) > 100 else ""),
                        "llm_type":  r["rule_type"],
                        "gold_type": gold_map[r["rule_id"]],
                    })

            print(f"\n  LLM Errors vs Gold: {len(gold_errors)}/{n_matched}")
            if gold_errors[:10]:
                print(f"\n  Sample errors (first 10):")
                for e in gold_errors[:10]:
                    print(f"    {e['rule_id']:10s}  Gold={e['gold_type']:<12}  LLM={e['llm_type']:<12}  {e['text']}")

            results["llm_vs_gold"] = {
                "n_matched": n_matched,
                "accuracy": metrics_gold["accuracy"],
                "n_correct": metrics_gold["n_correct"],
                "cohens_kappa": kappa_gold,
                "kappa_interpretation": interpret_kappa(kappa_gold),
                "macro_f1_3class": round(macro_f1_3class, 4),
                "per_class": metrics_gold["per_class"],
                "confusion_matrix": cm_serializable,
                "gold_distribution": gold_dist,
                "n_errors": len(gold_errors),
                "errors": gold_errors,
            }
    else:
        print(f"\n  WARNING: No author gold annotations found at: {gold_path}")
        print(f"    Run with --generate to create annotation template")
        generate_annotation_template(rules, template_path)

    # ── Save results ──────────────────────────────────────────────────
    out_path = output_dir / "full_d1_type_eval.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Results saved: {out_path}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
