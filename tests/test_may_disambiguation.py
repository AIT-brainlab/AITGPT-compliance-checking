"""
Test suite for epistemic vs. deontic "may" disambiguation.

Contains ~50 labelled sentences covering:
- Deontic "may" (permission): agent-directed actions
- Epistemic "may" (possibility): descriptive possibilities
- Ambiguous cases

These serve as both unit tests and a calibration eval set for thesis reporting.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.prefilter import disambiguate_may


# ── Deontic "may" — permission sentences ──────────────────────────────────

DEONTIC_SENTENCES = [
    "Students may apply for a leave of absence.",
    "Faculty members may request additional office space.",
    "Students may submit their thesis before the deadline.",
    "Residents may use the gymnasium between 6am and 10pm.",
    "Students may access the library resources online.",
    "Researchers may file a formal complaint with the dean.",
    "Applicants may obtain application forms from the registrar.",
    "Students may appeal the decision within 14 days.",
    "A student may not disclose confidential research data.",
    "Staff members may not use university resources for personal gain.",
    "No student may not enter the examination hall after 30 minutes.",
    "Faculty may request sabbatical leave every seven years.",
    "Students may apply for financial aid through the portal.",
    "Graduate students may submit a revised thesis.",
    "Committee members may use university vehicles for official travel.",
]

# ── Epistemic "may" — descriptive/possibility sentences ───────────────────

EPISTEMIC_SENTENCES = [
    "Research may be sponsored by a government agency.",
    "Contracted research may entail confidentiality agreements.",
    "The committee may be composed of internal and external members.",
    "Registration fees may include laboratory charges.",
    "The program may be revised based on feedback.",
    "Test results may contain errors due to equipment malfunction.",
    "The curriculum may have prerequisites from other departments.",
    "Publication may be delayed due to review cycles.",
    "Course materials may include digital and print resources.",
    "Scholarships may be funded by external donors.",
    "The degree may be awarded posthumously.",
    "Some courses may be offered in a hybrid format.",
    "The internship may result in a full-time position.",
    "Exams may have both written and oral components.",
    "Faculty workload may include research supervision duties.",
]

# ── Ambiguous "may" — context-dependent ───────────────────────────────────

AMBIGUOUS_SENTENCES = [
    "A supervisor may assign additional coursework.",
    "The committee may decide to postpone the review.",
    "Students may find the resources helpful.",
    "The policy may change without prior notice.",
    "Members may attend the meeting remotely.",
    "The department may offer additional tutoring sessions.",
    "Students may take electives from other programs.",
    "The university may provide accommodation for visiting scholars.",
    "Faculty may participate in international conferences.",
    "Students may choose their thesis topic freely.",
]

# ── Sentences without "may" ───────────────────────────────────────────────

NO_MAY_SENTENCES = [
    "Students must submit their thesis by the final deadline.",
    "All fees shall be paid before registration.",
    "Plagiarism is strictly prohibited.",
    "The university provides library resources.",
    "Students should consider attending workshops.",
]


class TestDisambiguateMay:
    """Test the disambiguate_may function from core.prefilter."""

    @pytest.mark.parametrize("text", DEONTIC_SENTENCES)
    def test_deontic_may_detected(self, text: str):
        result = disambiguate_may(text)
        assert result == "deontic", (
            f"Expected 'deontic' for: {text!r}, got {result!r}"
        )

    @pytest.mark.parametrize("text", EPISTEMIC_SENTENCES)
    def test_epistemic_may_detected(self, text: str):
        result = disambiguate_may(text)
        assert result == "epistemic", (
            f"Expected 'epistemic' for: {text!r}, got {result!r}"
        )

    @pytest.mark.parametrize("text", AMBIGUOUS_SENTENCES)
    def test_ambiguous_may_returns_ambiguous(self, text: str):
        result = disambiguate_may(text)
        # Ambiguous cases should NOT be classified as epistemic
        # (they might be deontic or ambiguous — both are acceptable)
        assert result in ("deontic", "ambiguous"), (
            f"Ambiguous sentence misclassified as epistemic: {text!r}, got {result!r}"
        )

    @pytest.mark.parametrize("text", NO_MAY_SENTENCES)
    def test_no_may_returns_na(self, text: str):
        result = disambiguate_may(text)
        assert result == "n/a", (
            f"Expected 'n/a' for sentence without 'may': {text!r}, got {result!r}"
        )


class TestDisambiguationStats:
    """Aggregate stats for thesis reporting."""

    def test_overall_accuracy(self):
        """Ensure combined accuracy across deontic + epistemic is ≥80%."""
        correct = 0
        total = 0

        for text in DEONTIC_SENTENCES:
            total += 1
            if disambiguate_may(text) == "deontic":
                correct += 1

        for text in EPISTEMIC_SENTENCES:
            total += 1
            if disambiguate_may(text) == "epistemic":
                correct += 1

        accuracy = correct / total if total else 0
        print(f"\nMay disambiguation accuracy: {correct}/{total} = {accuracy:.1%}")
        assert accuracy >= 0.80, (
            f"Overall accuracy {accuracy:.1%} below 80% threshold"
        )
