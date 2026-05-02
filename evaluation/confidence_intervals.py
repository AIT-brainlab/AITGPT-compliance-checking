"""
Compute Bootstrap 95% Confidence Intervals for thesis metrics M1-M4.

Usage:
    python -m evaluation.confidence_intervals

Outputs updated thesis_metrics_with_ci.json with confidence intervals.
"""
from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from typing import Tuple

PROJECT_ROOT = Path(__file__).parent.parent
N_BOOTSTRAP = 10000
RANDOM_SEED = 42


def bootstrap_ci(
    successes: int, total: int, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05
) -> Tuple[float, float, float]:
    """Compute bootstrap CI for a proportion.
    
    Returns (point_estimate, lower_bound, upper_bound).
    """
    if total == 0:
        return 0.0, 0.0, 0.0

    rng = np.random.default_rng(RANDOM_SEED)
    point = successes / total

    # Create binary outcome array
    outcomes = np.array([1] * successes + [0] * (total - successes))

    # Bootstrap resampling
    boot_proportions = np.zeros(n_boot)
    for i in range(n_boot):
        sample = rng.choice(outcomes, size=total, replace=True)
        boot_proportions[i] = sample.mean()

    lower = np.percentile(boot_proportions, 100 * (alpha / 2))
    upper = np.percentile(boot_proportions, 100 * (1 - alpha / 2))

    return point, lower, upper


def bootstrap_f1_ci(
    correct: int, too_strict: int, too_permissive: int,
    n_boot: int = N_BOOTSTRAP, alpha: float = 0.05
) -> Tuple[float, float, float]:
    """Compute bootstrap CI for F1 from correct/too_strict/too_permissive counts."""
    if correct + too_strict + too_permissive == 0:
        return 0.0, 0.0, 0.0

    rng = np.random.default_rng(RANDOM_SEED)

    # Encode verdicts: 0=correct, 1=too_strict, 2=too_permissive
    outcomes = np.array(
        [0] * correct + [1] * too_strict + [2] * too_permissive
    )
    total = len(outcomes)

    point_p = correct / (correct + too_strict) if (correct + too_strict) else 0
    point_r = correct / (correct + too_permissive) if (correct + too_permissive) else 0
    point_f1 = 2 * point_p * point_r / (point_p + point_r) if (point_p + point_r) else 0

    boot_f1 = np.zeros(n_boot)
    for i in range(n_boot):
        sample = rng.choice(outcomes, size=total, replace=True)
        c = (sample == 0).sum()
        ts = (sample == 1).sum()
        tp = (sample == 2).sum()
        p = c / (c + ts) if (c + ts) else 0
        r = c / (c + tp) if (c + tp) else 0
        boot_f1[i] = 2 * p * r / (p + r) if (p + r) else 0

    lower = np.percentile(boot_f1, 100 * (alpha / 2))
    upper = np.percentile(boot_f1, 100 * (1 - alpha / 2))

    return point_f1, lower, upper


def main():
    metrics_file = PROJECT_ROOT / "output" / "ait" / "thesis_metrics.json"
    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

    print("=" * 60)
    print("Bootstrap 95% Confidence Intervals (N=10,000)")
    print("=" * 60)

    # M1: Extraction coverage
    m1_point, m1_lo, m1_hi = bootstrap_ci(metrics["m1_aligned"], metrics["m1_total"])
    print(f"\nM1 Extraction Coverage:")
    print(f"  Point estimate: {m1_point:.3f}")
    print(f"  95% CI: [{m1_lo:.3f}, {m1_hi:.3f}]")
    print(f"  Report as: {m1_point*100:.1f}% [{m1_lo*100:.1f}%-{m1_hi*100:.1f}%]")

    # M2: Classification accuracy
    m2_point, m2_lo, m2_hi = bootstrap_ci(
        metrics["m2_correct_type"], metrics["m2_aligned_with_type"]
    )
    print(f"\nM2 Classification Accuracy:")
    print(f"  Point estimate: {m2_point:.3f}")
    print(f"  95% CI: [{m2_lo:.3f}, {m2_hi:.3f}]")
    print(f"  Report as: {m2_point*100:.1f}% [{m2_lo*100:.1f}%-{m2_hi*100:.1f}%]")

    # M3: FOL quality
    m3_point, m3_lo, m3_hi = bootstrap_ci(
        metrics["m3_semantic"], metrics["m3_total_fol"]
    )
    print(f"\nM3 FOL Quality:")
    print(f"  Point estimate: {m3_point:.3f}")
    print(f"  95% CI: [{m3_lo:.3f}, {m3_hi:.3f}]")
    print(f"  Report as: {m3_point*100:.1f}% [{m3_lo*100:.1f}%-{m3_hi*100:.1f}%]")

    # M4: Shape correctness F1
    m4_point, m4_lo, m4_hi = bootstrap_f1_ci(
        metrics["m4_correct"], metrics["m4_too_strict"], metrics["m4_too_permissive"]
    )
    print(f"\nM4 Shape Correctness (F1):")
    print(f"  Point estimate: {m4_point:.3f}")
    print(f"  95% CI: [{m4_lo:.3f}, {m4_hi:.3f}]")
    print(f"  Report as: F1={m4_point:.3f} [{m4_lo:.3f}-{m4_hi:.3f}]")

    # Save enhanced metrics
    enhanced = dict(metrics)
    enhanced["confidence_intervals"] = {
        "method": "bootstrap",
        "n_bootstrap": N_BOOTSTRAP,
        "alpha": 0.05,
        "m1_ci": [round(m1_lo, 4), round(m1_hi, 4)],
        "m2_ci": [round(m2_lo, 4), round(m2_hi, 4)],
        "m3_ci": [round(m3_lo, 4), round(m3_hi, 4)],
        "m4_f1_ci": [round(m4_lo, 4), round(m4_hi, 4)],
    }

    out_file = PROJECT_ROOT / "output" / "ait" / "thesis_metrics_with_ci.json"
    out_file.write_text(json.dumps(enhanced, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n\nSaved to: {out_file}")

    # Print thesis-ready table
    print("\n" + "=" * 60)
    print("THESIS-READY TABLE (copy to LaTeX/Markdown)")
    print("=" * 60)
    print(f"| Metric | Value | 95% CI |")
    print(f"|--------|-------|--------|")
    print(f"| M1 Extraction Coverage | {m1_point*100:.1f}% | [{m1_lo*100:.1f}%, {m1_hi*100:.1f}%] |")
    print(f"| M2 Classification Accuracy | {m2_point*100:.1f}% | [{m2_lo*100:.1f}%, {m2_hi*100:.1f}%] |")
    print(f"| M3 FOL Quality | {m3_point*100:.1f}% | [{m3_lo*100:.1f}%, {m3_hi*100:.1f}%] |")
    print(f"| M4 Shape Correctness (F1) | {m4_point:.3f} | [{m4_lo:.3f}, {m4_hi:.3f}] |")
    print(f"| M5 Reproducibility | 100% | N/A (deterministic) |")


if __name__ == "__main__":
    main()
