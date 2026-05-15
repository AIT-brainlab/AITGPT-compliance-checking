from langgraph_agent.state import PipelineState


def extract_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "extract"}


def prefilter_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "prefilter"}


def classify_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "classify"}


def reclassify_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "reclassify"}


def fol_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "fol"}


def shacl_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "shacl"}


def direct_shacl_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "direct_shacl"}


def validate_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "validate"}


def report_node(state: PipelineState) -> PipelineState:
    return {**state, "current_step": "report"}
