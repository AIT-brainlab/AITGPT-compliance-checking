from __future__ import annotations

from langgraph.graph import END, StateGraph

from langgraph_agent.state import PipelineState
from langgraph_agent.edges.route_classify import route_classify

from langgraph_agent.nodes.extract import extract_node
from langgraph_agent.nodes.prefilter import prefilter_node
from langgraph_agent.nodes.classify import classify_node
from langgraph_agent.nodes.reclassify import reclassify_node
from langgraph_agent.nodes.fol import fol_node
from langgraph_agent.nodes.shacl import shacl_node
from langgraph_agent.nodes.direct_shacl import direct_shacl_node
from langgraph_agent.nodes.validate import validate_node
from langgraph_agent.nodes.report import report_node


def build_graph() -> StateGraph:
    g = StateGraph(PipelineState)

    # ── Nodes ──────────────────────────────────────────────────────────────
    g.add_node("extract",      extract_node)
    g.add_node("prefilter",    prefilter_node)
    g.add_node("classify",     classify_node)
    g.add_node("reclassify",   reclassify_node)
    g.add_node("fol",          fol_node)
    g.add_node("shacl",        shacl_node)
    g.add_node("direct_shacl", direct_shacl_node)
    g.add_node("validate",     validate_node)
    g.add_node("report",       report_node)

    # ── Fixed edges ────────────────────────────────────────────────────────
    g.set_entry_point("extract")
    g.add_edge("extract",      "prefilter")
    g.add_edge("prefilter",    "classify")
    g.add_edge("reclassify",   "fol")       # after second opinion → FOL
    # fol fans out to BOTH nodes in parallel:
    #   shacl       → handles the 454 successful FOL formulas
    #   direct_shacl → handles the N failed FOL formulas (NL fallback)
    g.add_edge("fol",          "shacl")
    g.add_edge("fol",          "direct_shacl")
    # Both converge back to validate
    g.add_edge("shacl",        "validate")
    g.add_edge("direct_shacl", "validate")
    g.add_edge("validate",     "report")
    g.add_edge("report",       END)

    # ── Conditional edges ──────────────────────────────────────────────────
    g.add_conditional_edges(
        "classify",
        route_classify,
        {
            "reclassify": "reclassify",
            "fol":        "fol",
            "end":        END,
        },
    )

    return g.compile()


# Allow `python -m langgraph_agent.graph` to print the Mermaid diagram
if __name__ == "__main__":
    graph = build_graph()
    print(graph.get_graph().draw_mermaid())
