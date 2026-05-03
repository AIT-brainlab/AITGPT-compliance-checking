"""
Test evaluation/per_rule_eval.py — per-rule SHACL evaluation logic.

Uses a minimal fixture with one gold shape + matching pipeline shape +
Pos/Neg test entities to verify the 2x2 verdict logic.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.per_rule_eval import RuleEvalResult, evaluate_rule, _entity_subgraph

from rdflib import Graph, Namespace, URIRef, Literal, RDF


AIT = Namespace("http://example.org/ait-policy#")
SH = Namespace("http://www.w3.org/ns/shacl#")


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def ontology():
    """Minimal ontology."""
    g = Graph()
    g.parse(data="""
    @prefix ait: <http://example.org/ait-policy#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ait:Student rdfs:subClassOf ait:Person .
    """, format="turtle")
    return g


@pytest.fixture
def test_data_correct():
    """Test data where Pos entity passes and Neg entity fails."""
    g = Graph()
    g.parse(data="""
    @prefix ait: <http://example.org/ait-policy#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

    ait:Pos_GS001 a ait:Student ;
        ait:payFee "true" .

    ait:Neg_GS001 a ait:Student .
    """, format="turtle")
    return g


@pytest.fixture
def test_data_too_permissive():
    """Test data where both Pos and Neg conform (shape too permissive)."""
    g = Graph()
    g.parse(data="""
    @prefix ait: <http://example.org/ait-policy#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

    ait:Pos_GS002 a ait:Student ;
        ait:payFee "true" .

    ait:Neg_GS002 a ait:Student ;
        ait:payFee "false" .
    """, format="turtle")
    return g


CORRECT_SHAPE = """
ait:TestShape a sh:NodeShape ;
    sh:targetClass ait:Student ;
    sh:property [
        sh:path ait:payFee ;
        sh:minCount 1 ;
    ] .
"""

ALWAYS_PASS_SHAPE = """
ait:TestShape2 a sh:NodeShape ;
    sh:targetClass ait:Student ;
    sh:property [
        sh:path ait:payFee ;
        sh:minCount 0 ;
    ] .
"""


# ── Tests ─────────────────────────────────────────────────────────────────

class TestRuleEvalResult:
    """Test the result dataclass."""

    def test_correct_verdict(self):
        r = RuleEvalResult("GS-001", "AIT-0001", True, True, "correct")
        assert r.verdict == "correct"
        assert r.pos_passes is True
        assert r.neg_fails is True

    def test_skipped_verdict(self):
        r = RuleEvalResult("GS-099", "AIT-0099", None, None, "skipped")
        assert r.verdict == "skipped"


class TestEvaluateRule:
    """Test evaluate_rule with fixtures."""

    def test_correct_shape(self, test_data_correct, ontology):
        result = evaluate_rule(
            gs_id="GS-001",
            ait_id="AIT-0001",
            pipeline_turtle=CORRECT_SHAPE,
            test_data=test_data_correct,
            ontology=ontology,
        )
        assert result.verdict == "correct"
        assert result.pos_passes is True
        assert result.neg_fails is True

    def test_too_permissive_shape(self, test_data_too_permissive, ontology):
        result = evaluate_rule(
            gs_id="GS-002",
            ait_id="AIT-0002",
            pipeline_turtle=CORRECT_SHAPE.replace("TestShape", "TestShape2"),
            test_data=test_data_too_permissive,
            ontology=ontology,
        )
        # Both entities have payFee, so both pass → too_permissive
        assert result.verdict == "too_permissive"

    def test_invalid_turtle_skipped(self, test_data_correct, ontology):
        result = evaluate_rule(
            gs_id="GS-001",
            ait_id="AIT-0001",
            pipeline_turtle="THIS IS NOT VALID TURTLE",
            test_data=test_data_correct,
            ontology=ontology,
        )
        assert result.verdict == "skipped"

    def test_missing_entities_skipped(self, ontology):
        """When test data has no matching entities, verdict should be skipped."""
        empty_graph = Graph()
        result = evaluate_rule(
            gs_id="GS-999",
            ait_id="AIT-0999",
            pipeline_turtle=CORRECT_SHAPE,
            test_data=empty_graph,
            ontology=ontology,
        )
        assert result.verdict == "skipped"


class TestEntitySubgraph:
    """Test _entity_subgraph extraction."""

    def test_extracts_correct_properties(self, test_data_correct):
        sub = _entity_subgraph(test_data_correct, AIT["Pos_GS001"])
        triples = list(sub)
        assert len(triples) >= 1  # at least rdf:type
        subjects = {str(s) for s, _, _ in triples}
        assert str(AIT["Pos_GS001"]) in subjects

    def test_missing_entity_returns_empty(self, test_data_correct):
        sub = _entity_subgraph(test_data_correct, AIT["NonExistent"])
        assert len(sub) == 0
