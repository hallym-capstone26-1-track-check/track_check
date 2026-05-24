r"""
migrate_json_to_db.py — track_rules.json → PostgreSQL 손실 없는 마이그레이션 스크립트

목적:
    - track_rules.json의 핵심 데이터를 관계형 테이블로 분해 저장한다.
    - 동시에 원본 JSON 텍스트, 전체 JSONB, 각 객체 raw_payload를 저장하여
      JSON의 비고/원문조건/수동검토/보조필드가 DB 변환 과정에서 사라지지 않게 한다.

실행 방법 (Capstone_Design/backend 폴더 기준):
    .\.venv\Scripts\python.exe scripts\migrate_json_to_db.py

필수 조건:
    1. PostgreSQL 서버 실행 중
    2. .env 파일에 DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD 설정
    3. data\schema.sql을 먼저 실행하여 테이블 생성
    4. backend/data/track_rules.json 존재

주의:
    - 이 스크립트는 기준 데이터만 DB에 저장한다.
    - 학생 성적표 이미지, 이름, 학번, OCR 원문, 학생별 이수 과목/성적은 저장하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from dotenv import load_dotenv

# ─────────────────────────────────────────
# 경로 설정
# ─────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent          # Capstone_Design/backend/
DEFAULT_JSON_PATH = BASE_DIR / "data" / "track_rules.json"
JSON_PATH = Path(os.getenv("TRACK_RULES_JSON_PATH", str(DEFAULT_JSON_PATH)))
DOTENV_PATH = BASE_DIR / ".env"

load_dotenv(DOTENV_PATH)


# ─────────────────────────────────────────
# DB 연결
# ─────────────────────────────────────────
def get_connection():
    """.env의 DATABASE_URL 또는 DB_* 접속 정보를 사용해 PostgreSQL에 연결한다."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return psycopg2.connect(
            database_url,
            cursor_factory=RealDictCursor,
        )

    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "track_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        sslmode=os.getenv("DB_SSLMODE", "prefer"),
        cursor_factory=RealDictCursor,
    )


def as_jsonb(value: Any) -> Json:
    """Python dict/list 값을 psycopg2가 JSONB로 넣을 수 있게 감싼다."""
    return Json(value, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))


# ─────────────────────────────────────────
# 헬퍼: INSERT 후 id 반환
# ─────────────────────────────────────────
def insert_returning_id(cur, sql: str, params: tuple) -> int:
    cur.execute(sql + " RETURNING id", params)
    return cur.fetchone()["id"]


def insert_rule_items(cur, rule_id: int, values: list[str], item_type: str) -> int:
    """룰에 연결된 과목/원문/수동검토 항목을 순서대로 저장한다."""
    inserted = 0
    for pos, value in enumerate(values, start=1):
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        cur.execute(
            """
            INSERT INTO track_rule_courses
                (track_rule_id, course_name, item_type, position)
            VALUES (%s, %s, %s, %s)
            """,
            (rule_id, text, item_type, pos),
        )
        inserted += 1
    return inserted


def insert_manual_review(cur, *, dept_name: str | None, track_name: str | None,
                         item: Any, reason: str | None, source_scope: str) -> None:
    """최상위/트랙 내부 수동 검토 항목을 공통 방식으로 저장한다."""
    if item is None:
        return

    if isinstance(item, dict):
        item_text = str(item.get("item") or item.get("course_name") or item)
        reason_text = item.get("reason", reason)
        raw_payload = item
    else:
        item_text = str(item)
        reason_text = reason
        raw_payload = {"item": item}

    cur.execute(
        """
        INSERT INTO manual_review_items
            (dept_name, track_name, item, reason, source_scope, raw_payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (dept_name, track_name, item_text, reason_text, source_scope, as_jsonb(raw_payload)),
    )


# ─────────────────────────────────────────
# 메인 마이그레이션
# ─────────────────────────────────────────
def migrate(data: dict, original_json_text: str, cur) -> dict[str, int]:
    """track_rules.json 내용을 DB에 저장한다."""

    print("▶ 기존 데이터 초기화 중...")
    cur.execute(
        """
        TRUNCATE TABLE
            source_documents,
            manual_review_items,
            course_aliases,
            track_rule_course_indexes,
            track_rule_module_groups,
            track_rule_courses,
            track_rules,
            track_modules,
            tracks,
            module_courses,
            modules,
            departments,
            colleges
        RESTART IDENTITY CASCADE
        """
    )
    print("  초기화 완료")

    original_hash = hashlib.sha256(original_json_text.encode("utf-8")).hexdigest()

    # JSON 원본 전체 저장: DB가 JSON 원문을 완전히 보존하도록 하는 핵심 장치
    cur.execute(
        """
        INSERT INTO source_documents
            (document_name, source, schema_version, description,
             original_json_hash, original_json_text, full_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "track_rules.json",
            data.get("source"),
            data.get("schema_version"),
            data.get("description"),
            original_hash,
            original_json_text,
            as_jsonb(data),
        ),
    )

    counts = {
        "colleges": 0,
        "departments": 0,
        "modules": 0,
        "module_courses": 0,
        "tracks": 0,
        "track_modules": 0,
        "track_rules": 0,
        "track_rule_courses": 0,
        "track_rule_module_groups": 0,
        "track_rule_course_indexes": 0,
        "course_aliases": 0,
        "manual_review_items": 0,
    }

    # ── 단과대 / 학부 / 모듈 / 과목 / 트랙 / 룰 ─────────────────────
    for college_pos, college in enumerate(data.get("colleges", []), start=1):
        college_id = insert_returning_id(
            cur,
            """
            INSERT INTO colleges
                (college_name, position, raw_payload)
            VALUES (%s, %s, %s)
            """,
            (college["college_name"], college_pos, as_jsonb(college)),
        )
        counts["colleges"] += 1

        for dept_pos, dept in enumerate(college.get("departments", []), start=1):
            dept_name = dept["dept_name"]
            dept_id = insert_returning_id(
                cur,
                """
                INSERT INTO departments
                    (college_id, dept_name, page_ref, global_note, position, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    college_id,
                    dept_name,
                    dept.get("page_ref"),
                    dept.get("global_note"),
                    dept_pos,
                    as_jsonb(dept),
                ),
            )
            counts["departments"] += 1

            # 모듈 key → module id 매핑. 같은 학과 안에서만 사용한다.
            module_id_map: dict[str, int] = {}

            for module_pos, module in enumerate(dept.get("modules", []), start=1):
                module_key = module["module_key"]
                module_id = insert_returning_id(
                    cur,
                    """
                    INSERT INTO modules
                        (department_id, module_key, module_name, position, raw_payload)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        dept_id,
                        module_key,
                        module["module_name"],
                        module_pos,
                        as_jsonb(module),
                    ),
                )
                module_id_map[module_key] = module_id
                counts["modules"] += 1

                for course_pos, course in enumerate(module.get("courses", []), start=1):
                    cur.execute(
                        """
                        INSERT INTO module_courses
                            (module_id, course_name, credits, note, position, raw_payload)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            module_id,
                            course["course_name"],
                            course["credits"],
                            course.get("note"),
                            course_pos,
                            as_jsonb(course),
                        ),
                    )
                    counts["module_courses"] += 1

            for track_pos, track in enumerate(dept.get("tracks", []), start=1):
                track_id_text = track.get("track_id", f"{dept_name}__{track['track_name']}")
                track_id = insert_returning_id(
                    cur,
                    """
                    INSERT INTO tracks
                        (department_id, track_id_text, track_name, raw_requirement_text,
                         analysis_mode, note, required_courses, required_courses_raw,
                         unsupported_rule_types, manual_review_items_json, position, raw_payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        dept_id,
                        track_id_text,
                        track["track_name"],
                        track.get("raw_requirement_text"),
                        track.get("analysis_mode", "auto"),
                        track.get("note"),
                        as_jsonb(track.get("required_courses", [])),
                        as_jsonb(track.get("required_courses_raw", [])),
                        as_jsonb(track.get("unsupported_rule_types", [])),
                        as_jsonb(track.get("manual_review_items", [])),
                        track_pos,
                        as_jsonb(track),
                    ),
                )
                counts["tracks"] += 1

                # 트랙 ↔ 모듈 연결. module_keys 배열 순서까지 저장한다.
                for mk_pos, module_key in enumerate(track.get("module_keys", []), start=1):
                    module_id = module_id_map.get(module_key)
                    if module_id is None:
                        # JSON 자체의 문제를 빨리 발견하기 위해 조용히 넘기지 않는다.
                        raise ValueError(
                            f"트랙 '{track['track_name']}'에서 module_key '{module_key}'를 찾을 수 없습니다. "
                            f"학과: {dept_name}"
                        )
                    cur.execute(
                        """
                        INSERT INTO track_modules
                            (track_id, module_id, module_key, position)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (track_id, module_id) DO NOTHING
                        """,
                        (track_id, module_id, module_key, mk_pos),
                    )
                    counts["track_modules"] += 1

                # 트랙 내부 수동 검토 항목도 별도 테이블에 저장한다.
                for review_item in track.get("manual_review_items", []):
                    insert_manual_review(
                        cur,
                        dept_name=dept_name,
                        track_name=track.get("track_name"),
                        item=review_item,
                        reason=track.get("note"),
                        source_scope="track_level",
                    )
                    counts["manual_review_items"] += 1

                # 룰 삽입
                for rule_pos, rule in enumerate(track.get("rules", []), start=1):
                    rule_type = rule["type"]
                    value = rule.get("value")
                    module_key_ref = rule.get("module_key")

                    rule_id = insert_returning_id(
                        cur,
                        """
                        INSERT INTO track_rules
                            (track_id, rule_type, value, module_key_ref, note, position, raw_payload)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            track_id,
                            rule_type,
                            value,
                            module_key_ref,
                            rule.get("note"),
                            rule_pos,
                            as_jsonb(rule),
                        ),
                    )
                    counts["track_rules"] += 1

                    # 1) 과목/원문/수동검토 관련 룰 항목 저장
                    counts["track_rule_courses"] += insert_rule_items(
                        cur, rule_id, rule.get("courses", []), "canonical"
                    )
                    counts["track_rule_courses"] += insert_rule_items(
                        cur, rule_id, rule.get("courses_raw", []), "raw"
                    )
                    counts["track_rule_courses"] += insert_rule_items(
                        cur, rule_id, rule.get("canonical_courses_mapped", []), "canonical_mapped"
                    )
                    counts["track_rule_courses"] += insert_rule_items(
                        cur, rule_id, rule.get("manual_review_courses", []), "manual_review"
                    )

                    if rule_type == "required_items_raw":
                        counts["track_rule_courses"] += insert_rule_items(
                            cur, rule_id, rule.get("items", []), "raw_item"
                        )

                    if rule_type == "raw_text_requirement":
                        text = rule.get("text")
                        counts["track_rule_courses"] += insert_rule_items(
                            cur, rule_id, [text] if text else [], "raw_text"
                        )

                    # 비교과 예시도 검색 가능하게 저장하고 싶으면 examples로 넣어둔다.
                    # raw_payload에도 이미 보존되지만, 발표/디버깅 시 보기 편하다.
                    if rule_type == "extracurricular_program_required":
                        counts["track_rule_courses"] += insert_rule_items(
                            cur, rule_id, rule.get("examples", []), "example"
                        )

                    # 2) 모듈 그룹 저장
                    if rule_type in ("module_group_min_courses_total", "track_all_courses_in_modules"):
                        for group_pos, module_key in enumerate(rule.get("module_keys", []), start=1):
                            cur.execute(
                                """
                                INSERT INTO track_rule_module_groups
                                    (track_rule_id, module_key, position)
                                VALUES (%s, %s, %s)
                                """,
                                (rule_id, module_key, group_pos),
                            )
                            counts["track_rule_module_groups"] += 1

                    # 3) 모듈 내 특정 순번 저장
                    if rule_type == "module_course_indexes_all":
                        for idx_pos, idx in enumerate(rule.get("indexes", []), start=1):
                            cur.execute(
                                """
                                INSERT INTO track_rule_course_indexes
                                    (track_rule_id, module_key, course_index, position)
                                VALUES (%s, %s, %s, %s)
                                """,
                                (rule_id, module_key_ref, idx, idx_pos),
                            )
                            counts["track_rule_course_indexes"] += 1

    # ── course_aliases ───────────────────────
    aliases = data.get("course_aliases", {})
    for alias_pos, (alias, canonical) in enumerate(aliases.items(), start=1):
        cur.execute(
            """
            INSERT INTO course_aliases
                (alias_name, canonical_name, raw_payload)
            VALUES (%s, %s, %s)
            ON CONFLICT (alias_name)
            DO UPDATE SET canonical_name = EXCLUDED.canonical_name,
                          raw_payload = EXCLUDED.raw_payload
            """,
            (alias, canonical, as_jsonb({"alias_name": alias, "canonical_name": canonical, "position": alias_pos})),
        )
        counts["course_aliases"] += 1

    # ── 최상위 manual_review_required ──────────────────
    for item in data.get("manual_review_required", []):
        insert_manual_review(
            cur,
            dept_name=item.get("dept_name"),
            track_name=item.get("track_name"),
            item=item.get("item"),
            reason=item.get("reason"),
            source_scope="top_level",
        )
        counts["manual_review_items"] += 1

    print("▶ 삽입 완료")
    for key, value in counts.items():
        print(f"  {key:30s}: {value}건")

    return counts


# ─────────────────────────────────────────
# 검증
# ─────────────────────────────────────────
def count_expected(data: dict) -> dict[str, int]:
    """JSON 기준 예상 건수를 계산한다."""
    expected = {
        "colleges": 0,
        "departments": 0,
        "modules": 0,
        "module_courses": 0,
        "tracks": 0,
        "track_modules": 0,
        "track_rules": 0,
        "track_rule_module_groups": 0,
        "track_rule_course_indexes": 0,
        "course_aliases": len(data.get("course_aliases", {})),
        "manual_review_items": len(data.get("manual_review_required", [])),
    }

    for college in data.get("colleges", []):
        expected["colleges"] += 1
        for dept in college.get("departments", []):
            expected["departments"] += 1
            expected["modules"] += len(dept.get("modules", []))
            for module in dept.get("modules", []):
                expected["module_courses"] += len(module.get("courses", []))
            for track in dept.get("tracks", []):
                expected["tracks"] += 1
                expected["track_modules"] += len(track.get("module_keys", []))
                expected["manual_review_items"] += len(track.get("manual_review_items", []))
                expected["track_rules"] += len(track.get("rules", []))
                for rule in track.get("rules", []):
                    if rule.get("type") in ("module_group_min_courses_total", "track_all_courses_in_modules"):
                        expected["track_rule_module_groups"] += len(rule.get("module_keys", []))
                    if rule.get("type") == "module_course_indexes_all":
                        expected["track_rule_course_indexes"] += len(rule.get("indexes", []))
    return expected


def verify_counts(cur, expected: dict[str, int]) -> None:
    """JSON 예상 건수와 DB 실제 건수를 비교한다."""
    print("\n▶ JSON ↔ DB 건수 검증:")
    mismatches = []
    for table, exp_count in expected.items():
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
        db_count = cur.fetchone()["cnt"]
        status = "OK" if db_count == exp_count else "DIFF"
        print(f"  {table:30s}: JSON {exp_count:5d} / DB {db_count:5d}  [{status}]")
        if db_count != exp_count:
            mismatches.append((table, exp_count, db_count))

    if mismatches:
        raise AssertionError(f"JSON과 DB 건수가 다른 테이블이 있습니다: {mismatches}")


def verify_source_document(cur, original_hash: str) -> None:
    """source_documents에 저장된 JSON 원문 해시가 원본과 같은지 확인한다."""
    cur.execute(
        """
        SELECT original_json_hash, LENGTH(original_json_text) AS text_len
        FROM source_documents
        WHERE document_name = %s
        """,
        ("track_rules.json",),
    )
    row = cur.fetchone()
    if not row:
        raise AssertionError("source_documents에 track_rules.json 원본이 저장되지 않았습니다.")
    if row["original_json_hash"] != original_hash:
        raise AssertionError("source_documents의 JSON 원문 해시가 원본과 다릅니다.")
    print(f"\n▶ 원본 JSON 보존 검증: OK (text length: {row['text_len']})")


# ─────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────
if __name__ == "__main__":
    if not JSON_PATH.exists():
        print(f"[ERROR] track_rules.json 파일을 찾을 수 없습니다: {JSON_PATH}")
        sys.exit(1)

    print(f"▶ JSON 로드: {JSON_PATH}")
    original_json_text = JSON_PATH.read_text(encoding="utf-8")
    original_hash = hashlib.sha256(original_json_text.encode("utf-8")).hexdigest()
    data = json.loads(original_json_text)

    print("▶ DB 연결 중...")
    try:
        conn = get_connection()
    except Exception as e:
        print(f"[ERROR] DB 연결 실패: {e}")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            migrate(data, original_json_text, cur)
            verify_counts(cur, count_expected(data))
            verify_source_document(cur, original_hash)
        conn.commit()
        print("\n[완료] JSON → DB 손실 없는 마이그레이션이 성공적으로 완료되었습니다!")
        print("       현재 DB에는 관계형 데이터와 원본 JSON이 함께 저장되어 있습니다.")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] 마이그레이션 실패 (롤백됨): {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()
