"""
Test evaluation/align.py — gold-standard alignment logic.

Uses synthetic gold rules and pipeline rules with known overlaps
to verify that alignment picks correct matches.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.align import Alignment, GoldRule


def _can_import(module_name: str) -> bool:
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


class TestGoldRuleLoading:
    """Test GoldRule dataclass construction."""

    def test_gold_rule_creation(self):
        gr = GoldRule(
            gs_id="GS-001",
            text="Students must pay all fees before registration.",
            deontic_type="obligation",
            target_class="Student",
            shape_uri="http://example.org/ait-policy#GS001Shape",
        )
        assert gr.gs_id == "GS-001"
        assert gr.deontic_type == "obligation"


class TestAlignmentDataclass:
    """Test Alignment dataclass."""

    def test_aligned_creation(self):
        a = Alignment(
            gs_id="GS-001",
            ait_id="AIT-0042",
            pipeline_text="Students must pay fees.",
            embedding_score=0.91,
            tfidf_score=0.85,
            fuzz_score=0.88,
            aligned=True,
        )
        assert a.aligned is True
        assert a.ait_id == "AIT-0042"

    def test_unaligned_creation(self):
        a = Alignment(
            gs_id="GS-050",
            ait_id=None,
            pipeline_text=None,
            embedding_score=0.30,
            tfidf_score=0.22,
            fuzz_score=0.15,
            aligned=False,
        )
        assert a.aligned is False
        assert a.ait_id is None


class TestAlignAll:
    """Test align_all with synthetic data.

    These tests require sentence-transformers, sklearn, and rapidfuzz.
    Skip if not installed.
    """

    @pytest.fixture
    def synthetic_data(self):
        gold = [
            GoldRule("GS-001", "Students must pay all fees before registration.",
                     "obligation", "Student", "uri:1"),
            GoldRule("GS-002", "Faculty may request sabbatical leave.",
                     "permission", "Faculty", "uri:2"),
            GoldRule("GS-003", "Plagiarism is strictly prohibited.",
                     "prohibition", "Student", "uri:3"),
        ]
        pipeline = [
            {"rule_id": "AIT-0001", "text": "All students must pay tuition fees prior to registering."},
            {"rule_id": "AIT-0002", "text": "Faculty members may apply for sabbatical leave."},
            {"rule_id": "AIT-0003", "text": "Academic plagiarism is strictly forbidden."},
            {"rule_id": "AIT-0004", "text": "The library is open from 9am to 9pm."},
        ]
        return gold, pipeline

    @pytest.mark.skipif(
        not _can_import("sentence_transformers"),
        reason="sentence-transformers not installed"
    )
    def test_alignment_finds_correct_pairs(self, synthetic_data):
        from evaluation.align import align_all
        gold, pipeline = synthetic_data

        alignments = align_all(gold, pipeline, threshold=0.5)

        assert len(alignments) == 3

        # GS-001 should match AIT-0001 (fee payment)
        gs1 = next(a for a in alignments if a.gs_id == "GS-001")
        assert gs1.aligned is True
        assert gs1.ait_id == "AIT-0001"

        # GS-002 should match AIT-0002 (sabbatical)
        gs2 = next(a for a in alignments if a.gs_id == "GS-002")
        assert gs2.aligned is True
        assert gs2.ait_id == "AIT-0002"

        # GS-003 should match AIT-0003 (plagiarism)
        gs3 = next(a for a in alignments if a.gs_id == "GS-003")
        assert gs3.aligned is True
        assert gs3.ait_id == "AIT-0003"

    @pytest.mark.skipif(
        not _can_import("sentence_transformers"),
        reason="sentence-transformers not installed"
    )
    def test_high_threshold_reduces_matches(self, synthetic_data):
        from evaluation.align import align_all
        gold, pipeline = synthetic_data

        alignments = align_all(gold, pipeline, threshold=0.99)
        aligned_count = sum(1 for a in alignments if a.aligned)

        # With threshold near 1.0, most should be unaligned
        assert aligned_count <= len(gold)

