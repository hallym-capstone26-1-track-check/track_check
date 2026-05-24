"""
📋 upload_schemas.py — 이미지 업로드 API의 요청/응답 데이터 모양 정의
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CourseItem(BaseModel):
    course_name: str = Field(..., description="과목명", examples=["인공지능"])
    credits: int = Field(..., description="학점 수", ge=1, le=6, examples=[3])
    grade: str = Field(default="", description="성적 (A+, B0 등). 비어있으면 이수만 확인", examples=["A+"])
    match_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="OCR/과목 카탈로그 매칭 점수. 높을수록 공식 과목명과 더 잘 맞는다는 의미",
        examples=[97.0],
    )


class UploadResponse(BaseModel):
    success: bool = Field(default=True, description="처리 성공 여부")
    message: str = Field(default="OCR 처리 완료", description="처리 결과 메시지")
    total_images: int = Field(..., description="처리된 이미지 수")
    courses: list[CourseItem] = Field(default_factory=list, description="OCR로 추출된 과목 목록")
    warnings: list[str] = Field(default_factory=list, description="처리 중 발생한 경고 메시지")
    raw_text: str | None = Field(None, description="OCR로 추출된 전체 텍스트 (디버깅용)")
    next_step: str = Field(
        default="OCR 결과는 자동 추출 결과입니다. 분석 전 과목명/학점/성적을 확인·수정해주세요.",
        description="프론트에서 사용자에게 안내할 다음 단계 메시지",
    )
    ocr_mode: str = Field(default="mock", description="현재 적용된 OCR 모드")
