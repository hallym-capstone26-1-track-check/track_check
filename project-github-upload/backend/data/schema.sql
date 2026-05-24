-- =============================================================
-- schema_lossless.sql — track_rules.json 손실 없는 PostgreSQL 스키마
-- 목적:
--   1) 기존 JSON의 핵심 데이터를 관계형 테이블로 조회 가능하게 저장
--   2) JSON 원문/비고/수동검토/원문조건/보조필드를 raw JSON으로 함께 보존
--   3) 필요하면 DB만으로도 track_rules.json과 같은 의미를 복원 가능하게 함
-- =============================================================
-- 실행 방법 예시 (PowerShell):
--   $env:PGPASSWORD='비밀번호'
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d track_db -f schema_lossless.sql
-- =============================================================

-- 재실행을 위해 기존 객체 제거
DROP VIEW IF EXISTS v_all_courses CASCADE;
DROP TABLE IF EXISTS source_documents CASCADE;
DROP TABLE IF EXISTS manual_review_items CASCADE;
DROP TABLE IF EXISTS course_aliases CASCADE;
DROP TABLE IF EXISTS track_rule_course_indexes CASCADE;
DROP TABLE IF EXISTS track_rule_module_groups CASCADE;
DROP TABLE IF EXISTS track_rule_courses CASCADE;
DROP TABLE IF EXISTS track_rules CASCADE;
DROP TABLE IF EXISTS track_modules CASCADE;
DROP TABLE IF EXISTS tracks CASCADE;
DROP TABLE IF EXISTS module_courses CASCADE;
DROP TABLE IF EXISTS modules CASCADE;
DROP TABLE IF EXISTS departments CASCADE;
DROP TABLE IF EXISTS colleges CASCADE;

-- =============================================================
-- 0. source_documents
-- JSON 원본 전체를 그대로 보관하는 테이블.
-- 관계형 테이블로 분해하면서 누락될 수 있는 모든 정보를 이 테이블에서 보존한다.
-- original_json_text: 원본 텍스트 그대로 저장하므로 key 순서까지 보존 가능
-- full_json: JSONB로 저장하므로 DB 안에서 JSON 질의 가능
-- =============================================================
CREATE TABLE source_documents (
    id                  SERIAL PRIMARY KEY,
    document_name        VARCHAR(100) NOT NULL UNIQUE,
    source               TEXT,
    schema_version       VARCHAR(50),
    description          TEXT,
    original_json_hash   CHAR(64) NOT NULL,
    original_json_text   TEXT NOT NULL,
    full_json            JSONB NOT NULL,
    imported_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- 1. colleges (단과대/스쿨)
-- =============================================================
CREATE TABLE colleges (
    id            SERIAL PRIMARY KEY,
    college_name  VARCHAR(100) NOT NULL UNIQUE,
    position      INT NOT NULL,
    raw_payload   JSONB NOT NULL
);

-- =============================================================
-- 2. departments (학부/전공/학과)
-- global_note와 raw_payload를 추가하여 JSON의 학과 단위 비고를 보존한다.
-- =============================================================
CREATE TABLE departments (
    id            SERIAL PRIMARY KEY,
    college_id    INT NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
    dept_name     VARCHAR(150) NOT NULL,
    page_ref      VARCHAR(30),
    global_note   TEXT,
    position      INT NOT NULL,
    raw_payload   JSONB NOT NULL,
    UNIQUE (college_id, dept_name)
);

CREATE INDEX idx_departments_college_id ON departments(college_id);

-- =============================================================
-- 3. modules (모듈)
-- position과 raw_payload로 JSON 배열 순서와 원본 필드를 보존한다.
-- =============================================================
CREATE TABLE modules (
    id             SERIAL PRIMARY KEY,
    department_id  INT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    module_key     VARCHAR(10) NOT NULL,
    module_name    VARCHAR(150) NOT NULL,
    position       INT NOT NULL,
    raw_payload    JSONB NOT NULL,
    UNIQUE (department_id, module_key)
);

CREATE INDEX idx_modules_department_id ON modules(department_id);

-- =============================================================
-- 4. module_courses (모듈 소속 과목)
-- note를 추가하여 폐지/변경/미존재 교과목 등의 비고를 보존한다.
-- raw_payload로 과목 객체 원문 전체도 보존한다.
-- =============================================================
CREATE TABLE module_courses (
    id           SERIAL PRIMARY KEY,
    module_id    INT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    course_name  VARCHAR(250) NOT NULL,
    credits      INT NOT NULL CHECK (credits BETWEEN 0 AND 30),
    note         TEXT,
    position     INT NOT NULL,
    raw_payload  JSONB NOT NULL,
    UNIQUE (module_id, position)
);

CREATE INDEX idx_module_courses_module_id ON module_courses(module_id);
CREATE INDEX idx_module_courses_course_name ON module_courses(course_name);

-- =============================================================
-- 5. tracks (트랙)
-- required_courses, required_courses_raw, unsupported_rule_types,
-- manual_review_items를 JSONB로 보존한다.
-- raw_payload는 트랙 객체 전체를 그대로 저장한다.
-- =============================================================
CREATE TABLE tracks (
    id                       SERIAL PRIMARY KEY,
    department_id            INT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    track_id_text            VARCHAR(300) NOT NULL UNIQUE,
    track_name               VARCHAR(250) NOT NULL,
    raw_requirement_text     TEXT,
    analysis_mode            VARCHAR(20) NOT NULL DEFAULT 'auto',
    note                     TEXT,
    required_courses         JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_courses_raw     JSONB NOT NULL DEFAULT '[]'::jsonb,
    unsupported_rule_types   JSONB NOT NULL DEFAULT '[]'::jsonb,
    manual_review_items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    position                 INT NOT NULL,
    raw_payload              JSONB NOT NULL
);

CREATE INDEX idx_tracks_department_id ON tracks(department_id);
CREATE INDEX idx_tracks_track_name ON tracks(track_name);
CREATE INDEX idx_tracks_analysis_mode ON tracks(analysis_mode);

-- =============================================================
-- 6. track_modules (트랙 ↔ 모듈 연결)
-- position으로 track.module_keys 배열 순서를 보존한다.
-- =============================================================
CREATE TABLE track_modules (
    id        SERIAL PRIMARY KEY,
    track_id  INT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    module_id INT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    module_key VARCHAR(10) NOT NULL,
    position  INT NOT NULL,
    UNIQUE (track_id, module_id)
);

CREATE INDEX idx_track_modules_track_id ON track_modules(track_id);
CREATE INDEX idx_track_modules_module_id ON track_modules(module_id);

-- =============================================================
-- 7. track_rules (트랙 이수 규칙)
-- raw_payload를 추가하여 rule 내부의 note, examples, courses_raw,
-- canonical_courses_mapped, manual_review_courses, text, items 등을 모두 보존한다.
-- =============================================================
CREATE TABLE track_rules (
    id              SERIAL PRIMARY KEY,
    track_id        INT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    rule_type       VARCHAR(80) NOT NULL,
    value           INT,
    module_key_ref  VARCHAR(10),
    note            TEXT,
    position        INT NOT NULL,
    raw_payload     JSONB NOT NULL
);

CREATE INDEX idx_track_rules_track_id ON track_rules(track_id);
CREATE INDEX idx_track_rules_rule_type ON track_rules(rule_type);

-- =============================================================
-- 8. track_rule_courses
-- 이름은 courses지만, required_items_raw의 items와 raw_text_requirement의 text도
-- 보존하기 위해 item_type을 둔다.
-- item_type 예:
--   canonical, raw, canonical_mapped, manual_review, raw_item, raw_text
-- =============================================================
CREATE TABLE track_rule_courses (
    id             SERIAL PRIMARY KEY,
    track_rule_id  INT NOT NULL REFERENCES track_rules(id) ON DELETE CASCADE,
    course_name    TEXT NOT NULL,
    item_type      VARCHAR(50) NOT NULL DEFAULT 'canonical',
    position       INT NOT NULL
);

CREATE INDEX idx_track_rule_courses_rule_id ON track_rule_courses(track_rule_id);
CREATE INDEX idx_track_rule_courses_name ON track_rule_courses(course_name);

-- =============================================================
-- 9. track_rule_module_groups
-- module_group_min_courses_total / track_all_courses_in_modules에 사용.
-- position으로 module_keys 배열 순서를 보존한다.
-- =============================================================
CREATE TABLE track_rule_module_groups (
    id             SERIAL PRIMARY KEY,
    track_rule_id  INT NOT NULL REFERENCES track_rules(id) ON DELETE CASCADE,
    module_key     VARCHAR(10) NOT NULL,
    position       INT NOT NULL
);

CREATE INDEX idx_track_rule_module_groups_rule_id ON track_rule_module_groups(track_rule_id);

-- =============================================================
-- 10. track_rule_course_indexes
-- module_course_indexes_all에 사용.
-- =============================================================
CREATE TABLE track_rule_course_indexes (
    id             SERIAL PRIMARY KEY,
    track_rule_id  INT NOT NULL REFERENCES track_rules(id) ON DELETE CASCADE,
    module_key     VARCHAR(10) NOT NULL,
    course_index   INT NOT NULL,
    position       INT NOT NULL
);

CREATE INDEX idx_track_rule_course_indexes_rule_id ON track_rule_course_indexes(track_rule_id);

-- =============================================================
-- 11. course_aliases
-- OCR/입력 과목명 정규화용 별칭. raw_payload로 원본 pair도 저장한다.
-- =============================================================
CREATE TABLE course_aliases (
    id              SERIAL PRIMARY KEY,
    alias_name      VARCHAR(250) NOT NULL UNIQUE,
    canonical_name  VARCHAR(250) NOT NULL,
    raw_payload     JSONB NOT NULL
);

CREATE INDEX idx_course_aliases_canonical_name ON course_aliases(canonical_name);

-- =============================================================
-- 12. manual_review_items
-- 최상위 manual_review_required와 트랙 내부 manual_review_items를 모두 저장한다.
-- source_scope: top_level | track_level | rule_level
-- raw_payload로 원문 객체/문자열을 보존한다.
-- =============================================================
CREATE TABLE manual_review_items (
    id            SERIAL PRIMARY KEY,
    dept_name     VARCHAR(150),
    track_name    VARCHAR(250),
    item          TEXT NOT NULL,
    reason        TEXT,
    source_scope  VARCHAR(30) NOT NULL DEFAULT 'top_level',
    raw_payload   JSONB NOT NULL
);

CREATE INDEX idx_manual_review_items_dept_track ON manual_review_items(dept_name, track_name);

-- =============================================================
-- 편의 뷰 1: 전체 과목 목록 (OCR 퍼지 매칭용)
-- =============================================================
CREATE OR REPLACE VIEW v_all_courses AS
SELECT
    mc.id          AS course_id,
    mc.course_name,
    mc.credits,
    mc.note,
    mc.position,
    m.module_key,
    m.module_name,
    m.id           AS module_id,
    d.dept_name,
    d.id           AS department_id,
    c.college_name
FROM module_courses mc
JOIN modules     m ON m.id = mc.module_id
JOIN departments d ON d.id = m.department_id
JOIN colleges    c ON c.id = d.college_id;

-- =============================================================
-- 편의 뷰 2: 트랙별 규칙 요약
-- =============================================================
CREATE OR REPLACE VIEW v_track_rules_summary AS
SELECT
    c.college_name,
    d.dept_name,
    t.track_name,
    t.track_id_text,
    t.analysis_mode,
    t.unsupported_rule_types,
    tr.rule_type,
    tr.value,
    tr.module_key_ref,
    tr.position AS rule_position
FROM track_rules tr
JOIN tracks t      ON t.id = tr.track_id
JOIN departments d ON d.id = t.department_id
JOIN colleges c    ON c.id = d.college_id;

-- =============================================================
-- 완료
-- =============================================================
