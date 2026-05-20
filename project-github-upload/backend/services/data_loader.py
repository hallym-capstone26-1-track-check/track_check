"""
공통 데이터 로더

- 기본값은 track_rules.json을 기준 데이터로 사용하는 것입니다.
- DB를 붙이는 경우에도 JSON을 수정한 뒤 migrate_json_to_db.py로 DB를 갱신하는 흐름을 권장합니다.
- TRACK_DATA_SOURCE=db 또는 auto로 설정하면 PostgreSQL에서 데이터를 읽어
  기존 track_rules.json과 동일한 형태의 dict로 동적 조립하여 반환합니다.
- 덕분에 기존 분석 로직(track_analyzer 등)을 전혀 수정하지 않아도 됩니다.

실제 DB 스키마 기준 (2026-05-07 확인):
- colleges: id, college_name
- departments: id, college_id, dept_name, page_ref
- modules: id, department_id, module_key, module_name
- module_courses: id, module_id, course_name, credits, position, note
- tracks: id, department_id, track_id_text, track_name, raw_requirement_text, analysis_mode, note
- track_modules: id, track_id, module_id
- track_rules: id, track_id, rule_type, value, module_key_ref
- track_rule_courses: id, track_rule_id, course_name
- track_rule_module_groups: id, track_rule_id, module_key
- track_rule_course_indexes: id, track_rule_id, module_key, course_index
- course_aliases: alias_name, canonical_name
- manual_review_items: id, dept_name, track_name, item, reason
"""
from __future__ import annotations

import json
import logging
from typing import Any
from cachetools import cached, TTLCache

from config import TRACK_DATA_SOURCE, TRACK_RULES_JSON_PATH
from db import get_connection

logger = logging.getLogger(__name__)


def _load_track_rules_from_json() -> dict[str, Any]:
    """DB를 사용할 수 없을 때 로컬 track_rules.json을 읽습니다."""
    logger.info("로컬 JSON에서 트랙 규칙 데이터를 로드합니다: %s", TRACK_RULES_JSON_PATH)
    with open(TRACK_RULES_JSON_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


@cached(cache=TTLCache(maxsize=1, ttl=3600))
def load_track_rules() -> dict[str, Any]:
    """
    트랙 기준 데이터를 로드합니다.

    TRACK_DATA_SOURCE=json: track_rules.json만 읽습니다. MVP 기본값입니다.
    TRACK_DATA_SOURCE=db: DB만 읽습니다. 실패하면 오류를 발생시켜 데이터 문제를 드러냅니다.
    TRACK_DATA_SOURCE=auto: DB를 먼저 읽고, 실패하면 JSON으로 대체합니다.
    """
    if TRACK_DATA_SOURCE == "json":
        return _load_track_rules_from_json()

    logger.info("DB에서 트랙 규칙 데이터를 로드하고 JSON 구조로 조립 중...")

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # 1. 과목 별칭 로드
            cur.execute("SELECT alias_name, canonical_name FROM course_aliases")
            aliases_rows = cur.fetchall()
            course_aliases = {row["alias_name"]: row["canonical_name"] for row in aliases_rows}

            # 2. 수동 검토 항목 로드
            cur.execute("SELECT dept_name, track_name, item, reason FROM manual_review_items ORDER BY id")
            manual_reviews = [dict(row) for row in cur.fetchall()]

            # 3. Colleges 로드
            cur.execute("SELECT id, college_name FROM colleges ORDER BY id")
            colleges = cur.fetchall()

            colleges_data = []

            for college in colleges:
                # 4. Departments 로드
                cur.execute(
                    "SELECT id, dept_name, page_ref "
                    "FROM departments WHERE college_id = %s ORDER BY id",
                    (college["id"],)
                )
                departments = cur.fetchall()

                depts_data = []
                for dept in departments:
                    # 5. Modules 로드
                    cur.execute(
                        "SELECT id, module_key, module_name "
                        "FROM modules WHERE department_id = %s ORDER BY id",
                        (dept["id"],)
                    )
                    modules = cur.fetchall()

                    modules_data = []
                    for mod in modules:
                        # 6. Module Courses 로드
                        cur.execute(
                            "SELECT course_name, credits, note "
                            "FROM module_courses WHERE module_id = %s ORDER BY position",
                            (mod["id"],)
                        )
                        courses = cur.fetchall()

                        course_list = []
                        for c in courses:
                            c_dict = {"course_name": c["course_name"], "credits": c["credits"]}
                            if c["note"]:
                                c_dict["note"] = c["note"]
                            course_list.append(c_dict)

                        modules_data.append({
                            "module_key": mod["module_key"],
                            "module_name": mod["module_name"],
                            "courses": course_list
                        })

                    # 7. Tracks 로드
                    cur.execute(
                        "SELECT id, track_id_text, track_name, raw_requirement_text, analysis_mode, note "
                        "FROM tracks WHERE department_id = %s ORDER BY id",
                        (dept["id"],)
                    )
                    tracks = cur.fetchall()

                    tracks_data = []
                    for track in tracks:
                        track_dict = {
                            "track_id": track["track_id_text"],
                            "track_name": track["track_name"],
                            "analysis_mode": track["analysis_mode"] or "auto",
                        }
                        if track["raw_requirement_text"]:
                            track_dict["raw_requirement_text"] = track["raw_requirement_text"]
                        if track["note"]:
                            track_dict["note"] = track["note"]

                        # Track Module Keys
                        cur.execute("""
                            SELECT m.module_key FROM track_modules tm
                            JOIN modules m ON tm.module_id = m.id
                            WHERE tm.track_id = %s ORDER BY tm.id
                        """, (track["id"],))
                        mod_keys = [r["module_key"] for r in cur.fetchall()]
                        if mod_keys:
                            track_dict["module_keys"] = mod_keys

                        # 8. Rules 로드
                        cur.execute(
                            "SELECT id, rule_type, value, module_key_ref "
                            "FROM track_rules WHERE track_id = %s ORDER BY id",
                            (track["id"],)
                        )
                        rules = cur.fetchall()

                        rules_data = []
                        for rule in rules:
                            rt = rule["rule_type"]
                            rule_dict = {"type": rt}

                            if rule["value"] is not None:
                                rule_dict["value"] = rule["value"]
                            if rule["module_key_ref"]:
                                rule_dict["module_key"] = rule["module_key_ref"]

                            # required_courses_all: 보조 테이블에서 과목 목록 읽기
                            if rt == "required_courses_all":
                                cur.execute(
                                    "SELECT course_name FROM track_rule_courses "
                                    "WHERE track_rule_id = %s ORDER BY id",
                                    (rule["id"],)
                                )
                                courses_list = [r["course_name"] for r in cur.fetchall()]
                                rule_dict["courses"] = courses_list

                            # 모듈 그룹 규칙: 보조 테이블에서 module_keys 읽기
                            if rt in ("module_group_min_courses_total", "track_all_courses_in_modules"):
                                cur.execute(
                                    "SELECT module_key FROM track_rule_module_groups "
                                    "WHERE track_rule_id = %s ORDER BY id",
                                    (rule["id"],)
                                )
                                rule_dict["module_keys"] = [r["module_key"] for r in cur.fetchall()]

                            # 과목 인덱스 규칙
                            if rt == "module_course_indexes_all":
                                cur.execute(
                                    "SELECT course_index FROM track_rule_course_indexes "
                                    "WHERE track_rule_id = %s ORDER BY id",
                                    (rule["id"],)
                                )
                                rule_dict["indexes"] = [r["course_index"] for r in cur.fetchall()]

                            rules_data.append(rule_dict)

                        if rules_data:
                            track_dict["rules"] = rules_data

                        # manual_review_items에서 해당 트랙의 항목 수집
                        track_manual = [
                            m["item"] for m in manual_reviews
                            if m["dept_name"] == dept["dept_name"]
                            and m["track_name"] == track["track_name"]
                        ]
                        if track_manual:
                            track_dict["manual_review_items"] = track_manual

                        tracks_data.append(track_dict)

                    dept_dict = {
                        "dept_name": dept["dept_name"],
                    }
                    if dept["page_ref"]:
                        dept_dict["page_ref"] = dept["page_ref"]
                    if modules_data:
                        dept_dict["modules"] = modules_data
                    if tracks_data:
                        dept_dict["tracks"] = tracks_data

                    depts_data.append(dept_dict)

                colleges_data.append({
                    "college_name": college["college_name"],
                    "departments": depts_data
                })

            final_data = {
                "source": "capstone_db",
                "schema_version": "1.0",
                "description": "DB에서 동적 로드된 트랙 규칙 데이터",
                "notes": [],
                "rule_type_guide": {},
                "colleges": colleges_data,
                "course_aliases": course_aliases,
                "manual_review_required": manual_reviews,
                "rule_support_status": {
                    "supported_rule_types": [
                        "required_courses_all", "module_min_courses", "module_all_courses",
                        "module_min_credits", "track_min_credits", "total_min_courses",
                        "module_group_min_courses_total"
                    ],
                    "manual_review_rule_types": [
                        "module_course_indexes_all", "required_items_raw", "portfolio_min_items",
                        "extracurricular_program_required", "track_all_courses_in_modules",
                        "raw_text_requirement"
                    ]
                }
            }
            logger.info("DB 기반 데이터 조립 완료!")
            return final_data

    except Exception as e:
        if TRACK_DATA_SOURCE == "db":
            logger.exception("TRACK_DATA_SOURCE=db 상태에서 DB 데이터 로드에 실패했습니다.")
            raise RuntimeError(
                "DB 기준 데이터 로드에 실패했습니다. DB 연결과 마이그레이션 상태를 확인하세요."
            ) from e

        logger.warning(
            "DB 데이터 로드 실패(%s). 로컬 track_rules.json으로 대체합니다.",
            type(e).__name__,
        )
        return _load_track_rules_from_json()
    finally:
        if conn is not None:
            conn.close()
