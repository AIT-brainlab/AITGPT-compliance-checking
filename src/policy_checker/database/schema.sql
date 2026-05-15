-- =============================================================================
-- PolicyChecker - Realistic University Database Schema
-- =============================================================================
-- Models a real university student information system (SIS).
-- Tables mirror how an actual institution stores student, faculty,
-- staff, accommodation, and financial records.
--
-- The RDF converter (rdf_converter.py) reads these tables and maps
-- the relational fields to ait: ontology predicates for SHACL validation.
--
-- Run:  psql -U postgres -d ait_database -f db/schema.sql
-- Or:   python -m db.seed   (auto-runs this file first)
-- =============================================================================
-- ── Students ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    student_id VARCHAR(20) PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    program VARCHAR(200),
    degree_level VARCHAR(50),
    -- 'Master', 'PhD'
    enrollment_status VARCHAR(30) DEFAULT 'Active',
    -- Active, Inactive, Suspended, Graduated
    enrollment_date DATE,
    expected_graduation DATE,
    is_new_student BOOLEAN DEFAULT true,
    advisor VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- ── Fee Records ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fee_records (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    semester VARCHAR(20) NOT NULL,
    -- e.g. '2026-1'
    tuition_amount DECIMAL(10, 2),
    scholarship_amount DECIMAL(10, 2) DEFAULT 0,
    amount_paid DECIMAL(10, 2) DEFAULT 0,
    payment_status VARCHAR(20) DEFAULT 'Unpaid',
    -- Paid, Partial, Unpaid, Overdue
    payment_date DATE,
    first_installment_paid BOOLEAN DEFAULT false,
    payment_method VARCHAR(50),
    -- Bank Transfer, Cash, Sponsor
    UNIQUE(student_id, semester)
);
-- ── Accommodation ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accommodations (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    building VARCHAR(100),
    room_number VARCHAR(20),
    room_type VARCHAR(50),
    -- Single, Double, Family
    check_in_date DATE,
    check_out_date DATE,
    monthly_rent DECIMAL(10, 2),
    deposit_paid BOOLEAN DEFAULT false,
    rent_current BOOLEAN DEFAULT true,
    -- is rent up-to-date?
    with_spouse BOOLEAN DEFAULT false,
    on_waiting_list BOOLEAN DEFAULT false,
    provided_arrival_date BOOLEAN DEFAULT false,
    room_clean BOOLEAN DEFAULT true,
    -- maintains cleanliness
    common_area_clean BOOLEAN DEFAULT true,
    unit_hygiene BOOLEAN DEFAULT true,
    confirmed_offer BOOLEAN DEFAULT false,
    vacated_on_time BOOLEAN DEFAULT true,
    UNIQUE(student_id, building, room_number)
);
-- ── Conduct Records ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conduct_records (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    incident_type VARCHAR(100) NOT NULL,
    -- 'Cooking', 'Noise', 'Pet', 'Cheating'
    description TEXT,
    incident_date DATE,
    status VARCHAR(30) DEFAULT 'Open',
    -- Open, Resolved, Escalated
    reported_by VARCHAR(200)
);
-- ── Student Conduct (behavioral flags) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS student_conduct (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(20) UNIQUE NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    ethical_conduct BOOLEAN DEFAULT true,
    peaceful_environment BOOLEAN DEFAULT true,
    library_responsible_use BOOLEAN DEFAULT true,
    it_acceptable_use BOOLEAN DEFAULT true,
    brings_concerns_to_attention BOOLEAN DEFAULT true,
    cooking_in_dorm BOOLEAN DEFAULT false,
    -- violation if true
    noisy_in_dorm BOOLEAN DEFAULT false,
    -- violation if true
    pet_in_dorm BOOLEAN DEFAULT false,
    -- violation if true
    disturbing_residents BOOLEAN DEFAULT false -- violation if true
);
-- ── Academic Records ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS academic_records (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(20) UNIQUE NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    registered_with_registry BOOLEAN DEFAULT true,
    grade_determined_in_courses BOOLEAN DEFAULT true,
    makeup_classes_scheduled BOOLEAN DEFAULT true,
    serves_as_corresponding_author BOOLEAN DEFAULT false,
    corresponds_with_journal BOOLEAN DEFAULT false,
    first_author_in_multi_authored BOOLEAN DEFAULT false
);
-- ── Faculty ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS faculty (
    id SERIAL PRIMARY KEY,
    faculty_id VARCHAR(20) UNIQUE NOT NULL,
    -- e.g. 'FAC-001'
    title VARCHAR(20),
    -- Dr., Prof.
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    department VARCHAR(200),
    position VARCHAR(100),
    -- Lecturer, Assoc Prof, Prof
    grading_criteria_published BOOLEAN DEFAULT true,
    follows_disciplinary_procedures BOOLEAN DEFAULT true,
    discloses_conflicts BOOLEAN DEFAULT true,
    reports_cheating_suspects BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- ── Staff ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staff (
    id SERIAL PRIMARY KEY,
    staff_id VARCHAR(20) UNIQUE NOT NULL,
    -- e.g. 'STF-001'
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    department VARCHAR(200),
    role VARCHAR(100),
    -- Admin, Finance, HR, etc.
    gifts_reported BOOLEAN DEFAULT true,
    settlements_reported BOOLEAN DEFAULT true,
    fees_managed_properly BOOLEAN DEFAULT true,
    ethical_authority_use BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- ── Committees ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS committees (
    id SERIAL PRIMARY KEY,
    committee_name VARCHAR(200) UNIQUE NOT NULL,
    committee_type VARCHAR(100),
    -- Grievance, Ethics, Academic
    chair_elected BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    handles_grievances BOOLEAN DEFAULT false,
    maintains_confidentiality BOOLEAN DEFAULT true,
    records_facts BOOLEAN DEFAULT true,
    convenes_tribunals BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- ── Indexes ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_students_status ON students(enrollment_status);
CREATE INDEX IF NOT EXISTS idx_fees_student ON fee_records(student_id);
CREATE INDEX IF NOT EXISTS idx_accom_student ON accommodations(student_id);
CREATE INDEX IF NOT EXISTS idx_conduct_student ON conduct_records(student_id);