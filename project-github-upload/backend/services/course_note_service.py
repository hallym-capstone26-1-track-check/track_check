"""
📝 course_note_service.py — 교과목 비고(note) 정리 유틸

이 파일의 역할
- DB 기준 데이터의 과목 비고를 프론트가 바로 쓰기 좋은 형태로 변환합니다.
- 예: "2026-1학기 교과목 폐지" → note_type="abolished", warning_level="danger"

초보자 핵심
- 백엔드는 기준 데이터(note)를 내려주고,
- 프론트는 has_note / note / note_type / warning_level을 보고 아이콘과 툴팁을 표시합니다.
- 단, "전공필수", "전공선택"은 단순 교과 구분 정보이므로 경고/정보 아이콘 표시 대상에서 제외합니다.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


# 프론트 tooltip에 함께 표시할 라벨입니다.
# "전공필수", "전공선택"은 화면 경고/정보 아이콘 대상에서 제외했으므로 넣지 않습니다.
NOTE_TYPE_LABELS: dict[str, str] = {
    "not_found": "미존재 교과목",
    "abolished": "폐지 교과목",
    "not_offered": "미개설 예정",
    "changed": "변경 교과목",
    "new": "신설 교과목",
    "info": "비고",
}

# 단순 교과 구분 정보입니다.
# 프론트 경고 아이콘으로 띄우면 화면이 너무 복잡해지므로 숨깁니다.
IGNORED_NOTES: set[str] = {
    "전공필수",
    "전공선택",
}


def normalize_note(note: str | None) -> str:
    """비고 원문을 표시 대상으로 쓸 수 있도록 정리합니다."""
    text = str(note or "").strip()

    # "전공필수", "전공선택"은 경고/tooltip 대상에서 제외합니다.
    if text in IGNORED_NOTES:
        return ""

    return text


def classify_note_type(note: str | None) -> str | None:
    """비고 문구를 프론트 표시용 유형으로 분류합니다."""
    text = normalize_note(note)
    if not text:
        return None

    # 위험도가 높은 순서로 먼저 검사합니다.
    if "미존재" in text:
        return "not_found"
    if "폐지" in text:
        return "abolished"
    if "미개설" in text:
        return "not_offered"
    if "변경" in text:
        return "changed"
    if "신설" in text:
        return "new"

    return "info"


def get_warning_level(note_type: str | None) -> str | None:
    """note_type을 화면 색상/아이콘 수준으로 변환합니다."""
    if note_type in {"not_found", "abolished"}:
        return "danger"
    if note_type in {"not_offered", "changed"}:
        return "warning"
    if note_type in {"new", "info"}:
        return "info"
    return None


def build_note_meta(note: str | None) -> dict[str, Any]:
    """과목 비고를 API 응답에 포함할 공통 메타데이터로 만듭니다."""
    clean_note = normalize_note(note)
    note_type = classify_note_type(clean_note)
    warning_level = get_warning_level(note_type)

    return {
        "note": clean_note,
        "has_note": bool(clean_note),
        "note_type": note_type,
        "note_label": NOTE_TYPE_LABELS.get(note_type, "") if note_type else "",
        "warning_level": warning_level,
    }


def enrich_course(course: dict[str, Any]) -> dict[str, Any]:
    """과목 dict에 비고 메타데이터를 추가합니다."""
    result = deepcopy(course)
    raw_note = result.get("note") or result.get("remark") or ""
    result.update(build_note_meta(raw_note))
    return result


def build_course_detail(course_name: str, credits: int = 0, note: str | None = "") -> dict[str, Any]:
    """문자열 과목명을 상세 과목 객체로 변환합니다."""
    detail: dict[str, Any] = {
        "course_name": course_name,
        "credits": credits,
    }
    detail.update(build_note_meta(note))
    return detail
