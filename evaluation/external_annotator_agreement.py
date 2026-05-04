"""
External Annotator Agreement Study
====================================
Computes inter-annotator reliability between the author's gold standard
annotations and two external annotators (Kittipat, Mayuree) on a 50-item
stratified sample of AIT policy rules.

Outputs:
  - Fleiss' Kappa (3-annotator agreement)
  - Pairwise Cohen's Kappa
  - Binary (deontic vs. non-deontic) agreement
  - Per-class confusion matrices
  - Saved JSON results

Usage:
    python -m evaluation.external_annotator_agreement
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


# ── Label normalisation ──────────────────────────────────────────────────

def normalise_label(raw: str) -> str:
    """Map raw classification to canonical 4-class label."""
    raw = raw.strip().lower()

    if raw in ("obligation",):
        return "obligation"
    if raw in ("permission",):
        return "permission"
    if raw in ("prohibition",):
        return "prohibition"
    if "non-deontic" in raw or "constitutive" in raw or "epistemic" in raw:
        return "non-deontic"
    if "unclear" in raw or "truncated" in raw:
        return "non-deontic"  # collapse unclear into non-deontic
    # fallback
    return raw


def to_binary(label: str) -> str:
    """Collapse to binary: deontic vs. non-deontic."""
    return "non-deontic" if label == "non-deontic" else "deontic"


# ── Data loading ─────────────────────────────────────────────────────────

def load_data(output_dir: Path):
    """Load all annotator data and return aligned label lists."""
    answer_key = json.loads(
        (output_dir / "reannotation_answer_key.json").read_text(encoding="utf-8")
    )
    reannotation = json.loads(
        (output_dir / "reannotation_questionnaire.json").read_text(encoding="utf-8")
    )
    kittipat = json.loads(
        (output_dir / "questionnaire_kittipat.json").read_text(encoding="utf-8")
    )
    mayuree = json.loads(
        (output_dir / "questionnaire_mayuree.json").read_text(encoding="utf-8")
    )

    # Build lookup by item_id
    ak_map = {a["item_id"]: normalise_label(a["original_type"]) for a in answer_key}
    re_map = {r["item_id"]: normalise_label(r["reannotation"]) for r in reannotation
              if r.get("reannotation", "").strip()}
    ki_map = {k["item_id"]: normalise_label(k["classification"]) for k in kittipat}
    ma_map = {m["item_id"]: normalise_label(m["classification"]) for m in mayuree}

    # Align on common item_ids
    common_ids = sorted(set(ak_map) & set(re_map) & set(ki_map) & set(ma_map))

    return {
        "item_ids": common_ids,
        "gold": [ak_map[i] for i in common_ids],
        "author_reannot": [re_map[i] for i in common_ids],
        "kittipat": [ki_map[i] for i in common_ids],
        "mayuree": [ma_map[i] for i in common_ids],
        # Keep raw for detailed analysis
        "answer_key": answer_key,
        "kittipat_raw": kittipat,
        "mayuree_raw": mayuree,
    }


# ── Cohen's Kappa ────────────────────────────────────────────────────────

def cohens_kappa(labels1: list[str], labels2: list[str]) -> float:
    """Compute Cohen's Kappa coefficient."""
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
    return (p_o - p_e) / (1 - p_e)


# ── Fleiss' Kappa ────────────────────────────────────────────────────────

def fleiss_kappa(ratings: list[list[str]]) -> float:
    """
    Compute Fleiss' Kappa for multiple annotators.
    ratings: list of [annotator1_label, annotator2_label, ...] per item.
    """
    n_items = len(ratings)
    n_raters = len(ratings[0])
    categories = sorted(set(label for item in ratings for label in item))
    n_cats = len(categories)
    cat_idx = {c: i for i, c in enumerate(categories)}

    # Build count matrix: n_items × n_categories
    counts = []
    for item in ratings:
        row = [0] * n_cats
        for label in item:
            row[cat_idx[label]] += 1
        counts.append(row)

    # P_i for each item
    p_items = []
    for row in counts:
        p_i = (sum(r * r for r in row) - n_raters) / (n_raters * (n_raters - 1))
        p_items.append(p_i)

    P_bar = sum(p_items) / n_items

    # P_j for each category (proportion of all assignments to that category)
    p_cats = []
    for j in range(n_cats):
        total_j = sum(counts[i][j] for i in range(n_items))
        p_cats.append(total_j / (n_items * n_raters))

    P_e = sum(p * p for p in p_cats)

    if P_e >= 1.0:
        return 1.0 if P_bar >= 1.0 else 0.0
    return (P_bar - P_e) / (1 - P_e)


# ── Confusion matrix ─────────────────────────────────────────────────────

def confusion_matrix(labels_true: list[str], labels_pred: list[str],
                     label: str = "") -> dict:
    """Build confusion matrix and per-class metrics."""
    categories = sorted(set(labels_true) | set(labels_pred))
    matrix = {}
    for c1 in categories:
        for c2 in categories:
            matrix[(c1, c2)] = sum(
                1 for a, b in zip(labels_true, labels_pred) if a == c1 and b == c2
            )

    n = len(labels_true)
    agree = sum(1 for a, b in zip(labels_true, labels_pred) if a == b)

    # Per-class precision/recall/f1
    per_class = {}
    for c in categories:
        tp = matrix[(c, c)]
        fp = sum(matrix[(c2, c)] for c2 in categories if c2 != c)
        fn = sum(matrix[(c, c2)] for c2 in categories if c2 != c)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        per_class[c] = {"precision": round(prec, 4), "recall": round(rec, 4),
                        "f1": round(f1, 4), "support": tp + fn}

    return {
        "n": n,
        "agreement_rate": round(agree / n, 4) if n else 0,
        "categories": categories,
        "matrix": {f"{c1}_vs_{c2}": matrix[(c1, c2)]
                   for c1 in categories for c2 in categories},
        "per_class": per_class,
        "label": label,
    }


# ── Disagreement analysis ────────────────────────────────────────────────

def find_disagreements(data: dict) -> list[dict]:
    """Find items where annotators disagree and report details."""
    disagreements = []
    for idx, item_id in enumerate(data["item_ids"]):
        gold = data["gold"][idx]
        ki = data["kittipat"][idx]
        ma = data["mayuree"][idx]
        reannot = data["author_reannot"][idx]

        labels = {gold, ki, ma, reannot}
        if len(labels) > 1:
            # Find the GS-ID
            gs_id = None
            for ak in data["answer_key"]:
                if ak["item_id"] == item_id:
                    gs_id = ak["gs_id"]
                    break
            disagreements.append({
                "item_id": item_id,
                "gs_id": gs_id,
                "gold_original": gold,
                "author_reannot": reannot,
                "kittipat": ki,
                "mayuree": ma,
            })
    return disagreements


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    output_dir = PROJECT_ROOT / "output" / "ait"
    data = load_data(output_dir)
    n = len(data["item_ids"])

    print(f"\n{'='*70}")
    print(f"  EXTERNAL ANNOTATOR AGREEMENT STUDY (N={n})")
    print(f"{'='*70}")

    # ── 4-class analysis ──────────────────────────────────────────────
    print(f"\n{'-'*70}")
    print("  4-CLASS ANALYSIS (obligation / permission / prohibition / non-deontic)")
    print(f"{'-'*70}")

    # Fleiss' Kappa (3 external views: author-reannot, kittipat, mayuree)
    ratings_4class = list(zip(
        data["author_reannot"], data["kittipat"], data["mayuree"]
    ))
    fk_4class = fleiss_kappa([list(r) for r in ratings_4class])
    print(f"\n  Fleiss' Kappa (3 annotators, 4-class): {fk_4class:.4f}")

    # Pairwise Cohen's Kappa
    ck_gold_ki = cohens_kappa(data["gold"], data["kittipat"])
    ck_gold_ma = cohens_kappa(data["gold"], data["mayuree"])
    ck_gold_re = cohens_kappa(data["gold"], data["author_reannot"])
    ck_ki_ma = cohens_kappa(data["kittipat"], data["mayuree"])
    ck_re_ki = cohens_kappa(data["author_reannot"], data["kittipat"])
    ck_re_ma = cohens_kappa(data["author_reannot"], data["mayuree"])

    print(f"\n  Pairwise Cohen's Kappa (4-class):")
    print(f"    Gold vs Kittipat:       {ck_gold_ki:.4f}")
    print(f"    Gold vs Mayuree:        {ck_gold_ma:.4f}")
    print(f"    Gold vs Author-Reannot: {ck_gold_re:.4f}")
    print(f"    Kittipat vs Mayuree:    {ck_ki_ma:.4f}")
    print(f"    Author-Re vs Kittipat:  {ck_re_ki:.4f}")
    print(f"    Author-Re vs Mayuree:   {ck_re_ma:.4f}")

    # Per-pair agreement rates
    for name, l1, l2 in [
        ("Gold vs Kittipat", data["gold"], data["kittipat"]),
        ("Gold vs Mayuree", data["gold"], data["mayuree"]),
        ("Kittipat vs Mayuree", data["kittipat"], data["mayuree"]),
    ]:
        agree = sum(1 for a, b in zip(l1, l2) if a == b)
        print(f"    {name}: {agree}/{n} = {agree/n:.1%} raw agreement")

    # ── Binary analysis ───────────────────────────────────────────────
    print(f"\n{'-'*70}")
    print("  BINARY ANALYSIS (deontic vs. non-deontic)")
    print(f"{'-'*70}")

    gold_bin = [to_binary(l) for l in data["gold"]]
    re_bin = [to_binary(l) for l in data["author_reannot"]]
    ki_bin = [to_binary(l) for l in data["kittipat"]]
    ma_bin = [to_binary(l) for l in data["mayuree"]]

    ratings_bin = list(zip(re_bin, ki_bin, ma_bin))
    fk_bin = fleiss_kappa([list(r) for r in ratings_bin])
    print(f"\n  Fleiss' Kappa (3 annotators, binary): {fk_bin:.4f}")

    ck_gold_ki_bin = cohens_kappa(gold_bin, ki_bin)
    ck_gold_ma_bin = cohens_kappa(gold_bin, ma_bin)
    ck_ki_ma_bin = cohens_kappa(ki_bin, ma_bin)
    print(f"\n  Pairwise Cohen's Kappa (binary):")
    print(f"    Gold vs Kittipat:    {ck_gold_ki_bin:.4f}")
    print(f"    Gold vs Mayuree:     {ck_gold_ma_bin:.4f}")
    print(f"    Kittipat vs Mayuree: {ck_ki_ma_bin:.4f}")

    # ── Disagreement analysis ─────────────────────────────────────────
    disagreements = find_disagreements(data)
    print(f"\n{'-'*70}")
    print(f"  DISAGREEMENTS ({len(disagreements)} items with any disagreement)")
    print(f"{'-'*70}")
    for d in disagreements:
        labels = [d["gold_original"], d["author_reannot"], d["kittipat"], d["mayuree"]]
        marker = " <-- GOLD DIFFERS" if d["gold_original"] != d["kittipat"] or d["gold_original"] != d["mayuree"] else ""
        print(f"  {d['gs_id']:8s}  Gold={d['gold_original']:14s}  "
              f"Re={d['author_reannot']:14s}  "
              f"Ki={d['kittipat']:14s}  Ma={d['mayuree']:14s}{marker}")

    # ── Interpretation ────────────────────────────────────────────────
    def interpret_kappa(k):
        if k >= 0.81: return "Almost perfect"
        if k >= 0.61: return "Substantial"
        if k >= 0.41: return "Moderate"
        if k >= 0.21: return "Fair"
        return "Slight"

    # ── Save results ──────────────────────────────────────────────────
    results = {
        "n_items": n,
        "annotators": ["author_gold", "author_reannotation", "kittipat", "mayuree"],
        "four_class": {
            "fleiss_kappa": round(fk_4class, 4),
            "fleiss_interpretation": interpret_kappa(fk_4class),
            "pairwise_cohens_kappa": {
                "gold_vs_kittipat": round(ck_gold_ki, 4),
                "gold_vs_mayuree": round(ck_gold_ma, 4),
                "gold_vs_author_reannot": round(ck_gold_re, 4),
                "kittipat_vs_mayuree": round(ck_ki_ma, 4),
                "author_reannot_vs_kittipat": round(ck_re_ki, 4),
                "author_reannot_vs_mayuree": round(ck_re_ma, 4),
            },
            "categories": sorted(set(data["gold"]) | set(data["kittipat"]) | set(data["mayuree"])),
            "distribution": {
                "gold": dict(Counter(data["gold"])),
                "kittipat": dict(Counter(data["kittipat"])),
                "mayuree": dict(Counter(data["mayuree"])),
                "author_reannot": dict(Counter(data["author_reannot"])),
            },
        },
        "binary": {
            "fleiss_kappa": round(fk_bin, 4),
            "fleiss_interpretation": interpret_kappa(fk_bin),
            "pairwise_cohens_kappa": {
                "gold_vs_kittipat": round(ck_gold_ki_bin, 4),
                "gold_vs_mayuree": round(ck_gold_ma_bin, 4),
                "kittipat_vs_mayuree": round(ck_ki_ma_bin, 4),
            },
        },
        "disagreements": disagreements,
        "n_disagreements": len(disagreements),
    }

    out_path = output_dir / "external_annotator_agreement.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Saved: {out_path}")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  4-class Fleiss' kappa = {fk_4class:.4f} ({interpret_kappa(fk_4class)})")
    print(f"  Binary  Fleiss' kappa = {fk_bin:.4f} ({interpret_kappa(fk_bin)})")
    print(f"  Kittipat vs Mayuree (4-class): kappa = {ck_ki_ma:.4f} ({interpret_kappa(ck_ki_ma)})")
    print(f"  Disagreements: {len(disagreements)}/{n} items")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
