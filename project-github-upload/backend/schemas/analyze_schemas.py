"""
📊 analyze_schemas.py — 트랙 분석 API의 요청/응답 데이터 모양 정의

변경사항:
- ModuleResult 모델 추가 (모듈 완료 판별 결과)
- filtered_info 필드 추가 (F/NP 필터링 정보)
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from services.grade_normalizer import normalize_grade_text


class CourseDetail(BaseModel):
    """과목명 + 학점 + 비고 메타데이터"""
    course_name: str = Field(..., description="과목명")
    credits: int = Field(default=0, description="학점")
    note: str = Field(default="", description="가이드북 비고 원문")
    has_note: bool = Field(default=False, description="비고 존재 여부")
    note_type: str | None = Field(default=None, description="abolished | not_found | changed | new | not_offered | info 등")
    note_label: str = Field(default="", description="프론트 표시용 비고 유형 라벨")
    warning_level: str | None = Field(default=None, description="danger | warning | info | null")


class CourseInput(BaseModel):
    course_name: str = Field(..., description="과목명", max_length=50, examples=["인공지능기초"])
    credits: int = Field(..., description="학점. 과목명이 있으면 반드시 1~6 사이 숫자로 입력해야 합니다.", examples=[3])
    grade: str = Field(default="", description="성적 (A+, B0, F, NP 등)", examples=["A+"])

    @field_validator("course_name")
    @classmethod
    def validate_course_name(cls, value: str) -> str:
        """과목명은 빈 값이면 안 됩니다."""
        if value is None or not str(value).strip():
            raise ValueError("과목명은 필수입니다.")
        return str(value).strip()

    @field_validator("credits", mode="before")
    @classmethod
    def validate_credits(cls, value):
        """
        학점은 트랙 이수 조건 계산에 직접 사용되므로 반드시 검증합니다.

        막는 값:
        - None
        - 빈 문자열 ""
        - 공백 문자열 "   "
        - 0 이하
        - 6 초과
        - 숫자로 해석할 수 없는 값
        """
        if value is None:
            raise ValueError("학점은 필수입니다.")

        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                raise ValueError("학점은 필수입니다.")

            # 프론트가 실수로 "3학점"처럼 보낸 경우도 안전하게 처리합니다.
            raw = raw.replace("학점", "").strip()
        else:
            raw = value

        try:
            credits = float(raw)
        except (TypeError, ValueError):
            raise ValueError("학점은 숫자여야 합니다.")

        if not credits.is_integer():
            raise ValueError("학점은 정수여야 합니다.")

        credits_int = int(credits)

        if credits_int <= 0:
            raise ValueError("학점은 0보다 커야 합니다.")

        if credits_int > 6:
            raise ValueError("학점이 너무 큽니다. 입력값을 확인해주세요.")

        return credits_int

    @field_validator("grade", mode="before")
    @classmethod
    def normalize_grade(cls, value) -> str:
        """
        성적은 선택값이므로 없으면 빈 문자열로 통일합니다.

        OCR 또는 프론트 입력에서 Ao/AO/Bo처럼 들어온 값은
        백엔드 내부 표기인 A0/B0로 보정합니다.
        """
        return normalize_grade_text(value)


class AnalyzeRequest(BaseModel):
    dept_name: str = Field(
        ...,
        description="학과/전공명 (DB 기준 데이터의 dept_name과 일치해야 함)",
        examples=["소프트웨어학부"],
    )
    courses: list[CourseInput] = Field(
        ..., description="학생이 이수한 과목 목록", min_length=1
    )


class RuleResult(BaseModel):
    rule_type: str = Field(..., description="규칙 유형")
    description: str = Field(..., description="규칙 설명")
    satisfied: bool = Field(..., description="충족 여부")
    current_value: int = Field(default=0, description="현재 달성 값")
    required_value: int = Field(default=0, description="요구 값")
    shortage_count: int = Field(default=0, description="해당 규칙 충족까지 추가로 필요한 최소 과목 수")
    shortage_credits: int = Field(default=0, description="해당 규칙 충족까지 추가로 필요한 학점 수")
    missing_courses: list[str] = Field(default_factory=list, description="미충족 상태에서 보여줄 미이수 후보 과목")
    remaining_courses: list[str] = Field(default_factory=list, description="이미 조건은 충족했지만 아직 듣지 않은 선택 가능 과목")
    all_courses: list[str] = Field(default_factory=list, description="해당 규칙/모듈의 전체 후보 과목")
    taken_courses: list[str] = Field(default_factory=list, description="이수한 과목")
    missing_course_details: list[CourseDetail] = Field(default_factory=list, description="부족한 과목 상세 정보")
    remaining_course_details: list[CourseDetail] = Field(default_factory=list, description="조건 충족 후 남은 선택 가능 과목 상세 정보")
    taken_course_details: list[CourseDetail] = Field(default_factory=list, description="이수한 과목 상세 정보")
    evaluation_status: str = Field(default="supported", description="supported | partial | manual_review")
    note: str = Field(default="", description="수동 검토 필요 시 설명")


class TrackResult(BaseModel):
    track_id: str = Field(..., description="트랙 고유 ID")
    track_name: str = Field(..., description="트랙 이름")
    is_completed: bool = Field(..., description="트랙 이수 완료 여부")
    completion_rate: float = Field(..., description="이수율 (0.0~1.0)", ge=0.0, le=1.0)
    total_rules: int = Field(..., description="전체 규칙 수")
    satisfied_rules: int = Field(..., description="충족한 규칙 수")
    rule_results: list[RuleResult] = Field(default_factory=list, description="규칙별 상세 결과")
    missing_courses: list[str] = Field(default_factory=list, description="미이수 후보 과목 목록")
    missing_candidate_count: int = Field(default=0, description="미이수 후보 과목 수")
    additional_required_courses: int = Field(default=0, description="충족까지 추가로 필요한 최소 과목 수")
    taken_courses: list[str] = Field(default_factory=list, description="이수 완료 과목")
    missing_course_details: list[CourseDetail] = Field(default_factory=list, description="부족한 과목 상세 정보")
    taken_course_details: list[CourseDetail] = Field(default_factory=list, description="이수 완료 과목 상세 정보")
    analysis_mode: str = Field(default="auto", description="auto | partial | manual")
    unsupported_rule_types: list[str] = Field(default_factory=list)
    manual_review_items: list[str] = Field(default_factory=list)


class RecommendedTrack(BaseModel):
    rank: int = Field(default=0, description="후보 순위. 1이면 현재 이수 내역과 가장 가까운 후보")
    track_id: str
    track_name: str
    completion_rate: float = Field(..., description="이수율")
    remaining_courses: int = Field(..., description="추가 필요 과목 수. 기존 프론트 호환을 위해 유지")
    additional_required_courses: int = Field(default=0, description="충족까지 추가로 필요한 최소 과목 수")
    missing_candidate_count: int = Field(default=0, description="미이수 후보 과목 수")
    missing_courses: list[str] = Field(default_factory=list)
    reason: str = Field(default="", description="후보 선정 근거")


class IncompleteTrack(BaseModel):
    """미완료 트랙 목록 표시용 요약 정보"""
    track_id: str
    track_name: str
    completion_rate: float = Field(..., description="이수율")
    remaining_courses: int = Field(..., description="추가 필요 과목 수. 기존 프론트 호환을 위해 유지")
    additional_required_courses: int = Field(default=0, description="충족까지 추가로 필요한 최소 과목 수")
    missing_candidate_count: int = Field(default=0, description="미이수 후보 과목 수")
    missing_courses: list[str] = Field(default_factory=list)
    reason: str = Field(default="", description="0% 트랙은 추천 문구 없이 빈 문자열")


class ModuleResult(BaseModel):
    """모듈 완료 판별 결과 (트랙 조건 기준)"""
    module_key: str = Field(..., description="모듈 키 (a, b, c 등)")
    module_name: str = Field(..., description="모듈명")
    is_completed: bool = Field(..., description="트랙 조건 충족 여부")
    taken_count: int = Field(..., description="이수한 과목 수")
    total_courses: int = Field(..., description="모듈 전체 과목 수")
    taken_credits: int = Field(..., description="이수한 학점")
    total_credits: int = Field(..., description="모듈 전체 학점")
    completion_rate: float = Field(..., description="조건 대비 이수율 (0.0~1.0)")
    requirement_type: str = Field(default="", description="조건 유형 (module_min_credits 등)")
    requirement_value: int = Field(default=0, description="조건 값")
    requirement_label: str = Field(default="", description="조건 설명 (3학점 이상 등)")
    current_value: int = Field(default=0, description="현재 달성 값")
    related_tracks: list[str] = Field(default_factory=list, description="이 모듈을 사용하는 트랙들")
    taken_courses: list[str] = Field(default_factory=list, description="이수한 과목명 목록")
    not_taken_courses: list[str] = Field(default_factory=list, description="아직 이수하지 않은 과목명 목록")
    taken_course_details: list[CourseDetail] = Field(default_factory=list, description="이수한 과목 상세 정보")
    not_taken_course_details: list[CourseDetail] = Field(default_factory=list, description="아직 이수하지 않은 과목 상세 정보")
    all_course_details: list[CourseDetail] = Field(default_factory=list, description="모듈 전체 과목 상세 정보")
    course_notes: dict = Field(default_factory=dict, description="과목별 비고 원문")
    course_note_details: dict = Field(default_factory=dict, description="과목별 비고 메타데이터")


class AnalyzeResponse(BaseModel):
    success: bool = Field(default=True)
    dept_name: str = Field(..., description="분석 대상 학과명")
    total_courses_submitted: int = Field(..., description="제출된 과목 수")
    # 기존 프론트 호환용 필드입니다. 의미는 "실제 판별에 인정된 학점"입니다.
    total_credits: int = Field(..., description="인정 학점")
    submitted_credits: int = Field(default=0, description="사용자가 제출한 전체 학점")
    recognized_credits: int = Field(default=0, description="F/NP 및 재수강 정리 후 실제 판별에 인정된 학점")
    excluded_credits: int = Field(default=0, description="F/NP 또는 재수강 정리로 제외된 학점")
    track_results: list[TrackResult] = Field(default_factory=list)
    completed_tracks: list[str] = Field(default_factory=list)
    recommended_tracks: list[RecommendedTrack] = Field(default_factory=list)
    incomplete_tracks: list[IncompleteTrack] = Field(default_factory=list, description="추천 여부와 무관한 전체 미완료 트랙 목록")
    module_stats: dict = Field(default_factory=dict, description="모듈별 달성 현황 (raw)")
    module_results: list[ModuleResult] = Field(default_factory=list, description="모듈별 완료 판별 결과")
    filtered_info: dict = Field(default_factory=dict, description="F/NP 필터링 정보")
