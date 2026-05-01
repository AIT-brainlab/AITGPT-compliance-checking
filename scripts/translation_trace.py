"""
Translation Trace Table Generator
===================================
Generates a LaTeX-ready table showing the full pipeline trace for selected
representative rules: NL -> Classification -> FOL -> SHACL -> Validation.

This addresses Prof. Pong's committee feedback (Section 1.1) about demonstrating
meaning preservation through the pipeline stages.

Usage:
    python scripts/translation_trace.py
"""
import json
import re
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ── Selected rules for the trace ───────────────────────────────────────────
# These are chosen to be diverse across deontic types, formula quality, and
# pipeline outcomes.
SELECTED_RULES = [
    # 1. Obligation with "must" — semantic FOL (good pipeline output)
    "AIT-0051",  # "Students... are required to vacate their rooms" → O(VacateRoom(x))
    # 2. Prohibition with "shall not"
    "AIT-0084",  # "Students shall not disturb fellow students" → F(Action(x))
    # 3. Permission with "may" (disambiguated deontic)
    "AIT-0045",  # "students may opt to reside off-campus" → P(Action(x))
    # 4. Obligation with semantic predicate
    "AIT-0062",  # "required to vacate rooms within five days" → O(VacateRoom(x))
    # 5. Multi-condition / complex rule
    "AIT-0112",  # "expressing personal opinions outside the Institute" → O(expresses_personal_opinion...)
    # 6. Prohibition with "may not"
    "AIT-0048",  # "Families of non-resident students may not reside on campus"
    # 7. Rule where pipeline made interesting choice (too_strict)
    "AIT-0120",  # "Grievance Committee must be prepared" → O(prepared(...))
]


def load_data():
    """Load all pipeline outputs."""
    out = PROJECT_ROOT / "output" / "ait"
    rules = json.loads((out / "classified_rules.json").read_text(encoding="utf-8"))
    fols = json.loads((out / "fol_formulas.json").read_text(encoding="utf-8"))
    aligns = json.loads((out / "gold_alignment.json").read_text(encoding="utf-8"))
    evals = json.loads((out / "per_rule_eval.json").read_text(encoding="utf-8"))
    shapes_text = (out / "shapes_generated.ttl").read_text(encoding="utf-8")

    return {
        "rules": {r["rule_id"]: r for r in rules},
        "fols": {f["rule_id"]: f for f in fols},
        "aligns": {a["ait_id"]: a for a in aligns if a.get("aligned")},
        "evals": {e["ait_id"]: e for e in evals},
        "shapes": _split_shape_blocks(shapes_text),
    }


def _split_shape_blocks(ttl_text: str) -> dict:
    blocks = {}
    current_id = None
    current_lines = []
    for line in ttl_text.splitlines():
        m = re.match(r"# Rule:\s+(AIT-\d+)", line)
        if m:
            if current_id and current_lines:
                blocks[current_id] = "\n".join(current_lines)
            current_id = m.group(1)
            current_lines = [line]
        elif current_id:
            current_lines.append(line)
    if current_id and current_lines:
        blocks[current_id] = "\n".join(current_lines)
    return blocks


def truncate(text: str, max_len: int = 120) -> str:
    """Truncate text and clean whitespace."""
    text = " ".join(text.split())  # collapse whitespace
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def generate_trace(data: dict) -> list[dict]:
    """Generate trace entries for selected rules."""
    traces = []
    for rule_id in SELECTED_RULES:
        rule = data["rules"].get(rule_id, {})
        fol = data["fols"].get(rule_id, {})
        align = data["aligns"].get(rule_id, {})
        ev = data["evals"].get(rule_id, {})
        shape = data["shapes"].get(rule_id, "")

        # Extract key SHACL properties
        shape_paths = re.findall(r"sh:path\s+(ait:\w+)", shape)
        shape_target = re.search(r"sh:targetClass\s+(ait:\w+)", shape)
        shape_constraint = re.search(r"sh:(minCount|maxCount|hasValue)\s+(\S+)", shape)

        trace = {
            "rule_id": rule_id,
            "gs_id": align.get("gs_id", "—"),
            "nl_text": truncate(rule.get("text", ""), 150),
            "classification": rule.get("rule_type", "—"),
            "deontic_formula": fol.get("deontic_formula", "—"),
            "fol_expansion": truncate(fol.get("fol_expansion", "—"), 150),
            "shacl_target": shape_target.group(1) if shape_target else "—",
            "shacl_paths": shape_paths,
            "shacl_constraint": f"{shape_constraint.group(1)}={shape_constraint.group(2)}" if shape_constraint else "—",
            "verdict": ev.get("verdict", "not evaluated"),
            "cosine_sim": align.get("similarity", 0),
        }
        traces.append(trace)
    return traces


def format_latex(traces: list[dict]) -> str:
    """Generate LaTeX table for thesis inclusion."""
    lines = [
        r"\begin{longtable}{|p{1.5cm}|p{3.5cm}|p{1.5cm}|p{3.5cm}|p{2.5cm}|p{1.5cm}|}",
        r"\caption{Translation Trace: Pipeline Processing of Representative Rules}",
        r"\label{tab:translation-trace} \\",
        r"\hline",
        r"\textbf{Rule ID} & \textbf{Natural Language} & \textbf{Type} & \textbf{FOL Formula} & \textbf{SHACL Shape} & \textbf{Verdict} \\",
        r"\hline",
        r"\endfirsthead",
        r"\hline",
        r"\textbf{Rule ID} & \textbf{Natural Language} & \textbf{Type} & \textbf{FOL Formula} & \textbf{SHACL Shape} & \textbf{Verdict} \\",
        r"\hline",
        r"\endhead",
        "",
    ]

    for t in traces:
        # Escape LaTeX special chars
        nl = _latex_escape(t["nl_text"][:100])
        formula = _latex_escape(t["deontic_formula"][:80])
        paths = ", ".join(t["shacl_paths"][:2]) if t["shacl_paths"] else "—"
        shacl_info = f"target: {_latex_escape(t['shacl_target'])}\\newline paths: {_latex_escape(paths)}"
        
        lines.append(
            f"  {t['rule_id']} & {nl} & {t['classification']} & "
            f"\\texttt{{{formula}}} & {shacl_info} & {t['verdict']} \\\\"
        )
        lines.append(r"  \hline")

    lines.append(r"\end{longtable}")
    return "\n".join(lines)


def format_markdown(traces: list[dict]) -> str:
    """Generate Markdown table for review."""
    lines = [
        "# Translation Trace Table",
        "",
        "Pipeline processing trace for 7 representative rules demonstrating",
        "semantic preservation through each stage: NL → Classification → FOL → SHACL → Validation.",
        "",
    ]

    for i, t in enumerate(traces, 1):
        lines.extend([
            f"## Rule {i}: {t['rule_id']} (Gold: {t['gs_id']})",
            "",
            f"**Natural Language:**",
            f"> {t['nl_text']}",
            "",
            f"| Stage | Output |",
            f"|-------|--------|",
            f"| Classification | **{t['classification']}** |",
            f"| Deontic Formula | `{t['deontic_formula']}` |",
            f"| FOL Expansion | `{t['fol_expansion'][:120]}` |",
            f"| SHACL Target | `{t['shacl_target']}` |",
            f"| SHACL Paths | {', '.join(f'`{p}`' for p in t['shacl_paths'][:3]) or '—'} |",
            f"| SHACL Constraint | `{t['shacl_constraint']}` |",
            f"| Gold Alignment | cosine={t['cosine_sim']:.3f} |",
            f"| M4 Verdict | **{t['verdict']}** |",
            "",
        ])

    return "\n".join(lines)


def _latex_escape(text: str) -> str:
    """Escape LaTeX special characters."""
    chars = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
             "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
             "^": r"\^{}"}
    for k, v in chars.items():
        text = text.replace(k, v)
    return text


def main():
    data = load_data()
    traces = generate_trace(data)

    # Save Markdown (for review)
    md = format_markdown(traces)
    md_path = PROJECT_ROOT / "output" / "ait" / "translation_trace.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"Markdown saved: {md_path}")

    # Save LaTeX (for thesis)
    latex = format_latex(traces)
    latex_path = PROJECT_ROOT / "latex" / "translation_trace_table.tex"
    latex_path.write_text(latex, encoding="utf-8")
    print(f"LaTeX saved: {latex_path}")

    # Print summary
    print(f"\nGenerated traces for {len(traces)} rules:")
    for t in traces:
        formula = t['deontic_formula'][:50].encode('ascii', 'replace').decode('ascii')
        print(f"  {t['rule_id']:10s} ({t['classification']:12s}) -> {formula:50s} verdict={t['verdict']}")


if __name__ == "__main__":
    main()
