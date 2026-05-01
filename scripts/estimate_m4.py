"""Estimate M4 improvement by simulating property path normalization on existing shapes."""
import re
import difflib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Load property list
prop_list = (PROJECT_ROOT / "shacl" / "ontology" / "property_list.txt").read_text(encoding="utf-8").splitlines()
prop_list = [p.strip() for p in prop_list if p.strip()]
prop_lower_map = {}
for p in prop_list:
    low = p.lower()
    if low not in prop_lower_map:
        prop_lower_map[low] = p

# Load gold shapes paths
gold_text = (PROJECT_ROOT / "shacl" / "shapes" / "ait_policy_shapes.ttl").read_text(encoding="utf-8")
gold_paths = set(re.findall(r"sh:path\s+ait:(\w+)", gold_text))
# Exclude single-char
gold_paths_filtered = {p for p in gold_paths if len(p) > 1}

# Load pipeline shapes paths
pipeline_text = (PROJECT_ROOT / "output" / "ait" / "shapes_generated.ttl").read_text(encoding="utf-8")
pipeline_paths = re.findall(r"sh:path\s+ait:(\w+)", pipeline_text)

print(f"Gold standard paths (total):    {len(gold_paths)}")
print(f"Gold standard paths (filtered): {len(gold_paths_filtered)}")
print(f"Pipeline paths (total):         {len(pipeline_paths)}")
print(f"Pipeline unique paths:          {len(set(pipeline_paths))}")
print()

# Original overlap
orig_overlap = set(pipeline_paths) & gold_paths_filtered
print(f"=== ORIGINAL (no normalization) ===")
print(f"Overlap: {len(orig_overlap)} / {len(set(pipeline_paths))} pipeline paths match gold")
print(f"  Matching: {sorted(orig_overlap)[:10]}...")
print()

# With normalization
def normalize(raw):
    if raw in prop_list:
        return raw
    raw_lower = raw.lower()
    if raw_lower in prop_lower_map:
        return prop_lower_map[raw_lower]
    matches = difflib.get_close_matches(raw_lower, list(prop_lower_map.keys()), n=1, cutoff=0.6)
    if matches:
        return prop_lower_map[matches[0]]
    return raw_lower

normalized_paths = [normalize(p) for p in pipeline_paths]
norm_overlap = set(normalized_paths) & gold_paths_filtered
print(f"=== NORMALIZED (case + fuzzy match) ===")
print(f"Overlap: {len(norm_overlap)} / {len(set(normalized_paths))} pipeline paths match gold")
print(f"  Matching: {sorted(norm_overlap)[:15]}...")
print()

# Show some normalization examples
print("=== NORMALIZATION EXAMPLES ===")
examples = list(set(pipeline_paths))[:20]
for orig in sorted(examples):
    norm = normalize(orig)
    in_gold = "YES" if norm in gold_paths_filtered else "no"
    changed = "NORMALIZED" if norm != orig else "unchanged"
    print(f"  {orig:45s} -> {norm:45s}  [gold: {in_gold}] [{changed}]")
