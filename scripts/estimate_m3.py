"""Analyze existing FOL output to estimate M3 improvement."""
import json
import re
from pathlib import Path

fol_path = Path("output/ait/fol_formulas.json")
if not fol_path.exists():
    print("No FOL output found. Run the pipeline first.")
    exit(1)

fols = json.loads(fol_path.read_text(encoding="utf-8"))
print(f"Total FOL formulas: {len(fols)}")

_PLACEHOLDER_ACTIONS = {
    "action", "subject", "predicate", "condition",
    "thing", "entity", "x", "y", "z", "n", "m",
}

_PLACEHOLDER_PREDS = re.compile(
    r"[OPF]\(\s*(Action|Subject|Predicate|Condition|Thing|Entity|x|y|z|\?\w)\s*[()]",
    re.IGNORECASE,
)

# Old M3 (formula + expansion only)
old_semantic = 0
# New M3 (formula + expansion + predicates.action)
new_semantic = 0

for f in fols:
    formula = f.get("deontic_formula", "")
    expansion = f.get("fol_expansion", "")

    formula_ok = formula and not _PLACEHOLDER_PREDS.search(formula)
    expansion_ok = expansion and not _PLACEHOLDER_PREDS.search(expansion)

    preds = f.get("predicates") or {}
    action = (preds.get("action", "") if isinstance(preds, dict) else "").strip()
    action_ok = len(action) > 1 and action.lower() not in _PLACEHOLDER_ACTIONS

    if formula_ok or expansion_ok:
        old_semantic += 1
    if formula_ok or expansion_ok or action_ok:
        new_semantic += 1

print(f"\nOld M3 (formula+expansion only): {old_semantic}/{len(fols)} = {old_semantic/len(fols)*100:.1f}%")
print(f"New M3 (+ predicates.action):    {new_semantic}/{len(fols)} = {new_semantic/len(fols)*100:.1f}%")
print(f"Improvement: +{new_semantic - old_semantic} formulas")
