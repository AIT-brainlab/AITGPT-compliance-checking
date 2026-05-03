import pytest
from langgraph_agent.graph import build_graph

def test_graph_compiles():
    """Verify that the LangGraph can be compiled and has the proper structure."""
    graph = build_graph()
    
    # Assert nodes are present
    assert "extract" in graph.nodes
    assert "classify" in graph.nodes
    assert "fol" in graph.nodes
    assert "shacl" in graph.nodes
    assert "validate" in graph.nodes
    assert "report" in graph.nodes
    
    # Verify graph can run a small dummy state if necessary, 
    # but graph.nodes is enough to prove successful scaffold.
    assert len(graph.nodes) > 0
