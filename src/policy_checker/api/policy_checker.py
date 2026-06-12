from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import pypdf
import io
import hashlib

from policy_checker import PROJECT_ROOT

app = FastAPI(title="PolicyChecker Compliance Dashboard", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data paths ────────────────────────────────────────────────────────────
POLICY_DIR = PROJECT_ROOT / "data" / "institutional_policy" / "AIT"
SHAPES_FILE = PROJECT_ROOT / "data" / "output" / "ait" / "shapes_generated.ttl"


# ── Pydantic models ───────────────────────────────────────────────────────
class Conform(BaseModel):
    rule_id: str
    rule_text: str
    severity: str
    message: str


class Person(BaseModel):
    id: str
    name: str
    type: str
    not_conforms: List[Conform]


class ValidateByNameRequest(BaseModel):
    name: str


class ValidateByIdRequest(BaseModel):
    id: str


# ── SHACL helpers ─────────────────────────────────────────────────────────
def local_name(uri: str) -> str:
    """Extract local name from a URI (after # or last /)."""
    if "#" in uri:
        return uri.split("#")[-1]
    return uri.split("/")[-1]


def run_shacl_on_turtle(turtle_str: str) -> dict:
    """
    Run pyshacl on the given Turtle string against shapes_generated.ttl,
    filtered to the curated set of shapes (same approach as the POC in app.py).
    Returns a dict mapping entity local_name -> list of violation dicts.
    """
    from rdflib import Graph, Namespace, URIRef
    from pyshacl import validate

    AIT = Namespace("http://example.org/ait-policy#")
    SH = Namespace("http://www.w3.org/ns/shacl#")
    RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

    _CURATED_SHAPES = {
        # Student fee obligations (minCount 1 + xsd:decimal)
        AIT.AIT_0007Shape,  # payFirstSemesterFee (Student, min1)
        AIT.AIT_0096Shape,  # payRentForStayOnCampus (Student, min1, NO datatype)
        AIT.AIT_0219Shape,  # feesPaid — best fee message (Student, min1)
        # Accommodation obligations
        AIT.AIT_0068Shape,  # confirmOfferMove (Student, min1)
        AIT.AIT_0056Shape,  # vacateRoom - vacate after graduation (Student, min1)
        AIT.AIT_0070Shape,  # maintainCleanlinessOfBedroomAndFacilities (Student, min1)
        AIT.AIT_0072Shape,  # maintainCleanlinessOfCommonAreaAndLandscape (Student, min1)
        # Conduct obligations
        AIT.AIT_0041Shape,  # bringConcernsToAttention (Student, min1)
        AIT.AIT_0150Shape,  # meetHighestStandardsOfPersonalEthicalAndMoralConduct (Student, min1)
        # Conduct prohibitions
        AIT.AIT_0086Shape,  # cookInProhibitedDormitory (Student, max0)
        AIT.AIT_0089Shape,  # petInStudentAccommodation (Student, max0)
        AIT.AIT_0079Shape,  # noisyGroupStudyOrPartyInStudentAccommodation (Student, max0)
        AIT.AIT_0090Shape,  # disturbingpeace (Student, max0)
        # Faculty obligations
        AIT.AIT_0005Shape,  # followProceduresForDisciplinaryActions (Faculty, min1)
        AIT.AIT_0142Shape,  # makeKnownCriteriaForGrading (Faculty, min1)
        # Staff / Employee obligations
        AIT.AIT_0101Shape,  # disclose conflicts (Employee, min1)
        AIT.AIT_0100Shape,  # usesAuthorityEthically (Employee, min1)
        AIT.AIT_0029Shape,  # settled (Employee, min1)
    }

    #student data
    data_graph = Graph()
    data_graph.parse(data=turtle_str, format="turtle")

    #rules data
    shapes_graph = Graph()
    if SHAPES_FILE.exists():
        shapes_graph.parse(str(SHAPES_FILE), format="turtle")

    # Remove all NodeShapes NOT in the curated set
    all_node_shapes = set(shapes_graph.subjects(RDF_TYPE, SH.NodeShape))
    for ns in all_node_shapes - _CURATED_SHAPES:
        for prop_shape in shapes_graph.objects(ns, SH.property):
            for p, o in list(shapes_graph.predicate_objects(prop_shape)):
                shapes_graph.remove((prop_shape, p, o))
        for p, o in list(shapes_graph.predicate_objects(ns)):
            shapes_graph.remove((ns, p, o))

    # Strip sh:datatype and sh:pattern from curated shapes to avoid
    # false positives (we use presence/absence for compliance checking,
    # not typed value validation)
    for ns in _CURATED_SHAPES:
        for prop_shape in shapes_graph.objects(ns, SH.property):
            for dt in list(shapes_graph.objects(prop_shape, SH.datatype)):
                shapes_graph.remove((prop_shape, SH.datatype, dt))
            for pat in list(shapes_graph.objects(prop_shape, SH.pattern)):
                shapes_graph.remove((prop_shape, SH.pattern, pat))

    #validate
    _, results_graph, _ = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
        abort_on_first=False,
        do_owl_imports=False,
    )

    #parse violations
    violations_by_entity: dict = {}
    for result in results_graph.subjects(RDF_TYPE, SH.ValidationResult):
        focus_node    = str(results_graph.value(result, SH.focusNode)      or "")
        source_shape  = str(results_graph.value(result, SH.sourceShape)    or "")
        source_path   = str(results_graph.value(result, SH.resultPath)     or "")
        result_message = str(results_graph.value(result, SH.resultMessage) or "")
        severity      = str(results_graph.value(result, SH.resultSeverity) or "")

        entity_key = local_name(focus_node)
        violation = {
            "rule_id":   local_name(source_shape),
            "rule_text": local_name(source_path),
            "severity":  local_name(severity),
            "message":   result_message,
        }
        violations_by_entity.setdefault(entity_key, []).append(violation)

    return violations_by_entity


# ── DB helpers ────────────────────────────────────────────────────────────

def get_all_persons() -> list:
    """Return every person (students, faculty, staff).

    Committees are excluded — they are organizational units, not persons.
    """
    from policy_checker.database.connection import get_connection

    persons = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT student_id, first_name, last_name FROM students ORDER BY student_id"
            )
            for sid, first, last in cur.fetchall():
                persons.append({
                    "id": str(sid),
                    "name": f"{first} {last}",
                    "type": "Student",
                })

            cur.execute(
                "SELECT faculty_id, title, first_name, last_name FROM faculty ORDER BY id"
            )
            for fid, title, first, last in cur.fetchall():
                persons.append({
                    "id": str(fid),
                    "name": f"{title} {first} {last}".strip(),
                    "type": "Faculty",
                })

            cur.execute(
                "SELECT staff_id, first_name, last_name FROM staff ORDER BY id"
            )
            for sid, first, last in cur.fetchall():
                persons.append({
                    "id": str(sid),
                    "name": f"{first} {last}",
                    "type": "Employee",
                })

    return persons


def get_person_by_name(name: str) -> Optional[dict]:
    target = name.strip().lower()
    if not target:
        return None
    persons = get_all_persons()
    for p in persons:
        if p["name"].lower() == target:
            return p
    for p in persons:
        if target in p["name"].lower():
            return p
    return None


def get_person_by_id(person_id) -> Optional[dict]:
    pid = str(person_id)
    for p in get_all_persons():
        if p["id"] == pid:
            return p
    return None


# Cache of SHACL results per person, keyed by person["id"].
# Each entry is (turtle_hash, violations) — the SHACL run is skipped when the
# turtle for that person hashes the same as last time, since pyshacl validation
# is the expensive step while the DB fetch + turtle conversion is cheap.
_validation_cache: dict = {}


def validate_person(person: dict) -> Person:
    from policy_checker.database.rdf_converter import convert_db_to_turtle

    result = convert_db_to_turtle(entity_id=person["id"], entity_type=person["type"])
    turtle_hash = hashlib.sha256(result["turtle"].encode("utf-8")).hexdigest()
    cached = _validation_cache.get(person["id"])
    if cached and cached[0] == turtle_hash:
        violations = cached[1]
    else: 
        violations_by_entity = run_shacl_on_turtle(result["turtle"])
        violations = violations_by_entity.get(person["id"], [])
        _validation_cache[person["id"]] = (turtle_hash, violations)

    return Person(
        id=person["id"],
        name=person["name"],
        type=person["type"],
        not_conforms=[Conform(**v) for v in violations],
    )


# ── Policy endpoints ──────────────────────────────────────────────────────
def find_policy():
    pdf_files = list(POLICY_DIR.glob("*.pdf"))
    if pdf_files:
        return pdf_files[0]
    return None


@app.get("/api/policy")
async def get_policy():
    policy_file = find_policy()
    if not policy_file:
        raise HTTPException(status_code=404, detail="No policy PDF found")
    return str(policy_file)


@app.post("/api/policy")
async def upload_policy(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Uploaded file is not a valid PDF")
    try:
        reader = pypdf.PdfReader(io.BytesIO(contents))
        _ = len(reader.pages)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF is corrupted or unreadable: {e}")
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    policy_file = find_policy()
    if policy_file:
        policy_file.unlink()
    new_policy_file = POLICY_DIR / file.filename
    new_policy_file.write_bytes(contents)
    return {"message": "Policy PDF uploaded successfully", "path": str(new_policy_file)}


@app.delete("/api/policy")
async def delete_policy():
    policy_file = find_policy()
    if policy_file:
        policy_file.unlink()
    return {"message": "Policy PDF removed successfully"}


# ── Person endpoints ──────────────────────────────────────────────────────
@app.get("/api/person", response_model=List[Person])
async def get_persons():
    all_persons = get_all_persons()
    if not all_persons:
        return []
    return [validate_person(p) for p in all_persons]


@app.post("/api/person/validate-by-name", response_model=bool)
async def validate_by_name(body: ValidateByNameRequest):
    person = get_person_by_name(body.name)
    if not person:
        raise HTTPException(status_code=404, detail=f"Person '{body.name}' not found")
    return len(validate_person(person).not_conforms) == 0


@app.post("/api/person/validate-by-id", response_model=bool)
async def validate_by_id(body: ValidateByIdRequest):
    person = get_person_by_id(body.id)
    if not person:
        raise HTTPException(status_code=404, detail=f"Person with ID {body.id} not found")
    return len(validate_person(person).not_conforms) == 0


@app.get("/api/person/turtle-by-id", response_class=PlainTextResponse)
async def turtle_by_id(id: str):
    from policy_checker.database.rdf_converter import convert_db_to_turtle

    person = get_person_by_id(id)
    if not person:
        raise HTTPException(status_code=404, detail=f"Person with ID {id} not found")
    result = convert_db_to_turtle(entity_id=person["id"], entity_type=person["type"])
    return result["turtle"]


@app.get("/api/cache/validate")
async def check_validation_cache():
    global _validation_cache
    return _validation_cache


def main():
    uvicorn.run(app, host="0.0.0.0", port=8005)


if __name__ == "__main__":
    main()