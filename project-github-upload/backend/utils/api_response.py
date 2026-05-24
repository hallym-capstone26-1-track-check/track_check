"""
에러 응답 형식을 통일하기 위한 헬퍼 함수.
"""
from __future__ import annotations

from fastapi.responses import JSONResponse


def error_response(*, status_code: int, error_code: str, message: str, details: list[str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error_code": error_code,
            "message": message,
            "details": details or [],
        },
    )
