"""Extract all property vocabulary from gold shapes, test data, and RDF converter."""
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# 1. Extract sh:path values from gold shapes
shapes_text = (PROJECT_ROOT / "shacl" / "shapes" / "ait_policy_shapes.ttl").read_text(encoding="utf-8")
paths_from_shapes = set(re.findall(r"sh:path\s+ait:(\w+)", shapes_text))

# 2. Extract ait: properties from test data
test_text = (PROJECT_ROOT / "shacl" / "test_data" / "tdd_test_data_fixed.ttl").read_text(encoding="utf-8")
props_from_test = set(re.findall(r"\bait:(\w+)\s+(?:true|false|\")", test_text))

# 3. Extract ait: properties from rdf_converter.py
converter_text = (PROJECT_ROOT / "db" / "rdf_converter.py").read_text(encoding="utf-8")
props_from_converter = set(re.findall(r"ait:(\w+)", converter_text))

# 4. Get classes to exclude
ontology_text = (PROJECT_ROOT / "shacl" / "ontology" / "ait_policy_ontology.ttl").read_text(encoding="utf-8")
classes_in_ontology = set(re.findall(r"ait:(\w+)\s+a\s+owl:Class", ontology_text))
target_classes = set(re.findall(r"sh:targetClass\s+ait:(\w+)", shapes_text))
entity_types = set(re.findall(r"a\s+ait:(\w+)", test_text))

exclude = classes_in_ontology | target_classes | entity_types | {"PolicyOntology"}

# 5. Merge and filter
all_props = paths_from_shapes | props_from_test | props_from_converter
properties = sorted(all_props - exclude)
single_char = [p for p in properties if len(p) <= 1]

print(f"=== STATS ===")
print(f"From gold shapes sh:path: {len(paths_from_shapes)}")
print(f"From test data:           {len(props_from_test)}")
print(f"From RDF converter:       {len(props_from_converter)}")
print(f"Classes to exclude:       {len(exclude)}")
print(f"Final property count:     {len(properties)}")
print(f"Single-char props:        {len(single_char)} -> {single_char}")
print()

# 6. Build vocabulary JSON
vocab = {}
for p in properties:
    sources = []
    if p in paths_from_shapes:
        sources.append("gold_shapes")
    if p in props_from_test:
        sources.append("test_data")
    if p in props_from_converter:
        sources.append("rdf_converter")
    vocab[p] = {
        "sources": sources,
        "is_single_char": len(p) <= 1,
    }

# Print summary
for p in properties:
    src_str = ", ".join(vocab[p]["sources"])
    marker = " [SINGLE-CHAR]" if vocab[p]["is_single_char"] else ""
    print(f"  {p:55s} [{src_str}]{marker}")

# 7. Save vocabulary JSON
out_path = PROJECT_ROOT / "shacl" / "ontology" / "property_vocabulary.json"
output = {
    "description": "Complete property vocabulary extracted from gold shapes, test data, and RDF converter.",
    "total_properties": len(properties),
    "single_char_count": len(single_char),
    "properties": vocab,
}
out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nSaved: {out_path}")

# 8. Also create a simple list for prompt injection
valid_props = [p for p in properties if len(p) > 1]
list_path = PROJECT_ROOT / "shacl" / "ontology" / "property_list.txt"
list_path.write_text("\n".join(valid_props), encoding="utf-8")
print(f"Saved: {list_path} ({len(valid_props)} non-single-char properties)")
