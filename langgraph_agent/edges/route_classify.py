from langgraph_agent.state import PipelineState

CONFIDENCE_HIGH = 0.6
CONFIDENCE_LOW = 0.4


def route_classify(state: PipelineState) -> str:
    """Route after classify_node based on what was found."""
    has_confident = bool(state.get("rules"))
    has_uncertain = bool(state.get("uncertain_rules"))

    if not has_confident and not has_uncertain:
        return "end"
    if has_uncertain:
        return "reclassify"
    return "fol"
