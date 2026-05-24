"""
🏷️ track_schemas.py — 트랙 조회 API 응답 스키마

왜 필요한가?
- FastAPI Swagger 문서에 실제 응답 구조를 정확히 보여주기 위해 사용합니다.
- React/TypeScript 프론트엔드가 API 응답 타입을 맞출 때 기준으로 삼을 수 있습니다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class CourseNoteInfo(BaseModel):
    """과목 비고/경고 메타데이터"""
    note: str = Field(default="", description="가이드북 비고 원문")
    has_note: bool = Field(default=False, description="프론트에서 아이콘 표시 여부")
    note_type: str | None = Field(default=None, description="비고 유형: abolished, changed, new 등")
    note_label: str = Field(default="", description="프론트 표시용 비고 라벨")
    warning_level: str | None = Field(default=None, description="표시 강도: danger, warning, info 등")


class CourseInfo(BaseModel):
    """모듈 안의 교과목 정보"""
    model_config = ConfigDict(extra="allow")

    course_name: str = Field(..., description="교과목명")
    credits: int = Field(..., description="학점")
    note: str = Field(default="", description="가이드북 비고 원문")
    has_note: bool = Field(default=False, description="비고/경고 아이콘 표시 여부")
    note_type: str | None = Field(default=None, description="비고 유형")
    note_label: str = Field(default="", description="비고 라벨")
    warning_level: str | None = Field(default=None, description="경고 수준")


class ModuleInfo(BaseModel):
    """학과별 모듈 정보"""
    module_key: str = Field(..., description="모듈 키. 예: a, b, c")
    module_name: str = Field(..., description="모듈명")
    courses: list[CourseInfo] = Field(default_factory=list, description="모듈에 포함된 교과목 목록")


class DepartmentSummary(BaseModel):
    """전체 학과 목록에서 쓰는 학과 요약 정보"""
    dept_name: str = Field(..., description="학과/전공명")
    college_name: str = Field(..., description="소속 단과대학/스쿨명")
    track_count: int = Field(default=0, description="트랙 수")
    module_count: int = Field(default=0, description="모듈 수")
    tracks: list[str] = Field(default_factory=list, description="트랙명 목록")


class CollegeGroup(BaseModel):
    """단과대학/스쿨별 학과 그룹"""
    college_name: str = Field(..., description="단과대학/스쿨명")
    dept_count: int = Field(default=0, description="그룹 내 학과 수")
    departments: list[DepartmentSummary] = Field(default_factory=list, description="학과 요약 목록")


class TracksListResponse(BaseModel):
    """GET /api/v1/tracks 응답"""
    success: bool = Field(default=True)
    total_departments: int = Field(default=0, description="전체 학과/전공 수")
    total_tracks: int = Field(default=0, description="전체 트랙 수")
    colleges: list[CollegeGroup] = Field(default_factory=list, description="단과대학/스쿨별 학과 목록")
    dept_list: list[str] = Field(default_factory=list, description="프론트 드롭다운용 학과명 배열")


class TrackDetail(BaseModel):
    """특정 학과의 트랙 상세 정보"""
    track_id: str = Field(default="", description="트랙 고유 ID")
    track_name: str = Field(default="", description="트랙명")
    module_keys: list[str] = Field(default_factory=list, description="트랙에 포함된 모듈 키")
    module_names: list[str] = Field(default_factory=list, description="트랙에 포함된 모듈명")
    rules_summary: str = Field(default="", description="가이드북 원문 이수 조건 요약")
    rules: list[dict[str, Any]] = Field(default_factory=list, description="백엔드 판별용 규칙 목록")
    total_courses: int = Field(default=0, description="트랙 조합 모듈에 포함된 전체 과목 수")
    analysis_mode: str = Field(default="auto", description="auto, partial, manual")
    unsupported_rule_types: list[str] = Field(default_factory=list, description="현재 자동 판별이 어려운 rule type 목록")
    manual_review_items: list[str] = Field(default_factory=list, description="학과/담당자 확인이 필요한 항목")


class DepartmentTracksResponse(BaseModel):
    """특정 학과 트랙 상세 조회 응답"""
    success: bool = Field(default=True)
    dept_name: str = Field(..., description="학과/전공명")
    college_name: str = Field(default="", description="소속 단과대학/스쿨명")
    page_ref: str = Field(default="", description="가이드북 참고 페이지")
    tracks: list[TrackDetail] = Field(default_factory=list, description="트랙 상세 목록")
    modules: list[ModuleInfo] = Field(default_factory=list, description="모듈 및 교과목 목록")


class DepartmentModulesResponse(BaseModel):
    """특정 학과 모듈-과목 목록 조회 응답"""
    success: bool = Field(default=True)
    dept_name: str = Field(..., description="학과/전공명")
    modules: list[ModuleInfo] = Field(default_factory=list, description="모듈 및 교과목 목록")
    all_course_names: list[str] = Field(default_factory=list, description="학과 전체 교과목명 목록")
    course_note_map: dict[str, CourseNoteInfo] = Field(default_factory=dict, description="비고가 있는 과목만 모은 맵")
