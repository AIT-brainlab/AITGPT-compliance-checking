"""
db.seed - Populate PostgreSQL with AIT university data.

Creates tables (idempotent) and inserts demo data that mirrors
a real Student Information System (SIS): data includes:
- students, programs, degrees
- fees and payments
- accommodations
- conduct records
- academic records
- faculty and staff
- committees

Usage:
    python -m db.seed            # seed from project root
    python -m db.seed --reset    # drop + recreate tables first

"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def _run_schema(conn) -> None:
    """Execute schema.sql to create tables (idempotent)."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("[seed] [OK] Schema created/verified")


def _drop_tables(conn) -> None:
    """Drop all tables for a clean reset."""
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS conduct_records CASCADE;
            DROP TABLE IF EXISTS student_conduct CASCADE;
            DROP TABLE IF EXISTS academic_records CASCADE;
            DROP TABLE IF EXISTS accommodations CASCADE;
            DROP TABLE IF EXISTS fee_records CASCADE;
            DROP TABLE IF EXISTS committees CASCADE;
            DROP TABLE IF EXISTS staff CASCADE;
            DROP TABLE IF EXISTS faculty CASCADE;
            DROP TABLE IF EXISTS students CASCADE;
            DROP TABLE IF EXISTS entities CASCADE;
            DROP TABLE IF EXISTS entity_properties CASCADE;
        """)
    conn.commit()
    print("[seed] [OK] Old tables dropped")


def _seed_students(conn) -> dict:
    """Insert students and return {name: id} mapping."""
    students = [
        # (student_id, first, last, email, program, degree, status, enroll_date, grad_date, new, advisor)
        ("ST12400", "Somchai", "Prasert", "st12400@ait.asia",
         "Computer Science and Information Management", "Master", "Active",
         date(2025, 8, 15), date(2027, 5, 30), False, "Dr. Kenji Tanaka"),

        ("ST12401", "Napat", "Srikhao", "st12401@ait.asia",
         "Industrial Engineering and Management", "Bachelor", "Active",
         date(2026, 1, 10), date(2029, 12, 15), True, "Dr. Amara Chen"),

        ("ST12402", "Priya", "Sharma", "st12402@ait.asia",
         "Environmental Engineering and Management", "Master", "Active",
         date(2025, 8, 15), date(2027, 5, 30), False, "Dr. Rajesh Kumar"),

        ("ST12403", "Lin", "Wei", "st12403@ait.asia",
         "Remote Sensing and Geographic Information Systems", "PhD", "Active",
         date(2024, 1, 10), date(2028, 12, 15), False, "Prof. Yuko Sato"),

        ("ST12404", "Ahmad", "Rizky", "st12404@ait.asia",
         "Water Engineering and Management", "Master", "Active",
         date(2026, 1, 10), date(2027, 12, 15), True, "Dr. Kenji Tanaka"),

        ("ST12405", "Mei", "Nguyen", "st12405@ait.asia",
         "Data Science and Artificial Intelligence", "Master", "Suspended",
         date(2025, 8, 15), date(2027, 5, 30), False, "Dr. Amara Chen"),
    ]

    ids = {}
    with conn.cursor() as cur:
        for s in students:
            cur.execute("""
                INSERT INTO students
                    (student_id, first_name, last_name, email, program,
                     degree_level, enrollment_status, enrollment_date,
                     expected_graduation, is_new_student, advisor)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (student_id) DO UPDATE
                    SET first_name = EXCLUDED.first_name
                RETURNING student_id
            """, s)
            row_id = cur.fetchone()[0]
            ids[s[1]] = row_id  # first_name -> student_id
    conn.commit()
    print(f"  -> students: {len(students)} records")
    return ids


def _seed_fee_records(conn, student_ids: dict) -> None:
    """Insert fee payment records."""
    records = [
        # Somchai - fully paid
        (student_ids["Somchai"], "2025-2", 85000.00, 0, 85000.00, "Paid",
         date(2025, 8, 1), True, "Bank Transfer"),
        (student_ids["Somchai"], "2026-1", 85000.00, 0, 85000.00, "Paid",
         date(2026, 1, 5), True, "Bank Transfer"),

        # Napat - UNPAID (fee defaulter scenario)
        (student_ids["Napat"], "2026-1", 72000.00, 0, 0, "Overdue",
         None, False, None),

        # Priya - paid via scholarship
        (student_ids["Priya"], "2025-2", 85000.00, 40000.00, 85000.00, "Paid",
         date(2025, 8, 10), True, "Sponsor"),
        (student_ids["Priya"], "2026-1", 85000.00, 40000.00, 85000.00, "Paid",
         date(2026, 1, 8), True, "Sponsor"),

        # Lin - PhD, fully paid
        (student_ids["Lin"], "2025-2", 95000.00, 95000.00, 95000.00, "Paid",
         date(2025, 8, 3), True, "Scholarship"),
        (student_ids["Lin"], "2026-1", 95000.00, 95000.00, 95000.00, "Paid",
         date(2026, 1, 2), True, "Scholarship"),

        # Ahmad - new student, partial payment
        (student_ids["Ahmad"], "2026-1", 85000.00, 0, 42500.00, "Partial",
         date(2026, 1, 12), True, "Bank Transfer"),

        # Mei - suspended, fees unpaid
        (student_ids["Mei"], "2026-1", 85000.00, 0, 0, "Overdue",
         None, False, None),
    ]

    with conn.cursor() as cur:
        for r in records:
            cur.execute("""
                INSERT INTO fee_records
                    (student_id, semester, tuition_amount, scholarship_amount,
                     amount_paid, payment_status, payment_date,
                     first_installment_paid, payment_method)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (student_id, semester) DO NOTHING
            """, r)
    conn.commit()
    print(f"  -> fee_records: {len(records)} records")


def _seed_accommodations(conn, student_ids: dict) -> None:
    """Insert accommodation records."""
    records = [
        # Somchai - good resident
        (student_ids["Somchai"], "AIT Dormitory Block A", "A-204", "Single",
         date(2025, 8, 18), None, 4500.00,
         True, True, False, False, True, True, True, True, True, True),

        # Priya - disruptive dorm resident (cooking, noise, pet)
        (student_ids["Priya"], "AIT Dormitory Block C", "C-112", "Double",
         date(2025, 8, 20), None, 3500.00,
         True, True, False, False, True,
         False, False, False,  # room_clean=F, common_area_clean=F, unit_hygiene=F
         True, True),

        # Lin - PhD with spouse, family housing
        (student_ids["Lin"], "AIT Family Housing", "FH-08", "Family",
         date(2024, 1, 20), None, 7500.00,
         True, True, True, False, True, True, True, True, True, True),

        # Ahmad - new student, on waiting list
        (student_ids["Ahmad"], "AIT Dormitory Block B", "B-301", "Single",
         date(2026, 1, 15), None, 4500.00,
         False, True, False, True, True, True, True, True, False, True),
    ]

    with conn.cursor() as cur:
        for r in records:
            cur.execute("""
                INSERT INTO accommodations
                    (student_id, building, room_number, room_type,
                     check_in_date, check_out_date, monthly_rent,
                     deposit_paid, rent_current, with_spouse,
                     on_waiting_list, provided_arrival_date,
                     room_clean, common_area_clean, unit_hygiene,
                     confirmed_offer, vacated_on_time)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (student_id, building, room_number) DO NOTHING
            """, r)
    conn.commit()
    print(f"  -> accommodations: {len(records)} records")


def _seed_conduct_records(conn, student_ids: dict) -> None:
    """Insert conduct violation records for problematic students."""
    records = [
        # Priya - multiple dorm violations
        (student_ids["Priya"], "Cooking",
         "Caught using electric cooker in dorm room C-112. Category-1 dorms prohibit cooking.",
         date(2025, 10, 15), "Open", "Dorm Manager"),
        (student_ids["Priya"], "Noise",
         "Multiple complaints from neighbors about loud group study sessions after 22:00.",
         date(2025, 11, 2), "Open", "Resident Advisor"),
        (student_ids["Priya"], "Pet",
         "Unauthorized cat found in room during routine inspection.",
         date(2025, 12, 8), "Escalated", "Dorm Manager"),

        # Mei - academic misconduct
        (student_ids["Mei"], "Cheating",
         "Plagiarism detected in final project submission for DSAI-601.",
         date(2026, 1, 5), "Escalated", "Dr. Amara Chen"),
    ]

    with conn.cursor() as cur:
        for r in records:
            cur.execute("""
                INSERT INTO conduct_records
                    (student_id, incident_type, description,
                     incident_date, status, reported_by)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, r)
    conn.commit()
    print(f"  -> conduct_records: {len(records)} records")


def _seed_student_conduct(conn, student_ids: dict) -> None:
    """Insert behavioral conduct flags for each student."""
    records = [
        # (student_id, ethical, peaceful, library, IT, concerns,
        #  cooking, noisy, pet, disturbing)

        # Somchai - model student
        (student_ids["Somchai"], True, True, True, True, True,
         False, False, False, False),

        # Napat - good conduct, just can't pay fees
        (student_ids["Napat"], True, True, True, True, True,
         False, False, False, False),

        # Priya - dorm violations
        (student_ids["Priya"], True, True, True, True, True,
         True, True, True, True),    # cooking, noisy, pet, disturbing

        # Lin - model PhD student
        (student_ids["Lin"], True, True, True, True, True,
         False, False, False, False),

        # Ahmad - new, good conduct
        (student_ids["Ahmad"], True, True, True, True, True,
         False, False, False, False),

        # Mei - suspended, ethical issues
        (student_ids["Mei"], False, True, True, True, False,
         False, False, False, False),
    ]

    with conn.cursor() as cur:
        for r in records:
            cur.execute("""
                INSERT INTO student_conduct
                    (student_id, ethical_conduct, peaceful_environment,
                     library_responsible_use, it_acceptable_use,
                     brings_concerns_to_attention,
                     cooking_in_dorm, noisy_in_dorm, pet_in_dorm,
                     disturbing_residents)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (student_id) DO NOTHING
            """, r)
    conn.commit()
    print(f"  -> student_conduct: {len(records)} records")


def _seed_academic_records(conn, student_ids: dict) -> None:
    """Insert academic/publication records."""
    records = [
        # (student_id, registered, grade_det, makeup, corresponding, journal, first_author)
        (student_ids["Somchai"], True, True, True, True, True, True),
        (student_ids["Napat"], True, True, True, False, False, False),
        (student_ids["Priya"], True, True, True, True, True, True),
        (student_ids["Lin"], True, True, True, True, True, True),
        (student_ids["Ahmad"], True, True, True, False, False, False),
        (student_ids["Mei"], False, True, True, False, False, False),
    ]

    with conn.cursor() as cur:
        for r in records:
            cur.execute("""
                INSERT INTO academic_records
                    (student_id, registered_with_registry,
                     grade_determined_in_courses, makeup_classes_scheduled,
                     serves_as_corresponding_author,
                     corresponds_with_journal,
                     first_author_in_multi_authored)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (student_id) DO NOTHING
            """, r)
    conn.commit()
    print(f"  -> academic_records: {len(records)} records")


def _seed_faculty(conn) -> None:
    """Insert faculty members."""
    faculty = [
        # (faculty_id, title, first, last, email, department, position,
        #  grading_pub, disciplinary, discloses, reports_cheating)
        ("FAC-001", "Dr.", "Kenji", "Tanaka", "kenji.t@ait.ac.th",
         "Computer Science and Information Management", "Associate Professor",
         True, True, True, True),

        ("FAC-002", "Dr.", "Amara", "Chen", "amara.c@ait.ac.th",
         "Data Science and Artificial Intelligence", "Assistant Professor",
         True, True, True, True),

        ("FAC-003", "Prof.", "Rajesh", "Kumar", "rajesh.k@ait.ac.th",
         "Environmental Engineering and Management", "Professor",
         False, True, True, False),   # hasn't published grading criteria
    ]

    with conn.cursor() as cur:
        for f in faculty:
            cur.execute("""
                INSERT INTO faculty
                    (faculty_id, title, first_name, last_name, email,
                     department, position, grading_criteria_published,
                     follows_disciplinary_procedures, discloses_conflicts,
                     reports_cheating_suspects)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (faculty_id) DO NOTHING
            """, f)
    conn.commit()
    print(f"  -> faculty: {len(faculty)} records")


def _seed_staff(conn) -> None:
    """Insert administrative staff."""
    staff_records = [
        # (staff_id, first, last, email, department, role,
        #  gifts_reported, settlements_reported, fees_managed, ethical_auth)
        ("STF-001", "Maria", "Santos", "maria.s@ait.ac.th",
         "Office of Student Affairs", "Administrative Officer",
         False, False, True, True),    # unreported gift

        ("STF-002", "David", "Park", "david.p@ait.ac.th",
         "Finance Department", "Accounts Manager",
         True, True, True, True),
    ]

    with conn.cursor() as cur:
        for s in staff_records:
            cur.execute("""
                INSERT INTO staff
                    (staff_id, first_name, last_name, email,
                     department, role, gifts_reported,
                     settlements_reported, fees_managed_properly,
                     ethical_authority_use)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (staff_id) DO NOTHING
            """, s)
    conn.commit()
    print(f"  -> staff: {len(staff_records)} records")


def _seed_committees(conn) -> None:
    """Insert institutional committees."""
    committees = [
        # (name, type, chair_elected, active, grievances, confidential, records, tribunals)
        ("AIT Grievance and Ethics Committee", "Grievance",
         True, True, True, True, True, True),

        ("Academic Standards Committee", "Academic",
         True, True, False, True, True, False),
    ]

    with conn.cursor() as cur:
        for c in committees:
            cur.execute("""
                INSERT INTO committees
                    (committee_name, committee_type, chair_elected,
                     is_active, handles_grievances,
                     maintains_confidentiality, records_facts,
                     convenes_tribunals)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (committee_name) DO NOTHING
            """, c)
    conn.commit()
    print(f"  -> committees: {len(committees)} records")


def seed(reset: bool = False) -> None:
    """Run the full seed process."""
    with get_connection() as conn:
        if reset:
            _drop_tables(conn)

        _run_schema(conn)

        student_ids = _seed_students(conn)
        _seed_fee_records(conn, student_ids)
        _seed_accommodations(conn, student_ids)
        _seed_conduct_records(conn, student_ids)
        _seed_student_conduct(conn, student_ids)
        _seed_academic_records(conn, student_ids)
        _seed_faculty(conn)
        _seed_staff(conn)
        _seed_committees(conn)

        print(f"\n[seed] [OK] Database seeded with realistic AIT demo data")


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    seed(reset=reset_flag)
