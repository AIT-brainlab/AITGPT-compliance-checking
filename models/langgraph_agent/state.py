from __future__ import annotations

from typing import Annotated, List, TypedDict
import operator


class SentenceItem(TypedDict, total=False):
    # required
    text: str
    page: int
    source: str
    # optional — populated by prefilter_node
    deontic_strength: str       # "strong" | "weak" | "consequence" | "none"
    speech_act: str             # "directive" | "commissive" | "prohibitive" | "assertive" | "suggestive"
    section_context: str
    section_weight: float
    confidence_boost: float


class RuleItem(TypedDict):
    rule_id: str
    text: str
    source_document: str
    rule_type: str          # obligation | permission | prohibition
    confidence: float
    prefilter_strength: str # strong | weak | consequence | none
    section_context: str


class FOLItem(TypedDict):
    rule_id: str
    text: str
    deontic_type: str
    deontic_formula: str
    fol_expansion: str
    parse_success: bool


class SHACLShape(TypedDict):
    rule_id: str
    turtle_text: str
    target_class: str
    deontic_type: str
    syntax_valid: bool
    generation_method: str  # fol_mediated | direct_nl


class PipelineState(TypedDict):
    # Input
    source: str          # "ait"
    pdf_dir: str         # path to institutional_policy/AIT/

    # Step 1 — extraction
    extracted_sentences: List[SentenceItem]
    total_sentences: int

    # Step 2 — classification
    candidates: List[SentenceItem]   # passed prefilter
    rules: List[RuleItem]            # confident: confidence >= 0.6
    uncertain_rules: List[RuleItem]  # uncertain: 0.4 <= confidence < 0.6

    # Step 3 — FOL
    fol_formulas: List[FOLItem]
    fol_failed: List[RuleItem]       # rules where FOL generation failed

    # Step 4 — SHACL
    shacl_shapes: Annotated[List[SHACLShape], operator.add]
    shacl_output_path: str

    # Step 5 — validation
    validation_results: dict
    conforms: bool

    # Step 6 — report
    report: dict

    # Meta
    current_step: str
    errors: Annotated[List[str], operator.add]  # accumulates across all nodes
