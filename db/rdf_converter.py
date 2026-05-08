"""
db.rdf_converter - Convert realistic university DB data to RDF Turtle.

Reads proper relational tables (students, fee_records, accommodations,
conduct_records, faculty, staff, committees) and maps them to ait: ontology
predicates for SHACL validation.

The mapping layer translates real database fields into RDF:
  - enrollment_status = 'Active'    ->  ait:enrolled true
  - payment_status = 'Paid'         ->  ait:payFee true
  - cooking_in_dorm = true          ->  ait:cookInUnit true
  etc.

Usage (standalone):
    python -m db.rdf_converter                 # all entities
    python -m db.rdf_converter Somchai Lin     # specific students

Usage (programmatic):
    from db.rdf_converter import convert_db_to_turtle
    turtle_str = convert_db_to_turtle()
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---- RDF Prefixes -----------------------------------------------------------
TURTLE_PREFIXES = """\
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix ait:  <http://example.org/ait-policy#> .
"""

HEADER = """\
# =================================================================
# AIT Compliance Data -- Generated from PostgreSQL
# =================================================================
# Converted from relational student/faculty/staff records into
# RDF Turtle format for SHACL validation against AIT policy shapes.
# =================================================================
"""


def _b(val: bool) -> str:
    """Format a boolean for Turtle."""
    return "true" if val else "false"


# =============================================================================
# STUDENT MAPPING
# =============================================================================

def _build_student_turtle(conn, student_names: Optional[list[str]] = None) -> list[str]:
    """Query students + related tables and produce Turtle blocks."""
    with conn.cursor() as cur:
        # Build WHERE clause
        if student_names:
            placeholders = ",".join(["%s"] * len(student_names))
            where = f"WHERE s.first_name IN ({placeholders})"
            params = student_names
        else:
            where = ""
            params = []

        # Main student query with all related data via LEFT JOINs
        cur.execute(f"""
            SELECT
                s.student_id, s.first_name, s.last_name,
                s.email, s.program, s.degree_level,
                s.enrollment_status, s.is_new_student, s.advisor,
                -- Latest fee record
                fr.payment_status, fr.first_installment_paid,
                fr.amount_paid, fr.tuition_amount,
                -- Accommodation
                a.building, a.room_number, a.room_type,
                a.deposit_paid, a.rent_current, a.with_spouse,
                a.on_waiting_list, a.provided_arrival_date,
                a.room_clean, a.common_area_clean, a.unit_hygiene,
                a.confirmed_offer, a.vacated_on_time,
                -- Conduct flags
                sc.ethical_conduct, sc.peaceful_environment,
                sc.library_responsible_use, sc.it_acceptable_use,
                sc.brings_concerns_to_attention,
                sc.cooking_in_dorm, sc.noisy_in_dorm,
                sc.pet_in_dorm, sc.disturbing_residents,
                -- Academic
                ar.registered_with_registry, ar.grade_determined_in_courses,
                ar.makeup_classes_scheduled,
                ar.serves_as_corresponding_author,
                ar.corresponds_with_journal,
                ar.first_author_in_multi_authored
            FROM students s
            LEFT JOIN LATERAL (
                SELECT * FROM fee_records f
                WHERE f.student_id = s.student_id
                ORDER BY f.semester DESC LIMIT 1
            ) fr ON true
            LEFT JOIN LATERAL (
                SELECT * FROM accommodations ac
                WHERE ac.student_id = s.student_id
                ORDER BY ac.check_in_date DESC LIMIT 1
            ) a ON true
            LEFT JOIN student_conduct sc ON sc.student_id = s.student_id
            LEFT JOIN academic_records ar ON ar.student_id = s.student_id
            {where}
            ORDER BY s.student_id
        """, params)

        rows = cur.fetchall()

    lines = []
    for row in rows:
        (student_id, first, last, email, program, degree,
         status, is_new, advisor,
         pay_status, first_inst, amt_paid, tuition,
         bldg, room, room_type, deposit, rent_ok, with_spouse,
         waiting_list, arrival_date, room_clean, common_clean,
         unit_hygiene, confirmed, vacated,
         ethical, peaceful, library_use, it_use, concerns,
         cooking, noisy, pet, disturbing,
         registered, grade_det, makeup, corr_author, journal, first_auth) = row

        # Determine entity type
        entity_type = "PostgraduateStudent" if degree == "PhD" else "Student"
        entity_name = first  # use first name as URI

        # Fee compliance
        is_enrolled = (status == "Active")
        fees_paid = (pay_status == "Paid")
        fully_paid = (pay_status == "Paid" and amt_paid is not None
                      and tuition is not None and amt_paid >= tuition)
        first_paid = bool(first_inst)

        lines.append(f"# -- {first} {last} ({student_id}) --")
        lines.append(f"# Program: {program or 'N/A'} | {degree or 'N/A'} | Status: {status}")
        if bldg:
            lines.append(f"# Housing: {bldg}, Room {room}")
        lines.append(f"ait:{entity_name} a ait:{entity_type} ;")
        lines.append(f'    rdfs:label "{first} {last} - {degree or ""} Student ({status})" ;')
        lines.append(f"    ait:student {_b(True)} ;")
        lines.append(f"    ait:enrolled {_b(is_enrolled)} ;")
        lines.append(f"    ait:newStudent {_b(bool(is_new))} ;")

        # -- Fee properties
        lines.append(f"    ait:payFee {_b(fees_paid)} ;")
        lines.append(f"    ait:payFirstSemesterFee {_b(first_paid)} ;")
        lines.append(f"    ait:fullPayment {_b(fully_paid)} ;")
        lines.append(f"    ait:paidinadvanceorfully {_b(fully_paid)} ;")

        # -- Accommodation properties
        has_accom = bldg is not None
        lines.append(f"    ait:queuing {_b(has_accom)} ;")
        lines.append(f"    ait:confirmOfferMove {_b(bool(confirmed) if has_accom else False)} ;")
        lines.append(f"    ait:moveWithSpouse {_b(bool(with_spouse) if has_accom else False)} ;")
        lines.append(f"    ait:provideapproximatedateofarrivaloncampus {_b(bool(arrival_date) if has_accom else False)} ;")
        lines.append(f"    ait:putNameOnWaitingListForCampusAccommodation {_b(bool(waiting_list) if has_accom else True)} ;")
        lines.append(f"    ait:payRentForStayOnCampus {_b(bool(rent_ok) if has_accom else True)} ;")
        lines.append(f"    ait:vacatesRoom {_b(bool(vacated) if has_accom else True)} ;")
        lines.append(f"    ait:vacateRoom {_b(bool(vacated) if has_accom else True)} ;")
        lines.append(f"    ait:clean {_b(bool(room_clean) if has_accom else True)} ;")
        lines.append(f"    ait:regularcleaningandhygieneoftheunit {_b(bool(unit_hygiene) if has_accom else True)} ;")
        lines.append(f"    ait:maintainCleanlinessOfCommonAreaAndLandscape {_b(bool(common_clean) if has_accom else True)} ;")
        lines.append(f"    ait:maintainCleanlinessOfBedroomAndFacilities {_b(bool(room_clean) if has_accom else True)} ;")

        # -- Conduct violations (true = violation)
        lines.append(f"    ait:bringConcernsToAttention {_b(bool(concerns) if concerns is not None else True)} ;")
        lines.append(f"    ait:meetHighestStandardsOfPersonalEthicalAndMoralConduct {_b(bool(ethical) if ethical is not None else True)} ;")
        lines.append(f"    ait:maintainPeacefulHealthyLearningEnvironmentForFreeDiscussion {_b(bool(peaceful) if peaceful is not None else True)} ;")
        lines.append(f"    ait:useAITLibraryAndEducationalResourcesResponsibly {_b(bool(library_use) if library_use is not None else True)} ;")
        lines.append(f"    ait:abideByAcceptableUsePolicyForITResources {_b(bool(it_use) if it_use is not None else True)} ;")

        # Dorm violations
        if cooking:
            lines.append(f"    ait:cookInUnit true ;")
            lines.append(f"    ait:cookInProhibitedDormitory true ;")
        if noisy:
            lines.append(f"    ait:noisyGroupStudyOrPartyInStudentAccommodation true ;")
        if pet:
            lines.append(f"    ait:petInStudentAccommodation true ;")
        if disturbing:
            lines.append(f"    ait:disturbFellowStudentsInResidentialAreas true ;")

        # -- Academic properties
        lines.append(f"    ait:registry {_b(bool(registered) if registered is not None else True)} ;")
        lines.append(f"    ait:determineGradeInCourse {_b(bool(grade_det) if grade_det is not None else True)} ;")
        lines.append(f"    ait:scheduledoutsideregularhoursmakeupclasses {_b(bool(makeup) if makeup is not None else True)} ;")
        lines.append(f"    ait:serveAsCorrespondingAuthor {_b(bool(corr_author) if corr_author is not None else False)} ;")
        lines.append(f"    ait:correspondAsAuthorWithJournal {_b(bool(journal) if journal is not None else False)} ;")
        lines.append(f"    ait:multiAuthoredArticleWrittenByStudentShouldBeFirstAuthorUnlessJournalRequiresDifferentOrder {_b(bool(first_auth) if first_auth is not None else False)} .")
        lines.append("")

    return lines


# =============================================================================
# FACULTY MAPPING
# =============================================================================

def _build_faculty_turtle(conn, entity_names: Optional[list[str]] = None) -> list[str]:
    """Convert faculty records to Turtle."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT faculty_id, title, first_name, last_name, email,
                   department, position,
                   grading_criteria_published, follows_disciplinary_procedures,
                   discloses_conflicts, reports_cheating_suspects
            FROM faculty ORDER BY id
        """)
        rows = cur.fetchall()

    lines = []
    for (fid, title, first, last, email, dept, pos,
         grading, disciplinary, discloses, reports) in rows:
        name = f"{title}{first}{last}".replace(" ", "").replace(".", "")
        if entity_names and name not in entity_names:
            continue
        lines.append(f"# -- {title} {first} {last} ({fid}) --")
        lines.append(f"# Department: {dept} | Position: {pos}")
        lines.append(f"ait:{name} a ait:Faculty ;")
        lines.append(f'    rdfs:label "{title} {first} {last} - {pos}" ;')
        lines.append(f"    ait:makeKnownCriteriaForGrading {_b(grading)} ;")
        lines.append(f"    ait:followProceduresForDisciplinaryActions {_b(disciplinary)} ;")
        lines.append(f"    ait:disclose {_b(discloses)} ;")
        lines.append(f"    ait:suspectCheatingDuringExamOrAssignmentOrResearchProject {_b(reports)} ;")
        lines.append(f"    ait:reported {_b(reports)} .")
        lines.append("")

    return lines


# =============================================================================
# STAFF MAPPING
# =============================================================================

def _build_staff_turtle(conn, entity_names: Optional[list[str]] = None) -> list[str]:
    """Convert staff records to Turtle."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT staff_id, first_name, last_name, email,
                   department, role,
                   gifts_reported, settlements_reported,
                   fees_managed_properly, ethical_authority_use
            FROM staff ORDER BY id
        """)
        rows = cur.fetchall()

    lines = []
    for (sid, first, last, email, dept, role,
         gifts, settlements, fees, ethical) in rows:
        if entity_names and first not in entity_names:
            continue
        lines.append(f"# -- {first} {last} ({sid}) --")
        lines.append(f"# Department: {dept} | Role: {role}")
        lines.append(f"ait:{first} a ait:Employee ;")
        lines.append(f'    rdfs:label "{first} {last} - {role}" ;')
        lines.append(f"    ait:reported {_b(gifts)} ;")
        lines.append(f"    ait:settled {_b(settlements)} ;")
        lines.append(f"    ait:feesPaid {_b(fees)} ;")
        lines.append(f"    ait:payFees {_b(fees)} ;")
        lines.append(f"    ait:usesAuthorityEthicallyWithRespectAndSensitivityAndInAccordanceWithInstitutesPolicies {_b(ethical)} ;")
        lines.append(f"    ait:expresses_personal_opinion true ;")
        lines.append(f"    ait:undergoDisciplinaryAction true .")
        lines.append("")

    return lines


# =============================================================================
# COMMITTEE MAPPING
# =============================================================================

def _build_committee_turtle(conn, entity_names: Optional[list[str]] = None) -> list[str]:
    """Convert committee records to Turtle."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT committee_name, committee_type, chair_elected,
                   is_active, handles_grievances,
                   maintains_confidentiality, records_facts,
                   convenes_tribunals
            FROM committees ORDER BY id
        """)
        rows = cur.fetchall()

    lines = []
    for (name, ctype, chair, active, grievances,
         confidential, records, tribunals) in rows:
        uri = name.replace(" ", "").replace("&", "And")
        if entity_names and uri not in entity_names:
            continue
        lines.append(f"# -- {name} --")
        lines.append(f"# Type: {ctype}")
        lines.append(f"ait:{uri} a ait:Committee ;")
        lines.append(f'    rdfs:label "{name}" ;')
        lines.append(f"    ait:electsChair {_b(chair)} ;")
        lines.append(f"    ait:receive_grievance {_b(grievances)} ;")
        lines.append(f"    ait:grievanceCommitteePerformsRole {_b(active and grievances)} ;")
        lines.append(f"    ait:prepared {_b(active)} ;")
        lines.append(f"    ait:confidentiality_and_due_regard {_b(confidential)} ;")
        lines.append(f"    ait:grievanceProcedureInvolvement {_b(grievances)} ;")
        lines.append(f"    ait:writeDownGrievanceFacts {_b(records)} ;")
        lines.append(f"    ait:recordFacts {_b(records)} ;")
        lines.append(f"    ait:analyzeGrievance {_b(grievances)} ;")
        lines.append(f"    ait:conveneGrievanceTribunal {_b(tribunals)} ;")
        lines.append(f"    ait:attendHearing {_b(tribunals)} ;")
        lines.append(f"    ait:ascertainFactsOfCase {_b(records)} ;")
        lines.append(f"    ait:expressesInWriting {_b(records)} ;")
        lines.append(f"    ait:submitWrittenAgreementsToGrievanceCommittee {_b(records)} .")
        lines.append("")

    return lines


# =============================================================================
# MAIN CONVERTER
# =============================================================================

def convert_db_to_turtle(
    entity_names: Optional[list[str]] = None,
) -> dict:
    """
    Query all entity tables from PostgreSQL and generate valid Turtle RDF.

    Args:
        entity_names: Optional list of entity names to include.
                      Filters across ALL entity types (students, faculty,
                      staff, committees). None or empty = include all.

    Returns:
        dict with: turtle, entity_count, property_count
    """
    from db.connection import get_connection

    with get_connection() as conn:
        student_lines = _build_student_turtle(conn, entity_names)
        faculty_lines = _build_faculty_turtle(conn, entity_names)
        staff_lines = _build_staff_turtle(conn, entity_names)
        committee_lines = _build_committee_turtle(conn, entity_names)

    all_lines = [TURTLE_PREFIXES, "", HEADER]
    entity_count = 0
    prop_count = 0

    for section_name, section_lines in [
        ("Students", student_lines),
        ("Faculty", faculty_lines),
        ("Staff", staff_lines),
        ("Committees", committee_lines),
    ]:
        if section_lines:
            all_lines.append(f"# --- {section_name} ---")
            all_lines.append("")
            all_lines.extend(section_lines)
            # Count entities (lines with " a ait:")
            entity_count += sum(1 for l in section_lines if " a ait:" in l)
            # Count properties (lines with "    ait:")
            prop_count += sum(1 for l in section_lines if l.strip().startswith("ait:") and " a " not in l)

    turtle_str = "\n".join(all_lines)
    return {
        "turtle": turtle_str,
        "entity_count": entity_count,
        "property_count": prop_count,
    }


def list_entities() -> list[dict]:
    """Return a summary list of all entities in the database."""
    from db.connection import get_connection

    entities = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Students
            cur.execute("""
                SELECT s.first_name, s.last_name,
                       CASE WHEN s.degree_level = 'PhD' THEN 'PostgraduateStudent'
                            ELSE 'Student' END as entity_type,
                       s.program, s.enrollment_status, s.degree_level,
                       (SELECT COUNT(*) FROM fee_records f WHERE f.student_id = s.student_id) as fee_count,
                       (SELECT COUNT(*) FROM accommodations a WHERE a.student_id = s.student_id) as accom_count,
                       (SELECT COUNT(*) FROM conduct_records cr WHERE cr.student_id = s.student_id) as violation_count
                FROM students s ORDER BY s.student_id
            """)
            for row in cur.fetchall():
                entities.append({
                    "name": row[0],
                    "type": row[2],
                    "label": f"{row[0]} {row[1]} ({row[5]} - {row[3]})",
                    "property_count": 30 + (row[6] or 0) + (row[7] or 0),
                    "detail": f"{row[4]} | {row[8]} violations",
                })

            # Faculty
            cur.execute("""
                SELECT title, first_name, last_name, department, position
                FROM faculty ORDER BY id
            """)
            for row in cur.fetchall():
                entities.append({
                    "name": f"{row[0]}{row[1]}{row[2]}".replace(" ", "").replace(".", ""),
                    "type": "Faculty",
                    "label": f"{row[0]} {row[1]} {row[2]} ({row[4]}, {row[3]})",
                    "property_count": 5,
                    "detail": row[4],
                })

            # Staff
            cur.execute("""
                SELECT first_name, last_name, department, role
                FROM staff ORDER BY id
            """)
            for row in cur.fetchall():
                entities.append({
                    "name": row[0],
                    "type": "Employee",
                    "label": f"{row[0]} {row[1]} ({row[3]}, {row[2]})",
                    "property_count": 7,
                    "detail": row[3],
                })

            # Committees
            cur.execute("""
                SELECT committee_name, committee_type
                FROM committees ORDER BY id
            """)
            for row in cur.fetchall():
                entities.append({
                    "name": row[0].replace(" ", "").replace("&", "And"),
                    "type": "Committee",
                    "label": f"{row[0]} ({row[1]})",
                    "property_count": 14,
                    "detail": row[1],
                })

    return entities


# ---- CLI --------------------------------------------------------------------
if __name__ == "__main__":
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")

    names = sys.argv[1:] if len(sys.argv) > 1 else None
    result = convert_db_to_turtle(entity_names=names)
    print(result["turtle"])
    print(f"\n# Converted {result['entity_count']} entities, "
          f"{result['property_count']} properties", file=sys.stderr)
