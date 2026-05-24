from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
RULES_PATH = BASE_DIR / "data" / "track_rules.json"
# tracks.json은 제거됨 — 트랙/모듈 정보는 track_rules.json으로 통합


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_guidebook_summary_counts_match_project_json():
    """가이드북 요약 기준: 모듈 218개, 전공트랙 110개를 유지해야 한다."""
    rules = _load_json(RULES_PATH)
    module_count = 0
    track_count = 0
    dept_count = 0
    for college in rules["colleges"]:
        for dept in college["departments"]:
            dept_count += 1
            module_count += len(dept.get("modules", []))
            track_count += len(dept.get("tracks", []))
    assert dept_count == 30
    assert module_count == 218
    assert track_count == 110


def test_track_ids_are_unique_and_module_references_are_valid():
    rules = _load_json(RULES_PATH)
    track_ids: list[str] = []
    for college in rules["colleges"]:
        for dept in college["departments"]:
            valid_module_keys = {m["module_key"] for m in dept.get("modules", [])}
            for track in dept.get("tracks", []):
                track_ids.append(track["track_id"])
                assert set(track.get("module_keys", [])) <= valid_module_keys
                for rule in track.get("rules", []):
                    if "module_key" in rule:
                        assert rule["module_key"] in valid_module_keys
    duplicated = [track_id for track_id, count in Counter(track_ids).items() if count > 1]
    assert duplicated == []


def test_track_names_are_unique_within_department():
    """같은 학과 안에서 트랙 이름이 중복되지 않아야 한다 (tracks.json 동기화 테스트 대체)."""
    rules = _load_json(RULES_PATH)
    for college in rules["colleges"]:
        for dept in college["departments"]:
            names = [t["track_name"] for t in dept.get("tracks", [])]
            duplicated = [n for n, cnt in Counter(names).items() if cnt > 1]
            assert duplicated == [], (
                f"{dept['dept_name']}: 트랙명 중복 발견 {duplicated}"
            )


def test_total_min_courses_is_supported_and_not_left_as_unsupported():
    rules = _load_json(RULES_PATH)
    status = rules["rule_support_status"]
    assert "total_min_courses" in status["supported_rule_types"]
    assert "total_min_courses" not in status["manual_review_rule_types"]
    offenders = []
    for college in rules["colleges"]:
        for dept in college["departments"]:
            for track in dept.get("tracks", []):
                if "total_min_courses" in track.get("unsupported_rule_types", []):
                    offenders.append((dept["dept_name"], track["track_name"]))
    assert offenders == []


def test_course_alias_summary_count_is_correct():
    rules = _load_json(RULES_PATH)
    assert rules["json_review_summary"]["alias_entries_total"] == len(rules.get("course_aliases", {}))


def test_course_notes_exist_for_known_guidebook_remarks():
    """비고 표시 기능에 필요한 대표 과목 note가 JSON에 유지되어야 한다."""
    rules = _load_json(RULES_PATH)
    note_map = {}
    for college in rules["colleges"]:
        for dept in college["departments"]:
            for module in dept.get("modules", []):
                for course in module.get("courses", []):
                    note = course.get("note") or course.get("remark") or ""
                    if note:
                        note_map[(dept["dept_name"], course["course_name"])] = note

    assert note_map[("인공지능융합학부", "인공지능시스템프로그래밍")] == "2026-1학기 교과목 폐지"
    assert note_map[("화학과", "캡스톤-향수추출합성실습")] == "미존재 교과목"



def test_module_group_min_courses_total_is_supported():
    """여러 모듈 묶음에서 총 N과목 이상 조건은 자동 판별 지원 규칙이어야 한다."""
    rules = _load_json(RULES_PATH)
    status = rules["rule_support_status"]
    assert "module_group_min_courses_total" in status["supported_rule_types"]
    assert "module_group_min_courses_total" not in status["manual_review_rule_types"]

    offenders = []
    for college in rules["colleges"]:
        for dept in college["departments"]:
            for track in dept.get("tracks", []):
                if "module_group_min_courses_total" in track.get("unsupported_rule_types", []):
                    offenders.append((dept["dept_name"], track["track_name"]))
    assert offenders == []
