"""Extract all 38 misclassified permission rules for manual review."""
import json, re, sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

gold = json.load(open('output/ait/gold_annotations_d1.json', 'r', encoding='utf-8'))
rules = json.load(open('output/ait/classified_rules.json', 'r', encoding='utf-8'))

llm_map = {r['rule_id']: r for r in rules}
perms = [g for g in gold if g['gold_type'] == 'permission']

wrong = []
correct = []
for p in perms:
    r = llm_map[p['rule_id']]
    if r['rule_type'] == 'permission':
        correct.append((p, r))
    else:
        wrong.append((p, r))

# Pattern analysis
has_may = re.compile(r'\bmay\b', re.I)
has_obl = re.compile(r'\b(must|shall|required|should|need to)\b', re.I)
has_not = re.compile(r'\b(may not|may only|cannot|shall not)\b', re.I)
has_perm = re.compile(r'\b(allowed|permitted|entitled|eligible|can choose|can opt|can request|can apply)\b', re.I)

# Build review document
output = []
output.append("# Permission Rules Audit — 38 Misclassified Cases")
output.append("")
output.append("Review each case and mark your judgment:")
output.append("- **GOLD CORRECT** = gold label is right, LLM is wrong (true error)")
output.append("- **LLM CORRECT** = LLM is actually right, gold label should change")
output.append("- **AMBIGUOUS** = genuinely borderline, could go either way")
output.append("")
output.append(f"Total permission rules: {len(perms)}")
output.append(f"Correctly classified: {len(correct)}")
output.append(f"Misclassified: {len(wrong)}")
output.append("")

# Group by LLM classification
by_llm = {}
for p, r in wrong:
    by_llm.setdefault(r['rule_type'], []).append((p, r))

for llm_type, items in sorted(by_llm.items()):
    output.append(f"---")
    output.append(f"")
    output.append(f"## Gold=Permission, LLM={llm_type.upper()} ({len(items)} cases)")
    output.append(f"")
    
    for i, (p, r) in enumerate(items, 1):
        text = p['text']
        markers = []
        if has_may.search(text): markers.append('"may"')
        if has_obl.search(text): markers.append('OBL-marker')
        if has_not.search(text): markers.append('RESTRICTIVE')
        if has_perm.search(text): markers.append('PERM-marker')
        
        output.append(f"### {i}. {p['rule_id']}")
        output.append(f"")
        output.append(f"> {text}")
        output.append(f"")
        output.append(f"- **Gold**: permission")
        output.append(f"- **LLM**: {r['rule_type']}")
        output.append(f"- **Markers**: {', '.join(markers) if markers else 'none'}")
        output.append(f"- **Your judgment**: [ ] GOLD CORRECT  [ ] LLM CORRECT  [ ] AMBIGUOUS")
        output.append(f"")

output.append(f"---")
output.append(f"")
output.append(f"## Summary Statistics")
output.append(f"")
output.append(f"After reviewing all 38 cases, tally:")
output.append(f"- Gold Correct (true LLM errors): ___")
output.append(f"- LLM Correct (gold label errors): ___")  
output.append(f"- Ambiguous: ___")
output.append(f"")
output.append(f"### Impact Calculation")
output.append(f"If X gold labels are corrected:")
output.append(f"- New permission count: 87 - X")
output.append(f"- New correct: 373 + X")
output.append(f"- New accuracy: (373 + X) / 443")
output.append(f"")

with open('evaluation/permission_audit.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print(f"Written {len(wrong)} cases to evaluation/permission_audit.md")
print(f"\nBreakdown: {dict((k, len(v)) for k, v in by_llm.items())}")
