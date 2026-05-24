"""
🏷️ tracks.py — 트랙 목록 조회 API 라우터

핵심 수정사항:
- response_model을 적용해 Swagger 문서가 실제 응답 구조를 정확히 보여주도록 개선
- 학과명에 '/'가 포함되어도 안전한 query parameter 방식 API 추가
  예: GET /api/v1/tracks/by-department?dept_name=소프트웨어학부
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from schemas.common_schemas import ApiErrorResponse
from schemas.track_schemas import (
    DepartmentModulesResponse,
    DepartmentTracksResponse,
    TracksListResponse,
)
from services.course_note_service import enrich_course
from utils.api_response import error_response
from services.data_loader import load_track_rules

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["🏷️ 트랙 목록 조회"])

def _find_department(dept_name: str) -> tuple[dict, dict] | None:
    """
    학과명을 기준으로 (college, department)를 찾습니다.

    왜 따로 함수로 뺐나?
    - path 방식 API와 query parameter 방식 API가 같은 로직을 재사용하게 하기 위해서입니다.
    - 같은 코드를 두 번 쓰면 나중에 한쪽만 수정되는 실수가 생깁니다.
    """
    rules_data = load_track_rules()
    for college in rules_data.get("colleges", []):
        for dept in college.get("departments", []):
            if dept.get("dept_name") == dept_name:
                return college, dept
    return None


def _enrich_modules_with_course_notes(modules: list[dict]) -> list[dict]:
    """
    모듈-과목 목록에 비고 메타데이터를 붙입니다.

    프론트엔드는 course.has_note가 true이면 경고/정보 아이콘을 띄우고,
    course.note를 tooltip으로 보여주면 됩니다.
    """
    result = []
    for module in modules:
        copied = dict(module)
        copied["courses"] = [enrich_course(course) for course in module.get("courses", [])]
        result.append(copied)
    return result


def _build_department_tracks_response(college: dict, dept: dict) -> dict:
    """특정 학과의 트랙 상세 응답을 만듭니다."""
    module_key_to_name = {
        m["module_key"]: m["module_name"] for m in dept.get("modules", [])
    }

    tracks_detail = []
    for track in dept.get("tracks", []):
        module_keys = track.get("module_keys", [])
        module_names = [module_key_to_name.get(k, k) for k in module_keys]
        total_courses = sum(
            len(m.get("courses", []))
            for m in dept.get("modules", [])
            if m.get("module_key") in module_keys
        )

        tracks_detail.append(
            {
                "track_id": track.get("track_id", ""),
                "track_name": track.get("track_name", ""),
                "module_keys": module_keys,
                "module_names": module_names,
                "rules_summary": track.get("raw_requirement_text", ""),
                "rules": track.get("rules", []),
                "total_courses": total_courses,
                "analysis_mode": track.get("analysis_mode", "auto"),
                "unsupported_rule_types": track.get("unsupported_rule_types", []),
                "manual_review_items": track.get("manual_review_items", []),
            }
        )

    return {
        "success": True,
        "dept_name": dept.get("dept_name", ""),
        "college_name": college.get("college_name", ""),
        "page_ref": dept.get("page_ref", ""),
        "tracks": tracks_detail,
        "modules": _enrich_modules_with_course_notes(dept.get("modules", [])),
    }


def _build_department_modules_response(dept: dict) -> dict:
    """특정 학과의 모듈/과목 목록 응답을 만듭니다."""
    modules = _enrich_modules_with_course_notes(dept.get("modules", []))
    all_course_names = [
        course["course_name"]
        for module in modules
        for course in module.get("courses", [])
    ]
    course_note_map = {
        course["course_name"]: {
            "note": course.get("note", ""),
            "has_note": course.get("has_note", False),
            "note_type": course.get("note_type"),
            "note_label": course.get("note_label", ""),
            "warning_level": course.get("warning_level"),
        }
        for module in modules
        for course in module.get("courses", [])
        if course.get("has_note")
    }

    return {
        "success": True,
        "dept_name": dept.get("dept_name", ""),
        "modules": modules,
        "all_course_names": all_course_names,
        "course_note_map": course_note_map,
    }


@router.get(
    "/tracks",
    response_model=TracksListResponse,
    summary="전체 학과 목록 조회",
    description="프론트 드롭다운에 바로 넣을 수 있는 학과 목록과 요약 정보를 반환합니다.",
)
async def get_all_tracks():
    rules_data = load_track_rules()
    colleges_result = []
    dept_list = []
    total_departments = 0
    total_tracks = 0

    for college in rules_data.get("colleges", []):
        college_name = college.get("college_name", "")
        depts_in_college = []
        for dept in college.get("departments", []):
            dept_name = dept["dept_name"]
            tracks = dept.get("tracks", [])
            modules = dept.get("modules", [])
            track_names = [t.get("track_name", "") for t in tracks]

            depts_in_college.append(
                {
                    "dept_name": dept_name,
                    "college_name": college_name,
                    "track_count": len(tracks),
                    "module_count": len(modules),
                    "tracks": track_names,
                }
            )
            dept_list.append(dept_name)
            total_tracks += len(tracks)
            total_departments += 1

        colleges_result.append(
            {
                "college_name": college_name,
                "dept_count": len(depts_in_college),
                "departments": depts_in_college,
            }
        )

    return {
        "success": True,
        "total_departments": total_departments,
        "total_tracks": total_tracks,
        "colleges": colleges_result,
        "dept_list": dept_list,
    }


@router.get(
    "/tracks/by-department",
    response_model=DepartmentTracksResponse,
    summary="특정 학과 트랙 상세 조회 — 프론트 권장 방식",
    description=(
        "학과명을 query parameter로 받아 트랙 상세 정보를 반환합니다. "
        "학과명에 '/'가 포함되어도 URL path가 깨지지 않아 React 연동에 안전합니다."
    ),
    responses={404: {"model": ApiErrorResponse, "description": "학과 없음"}},
)
async def get_department_tracks_by_query(
    dept_name: str = Query(..., description="학과/전공명. 예: 소프트웨어학부")
):
    found = _find_department(dept_name)
    if not found:
        return error_response(
            status_code=404,
            error_code="DEPARTMENT_NOT_FOUND",
            message=f"'{dept_name}' 학과를 찾을 수 없습니다. GET /api/v1/tracks 에서 전체 학과 목록을 확인하세요.",
        )
    college, dept = found
    return _build_department_tracks_response(college, dept)


@router.get(
    "/modules/by-department",
    response_model=DepartmentModulesResponse,
    summary="특정 학과 모듈-과목 목록 조회 — 프론트 권장 방식",
    description=(
        "학과명을 query parameter로 받아 모듈/과목 목록만 반환합니다. "
        "학과명에 '/'가 포함되어도 안전합니다."
    ),
    responses={404: {"model": ApiErrorResponse, "description": "학과 없음"}},
)
async def get_department_modules_by_query(
    dept_name: str = Query(..., description="학과/전공명. 예: 소프트웨어학부")
):
    found = _find_department(dept_name)
    if not found:
        return error_response(
            status_code=404,
            error_code="DEPARTMENT_NOT_FOUND",
            message=f"'{dept_name}' 학과를 찾을 수 없습니다.",
        )
    _, dept = found
    return _build_department_modules_response(dept)


# ─────────────────────────────────────────
# 아래 path 방식 API는 기존 테스트 페이지/호환성 유지용입니다.
# React 신규 연동에서는 위 query parameter 방식 API 사용을 권장합니다.
# ─────────────────────────────────────────


@router.get(
    "/tracks/{dept_name:path}/modules",
    response_model=DepartmentModulesResponse,
    summary="특정 학과 모듈-과목 목록 조회 — 구 방식",
    description="기존 path 방식 API입니다. 신규 프론트 연동은 /modules/by-department?dept_name=... 사용을 권장합니다.",
    responses={404: {"model": ApiErrorResponse, "description": "학과 없음"}},
)
async def get_department_modules(dept_name: str):
    found = _find_department(dept_name)
    if not found:
        return error_response(
            status_code=404,
            error_code="DEPARTMENT_NOT_FOUND",
            message=f"'{dept_name}' 학과를 찾을 수 없습니다.",
        )
    _, dept = found
    return _build_department_modules_response(dept)


@router.get(
    "/tracks/{dept_name:path}",
    response_model=DepartmentTracksResponse,
    summary="특정 학과 트랙 상세 조회 — 구 방식",
    description="기존 path 방식 API입니다. 신규 프론트 연동은 /tracks/by-department?dept_name=... 사용을 권장합니다.",
    responses={404: {"model": ApiErrorResponse, "description": "학과 없음"}},
)
async def get_department_tracks(dept_name: str):
    found = _find_department(dept_name)
    if not found:
        return error_response(
            status_code=404,
            error_code="DEPARTMENT_NOT_FOUND",
            message=f"'{dept_name}' 학과를 찾을 수 없습니다. GET /api/v1/tracks 에서 전체 학과 목록을 확인하세요.",
        )
    college, dept = found
    return _build_department_tracks_response(college, dept)
