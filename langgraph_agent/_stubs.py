from __future__ import annotations

from collections.abc import Callable

from langgraph_agent.state import PipelineState


def _stub_node(step: str) -> Callable[[PipelineState], PipelineState]:
    def node(state: PipelineState) -> PipelineState:
        return {**state, "current_step": step}

    node.__name__ = f"{step}_node"
    return node


extract_node = _stub_node("extract")
prefilter_node = _stub_node("prefilter")
classify_node = _stub_node("classify")
reclassify_node = _stub_node("reclassify")
fol_node = _stub_node("fol")
shacl_node = _stub_node("shacl")
direct_shacl_node = _stub_node("direct_shacl")
validate_node = _stub_node("validate")
report_node = _stub_node("report")
