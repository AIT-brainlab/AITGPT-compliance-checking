#!/usr/bin/env python3
"""
Pre-Filter Unit Tests
=====================
Tests for the hierarchical pre-filter module (Q1 Solution).

Usage:
    pytest tests/test_prefilter.py -v
    pytest tests/test_prefilter.py -v -m prefilter
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.prefilter import PreFilter, FilterResult


@pytest.fixture
def pf():
    """Create a PreFilter instance."""
    return PreFilter()


# =============================================================================
# DEONTIC MARKER DETECTION
# =============================================================================

class TestDeonticMarkerDetection:
    """Test that deontic markers are correctly detected."""
    
    @pytest.mark.prefilter
    def test_strong_must(self, pf):
        """'must' is a strong deontic marker."""
        r = pf.filter_sentence("Students must submit their thesis by May 15th.")
        assert r.is_candidate
        assert r.deontic_strength == "strong"
        assert any("must" in m.lower() for m in r.deontic_markers)
    
    @pytest.mark.prefilter
    def test_strong_shall(self, pf):
        """'shall' is a strong deontic marker."""
        r = pf.filter_sentence("The committee shall review all applications.")
        assert r.is_candidate
        assert r.deontic_strength == "strong"
    
    @pytest.mark.prefilter
    def test_strong_required(self, pf):
        """'is required' is a strong deontic marker."""
        r = pf.filter_sentence("A student is required to maintain good standing.")
        assert r.is_candidate
        assert r.deontic_strength == "strong"
    
    @pytest.mark.prefilter
    def test_strong_prohibited(self, pf):
        """'is prohibited' is a strong deontic marker."""
        r = pf.filter_sentence("Plagiarism is prohibited in all forms.")
        assert r.is_candidate
        assert r.deontic_strength == "strong"
    
    @pytest.mark.prefilter
    def test_weak_may(self, pf):
        """'may' is a weak deontic marker."""
        r = pf.filter_sentence("Faculty may request additional office space.")
        assert r.is_candidate
        assert r.deontic_strength == "weak"
    
    @pytest.mark.prefilter
    def test_weak_should(self, pf):
        """'should' is a weak deontic marker."""
        r = pf.filter_sentence("Students should consider attending workshops.")
        assert r.is_candidate
        assert r.deontic_strength == "weak"
    
    @pytest.mark.prefilter
    def test_consequence_language(self, pf):
        """Consequence language should be detected."""
        r = pf.filter_sentence("Failure to comply will result in suspension from the program.")
        assert r.is_candidate
        assert r.deontic_strength in ("consequence", "strong")
    
    @pytest.mark.prefilter
    def test_no_deontic_markers(self, pf):
        """Sentences without deontic markers should be rejected."""
        r = pf.filter_sentence("The university provides library resources to all students.")
        assert not r.is_candidate
        assert r.deontic_strength == "none"
    
    @pytest.mark.prefilter
    def test_factual_statement_rejected(self, pf):
        """Factual descriptions should be rejected."""
        r = pf.filter_sentence("This document was last updated on January 2024.")
        assert not r.is_candidate


# =============================================================================
# LENGTH FILTERING
# =============================================================================

class TestLengthFiltering:
    """Test sentence length checks."""
    
    @pytest.mark.prefilter
    def test_too_short_rejected(self, pf):
        """Headers and very short text should be rejected."""
        r = pf.filter_sentence("Requirements")
        assert not r.is_candidate
        assert "Too short" in r.rejection_reason
    
    @pytest.mark.prefilter
    def test_very_short_rejected(self, pf):
        """Single words should be rejected."""
        r = pf.filter_sentence("Hello")
        assert not r.is_candidate
    
    @pytest.mark.prefilter
    def test_normal_length_accepted(self, pf):
        """Normal-length sentences with deontic markers should pass."""
        r = pf.filter_sentence("Students must pay all tuition fees before the registration deadline.")
        assert r.is_candidate
    
    @pytest.mark.prefilter
    def test_too_long_rejected(self):
        """Very long sentences should be rejected."""
        pf = PreFilter(max_words=20)
        long_text = "Students must " + " ".join(["word"] * 25) + " by the deadline."
        r = pf.filter_sentence(long_text)
        assert not r.is_candidate
        assert "Too long" in r.rejection_reason


# =============================================================================
# SECTION CONTEXT
# =============================================================================

class TestSectionContext:
    """Test section-aware classification."""
    
    @pytest.mark.prefilter
    def test_high_deontic_section_boosts(self, pf):
        """High-deontic sections should boost confidence."""
        page = """
        2. Requirements
        Students must submit their thesis by May 15th.
        """
        results = pf.filter_sentences(
            ["Students must submit their thesis by May 15th."],
            page
        )
        assert len(results) == 1
        r = results[0]
        assert r.is_candidate
        assert r.section_weight >= 1.2
        assert r.confidence_boost > 0
    
    @pytest.mark.prefilter
    def test_low_deontic_section_reduces(self, pf):
        """Low-deontic sections should reduce confidence for weak markers."""
        page = """
        1. Introduction
        Students should consider attending workshops.
        """
        results = pf.filter_sentences(
            ["Students should consider attending workshops."],
            page
        )
        assert len(results) == 1
        r = results[0]
        # Weak marker ("should") in Introduction (weight < 0.5) → rejected
        assert not r.is_candidate or r.section_weight < 0.5
    
    @pytest.mark.prefilter
    def test_section_header_detection(self, pf):
        """Section headers should be detected from page text."""
        page = """
        1. Introduction
        Overview text here.
        
        2. Requirements
        Rule text here.
        
        3. Procedures
        Steps here.
        """
        headers = pf.detect_section_headers(page)
        header_names = [h[1] for h in headers]
        assert any("Introduction" in h for h in header_names)
        assert any("Requirements" in h for h in header_names)
    
    @pytest.mark.prefilter
    def test_definitions_section_rejected(self, pf):
        """Weak markers in Definitions section should be rejected."""
        page = """
        A. Definitions
        The term 'student' may refer to any enrolled individual.
        """
        results = pf.filter_sentences(
            ["The term 'student' may refer to any enrolled individual."],
            page
        )
        assert len(results) == 1
        r = results[0]
        # Weak "may" in Definitions (weight 0.3) → should be rejected
        assert not r.is_candidate


# =============================================================================
# SPEECH ACT CLASSIFICATION
# =============================================================================

class TestSpeechActClassification:
    """Test speech act type detection."""
    
    @pytest.mark.prefilter
    def test_directive(self, pf):
        """'must/shall' should classify as directive."""
        r = pf.filter_sentence("Students must register by September 1.")
        assert r.speech_act == "directive"
    
    @pytest.mark.prefilter
    def test_commissive(self, pf):
        """'may/entitled' should classify as commissive."""
        r = pf.filter_sentence("Faculty may request sabbatical leave.")
        assert r.speech_act == "commissive"
    
    @pytest.mark.prefilter
    def test_prohibitive(self, pf):
        """'must not/cannot' should classify as prohibitive."""
        r = pf.filter_sentence("Students must not plagiarize any work.")
        assert r.speech_act == "prohibitive"
    
    @pytest.mark.prefilter
    def test_suggestive(self, pf):
        """'should/recommended' should classify as suggestive."""
        r = pf.filter_sentence("Students should attend orientation sessions regularly.")
        assert r.speech_act == "suggestive"
    
    @pytest.mark.prefilter
    def test_assertive(self, pf):
        """Factual descriptions should classify as assertive."""
        r = pf.filter_sentence("The library provides access to digital resources.")
        assert r.speech_act == "assertive"


# =============================================================================
# FILTERING STATISTICS
# =============================================================================

class TestFilteringStats:
    """Test filtering statistics calculation."""
    
    @pytest.mark.prefilter
    def test_stats_counts(self, pf):
        """Statistics should correctly count candidates and rejections."""
        sentences = [
            "Students must submit their thesis by May 15th.",   # candidate
            "The university provides library resources.",        # rejected
            "Requirements",                                     # rejected (short)
            "Faculty may request office space.",                 # candidate
        ]
        results = pf.filter_sentences(sentences)
        stats = pf.get_stats(results)
        
        assert stats["total_sentences"] == 4
        assert stats["candidates"] == 2
        assert stats["rejected"] == 2
    
    @pytest.mark.prefilter
    def test_get_candidates_only(self, pf):
        """get_candidates should return only passing sentences."""
        sentences = [
            "Students must pay all tuition fees on time.",
            "The sky is a beautiful shade of blue today.",
            "Faculty shall review applications within two weeks.",
        ]
        candidates = pf.get_candidates(sentences)
        assert len(candidates) == 2
        for c in candidates:
            assert c.is_candidate


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
