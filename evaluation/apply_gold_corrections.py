"""Apply 12 gold label corrections and re-run evaluation."""
import json, sys

sys.stdout.reconfigure(encoding='utf-8')

gold_path = 'output/ait/gold_annotations_d1.json'
gold = json.load(open(gold_path, 'r', encoding='utf-8'))

# 12 corrections: permission -> correct type
corrections = {
    # Permission -> Obligation (10 cases)
    "AIT-0177": "obligation",   # "You may find it necessary" - epistemic may
    "AIT-0186": "obligation",   # Fee schedule - factual statement
    "AIT-0227": "obligation",   # "students will be provided" - announcement
    "AIT-0275": "obligation",   # "may be considered grounds" - consequence
    "AIT-0282": "obligation",   # "may sometimes follow" - descriptive
    "AIT-0287": "obligation",   # "may only be initiated" - restrictive
    "AIT-0167": "obligation",   # "may consist of" - descriptive composition
    "AIT-0246": "obligation",   # "allowed to max 40 hrs" - obligation cap
    "AIT-0247": "obligation",   # "allowed to max 60 hrs" - obligation cap
    "AIT-0248": "obligation",   # "allowed to max 80 hrs" - obligation cap
    # Permission -> Prohibition (2 cases)
    "AIT-0147": "prohibition",  # "may not deface or vandalize" - textbook prohibition
    "AIT-0274": "prohibition",  # "will not be tolerated" - prohibition
}

applied = 0
for item in gold:
    if item['rule_id'] in corrections:
        old = item['gold_type']
        new = corrections[item['rule_id']]
        print(f"  {item['rule_id']}: {old} -> {new}")
        item['gold_type'] = new
        applied += 1

print(f"\nApplied {applied} corrections")

# Save
with open(gold_path, 'w', encoding='utf-8') as f:
    json.dump(gold, f, indent=2, ensure_ascii=False)
print(f"Saved to {gold_path}")

# Verify new distribution
from collections import Counter
dist = Counter(g['gold_type'] for g in gold)
print(f"\nNew gold distribution:")
for t, c in sorted(dist.items()):
    print(f"  {t}: {c}")
print(f"  Total: {sum(dist.values())}")
