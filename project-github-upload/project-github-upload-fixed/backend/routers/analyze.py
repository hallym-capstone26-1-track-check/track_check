"""
📊 analyze.py — 트랙 분석 및 후보 산정 API 라우터

변경사항:
- module_results (모듈 완료 판별) 반환
- filtered_info (F/NP 필터링 정보) 반환
- /api/v1/encrypt, /api/v1/decrypt 암호화 엔드포인트 추가
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from schemas.analyze_schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    IncompleteTrack,
    ModuleResult,
    RecommendedTrack,
    RuleResult,
    TrackResult,
)
from schemas.common_schemas import ApiErrorResponse
from services.course_normalizer import normalize_course_records
from services.privacy_service import (
    encrypt_sensitive_fields,
)
from services.track_analyzer import analyze_tracks
from services.track_recommender import build_incomplete_tracks, recommend_tracks
from utils.api_response import error_response
from config import DEBUG_MODE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["📊 트랙 분석 & 후보 산정"])


# ═══════════════════════════════════════════
# 📊 트랙 분석 엔드포인트
# ═══════════════════════════════════════════

@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="이수 과목 기반 트랙 진단 및 후보 산정",
    description=(
        "학과명과 이수 과목 목록을 보내면 전공트랙 이수 현황을 분석하고 후보 트랙을 반환합니다.\n\n"
        "F학점과 NP는 이수 미완료로 처리되며, 재수강 시 가장 좋은 성적이 적용됩니다."
    ),
    responses={
        404: {"model": ApiErrorResponse, "description": "학과 없음"},
        500: {"model": ApiErrorResponse, "description": "서버 내부 오류"},
    },
)
async def analyze_student_tracks(request: AnalyzeRequest):
    logger.info(
        "분석 요청 — 학과: %s, 과목 수: %s개",
        request.dept_name, len(request.courses),
    )
    # 개인정보 보호 원칙:
    # 과목명/학점/성적은 분석에는 필요하지만, 평문 로그에는 남기지 않습니다.
    # 디버그 로그도 요청 전체 payload 대신 요약 정보만 기록합니다.
    logger.debug(
        "분석 요청 요약 — 학과: %s, 과목 수: %s개",
        request.dept_name, len(request.courses),
    )

    # 과목 리스트 → dict 변환
    student_courses = [
        {
            "course_name": c.course_name,
            "credits": c.credits,
            "grade": c.grade,
        }
        for c in request.courses
    ]
    normalized_courses = normalize_course_records(student_courses)

    # 트랙 분석 실행
    try:
        result = analyze_tracks(request.dept_name, normalized_courses)
    except Exception as e:
        logger.error("트랙 분석 중 오류: %s", type(e).__name__)
        return error_response(
            status_code=500,
            error_code="ANALYZE_FAILED",
            message="트랙 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            details=[type(e).__name__],
        )

    if "error" in result:
        return error_response(
            status_code=404,
            error_code="DEPARTMENT_NOT_FOUND",
            message=result["error"],
        )

    # 결과 조립
    raw_track_results = result.get("track_results", [])
    recommendations = recommend_tracks(raw_track_results, top_n=len(raw_track_results))
    incomplete_tracks = build_incomplete_tracks(raw_track_results)

    # 학점은 "사용자가 입력한 전체 학점"과 "실제 판별에 인정된 학점"을 구분합니다.
    # total_credits는 기존 프론트 호환을 위해 유지하되, 이제 인정 학점과 같은 의미로 내려줍니다.
    credit_summary = result.get("credit_summary", {})
    submitted_credits = int(credit_summary.get(
        "submitted_credits",
        sum(int(c.get("credits", 0) or 0) for c in normalized_courses),
    ))
    recognized_credits = int(credit_summary.get("recognized_credits", submitted_credits))
    excluded_credits = int(credit_summary.get(
        "excluded_credits",
        max(0, submitted_credits - recognized_credits),
    ))

    # TrackResult 모델 변환
    track_results_models = []
    for tr in raw_track_results:
        rule_results = [RuleResult(**rr) for rr in tr.get("rule_results", [])]
        track_results_models.append(
            TrackResult(
                track_id=tr["track_id"],
                track_name=tr["track_name"],
                is_completed=tr["is_completed"],
                completion_rate=tr["completion_rate"],
                total_rules=tr["total_rules"],
                satisfied_rules=tr["satisfied_rules"],
                rule_results=rule_results,
                missing_courses=tr.get("missing_courses", []),
                missing_candidate_count=tr.get("missing_candidate_count", len(tr.get("missing_courses", []))),
                additional_required_courses=tr.get("additional_required_courses", 0),
                taken_courses=tr.get("taken_courses", []),
                missing_course_details=tr.get("missing_course_details", []),
                taken_course_details=tr.get("taken_course_details", []),
                analysis_mode=tr.get("analysis_mode", "auto"),
                unsupported_rule_types=tr.get("unsupported_rule_types", []),
                manual_review_items=tr.get("manual_review_items", []),
            )
        )

    recommended_models = [RecommendedTrack(**r) for r in recommendations]
    incomplete_track_models = [IncompleteTrack(**t) for t in incomplete_tracks]

    # ModuleResult 변환
    module_results_models = [
        ModuleResult(**mr) for mr in result.get("module_results", [])
    ]

    return AnalyzeResponse(
        success=True,
        dept_name=request.dept_name,
        total_courses_submitted=len(normalized_courses),
        total_credits=recognized_credits,
        submitted_credits=submitted_credits,
        recognized_credits=recognized_credits,
        excluded_credits=excluded_credits,
        track_results=track_results_models,
        completed_tracks=result.get("completed_tracks", []),
        recommended_tracks=recommended_models,
        incomplete_tracks=incomplete_track_models,
        module_stats=result.get("module_stats", {}),
        module_results=module_results_models,
        filtered_info=result.get("filtered_info", {}),
    )


# ═══════════════════════════════════════════
# 🔐 암호화 / 복호화 엔드포인트 (개발 전용)
# ═══════════════════════════════════════════
#
# 이 두 엔드포인트는 Fernet 대칭키 암호화 동작을 테스트하기 위한 용도이고,
# 특히 /api/v1/decrypt 는 인증 없이 외부에 공개되면 안 됩니다.
# 그래서 config.DEBUG_MODE 가 켜져 있을 때만 등록합니다.
#
# 운영 배포 시:
#   - 환경변수 DEBUG_MODE=0 으로 설정하면 아래 블록 전체가 등록되지 않습니다.
#   - 즉 /api/v1/encrypt, /api/v1/decrypt 가 404 가 됩니다.
#
# 발표/시연 시:
#   - 기본값 DEBUG_MODE=1 이라 자동으로 노출됩니다.

if DEBUG_MODE:

    class EncryptRequest(BaseModel):
        """암호화 요청 데이터"""
        data: dict = Field(..., description="암호화할 데이터 (민감 필드 포함)", examples=[{"student_id": "20241234", "name": "홍길동"}])
        fields: list[str] | None = Field(default=None, description="암호화할 필드명 목록 (None이면 기본 민감 필드)")


    class DecryptRequest(BaseModel):
        """복호화 요청 데이터"""
        data: dict = Field(..., description="복호화할 데이터 (암호화된 필드 포함)")
        fields: list[str] | None = Field(default=None, description="복호화할 필드명 목록")


    @router.post(
        "/encrypt",
        tags=["🔐 암호화 (DEBUG)"],
        summary="민감 데이터 암호화 — 개발 전용",
        description=(
            "학번, 이름처럼 학생을 직접 식별할 수 있는 민감 필드를 "
            "Fernet 대칭키로 암호화합니다. "
            "학과/과목명/성적은 현재 MVP 기본 암호화 대상이 아닙니다.\n\n"
            "⚠️ 이 엔드포인트는 DEBUG_MODE=1 일 때만 노출됩니다."
        ),
    )
    async def encrypt_data(request: EncryptRequest):
        """민감 데이터를 암호화합니다."""
        try:
            encrypted = encrypt_sensitive_fields(request.data, request.fields)
            return {
                "success": True,
                "encrypted_data": encrypted,
                "message": "민감 데이터가 암호화되었습니다.",
            }
        except Exception as e:
            logger.error("암호화 실패: %s", type(e).__name__)
            return error_response(
                status_code=500,
                error_code="ENCRYPTION_FAILED",
                message="암호화 처리 중 오류가 발생했습니다.",
            )


    @router.post(
        "/decrypt",
        tags=["🔐 암호화 (DEBUG)"],
        summary="암호화된 데이터 복호화 — 개발 전용",
        description=(
            "암호화 테스트용 복호화 API입니다.\n\n"
            "⚠️ 이 엔드포인트는 DEBUG_MODE=1 일 때만 노출되며, "
            "실서비스에서는 절대 노출하면 안 됩니다."
        ),
    )
    async def decrypt_data(request: DecryptRequest):
        """암호화된 데이터를 복호화합니다."""
        try:
            from services.privacy_service import decrypt_sensitive_fields
            decrypted = decrypt_sensitive_fields(request.data, request.fields)
            return {
                "success": True,
                "decrypted_data": decrypted,
                "message": "데이터가 복호화되었습니다.",
            }
        except ValueError as e:
            return error_response(
                status_code=400,
                error_code="DECRYPTION_FAILED",
                message=str(e),
            )
        except Exception as e:
            logger.error("복호화 실패: %s", type(e).__name__)
            return error_response(
                status_code=500,
                error_code="DECRYPTION_FAILED",
                message="복호화 처리 중 오류가 발생했습니다.",
            )

else:
    logger.info("DEBUG_MODE=0 → /api/v1/encrypt, /api/v1/decrypt 엔드포인트는 등록되지 않았습니다.")
