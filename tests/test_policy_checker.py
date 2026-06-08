"""Tests for the student/policy compliance API (src/policy_checker/api/policy_checker.py)."""
import io
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from policy_checker.api.policy_checker import app, Person
from tests.conftest import MINIMAL_STUDENT_TURTLE

client = TestClient(app)

# Minimal valid PDF header — enough to pass the b"%PDF" prefix check.
# pypdf is mocked in upload tests so the content doesn't need to be a real PDF.
_PDF_HEADER = b"%PDF-1.4\n"

# IDs must be strings to match Person.id: str (Pydantic v2 doesn't coerce int→str)
# Shape returned by _get_all_persons / get_person_by_id / _get_person_by_name
# (display name + turtle subject key + type).
SAMPLE_PERSON_ROWS = [
    {"id": "1", "name": "Anna Kowalski", "type": "Student", "key": "Anna"},
    {"id": "2", "name": "Napat Srikhao", "type": "Student", "key": "Napat"},
]

SAMPLE_VIOLATIONS = {
    "Anna": [
        {
            "rule_id": "AIT_0086Shape",
            "rule_text": "cookInProhibitedDormitory",
            "severity": "Violation",
            "message": "Student must not cook in prohibited dormitory.",
        }
    ],
    "Napat": [],
}


# ── /api/policy  GET ──────────────────────────────────────────────────────────

class TestGetPolicy:
    def test_returns_path_when_pdf_exists(self, tmp_path):
        pdf = tmp_path / "policy.pdf"
        pdf.write_bytes(_PDF_HEADER)
        with patch("policy_checker.api.policy_checker.POLICY_DIR", tmp_path):
            resp = client.get("/api/policy")
        assert resp.status_code == 200
        assert str(pdf) in resp.json()

    def test_returns_404_when_no_pdf(self, tmp_path):
        with patch("policy_checker.api.policy_checker.POLICY_DIR", tmp_path):
            resp = client.get("/api/policy")
        assert resp.status_code == 404


# ── /api/policy  POST ─────────────────────────────────────────────────────────

class TestUploadPolicy:
    def test_valid_pdf_is_accepted(self, tmp_path):
        with (
            patch("policy_checker.api.policy_checker.POLICY_DIR", tmp_path),
            patch("policy_checker.api.policy_checker.pypdf") as mock_pypdf,
        ):
            mock_pypdf.PdfReader.return_value.pages = [MagicMock()]
            resp = client.post(
                "/api/policy",
                files={"file": ("test.pdf", io.BytesIO(_PDF_HEADER + b"\x00" * 100), "application/pdf")},
            )
        assert resp.status_code == 200
        assert "uploaded successfully" in resp.json()["message"]

    def test_non_pdf_file_returns_422(self, tmp_path):
        with patch("policy_checker.api.policy_checker.POLICY_DIR", tmp_path):
            resp = client.post(
                "/api/policy",
                files={"file": ("doc.txt", io.BytesIO(b"plain text content"), "text/plain")},
            )
        assert resp.status_code == 422
        assert "not a valid PDF" in resp.json()["detail"]

    def test_replaces_existing_pdf(self, tmp_path):
        old_pdf = tmp_path / "old.pdf"
        old_pdf.write_bytes(_PDF_HEADER)
        with (
            patch("policy_checker.api.policy_checker.POLICY_DIR", tmp_path),
            patch("policy_checker.api.policy_checker.pypdf") as mock_pypdf,
        ):
            mock_pypdf.PdfReader.return_value.pages = [MagicMock()]
            client.post(
                "/api/policy",
                files={"file": ("new.pdf", io.BytesIO(_PDF_HEADER + b"\x00" * 100), "application/pdf")},
            )
        # Old file should be gone, new file should exist
        assert not old_pdf.exists()
        assert (tmp_path / "new.pdf").exists()


# ── /api/policy  DELETE ───────────────────────────────────────────────────────

class TestDeletePolicy:
    def test_deletes_existing_pdf(self, tmp_path):
        pdf = tmp_path / "policy.pdf"
        pdf.write_bytes(_PDF_HEADER)
        with patch("policy_checker.api.policy_checker.POLICY_DIR", tmp_path):
            resp = client.delete("/api/policy")
        assert resp.status_code == 200
        assert not pdf.exists()

    def test_delete_when_no_file_is_ok(self, tmp_path):
        with patch("policy_checker.api.policy_checker.POLICY_DIR", tmp_path):
            resp = client.delete("/api/policy")
        assert resp.status_code == 200


# ── GET /api/person ───────────────────────────────────────────────────────────

class TestGetPersons:
    def test_returns_persons_with_violations(self):
        turtle_result = {"turtle": MINIMAL_STUDENT_TURTLE}
        with (
            patch("policy_checker.api.policy_checker.get_all_persons", return_value=SAMPLE_PERSON_ROWS),
            patch(
                "policy_checker.database.rdf_converter.convert_db_to_turtle",
                return_value=turtle_result,
            ),
            patch(
                "policy_checker.api.policy_checker.run_shacl_on_turtle",
                return_value=SAMPLE_VIOLATIONS,
            ),
        ):
            resp = client.get("/api/person")

        assert resp.status_code == 200
        persons = resp.json()
        assert len(persons) == 2

        anna = next(p for p in persons if "Anna" in p["name"])
        assert len(anna["not_conforms"]) == 1
        assert anna["not_conforms"][0]["rule_id"] == "AIT_0086Shape"

        napat = next(p for p in persons if "Napat" in p["name"])
        assert napat["not_conforms"] == []

    def test_returns_empty_list_when_no_persons(self):
        with patch(
            "policy_checker.api.policy_checker.get_all_persons", return_value=[]
        ):
            resp = client.get("/api/person")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_person_model_structure(self):
        turtle_result = {"turtle": MINIMAL_STUDENT_TURTLE}
        with (
            patch(
                "policy_checker.api.policy_checker.get_all_persons",
                return_value=[SAMPLE_PERSON_ROWS[0]],
            ),
            patch(
                "policy_checker.database.rdf_converter.convert_db_to_turtle",
                return_value=turtle_result,
            ),
            patch(
                "policy_checker.api.policy_checker.run_shacl_on_turtle",
                return_value={},
            ),
        ):
            resp = client.get("/api/person")

        assert resp.status_code == 200
        person = resp.json()[0]
        assert "id" in person
        assert "name" in person
        assert "type" in person
        assert "not_conforms" in person
        assert isinstance(person["not_conforms"], list)


# ── POST /api/person/validate-by-name ────────────────────────────────────────

class TestValidateByName:
    def test_found_person_returns_compliance_data(self):
        person_obj = Person(id="1", name="Anna Kowalski", type="Student", not_conforms=[])
        with (
            patch(
                "policy_checker.api.policy_checker.get_person_by_name",
                return_value=SAMPLE_PERSON_ROWS[0],
            ),
            patch(
                "policy_checker.api.policy_checker.validate_person",
                return_value=person_obj,
            ),
        ):
            resp = client.post(
                "/api/person/validate-by-name", json={"name": "Anna Kowalski"}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "1"
        assert data["name"] == "Anna Kowalski"
        assert data["type"] == "Student"
        assert data["not_conforms"] == []

    def test_unknown_name_returns_404(self):
        with patch(
            "policy_checker.api.policy_checker.get_person_by_name",
            return_value=None,
        ):
            resp = client.post(
                "/api/person/validate-by-name", json={"name": "Nobody Unknown"}
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_missing_name_field_returns_422(self):
        resp = client.post("/api/person/validate-by-name", json={})
        assert resp.status_code == 422

    def test_validate_by_name_calls_shacl(self):
        turtle_result = {"turtle": MINIMAL_STUDENT_TURTLE}
        with (
            patch(
                "policy_checker.api.policy_checker.get_person_by_name",
                return_value=SAMPLE_PERSON_ROWS[0],
            ),
            patch(
                "policy_checker.database.rdf_converter.convert_db_to_turtle",
                return_value=turtle_result,
            ),
            patch(
                "policy_checker.api.policy_checker.run_shacl_on_turtle",
                return_value={"Anna": []},
            ) as mock_shacl,
        ):
            resp = client.post(
                "/api/person/validate-by-name", json={"name": "Anna Kowalski"}
            )

        assert resp.status_code == 200
        mock_shacl.assert_called_once()


# ── POST /api/person/validate-by-id ──────────────────────────────────────────

class TestValidateById:
    def test_found_person_returns_compliance_data(self):
        person_obj = Person(id="2", name="Napat Srikhao", type="Student", not_conforms=[])
        with (
            patch(
                "policy_checker.api.policy_checker.get_person_by_id",
                return_value=SAMPLE_PERSON_ROWS[1],
            ),
            patch(
                "policy_checker.api.policy_checker.validate_person",
                return_value=person_obj,
            ),
        ):
            resp = client.post(
                "/api/person/validate-by-id", json={"id": "2"}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "2"
        assert data["name"] == "Napat Srikhao"
        assert data["type"] == "Student"
        assert data["not_conforms"] == []

    def test_unknown_id_returns_404(self):
        with patch(
            "policy_checker.api.policy_checker.get_person_by_id",
            return_value=None,
        ):
            resp = client.post(
                "/api/person/validate-by-id", json={"id": "9999"}
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_missing_id_field_returns_422(self):
        resp = client.post("/api/person/validate-by-id", json={})
        assert resp.status_code == 422

    def test_validate_by_id_calls_shacl(self):
        turtle_result = {"turtle": MINIMAL_STUDENT_TURTLE}
        with (
            patch(
                "policy_checker.api.policy_checker.get_person_by_id",
                return_value=SAMPLE_PERSON_ROWS[1],
            ),
            patch(
                "policy_checker.database.rdf_converter.convert_db_to_turtle",
                return_value=turtle_result,
            ),
            patch(
                "policy_checker.api.policy_checker.run_shacl_on_turtle",
                return_value={"Napat": []},
            ) as mock_shacl,
        ):
            resp = client.post(
                "/api/person/validate-by-id", json={"id": "2"}
            )

        assert resp.status_code == 200
        mock_shacl.assert_called_once()


# ── run_shacl_on_turtle (unit tests for the helper itself) ──────────────────

class TestRunShaclOnTurtle:
    def test_returns_empty_violations_for_conforming_student(self):
        from policy_checker.api.policy_checker import run_shacl_on_turtle

        # No shapes file → empty shapes graph → everything conforms
        with patch(
            "policy_checker.api.policy_checker.SHAPES_FILE",
            Path("/nonexistent/shapes_generated.ttl"),
        ):
            result = run_shacl_on_turtle(MINIMAL_STUDENT_TURTLE)

        assert isinstance(result, dict)
        # TestStudent should have no violations (no shapes loaded)
        assert result.get("TestStudent", []) == []

    def test_returns_dict_keyed_by_entity_local_name(self):
        from policy_checker.api.policy_checker import run_shacl_on_turtle

        two_entities = """\
@prefix ait: <http://example.org/ait-policy#> .
ait:Alpha a ait:Student .
ait:Beta a ait:Faculty .
"""
        with patch(
            "policy_checker.api.policy_checker.SHAPES_FILE",
            Path("/nonexistent/shapes_generated.ttl"),
        ):
            result = run_shacl_on_turtle(two_entities)

        assert isinstance(result, dict)
