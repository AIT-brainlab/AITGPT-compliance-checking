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
    from policy_checker.database.rdf_converter import convert_db_to_turtle
    turtle_str = convert_db_to_turtle()
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# PROJECT_ROOT = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(PROJECT_ROOT))
# (not needed — package is installed via uv)

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
        # entity_type = "Student"
        entity_type = "PostgraduateStudent" if degree == "PhD" else "Student"
        entity_name = first

        # Fee compliance
        is_enrolled = (status == "Active")
        fees_paid = (pay_status == "Paid")
        fully_paid = (pay_status == "Paid" and amt_paid is not None
                      and tuition is not None and amt_paid >= tuition)
        first_paid = bool(first_inst)

        has_accom = bldg is not None

        # Build property list — SHACL semantics:
        #   Obligations (sh:minCount 1): only emit when TRUE → present = compliant
        #   Prohibitions (sh:maxCount 0): only emit when TRUE → present = violation
        #   Omitted property → minCount fails (obligation violation)
        #   Omitted property → maxCount satisfied (no prohibition violation)
        props = []

        # -- Always-present metadata --
        props.append(("student", "true"))
        props.append(("enrolled", _b(is_enrolled)))
        props.append(("newStudent", _b(bool(is_new))))

        # -- Fee obligations: emit only when paid --
        if fees_paid:
            props.append(("payFee", "true"))
        if first_paid:
            props.append(("payFirstSemesterFee", "true"))
        if fully_paid:
            props.append(("fullPayment", "true"))
            props.append(("paidinadvanceorfully", "true"))
            props.append(("feesPaid", "true"))

        # -- Accommodation obligations: emit only when compliant --
        if has_accom and bool(confirmed):
            props.append(("confirmOfferMove", "true"))
        if has_accom and bool(with_spouse):
            props.append(("moveWithSpouse", "true"))
        if has_accom and bool(arrival_date):
            props.append(("provideapproximatedateofarrivaloncampus", "true"))
        if bool(rent_ok) if has_accom else True:
            props.append(("payRentForStayOnCampus", "true"))
        if bool(vacated) if has_accom else True:
            props.append(("vacatesRoom", "true"))
            props.append(("vacateRoom", "true"))
        if bool(room_clean) if has_accom else True:
            props.append(("clean", "true"))
            props.append(("maintainCleanlinessOfBedroomAndFacilities", "true"))
        if bool(unit_hygiene) if has_accom else True:
            props.append(("regularcleaningandhygieneoftheunit", "true"))
        if bool(common_clean) if has_accom else True:
            props.append(("maintainCleanlinessOfCommonAreaAndLandscape", "true"))

        # -- Conduct obligations: emit only when compliant --
        if bool(concerns) if concerns is not None else True:
            props.append(("bringConcernsToAttention", "true"))
        if bool(ethical) if ethical is not None else True:
            props.append(("meetHighestStandardsOfPersonalEthicalAndMoralConduct", "true"))
        if bool(peaceful) if peaceful is not None else True:
            props.append(("maintainPeacefulHealthyLearningEnvironmentForFreeDiscussion", "true"))
        if bool(library_use) if library_use is not None else True:
            props.append(("useAITLibraryAndEducationalResourcesResponsibly", "true"))
        if bool(it_use) if it_use is not None else True:
            props.append(("abideByAcceptableUsePolicyForITResources", "true"))

        # -- Prohibition violations: emit only when violating --
        if cooking:
            props.append(("cookInUnit", "true"))
            props.append(("cookInProhibitedDormitory", "true"))
        if noisy:
            props.append(("noisyGroupStudyOrPartyInStudentAccommodation", "true"))
        if pet:
            props.append(("petInStudentAccommodation", "true"))
        if disturbing:
            props.append(("disturbFellowStudentsInResidentialAreas", "true"))
            props.append(("disturbingpeace", "true"))

        # -- Academic obligations: emit only when compliant --
        if bool(registered) if registered is not None else True:
            props.append(("registry", "true"))
        if bool(grade_det) if grade_det is not None else True:
            props.append(("determineGradeInCourse", "true"))
        if bool(makeup) if makeup is not None else True:
            props.append(("scheduledoutsideregularhoursmakeupclasses", "true"))
        if bool(corr_author):
            props.append(("serveAsCorrespondingAuthor", "true"))
            props.append(("correspondAsAuthorWithJournal", "true"))
        if bool(first_auth):
            props.append(("multiAuthoredArticleWrittenByStudentShouldBeFirstAuthorUnlessJournalRequiresDifferentOrder", "true"))

        # -- Build Turtle block --
        lines.append(f"# -- {first} {last} ({student_id}) --")
        lines.append(f"# Program: {program or 'N/A'} | {degree or 'N/A'} | Status: {status}")
        if bldg:
            lines.append(f"# Housing: {bldg}, Room {room}")
        lines.append(f"ait:{entity_name} a ait:{entity_type} ;")
        lines.append(f'    rdfs:label "{first} {last} - {degree or ""} Student ({status})" ;')
        for i, (pred, val) in enumerate(props):
            end = " ." if i == len(props) - 1 else " ;"
            lines.append(f"    ait:{pred} {val}{end}")
        lines.append("")

    return lines


# =============================================================================
# FACULTY MAPPING
# =============================================================================

def _build_faculty_turtle(conn, entity_names: Optional[list[str]] = None) -> list[str]:
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
        props = []
        if grading:
            props.append(("makeKnownCriteriaForGrading", "true"))
        if disciplinary:
            props.append(("followProceduresForDisciplinaryActions", "true"))
        if discloses:
            props.append(("disclose", "true"))
        if reports:
            props.append(("suspectCheatingDuringExamOrAssignmentOrResearchProject", "true"))
            props.append(("reported", "true"))
        lines.append(f"# -- {title} {first} {last} ({fid}) --")
        lines.append(f"# Department: {dept} | Position: {pos}")
        lines.append(f"ait:{name} a ait:Faculty ;")
        lines.append(f'    rdfs:label "{title} {first} {last} - {pos}" ;')
        for i, (pred, val) in enumerate(props):
            end = " ." if i == len(props) - 1 else " ;"
            lines.append(f"    ait:{pred} {val}{end}")
        if not props:
            lines[-1] = lines[-1].rstrip(" ;") + " ."
        lines.append("")

    return lines


# =============================================================================
# STAFF MAPPING
# =============================================================================

def _build_staff_turtle(conn, entity_names: Optional[list[str]] = None) -> list[str]:
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
        props = []
        if gifts:
            props.append(("reported", "true"))
        if settlements:
            props.append(("settled", "true"))
        if fees:
            props.append(("feesPaid", "true"))
            props.append(("payFees", "true"))
        if ethical:
            props.append(("usesAuthorityEthicallyWithRespectAndSensitivityAndInAccordanceWithInstitutesPolicies", "true"))
            props.append(("disclose", "true"))  # ethical employees disclose conflicts
        props.append(("expresses_personal_opinion", "true"))
        props.append(("undergoDisciplinaryAction", "true"))
        lines.append(f"# -- {first} {last} ({sid}) --")
        lines.append(f"# Department: {dept} | Role: {role}")
        lines.append(f"ait:{first} a ait:Employee ;")
        lines.append(f'    rdfs:label "{first} {last} - {role}" ;')
        for i, (pred, val) in enumerate(props):
            end = " ." if i == len(props) - 1 else " ;"
            lines.append(f"    ait:{pred} {val}{end}")
        lines.append("")

    return lines

# =============================================================================
# COMMITTEE MAPPING
# =============================================================================

def _build_committee_turtle(conn, entity_names: Optional[list[str]] = None) -> list[str]:
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
        entity_names: Optional[list[str]] = None
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
    from policy_checker.database.connection import get_connection

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
            entity_count += sum(1 for l in section_lines if " a ait:" in l)
            prop_count += sum(1 for l in section_lines if l.strip().startswith("ait:") and " a " not in l)

    turtle_str = "\n".join(all_lines)
    return {
        "turtle": turtle_str,
        "entity_count": entity_count,
        "property_count": prop_count,
    }

def list_entities() -> list[dict]:
    from policy_checker.database.connection import get_connection

    entities = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.first_name, s.last_name,
                       'Student' as entity_type,
                       s.program, s.enrollment_status, s.degree_level,
                       (SELECT COUNT(*) FROM conduct_records cr WHERE cr.student_id = s.student_id) as violation_count,
                       COALESCE(fr.payment_status, 'N/A') as pay_status,
                       COALESCE(sc.cooking_in_dorm, false) as cooking,
                       COALESCE(sc.pet_in_dorm, false) as pet,
                       COALESCE(sc.noisy_in_dorm, false) as noisy,
                       COALESCE(sc.disturbing_residents, false) as disturbing
                FROM students s
                LEFT JOIN LATERAL (
                    SELECT payment_status FROM fee_records f
                    WHERE f.student_id = s.student_id
                    ORDER BY f.semester DESC LIMIT 1
                ) fr ON true
                LEFT JOIN student_conduct sc ON sc.student_id = s.student_id
                ORDER BY s.student_id
            """)
            for row in cur.fetchall():
                (first, last, etype, program, status, degree,
                 viol_count, pay_status, cooking, pet, noisy, disturbing) = row
                # Build detail string
                issues = []
                if pay_status in ("Overdue", "Partial"):
                    issues.append(f"Fee: {pay_status}")
                if cooking:
                    issues.append("Cooking violation")
                if pet:
                    issues.append("Pet violation")
                if noisy:
                    issues.append("Noise violation")
                if disturbing:
                    issues.append("Disturbing residents")
                detail_str = ", ".join(issues) if issues else "No known issues"
                entities.append({
                    "name": first,
                    "type": etype,
                    "label": f"{first} {last} ({degree} - {program})",
                    "properties": 30,
                    "detail": f"{status} | {detail_str}",
                    "status": status,
                    "issues": len(issues),
                })

            # Faculty
            cur.execute("""
                SELECT title, first_name, last_name, department, position,
                       grading_criteria_published, follows_disciplinary_procedures,
                       discloses_conflicts, reports_cheating_suspects
                FROM faculty ORDER BY id
            """)
            for row in cur.fetchall():
                title, first, last, dept, pos, grading, disc, conflicts, reports = row
                issues = []
                if not grading:
                    issues.append("No grading criteria")
                if not disc:
                    issues.append("No disciplinary procedures")
                if not conflicts:
                    issues.append("Undisclosed conflicts")
                if not reports:
                    issues.append("Not reporting cheating")
                detail_str = ", ".join(issues) if issues else "No known issues"
                entities.append({
                    "name": f"{title}{first}{last}".replace(" ", "").replace(".", ""),
                    "type": "Faculty",
                    "label": f"{title} {first} {last} ({pos}, {dept})",
                    "properties": 5,
                    "detail": detail_str,
                    "status": "Active",
                    "issues": len(issues),
                })

            # Staff
            cur.execute("""
                SELECT first_name, last_name, department, role,
                       gifts_reported, settlements_reported,
                       fees_managed_properly, ethical_authority_use
                FROM staff ORDER BY id
            """)
            for row in cur.fetchall():
                first, last, dept, role, gifts, settle, fees, ethical = row
                issues = []
                if not gifts:
                    issues.append("Unreported gifts")
                if not settle:
                    issues.append("Unsettled obligations")
                if not ethical:
                    issues.append("Authority misuse")
                detail_str = ", ".join(issues) if issues else "No known issues"
                entities.append({
                    "name": first,
                    "type": "Employee",
                    "label": f"{first} {last} ({role}, {dept})",
                    "properties": 7,
                    "detail": detail_str,
                    "status": "Active",
                    "issues": len(issues),
                })

            # Committees
            cur.execute("""
                SELECT committee_name, committee_type, chair_elected
                FROM committees ORDER BY id
            """)
            for row in cur.fetchall():
                name, ctype, chair = row
                issues = []
                if not chair:
                    issues.append("No chair elected")
                detail_str = ", ".join(issues) if issues else "No known issues"
                entities.append({
                    "name": name.replace(" ", "").replace("&", "And"),
                    "type": "Committee",
                    "label": f"{name} ({ctype})",
                    "properties": 14,
                    "detail": detail_str,
                    "status": "Active",
                    "issues": len(issues),
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