"""
Corpus Configuration Loader
============================
Loads domain-specific settings from ``config/<corpus>.yaml`` so the pipeline
can switch between corpora by changing a single CLI flag.

Usage::

    from langgraph_agent.corpus_config import get_corpus_config

    cfg = get_corpus_config("ait")
    print(cfg.vocabulary_path)        # Path to property_list.txt
    print(cfg.domain_words)           # list[str]
    print(cfg.fol_examples_block())   # formatted string for FOL prompt
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None  # graceful fallback — see _load_yaml()

from policy_checker import PROJECT_ROOT

# ── Dataclass ─────────────────────────────────────────────────────────────

@dataclass
class CorpusConfig:
    """Immutable, validated corpus configuration."""

    # Identity
    name: str
    display_name: str
    namespace: str
    prefix: str

    # Paths (absolute, resolved from PROJECT_ROOT)
    pdf_dir: Path
    ontology_path: Path
    vocabulary_path: Path
    gold_shapes_path: Path
    test_data_path: Path

    # Prompt customisation
    fol_examples: List[dict] = field(default_factory=list)

    # SHACL target class mapping
    target_class_patterns: List[Tuple[re.Pattern, str]] = field(default_factory=list)

    # Domain vocabulary
    domain_words: List[str] = field(default_factory=list)

    # Extra stop words
    stop_words_extra: List[str] = field(default_factory=list)

    # ── Derived helpers ───────────────────────────────────────────────────

    def load_vocabulary(self) -> List[str]:
        """Load the property vocabulary list from file."""
        if not self.vocabulary_path.exists():
            return []
        return [
            line.strip()
            for line in self.vocabulary_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and len(line.strip()) > 2
        ]

    def vocabulary_hint(self) -> str:
        """Formatted vocabulary string for injection into LLM prompts."""
        props = self.load_vocabulary()
        if not props:
            return "(no domain vocabulary available — create a new camelCase predicate)"
        return ", ".join(props)

    def fol_examples_block(self) -> str:
        """Format FOL examples for injection into the prompt template."""
        if not self.fol_examples:
            return "(no domain-specific examples available)"

        lines = []
        for ex in self.fol_examples:
            text = ex["text"]
            dt = ex["deontic_type"]
            formula = ex["formula"]
            expansion = ex["expansion"]
            action = ex["action"]
            lines.append(
                f'Rule: "{text}"\n'
                f'Good: {{"deontic_type": "{dt}", '
                f'"deontic_formula": "{formula}", '
                f'"fol_expansion": "{expansion}", '
                f'"predicates": {{"subject": "...", "action": "{action}", "condition": ""}}, '
                f'"shacl_hint": "{action} property"}}'
            )
        return "\n\n".join(lines)

    def target_class_for(self, rule_text: str) -> str:
        """Return the OWL target class for a given rule text."""
        text_lower = rule_text.lower()
        for pattern, cls in self.target_class_patterns:
            if pattern.search(text_lower):
                return cls
        return "Person"  # sensible default

    def sorted_domain_words(self) -> List[str]:
        """Domain words sorted by length descending (for greedy matching)."""
        return sorted(self.domain_words, key=len, reverse=True)

    def full_stop_words(self) -> frozenset:
        """Universal stop words + corpus-specific extras."""
        return _UNIVERSAL_STOP_WORDS | frozenset(self.stop_words_extra)


# ── Universal stop words (language-level, not domain-level) ───────────────

_UNIVERSAL_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "must", "need", "ought",
    "and", "or", "but", "if", "then", "else", "when", "where", "who",
    "which", "what", "that", "this", "these", "those", "it", "its",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "over", "out", "up", "down", "off", "about",
    "not", "no", "nor", "only", "also", "very", "just", "than", "more",
    "most", "other", "some", "any", "all", "each", "every", "both",
    "few", "many", "much", "such", "own", "same", "so", "too",
})


# ── Loading & caching ────────────────────────────────────────────────────

_CONFIG_CACHE: Dict[str, CorpusConfig] = {}


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, with a pure-Python fallback for simple configs."""
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal fallback parser for simple flat YAML (no anchors, no complex nesting)
    # Good enough for our config structure
    import json
    # Try treating it as simplified YAML → convert to JSON-ish
    raise ImportError(
        "PyYAML is required: pip install pyyaml --break-system-packages"
    )


def _resolve_path(raw: str) -> Path:
    """Resolve a config path relative to PROJECT_ROOT."""
    p = Path(raw)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def load_corpus_config(corpus_name: str) -> CorpusConfig:
    """Load and validate a corpus configuration from ``config/<name>.yaml``."""
    config_path = PROJECT_ROOT / "config" / f"{corpus_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No corpus config found at {config_path}. "
            f"Create one by copying config/ait.yaml and adjusting the values."
        )

    raw = _load_yaml(config_path)

    corpus = raw.get("corpus", {})
    paths = raw.get("paths", {})
    prompts = raw.get("prompts", {})

    # Parse target class patterns
    tc_patterns = []
    for item in raw.get("target_class_patterns", []):
        tc_patterns.append((
            re.compile(item["pattern"], re.IGNORECASE),
            item["class"],
        ))

    cfg = CorpusConfig(
        name=corpus.get("name", corpus_name),
        display_name=corpus.get("display_name", corpus_name),
        namespace=corpus.get("namespace", f"http://example.org/{corpus_name}-policy#"),
        prefix=corpus.get("prefix", corpus_name),
        pdf_dir=_resolve_path(paths.get("pdf_dir", f"institutional_policy/{corpus_name}")),
        ontology_path=_resolve_path(paths.get("ontology", f"shacl/ontology/{corpus_name}_policy_ontology.ttl")),
        vocabulary_path=_resolve_path(paths.get("vocabulary", f"shacl/ontology/property_list.txt")),
        gold_shapes_path=_resolve_path(paths.get("gold_shapes", "")),
        test_data_path=_resolve_path(paths.get("test_data", "")),
        fol_examples=prompts.get("fol_examples", []),
        target_class_patterns=tc_patterns,
        domain_words=raw.get("domain_words", []),
        stop_words_extra=raw.get("stop_words_extra", []),
    )

    return cfg


def get_corpus_config(corpus_name: Optional[str] = None) -> CorpusConfig:
    """Get a corpus config, with caching. Reads CORPUS env var as default."""
    if corpus_name is None:
        corpus_name = os.environ.get("POLICYCHECKER_CORPUS", "ait")

    if corpus_name not in _CONFIG_CACHE:
        _CONFIG_CACHE[corpus_name] = load_corpus_config(corpus_name)

    return _CONFIG_CACHE[corpus_name]


def reset_config_cache() -> None:
    """Clear the config cache (useful for testing)."""
    _CONFIG_CACHE.clear()
