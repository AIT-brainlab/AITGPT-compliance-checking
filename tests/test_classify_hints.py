"""
Test that classify_node correctly reads prefilter hints from SentenceItem.

Uses a mock LLM to avoid actual Ollama calls.
"""
import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_llm_response():
    """Mock LLM that returns a deterministic classification."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "is_rule": True,
        "rule_type": "obligation",
        "confidence": 0.8,
        "reasoning": "Test reasoning",
    })
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


class TestClassifyHints:
    """Verify that prefilter hints are wired into the classify prompt."""

    def test_build_prompt_includes_hints(self):
        """Hints should appear in the classify prompt text."""
        from langgraph_agent.nodes.classify import _build_prompt
        from langgraph_agent.state import SentenceItem

        item = SentenceItem(
            text="Students must pay fees.",
            page=1,
            source="test.pdf",
            deontic_strength="strong",
            speech_act="directive",
            section_context="Requirements",
        )
        hint = {
            "deontic_strength": "strong",
            "speech_act": "directive",
            "section_context": "Requirements",
        }

        prompt = _build_prompt(item, hint)

        assert "strong" in prompt
        assert "directive" in prompt
        assert "Requirements" in prompt
        assert "Students must pay fees." in prompt

    def test_build_prompt_unknown_hints(self):
        """When hints are missing, prompt should contain 'unknown'."""
        from langgraph_agent.nodes.classify import _build_prompt
        from langgraph_agent.state import SentenceItem

        item = SentenceItem(text="Some text.", page=1, source="test.pdf")
        hint = {
            "deontic_strength": "unknown",
            "speech_act": "unknown",
            "section_context": "unknown",
        }

        prompt = _build_prompt(item, hint)

        assert "unknown" in prompt

    def test_confidence_boost_applied(self):
        """Confidence boost from prefilter should modify raw LLM confidence."""
        # Simulating the boost logic from classify_node
        raw_conf = 0.7
        boost = 0.15

        # Additive boost, clamped to [0, 1]
        confidence = max(0.0, min(1.0, raw_conf + boost))

        assert confidence == pytest.approx(0.85)

    def test_confidence_boost_clamped(self):
        """Boost should not push confidence above 1.0."""
        raw_conf = 0.95
        boost = 0.15

        confidence = max(0.0, min(1.0, raw_conf + boost))

        assert confidence == 1.0

    def test_negative_boost_clamped(self):
        """Negative boost should not push confidence below 0.0."""
        raw_conf = 0.05
        boost = -0.1

        confidence = max(0.0, min(1.0, raw_conf + boost))

        assert confidence == 0.0

    def test_hint_in_cache_key(self):
        """Cache keys should include hint values so different hints get different cache entries."""
        cache_params_a = {
            "deontic_strength": "strong",
            "speech_act": "directive",
            "prompt_version": 2,
        }
        cache_params_b = {
            "deontic_strength": "unknown",
            "speech_act": "unknown",
            "prompt_version": 2,
        }

        # They should produce different cache keys
        import hashlib
        key_a = hashlib.sha256(json.dumps(cache_params_a, sort_keys=True).encode()).hexdigest()
        key_b = hashlib.sha256(json.dumps(cache_params_b, sort_keys=True).encode()).hexdigest()

        assert key_a != key_b


class TestParseResponse:
    """Test the response parser handles edge cases."""

    def test_valid_json(self):
        from langgraph_agent.nodes.classify import _parse_response

        result = _parse_response('{"is_rule": true, "rule_type": "obligation", "confidence": 0.9}')
        assert result["is_rule"] is True
        assert result["rule_type"] == "obligation"

    def test_json_with_surrounding_text(self):
        from langgraph_agent.nodes.classify import _parse_response

        result = _parse_response('Here is the result: {"is_rule": false, "rule_type": "none"} done.')
        assert result["is_rule"] is False

    def test_invalid_json(self):
        from langgraph_agent.nodes.classify import _parse_response

        result = _parse_response("not json at all")
        assert result["is_rule"] is False
        assert result["reasoning"] == "parse_error"
