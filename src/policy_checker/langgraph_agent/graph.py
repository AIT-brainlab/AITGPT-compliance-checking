from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Any

from langgraph.graph import END, StateGraph

from policy_checker.langgraph_agent.edges.route_classify import route_classify
from policy_checker.langgraph_agent.state import PipelineState

NodeFn = Callable[[PipelineState], dict[str, Any]]

_NODE_SPECS = (
    ("extract", "policy_checker.langgraph_agent.nodes.extract", "extract_node"),
    ("prefilter", "policy_checker.langgraph_agent.nodes.prefilter", "prefilter_node"),
    ("classify", "policy_checker.langgraph_agent.nodes.classify", "classify_node"),
    ("reclassify", "policy_checker.langgraph_agent.nodes.reclassify", "reclassify_node"),
    ("fol", "policy_checker.langgraph_agent.nodes.fol", "fol_node"),
    ("shacl", "policy_checker.langgraph_agent.nodes.shacl", "shacl_node"),
    ("direct_shacl", "policy_checker.langgraph_agent.nodes.direct_shacl", "direct_shacl_node"),
    ("validate", "policy_checker.langgraph_agent.nodes.validate", "validate_node"),
    ("report", "policy_checker.langgraph_agent.nodes.report", "report_node"),
)

_FIXED_EDGES = (
    ("extract", "prefilter"),
    ("prefilter", "classify"),
    ("reclassify", "fol"),
    ("fol", "shacl"),
    ("fol", "direct_shacl"),
    ("shacl", "validate"),
    ("direct_shacl", "validate"),
    ("validate", "report"),
    ("report", END),
)


def _load_node(module_path: str, attr: str) -> NodeFn:
    try:
        return getattr(import_module(module_path), attr)
    except (AttributeError, ImportError):
        return getattr(import_module("policy_checker.langgraph_agent._stubs"), attr)


def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    for node_name, module_path, attr in _NODE_SPECS:
        graph.add_node(node_name, _load_node(module_path, attr))

    graph.set_entry_point("extract")
    for source, target in _FIXED_EDGES:
        graph.add_edge(source, target)

    graph.add_conditional_edges(
        "classify",
        route_classify,
        {"reclassify": "reclassify", "fol": "fol", "end": END},
    )

    return graph.compile()


if __name__ == "__main__":
    compiled = build_graph()
    print(compiled.get_graph().draw_mermaid())
