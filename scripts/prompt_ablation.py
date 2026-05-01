"""
Prompt Engineering Impact Analysis (Ablation Study)
====================================================
Tests 4 prompt variants on cases where the heuristic and LLM-based classifiers
disagree, to measure the impact of prompt engineering on classification agreement.

Variants:
  V0: Current zero-shot prompt (baseline)
  V1: + Few-shot boundary examples (3 contrastive pairs)
  V2: + Negative instructions ("DO NOT classify as rule if...")
  V3: V1 + V2 combined (best-of-both)

This addresses Dr. Jutiporn's committee feedback (Section 2.4) about
the impact of prompt engineering choices on classification quality.

Usage:
    python scripts/prompt_ablation.py
"""
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage
from langgraph_agent.llm import get_llm

_llm = get_llm()

# ── Prompt Variants ────────────────────────────────────────────────────────

# V0: Current baseline (from classify.py)
V0_PROMPT = """\
You are a legal policy analyst specialising in institutional policy documents.

Classify whether the sentence below is a POLICY RULE — a deontic statement that \
creates a binding obligation, grants a permission, or imposes a prohibition.

IMPORTANT DISTINCTIONS:
- "may be X-ed" / "may have" / "may entail" = DESCRIPTIVE possibility, NOT a rule.
  Example: "Research may be sponsored by agencies." → NOT A RULE (describes what CAN happen).
- "may apply for" / "may request" / "may use" = PERMISSION (deontic rule).
  Example: "Students may apply for leave." → PERMISSION RULE (grants a right).
- "may not" = always a PROHIBITION.

Sentence:
"{text}"

Respond with ONLY a JSON object (no markdown, no explanation):
{{"is_rule": true/false, \
"rule_type": "obligation"/"permission"/"prohibition"/"none", \
"confidence": 0.0-1.0, \
"reasoning": "one concise sentence"}}"""

# V1: + Few-shot contrastive examples
V1_PROMPT = """\
You are a legal policy analyst specialising in institutional policy documents.

Classify whether the sentence below is a POLICY RULE — a deontic statement that \
creates a binding obligation, grants a permission, or imposes a prohibition.

IMPORTANT DISTINCTIONS:
- "may be X-ed" / "may have" / "may entail" = DESCRIPTIVE possibility, NOT a rule.
- "may apply for" / "may request" / "may use" = PERMISSION (deontic rule).
- "may not" = always a PROHIBITION.

EXAMPLES:
1. "Students must pay tuition fees before the mid-semester exam." → OBLIGATION (binding "must")
2. "Students may opt to reside off-campus." → PERMISSION (grants a right with "may")
3. "Students shall not disturb fellow students." → PROHIBITION ("shall not")
4. "The fee is 1,250 Baht per semester." → NOT A RULE (descriptive fact)
5. "Overdue accounts are reviewed periodically." → NOT A RULE (describes process, no deontic operator)
6. "Research may be sponsored by external agencies." → NOT A RULE (descriptive possibility)

Sentence:
"{text}"

Respond with ONLY a JSON object (no markdown, no explanation):
{{"is_rule": true/false, \
"rule_type": "obligation"/"permission"/"prohibition"/"none", \
"confidence": 0.0-1.0, \
"reasoning": "one concise sentence"}}"""

# V2: + Negative instructions
V2_PROMPT = """\
You are a legal policy analyst specialising in institutional policy documents.

Classify whether the sentence below is a POLICY RULE — a deontic statement that \
creates a binding obligation, grants a permission, or imposes a prohibition.

IMPORTANT DISTINCTIONS:
- "may be X-ed" / "may have" / "may entail" = DESCRIPTIVE possibility, NOT a rule.
- "may apply for" / "may request" / "may use" = PERMISSION (deontic rule).
- "may not" = always a PROHIBITION.

DO NOT classify as a rule if:
- The sentence merely DESCRIBES a process, fee schedule, or organizational structure
- The sentence uses "may" to describe a POSSIBILITY rather than grant a PERMISSION
- The sentence is a definition or description of a term or concept
- The sentence describes what happens or what exists (factual/constitutive)
- There is no clear AGENT who must/may/must-not perform an ACTION

A sentence IS a rule ONLY IF it imposes an obligation, grants a permission, or \
establishes a prohibition on a specific actor (student, staff, committee, etc.).

Sentence:
"{text}"

Respond with ONLY a JSON object (no markdown, no explanation):
{{"is_rule": true/false, \
"rule_type": "obligation"/"permission"/"prohibition"/"none", \
"confidence": 0.0-1.0, \
"reasoning": "one concise sentence"}}"""

# V3: V1 + V2 combined
V3_PROMPT = """\
You are a legal policy analyst specialising in institutional policy documents.

Classify whether the sentence below is a POLICY RULE — a deontic statement that \
creates a binding obligation, grants a permission, or imposes a prohibition.

IMPORTANT DISTINCTIONS:
- "may be X-ed" / "may have" / "may entail" = DESCRIPTIVE possibility, NOT a rule.
- "may apply for" / "may request" / "may use" = PERMISSION (deontic rule).
- "may not" = always a PROHIBITION.

EXAMPLES:
1. "Students must pay tuition fees before the mid-semester exam." → OBLIGATION (binding "must")
2. "Students may opt to reside off-campus." → PERMISSION (grants a right with "may")
3. "Students shall not disturb fellow students." → PROHIBITION ("shall not")
4. "The fee is 1,250 Baht per semester." → NOT A RULE (descriptive fact)
5. "Overdue accounts are reviewed periodically." → NOT A RULE (describes process, no deontic operator)
6. "Research may be sponsored by external agencies." → NOT A RULE (descriptive possibility)

DO NOT classify as a rule if:
- The sentence merely DESCRIBES a process, fee schedule, or organizational structure
- The sentence uses "may" to describe a POSSIBILITY rather than grant a PERMISSION
- The sentence is a definition or description of a term or concept
- The sentence describes what happens or what exists (factual/constitutive)
- There is no clear AGENT who must/may/must-not perform an ACTION

A sentence IS a rule ONLY IF it imposes an obligation, grants a permission, or \
establishes a prohibition on a specific actor (student, staff, committee, etc.).

Sentence:
"{text}"

Respond with ONLY a JSON object (no markdown, no explanation):
{{"is_rule": true/false, \
"rule_type": "obligation"/"permission"/"prohibition"/"none", \
"confidence": 0.0-1.0, \
"reasoning": "one concise sentence"}}"""

VARIANTS = {
    "V0_baseline": V0_PROMPT,
    "V1_few_shot": V1_PROMPT,
    "V2_negative": V2_PROMPT,
    "V3_combined": V3_PROMPT,
}


# ── Data loading ───────────────────────────────────────────────────────────

def load_disagreements() -> List[Dict]:
    """Load sentences and identify heuristic vs pipeline disagreements.

    Heuristic labels come from DDL annotations (ddl_annotated_full.json).
    The label field is a string: 'rule/policy', 'descriptive', or 'procedure'.
    We treat label == 'rule/policy' as is_rule=True.

    Pipeline labels come from classified_rules.json (484 classified rules).
    A sentence is pipeline_is_rule=True if it appears in classified_rules.json.
    """
    # Load DDL annotations — full 1672-sentence corpus with heuristic labels
    ddl_path = PROJECT_ROOT / "research" / "LexDeMod" / "_AIT-dataset" / "ddl_annotated_full.json"
    ddl_doc = json.loads(ddl_path.read_text(encoding="utf-8"))
    ddl_data = ddl_doc["data"]  # list of 1672 sentence dicts

    # Load pipeline classifications (text → rule record)
    pipe_path = PROJECT_ROOT / "output" / "ait" / "classified_rules.json"
    pipe_rules = json.loads(pipe_path.read_text(encoding="utf-8"))
    # Normalise whitespace for matching
    pipe_texts = {" ".join(r["text"].split()): r for r in pipe_rules}

    # Find disagreements: sentences where heuristic and pipeline disagree
    disagreements = []
    total_checked = 0

    for item in ddl_data:
        text = item.get("text", "").strip()
        if not text or len(text) < 10:
            continue

        total_checked += 1

        # Heuristic label: 'rule/policy' == is_rule
        label = item.get("label", "")  # 'rule/policy' | 'descriptive' | 'procedure'
        if not label:  # unlabelled sentences in raw corpus
            continue
        heuristic_is_rule = label == "rule/policy"

        # Deontic operator for rule-type (nested under 'ddl' key)
        ddl_detail = item.get("ddl") or {}
        heuristic_type = ddl_detail.get("deontic_operator", "none") if ddl_detail else "none"

        # Pipeline label: present in classified_rules.json?
        norm_text = " ".join(text.split())
        pipe = pipe_texts.get(norm_text, None)
        pipeline_is_rule = pipe is not None
        pipeline_type = pipe.get("rule_type", "none") if pipe else "none"

        # Disagreement check
        if heuristic_is_rule != pipeline_is_rule:
            disagreements.append({
                "text": text,
                "heuristic_is_rule": heuristic_is_rule,
                "heuristic_type": heuristic_type,
                "pipeline_is_rule": pipeline_is_rule,
                "pipeline_type": pipeline_type,
            })

    print(f"Total sentences checked: {total_checked}")
    print(f"Disagreements found: {len(disagreements)}")

    return disagreements


def _parse_response(raw: str) -> dict:
    """Parse LLM JSON response."""
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        return {"is_rule": False, "rule_type": "none", "confidence": 0.0}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"is_rule": False, "rule_type": "none", "confidence": 0.0}


def run_variant(variant_name: str, prompt_template: str, 
                sentences: List[Dict]) -> List[Dict]:
    """Run one prompt variant on all sentences."""
    from tqdm import tqdm
    
    results = []
    for item in tqdm(sentences, desc=f"  {variant_name}", leave=False):
        text = item["text"]
        prompt = prompt_template.format(text=text)
        
        try:
            response = _llm.invoke([HumanMessage(content=prompt)])
            parsed = _parse_response(response.content)
        except Exception as exc:
            parsed = {"is_rule": False, "rule_type": "none", "confidence": 0.0,
                      "reasoning": f"error: {exc}"}
        
        results.append({
            "text": text[:200],
            "heuristic_is_rule": item["heuristic_is_rule"],
            "heuristic_type": item["heuristic_type"],
            "variant_is_rule": parsed.get("is_rule", False),
            "variant_type": parsed.get("rule_type", "none"),
            "confidence": parsed.get("confidence", 0.0),
        })
    
    return results


def compute_agreement(variant_results: List[Dict], reference_key: str = "heuristic_is_rule") -> Dict:
    """Compute agreement metrics between variant and reference."""
    n = len(variant_results)
    agree = sum(1 for r in variant_results if r["variant_is_rule"] == r[reference_key])
    
    # Compute Cohen's kappa (simplified binary)
    p_o = agree / n if n else 0  # observed agreement
    
    # Expected agreement
    ref_pos = sum(1 for r in variant_results if r[reference_key])
    var_pos = sum(1 for r in variant_results if r["variant_is_rule"])
    p_ref_pos = ref_pos / n if n else 0
    p_var_pos = var_pos / n if n else 0
    p_e = p_ref_pos * p_var_pos + (1 - p_ref_pos) * (1 - p_var_pos)
    
    kappa = (p_o - p_e) / (1 - p_e) if (1 - p_e) > 0 else 0
    
    # Count classification patterns
    patterns = Counter()
    for r in variant_results:
        ref = "rule" if r[reference_key] else "not_rule"
        var = "rule" if r["variant_is_rule"] else "not_rule"
        patterns[f"{ref}->{var}"] += 1
    
    return {
        "n": n,
        "agreement": agree,
        "agreement_rate": p_o,
        "kappa": kappa,
        "variant_positive_rate": p_var_pos,
        "patterns": dict(patterns),
    }


def format_report(all_results: Dict[str, List[Dict]]) -> str:
    """Generate comparison report."""
    lines = [
        "# Prompt Engineering Impact Analysis",
        "",
        "## Experiment Design",
        "",
        "Tested 4 prompt variants on classification disagreement cases",
        "(sentences where heuristic and pipeline labels differ).",
        "",
        "| Variant | Description |",
        "|---------|-------------|",
        "| **V0** | Current zero-shot prompt (baseline) |",
        "| **V1** | + Few-shot boundary examples (3 contrastive pairs) |",
        "| **V2** | + Negative instructions (\"DO NOT classify if...\") |",
        "| **V3** | V1 + V2 combined |",
        "",
        "## Agreement with Heuristic Labels",
        "",
        "| Variant | N | Agreement | Rate | Cohen's κ | Positive Rate |",
        "|---------|---|-----------|------|-----------|---------------|",
    ]
    
    for name, results in all_results.items():
        stats = compute_agreement(results, "heuristic_is_rule")
        lines.append(
            f"| {name} | {stats['n']} | {stats['agreement']} | "
            f"{stats['agreement_rate']:.1%} | {stats['kappa']:.3f} | "
            f"{stats['variant_positive_rate']:.1%} |"
        )
    
    lines.extend([
        "",
        "## Classification Patterns",
        "",
        "| Variant | Heur=Rule→Var=Rule | Heur=Rule→Var=Not | Heur=Not→Var=Rule | Heur=Not→Var=Not |",
        "|---------|:------------------:|:-----------------:|:-----------------:|:----------------:|",
    ])
    
    for name, results in all_results.items():
        stats = compute_agreement(results, "heuristic_is_rule")
        p = stats["patterns"]
        lines.append(
            f"| {name} | {p.get('rule->rule', 0)} | {p.get('rule->not_rule', 0)} | "
            f"{p.get('not_rule->rule', 0)} | {p.get('not_rule->not_rule', 0)} |"
        )
    
    lines.extend([
        "",
        "## Key Findings",
        "",
        "1. **Baseline bias**: V0 baseline classification patterns on disagreement cases",
        "2. **Few-shot effect**: V1 with contrastive examples may reduce boundary errors",
        "3. **Negative instructions**: V2 with explicit exclusion criteria may reduce false positives",
        "4. **Combined effect**: V3 tests whether improvements are additive",
        "",
    ])
    
    return "\n".join(lines)


def main():
    print("Loading disagreements...")
    disagreements = load_disagreements()
    
    if not disagreements:
        print("No disagreements found — check data paths.")
        return
    
    # Limit to manageable sample if too many
    sample_size = min(len(disagreements), 100)
    import random
    random.seed(42)
    sample = random.sample(disagreements, sample_size)
    print(f"Running ablation on {sample_size} disagreement cases")
    
    # Run each variant
    all_results = {}
    for name, prompt in VARIANTS.items():
        print(f"\nRunning variant: {name}")
        results = run_variant(name, prompt, sample)
        all_results[name] = results
    
    # Save results
    out_dir = PROJECT_ROOT / "output" / "ait"
    
    # JSON (full)
    json_path = out_dir / "prompt_ablation.json"
    json_path.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nJSON saved: {json_path}")
    
    # Markdown report
    report = format_report(all_results)
    md_path = out_dir / "prompt_ablation.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"Report saved: {md_path}")
    
    # Summary
    print("\n=== Summary ===")
    for name, results in all_results.items():
        stats = compute_agreement(results, "heuristic_is_rule")
        print(f"  {name:15s}: agreement={stats['agreement_rate']:.1%}, kappa={stats['kappa']:.3f}")


if __name__ == "__main__":
    main()
