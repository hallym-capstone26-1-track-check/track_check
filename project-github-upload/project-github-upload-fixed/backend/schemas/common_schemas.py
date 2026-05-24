"""
공통 응답 스키마.
여러 라우터에서 동일한 에러 형식을 쓰기 위해 분리했습니다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ApiErrorResponse(BaseModel):
    success: bool = Field(default=False, description="성공 여부")
    error_code: str = Field(..., description="프론트 분기 처리용 에러 코드")
    message: str = Field(..., description="사용자에게 보여줄 에러 메시지")
    details: list[str] = Field(default_factory=list, description="세부 메시지 목록")
