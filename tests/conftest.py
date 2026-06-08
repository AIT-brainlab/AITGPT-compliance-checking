"""Shared fixtures for the API test suite."""
import pytest


SAMPLE_RULES = [
    {
        "rule_id": "AIT_0001",
        "rule_type": "obligation",
        "text": "Students must pay tuition fees before the registration deadline.",
        "source_document": "FB-6-1-1",
    },
    {
        "rule_id": "AIT_0002",
        "rule_type": "prohibition",
        "text": "Students must not cook in dormitories.",
        "source_document": "FS-1-1-1",
    },
    {
        "rule_id": "AIT_0003",
        "rule_type": "obligation",
        "text": "Faculty must disclose conflicts of interest.",
        "source_document": "PA-2-1-2",
    },
]

SAMPLE_FOL = [
    {
        "rule_id": "AIT_0001",
        "formula": "∀x (Student(x) ∧ enrolled(x) → payFee(x))",
        "status": "ok",
    },
    {
        "rule_id": "AIT_0002",
        "formula": "∀x (Student(x) → ¬cookInDormitory(x))",
        "status": "ok",
    },
]

SAMPLE_REPORT = {
    "pipeline_version": "2.0",
    "summary": {
        "sentences_extracted": 100,
        "candidates_prefiltered": 80,
        "fol_formulas_ok": 75,
        "fol_formulas_failed": 5,
        "shacl_shapes_total": 70,
        "shacl_shapes_valid": 68,
    },
}

MINIMAL_STUDENT_TURTLE = """\
@prefix ait: <http://example.org/ait-policy#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ait:TestStudent a ait:Student ;
    rdfs:label "Test Student" .
"""

STUDENT_WITH_VIOLATION_TURTLE = """\
@prefix ait: <http://example.org/ait-policy#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ait:BadStudent a ait:Student ;
    rdfs:label "Bad Student" ;
    ait:cookInProhibitedDormitory true .
"""
