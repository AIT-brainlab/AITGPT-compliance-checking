#!/usr/bin/env python3
"""
Hierarchical Pre-Filter for Policy Rule Classification
========================================================
Stage 1 of the Two-Stage Pipeline (Solution for Q1).

Applies heuristic checks BEFORE sending sentences to the LLM,
reducing noise and adding section context for improved classification.

Research basis:
- Goknil et al. (2024) — PAPEL: hierarchical filtering
- Searle (1969) — Speech Act Theory for deontic detection
- Brodie et al. (2006) — Section-aware classification

Usage:
    from core.prefilter import PreFilter
    pf = PreFilter()
    candidates = pf.filter_sentences(sentences, page_texts)
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


# =============================================================================
# SECTION-AWARE CLASSIFICATION WEIGHTS
# =============================================================================
# Based on Brodie et al. (2006) — section context improves accuracy by 8-12%

SECTION_WEIGHTS = {
    # High-deontic sections (boost rule likelihood)
    "requirements": 1.3,
    "requirement": 1.3,
    "regulations": 1.3,
    "regulation": 1.3,
    "rules": 1.3,
    "obligations": 1.3,
    "compliance": 1.2,
    "conduct": 1.2,
    "code of conduct": 1.3,
    "disciplinary": 1.2,
    "policy": 1.1,
    "policies": 1.1,
    "rights and responsibilities": 1.2,
    "responsibilities": 1.2,
    "penalties": 1.2,
    "sanctions": 1.2,
    "violations": 1.2,
    "prohibited": 1.3,
    "permissions": 1.2,
    "eligibility": 1.1,
    "accommodation": 1.1,
    "fees": 1.1,
    "payment": 1.1,
    "registration": 1.1,
    "academic integrity": 1.3,
    "grievance": 1.1,
    "appeal": 1.1,
    
    # Low-deontic sections (reduce rule likelihood)
    "introduction": 0.4,
    "overview": 0.4,
    "background": 0.4,
    "purpose": 0.5,
    "scope": 0.6,
    "definitions": 0.3,
    "definition": 0.3,
    "glossary": 0.2,
    "references": 0.2,
    "appendix": 0.5,
    "appendices": 0.5,
    "table of contents": 0.1,
    "acknowledgment": 0.2,
    "acknowledgement": 0.2,
    "history": 0.3,
    "revision history": 0.2,
    
    # Procedural sections (moderate — may contain rules but often procedures)
    "procedures": 0.7,
    "procedure": 0.7,
    "process": 0.7,
    "guidelines": 0.6,
    "guideline": 0.6,
    "recommendations": 0.5,
    "best practices": 0.5,
    "instructions": 0.6,
    "steps": 0.5,
}

# =============================================================================
# DEONTIC MARKERS (Modal Verbs + Deontic Phrases)
# =============================================================================

STRONG_DEONTIC_MARKERS = [
    r'\bmust\b', r'\bshall\b', r'\bis required\b', r'\bare required\b',
    r'\bis prohibited\b', r'\bare prohibited\b', r'\bprohibited from\b',
    r'\bnot allowed\b', r'\bnot permitted\b',
    r'\bmust not\b', r'\bshall not\b', r'\bcannot\b',
    r'\bis obligated\b', r'\bare obligated\b',
    r'\bis mandatory\b', r'\bmandatory\b',
    r'\bhas to\b', r'\bhave to\b',
]

WEAK_DEONTIC_MARKERS = [
    r'\bmay\b', r'\bshould\b', r'\bis encouraged\b',
    r'\bis expected\b', r'\bare expected\b',
    r'\bis entitled\b', r'\bare entitled\b',
    r'\ballowed to\b', r'\bpermitted to\b',
]

CONSEQUENCE_MARKERS = [
    r'\bwill be\b.*\b(suspended|terminated|dismissed|fined|expelled|penalized)\b',
    r'\bsubject to\b.*\b(disciplin|sanction|penalty|action)\b',
    r'\bfailure to\b.*\bwill\b',
    r'\bresult in\b.*\b(dismissal|suspension|penalty|fine)\b',
]

STRONG_PATTERN = re.compile('|'.join(STRONG_DEONTIC_MARKERS), re.IGNORECASE)
WEAK_PATTERN = re.compile('|'.join(WEAK_DEONTIC_MARKERS), re.IGNORECASE)
CONSEQUENCE_PATTERN = re.compile('|'.join(CONSEQUENCE_MARKERS), re.IGNORECASE)

# =============================================================================
# MAY DISAMBIGUATION
# =============================================================================

EPISTEMIC_MAY_PATTERNS = [
    re.compile(r"\bmay\s+be\b", re.IGNORECASE),
    re.compile(r"\bmay\s+have\b", re.IGNORECASE),
    re.compile(r"\bmay\s+entail\b", re.IGNORECASE),
    re.compile(r"\bmay\s+include\b", re.IGNORECASE),
    re.compile(r"\bmay\s+contain\b", re.IGNORECASE),
    re.compile(r"\bmay\s+result\s+in\b", re.IGNORECASE),
]

DEONTIC_MAY_PATTERNS = [
    re.compile(r"\bmay\s+(apply|request|submit|use|access|file|obtain|appeal)\b",
               re.IGNORECASE),
    re.compile(r"\bmay\s+not\b", re.IGNORECASE),
]

def disambiguate_may(text: str) -> str:
    if not re.search(r"\bmay\b", text, re.IGNORECASE):
        return "n/a"
    if any(p.search(text) for p in DEONTIC_MAY_PATTERNS):
        return "deontic"
    if any(p.search(text) for p in EPISTEMIC_MAY_PATTERNS):
        return "epistemic"
    return "ambiguous"

# =============================================================================
# SECTION HEADER DETECTION
# =============================================================================

SECTION_HEADER_PATTERNS = [
    # Numbered sections: "1.2 Requirements", "Section 3: Conduct" (allows leading whitespace)
    re.compile(r'^\s*[\d.]+\s+(.+)$', re.MULTILINE),
    # Roman numerals: "III. Procedures"
    re.compile(r'^\s*[IVXLC]+\.\s+(.+)$', re.MULTILINE),
    # Letter sections: "A. Definitions"
    re.compile(r'^\s*[A-Z]\.\s+(.+)$', re.MULTILINE),
    # All caps headers (allows leading whitespace)
    re.compile(r'^\s*([A-Z][A-Z\s&/]{4,})$', re.MULTILINE),
    # Article/Section keyword
    re.compile(r'^\s*(?:Article|Section|Part|Chapter)\s+\d*[.:]\s*(.+)$', re.MULTILINE | re.IGNORECASE),
]

# =============================================================================
# SPEECH ACT CATEGORIES (Searle, 1969)
# =============================================================================

SPEECH_ACTS = {
    "directive": {
        "description": "Commands/orders — high deontic content",
        "markers": ["must", "shall", "required", "has to", "have to"],
        "is_deontic": True,
    },
    "commissive": {
        "description": "Grants/promises — permission deontic",
        "markers": ["may", "entitled", "allowed", "permitted"],
        "is_deontic": True,
    },
    "prohibitive": {
        "description": "Bans/forbids — prohibition deontic",
        "markers": ["must not", "shall not", "cannot", "prohibited", "not allowed"],
        "is_deontic": True,
    },
    "assertive": {
        "description": "Facts/descriptions — NOT deontic",
        "markers": ["is", "are", "has", "have", "provides", "consists"],
        "is_deontic": False,
    },
    "suggestive": {
        "description": "Advice/recommendations — usually NOT deontic",
        "markers": ["should", "recommended", "encouraged", "advised"],
        "is_deontic": False,  # "should" is ambiguous; handled specially
    },
}


@dataclass
class FilterResult:
    """Result of pre-filtering a sentence."""
    text: str
    is_candidate: bool
    deontic_strength: str  # "strong", "weak", "consequence", "none"
    deontic_markers: List[str] = field(default_factory=list)
    section_context: str = ""
    section_weight: float = 1.0
    speech_act: str = ""
    rejection_reason: str = ""
    confidence_boost: float = 0.0


class PreFilter:
    """
    Hierarchical pre-filter for policy rule classification.
    
    Filters out non-rule sentences BEFORE LLM classification:
    1. Length check — skip headers (<5 words) and split long paragraphs
    2. Modal verb detection — check for deontic markers
    3. Section context — detect and weight by document section
    4. Speech act hint — classify directive/commissive/assertive
    """
    
    def __init__(self, min_words: int = 5, max_words: int = 150):
        self.min_words = min_words
        self.max_words = max_words
    
    def detect_section_headers(self, page_text: str) -> List[Tuple[int, str]]:
        """
        Detect section headers in a page of text.
        Returns list of (char_position, section_name) tuples.
        """
        headers = []
        for pattern in SECTION_HEADER_PATTERNS:
            for match in pattern.finditer(page_text):
                header_text = match.group(1) if match.lastindex else match.group(0)
                header_text = header_text.strip().rstrip(':.')
                headers.append((match.start(), header_text))
        
        # Sort by position
        headers.sort(key=lambda x: x[0])
        return headers
    
    def get_section_context(self, sentence_pos: int, headers: List[Tuple[int, str]]) -> Tuple[str, float]:
        """
        Determine which section a sentence belongs to based on nearest preceding header.
        Returns (section_name, section_weight).
        """
        current_section = ""
        for pos, header in headers:
            if pos < sentence_pos:
                current_section = header
            else:
                break
        
        if not current_section:
            return ("", 1.0)
        
        # Match section name to weights
        section_lower = current_section.lower().strip()
        
        # Try exact match first, then partial match
        weight = SECTION_WEIGHTS.get(section_lower, None)
        if weight is None:
            # Partial match — check if any key is contained in section name
            for key, w in SECTION_WEIGHTS.items():
                if key in section_lower:
                    weight = w
                    break
        
        if weight is None:
            weight = 1.0  # Neutral if unknown section
        
        return (current_section, weight)
    
    def check_deontic_markers(self, text: str) -> Tuple[str, List[str]]:
        """
        Check for deontic markers in text.
        Returns (strength, markers_found).
        
        Strength levels:
        - "strong": must, shall, required, prohibited (high confidence)
        - "consequence": penalty/sanction language (medium-high)
        - "weak": may, should, encouraged (needs LLM disambiguation)
        - "none": no deontic markers found
        """
        # Check strong markers first
        strong_matches = [m.group() for m in STRONG_PATTERN.finditer(text)]
        if strong_matches:
            return ("strong", strong_matches)
        
        # Check consequence markers
        consequence_matches = [m.group() for m in CONSEQUENCE_PATTERN.finditer(text)]
        if consequence_matches:
            return ("consequence", consequence_matches)
        
        # Check weak markers
        weak_matches = [m.group() for m in WEAK_PATTERN.finditer(text)]
        if weak_matches:
            return ("weak", weak_matches)
        
        return ("none", [])
    
    def classify_speech_act(self, text: str) -> str:
        """
        Classify the speech act type of a sentence (Searle, 1969).
        Returns: "directive", "commissive", "prohibitive", "assertive", "suggestive", or "unknown"
        """
        text_lower = text.lower()
        
        # Check prohibitive first (most specific)
        for marker in SPEECH_ACTS["prohibitive"]["markers"]:
            if marker in text_lower:
                return "prohibitive"
        
        # Check directive
        for marker in SPEECH_ACTS["directive"]["markers"]:
            if marker in text_lower:
                return "directive"
        
        # Check commissive
        for marker in SPEECH_ACTS["commissive"]["markers"]:
            if marker in text_lower:
                return "commissive"
        
        # Check suggestive
        for marker in SPEECH_ACTS["suggestive"]["markers"]:
            if marker in text_lower:
                return "suggestive"
        
        # Default to assertive
        return "assertive"
    
    def has_subject_verb_structure(self, text: str) -> bool:
        """
        Simple check for subject-verb-object structure.
        Returns True if the sentence appears to be a complete clause.
        """
        # Very basic: has at least one verb-like word and one noun-like word
        words = text.split()
        if len(words) < 3:
            return False
        
        # Check for typical subject indicators
        subject_indicators = [
            'student', 'students', 'faculty', 'staff', 'employee', 'employees',
            'adviser', 'advisor', 'member', 'members', 'applicant', 'applicants',
            'candidate', 'candidates', 'person', 'individual', 'committee',
            'university', 'institute', 'department', 'office', 'director',
            'registrar', 'president', 'dean', 'supervisor', 'resident',
            'sponsor', 'researcher', 'author', 'they', 'he', 'she', 'it',
            'the', 'a', 'an', 'all', 'any', 'each', 'every', 'no',
        ]
        
        has_subject = any(w.lower() in subject_indicators for w in words[:5])
        
        return has_subject
    
    def filter_sentence(self, text: str, page_text: str = "", 
                       sentence_pos: int = 0, 
                       headers: List[Tuple[int, str]] = None) -> FilterResult:
        """
        Apply all pre-filter checks to a single sentence.
        
        Returns FilterResult with is_candidate=True only if the sentence
        passes all heuristic checks and should be sent to the LLM.
        """
        text = text.strip()
        word_count = len(text.split())
        
        # Always compute speech_act for metadata, even if rejected
        speech_act = self.classify_speech_act(text)
        
        # --- Check 1: Length filter ---
        if word_count < self.min_words:
            return FilterResult(
                text=text, is_candidate=False,
                deontic_strength="none",
                speech_act=speech_act,
                rejection_reason=f"Too short ({word_count} words < {self.min_words})"
            )
        
        if word_count > self.max_words:
            return FilterResult(
                text=text, is_candidate=False,
                deontic_strength="none",
                speech_act=speech_act,
                rejection_reason=f"Too long ({word_count} words > {self.max_words}), needs splitting"
            )
        
        # --- Check 2: Deontic marker detection ---
        strength, markers = self.check_deontic_markers(text)
        
        # --- Check 3: Section context ---
        section_name = ""
        section_weight = 1.0
        if headers:
            section_name, section_weight = self.get_section_context(sentence_pos, headers)
        
        # speech_act already computed above (before length check)
        
        # --- Decision logic ---
        confidence_boost = 0.0
        
        if strength == "none":
            # No deontic markers at all
            # Still allow if in high-deontic section (may have implicit deontic content)
            if section_weight >= 1.2:
                # High-deontic section — send to LLM anyway but with low boost
                confidence_boost = -0.1
                return FilterResult(
                    text=text, is_candidate=True,
                    deontic_strength=strength, deontic_markers=markers,
                    section_context=section_name, section_weight=section_weight,
                    speech_act=speech_act, confidence_boost=confidence_boost
                )
            else:
                return FilterResult(
                    text=text, is_candidate=False,
                    deontic_strength=strength, deontic_markers=markers,
                    section_context=section_name, section_weight=section_weight,
                    speech_act=speech_act,
                    rejection_reason="No deontic markers found"
                )
        
        if strength == "strong":
            # Strong deontic markers — high confidence candidate
            confidence_boost = 0.15 * section_weight
        elif strength == "consequence":
            # Consequence language — likely describes penalties (is a rule)
            confidence_boost = 0.10 * section_weight
        elif strength == "weak":
            # Weak markers — need LLM to disambiguate
            if "may" in text.lower():
                # §7 — Ablation: skip may disambiguation if disabled
                import os
                if os.getenv("ABLATION_NO_MAY_DISAMBIG", "0") != "1":
                    may_sense = disambiguate_may(text)
                    if may_sense == "epistemic":
                        return FilterResult(
                            text=text, is_candidate=False,
                            deontic_strength="none",
                            rejection_reason="Epistemic 'may' (possibility, not permission)",
                            speech_act="assertive",
                            section_context=section_name, section_weight=section_weight,
                        )

            
            if section_weight < 0.5:
                # In a low-deontic section with weak markers → likely not a rule
                return FilterResult(
                    text=text, is_candidate=False,
                    deontic_strength=strength, deontic_markers=markers,
                    section_context=section_name, section_weight=section_weight,
                    speech_act=speech_act,
                    rejection_reason=f"Weak deontic marker in non-rule section '{section_name}'"
                )
            confidence_boost = 0.05 * section_weight
        
        return FilterResult(
            text=text, is_candidate=True,
            deontic_strength=strength, deontic_markers=markers,
            section_context=section_name, section_weight=section_weight,
            speech_act=speech_act, confidence_boost=confidence_boost
        )
    
    def filter_sentences(self, sentences: List[str], 
                        page_text: str = "") -> List[FilterResult]:
        """
        Filter a list of sentences from a page.
        
        Args:
            sentences: List of extracted sentences
            page_text: Full page text (for section header detection)
        
        Returns:
            List of FilterResult objects (both candidates and rejected)
        """
        # Detect section headers from page text
        headers = self.detect_section_headers(page_text) if page_text else []
        
        results = []
        current_pos = 0
        
        for sentence in sentences:
            # Approximate position in page text
            if page_text:
                pos = page_text.find(sentence, current_pos)
                if pos >= 0:
                    current_pos = pos + len(sentence)
                else:
                    pos = current_pos
            else:
                pos = current_pos
            
            result = self.filter_sentence(sentence, page_text, pos, headers)
            results.append(result)
        
        return results
    
    def get_candidates(self, sentences: List[str], 
                      page_text: str = "") -> List[FilterResult]:
        """
        Convenience method — returns only candidate sentences.
        """
        all_results = self.filter_sentences(sentences, page_text)
        return [r for r in all_results if r.is_candidate]
    
    def get_stats(self, results: List[FilterResult]) -> Dict:
        """
        Calculate filtering statistics.
        """
        total = len(results)
        candidates = sum(1 for r in results if r.is_candidate)
        rejected = total - candidates
        
        by_strength = {}
        for r in results:
            s = r.deontic_strength
            by_strength[s] = by_strength.get(s, 0) + 1
        
        by_speech_act = {}
        for r in results:
            sa = r.speech_act
            by_speech_act[sa] = by_speech_act.get(sa, 0) + 1
        
        rejection_reasons = {}
        for r in results:
            if r.rejection_reason:
                reason = r.rejection_reason.split('(')[0].strip()  # Simplify
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        
        return {
            "total_sentences": total,
            "candidates": candidates,
            "rejected": rejected,
            "filter_rate": f"{rejected / total * 100:.1f}%" if total > 0 else "0%",
            "by_deontic_strength": by_strength,
            "by_speech_act": by_speech_act,
            "rejection_reasons": rejection_reasons,
        }


# =============================================================================
# STANDALONE USAGE
# =============================================================================

if __name__ == "__main__":
    # Demo with sample sentences
    demo_sentences = [
        "Students must submit their thesis by May 15th.",
        "Faculty may request additional office space.",
        "Plagiarism is strictly prohibited.",
        "The university provides library resources.",
        "Students should consider attending workshops.",
        "Requirements",  # Header — should be filtered (too short)
        "All fees must be paid before the registration deadline to ensure enrollment.",
        "It may rain tomorrow.",
        "The committee shall review all applications within 14 days.",
        "This document was last updated on January 2024.",
        "Failure to comply will result in suspension.",
    ]
    
    demo_page = """
    1. Introduction
    The university provides library resources for all students.
    This document was last updated on January 2024.
    
    2. Requirements  
    Students must submit their thesis by May 15th.
    All fees must be paid before the registration deadline to ensure enrollment.
    
    3. Permissions
    Faculty may request additional office space.
    
    4. Academic Integrity
    Plagiarism is strictly prohibited.
    The committee shall review all applications within 14 days.
    Failure to comply will result in suspension.
    
    5. Guidelines
    Students should consider attending workshops.
    It may rain tomorrow.
    """
    
    pf = PreFilter()
    results = pf.filter_sentences(demo_sentences, demo_page)
    
    print("=" * 70)
    print("PRE-FILTER DEMO RESULTS")
    print("=" * 70)
    
    for r in results:
        status = "✅ CANDIDATE" if r.is_candidate else "❌ REJECTED"
        print(f"\n{status}: {r.text[:80]}...")
        if r.is_candidate:
            print(f"   Deontic: {r.deontic_strength} {r.deontic_markers}")
            print(f"   Section: '{r.section_context}' (weight={r.section_weight})")
            print(f"   Speech Act: {r.speech_act}")
            print(f"   Confidence Boost: {r.confidence_boost:+.2f}")
        else:
            print(f"   Reason: {r.rejection_reason}")
    
    print("\n" + "=" * 70)
    stats = pf.get_stats(results)
    print(f"STATS: {stats['candidates']}/{stats['total_sentences']} candidates "
          f"({stats['filter_rate']} filtered out)")
    print(f"By strength: {stats['by_deontic_strength']}")
    print(f"By speech act: {stats['by_speech_act']}")
