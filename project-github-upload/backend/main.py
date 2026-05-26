"""
🚀 main.py — FastAPI 애플리케이션 진입점 (서버의 시작점)
"""

from __future__ import annotations

import logging
import os

# ⚠️ 반드시 config보다 먼저 실행되어야 합니다.
# config.py가 임포트되는 순간 os.environ을 읽으므로,
# 그 전에 .env 파일을 환경변수에 적재해야 OCR_MODE, DB_PASSWORD 등이 올바르게 로드됩니다.
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import config
from config import BASE_DIR
from fastapi.middleware.cors import CORSMiddleware

# 라우터 임포트 (각 기능별 API 모음)
from routers import upload, analyze, tracks
from db import check_database_health
from config import CORS_ORIGINS

# ─────────────────────────────────────────
# 📋 로깅 설정
# ─────────────────────────────────────────
# 로그 = 프로그램이 실행되면서 남기는 기록
# 에러를 추적하거나, 동작을 확인할 때 사용
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG_MODE else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 🚀 FastAPI 앱 생성
# ─────────────────────────────────────────
app = FastAPI(
    title="트랙길잡이",
    description=(
        "학생의 성적표 이미지를 업로드하면 OCR로 과목을 추출하고, "
        "전공트랙 이수 기준과 비교하여 진단 및 추천 결과를 제공합니다.\n\n"
        "**개인정보 보호**: 원본 이미지는 서버에 저장되지 않으며, "
        "메모리에서만 처리 후 즉시 삭제됩니다."
    ),
    version="1.0.0-mvp",
    docs_url="/docs",      # Swagger UI 경로
    redoc_url="/redoc",     # ReDoc 경로
)


# ─────────────────────────────────────────
# 🌐 CORS 설정
# ─────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing)
# = 다른 주소에서 실행되는 프론트엔드가 이 백엔드에 접근하도록 허용
#
# 예를 들어:
#   프론트: http://localhost:3000 (React)
#   백엔드: http://localhost:8000 (FastAPI)
#   → 주소(origin)가 다르므로 CORS 설정 없이는 통신 불가
#
# ⚠️ allow_origins=["*"]는 개발용! 배포 시 반드시 특정 주소만 허용!
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,       # 허용할 프론트엔드 주소 (config.py)
    allow_credentials=True,           # 쿠키 전송 허용
    allow_methods=["*"],              # 모든 HTTP 메서드 허용 (GET, POST 등)
    allow_headers=["*"],              # 모든 헤더 허용
)


# ─────────────────────────────────────────
# 🇰🇷 422 Validation 에러 한글화
# ─────────────────────────────────────────
# FastAPI / Pydantic 의 기본 422 응답은 영어로 떨어집니다.
# 예: "List should have at least 1 item after validation, not 0"
#
# 프론트가 이 메시지를 그대로 사용자에게 보여주면 혼란스러우므로
# 자주 발생하는 에러 타입을 한글로 매핑합니다.
#
# 응답 형식은 다른 에러 응답(error_response)과 동일하게 맞춥니다:
#   { success, error_code, message, details }

# pydantic 에러의 type 필드 → 한글 메시지 매핑
_VALIDATION_TYPE_TO_KO: dict[str, str] = {
    "missing": "필수 값이 빠졌습니다.",
    "string_type": "문자열이어야 합니다.",
    "int_type": "정수여야 합니다.",
    "int_parsing": "정수로 변환할 수 없는 값입니다.",
    "float_parsing": "숫자로 변환할 수 없는 값입니다.",
    "bool_parsing": "참/거짓 값이어야 합니다.",
    "value_error": "값이 올바르지 않습니다.",
    "type_error": "값의 타입이 올바르지 않습니다.",
    "list_type": "리스트(목록) 형태여야 합니다.",
    "dict_type": "객체(딕셔너리) 형태여야 합니다.",
    "string_too_short": "문자열이 너무 짧습니다.",
    "string_too_long": "문자열이 너무 깁니다.",
    "too_short": "항목이 너무 적습니다.",
    "too_long": "항목이 너무 많습니다.",
    "greater_than": "값이 너무 작습니다.",
    "greater_than_equal": "값이 너무 작습니다.",
    "less_than": "값이 너무 큽니다.",
    "less_than_equal": "값이 너무 큽니다.",
    "json_invalid": "JSON 형식이 올바르지 않습니다.",
    "model_attributes_type": "요청 본문 형식이 올바르지 않습니다.",
}


def _translate_pydantic_error(err: dict) -> str:
    """
    pydantic 에러 dict 하나를 한글 문장으로 변환합니다.

    err 예시:
      {
        "type": "too_short",
        "loc": ["body", "courses"],
        "msg": "List should have at least 1 item after validation, not 0",
        "ctx": {"min_length": 1, "actual_length": 0},
      }

    우선순위:
    1) ValueError 로 던진 한글 메시지(field_validator 안에서 직접 작성한 것)
       → 이미 한글이면 그대로 사용
    2) type 매핑 테이블에서 한글 메시지를 찾음
    3) 둘 다 안 되면 기본 영어 msg 사용
    """
    err_type = err.get("type", "")
    raw_msg = err.get("msg", "") or ""
    ctx = err.get("ctx", {}) or {}

    # field_validator 에서 raise ValueError("학점은 필수입니다.") 처럼
    # 직접 한글 메시지를 던진 경우는 type 이 "value_error" 로 잡히고
    # msg 는 "Value error, 학점은 필수입니다." 형태가 됩니다.
    # → 이미 한글이 들어 있으니 접두사만 떼서 그대로 살려줍니다.
    if err_type == "value_error" and raw_msg.startswith("Value error, "):
        return raw_msg[len("Value error, "):].strip()

    # 매핑 테이블 우선
    base_ko = _VALIDATION_TYPE_TO_KO.get(err_type)

    # 길이 관련 에러는 컨텍스트로 좀 더 구체적으로 만들 수 있습니다.
    if err_type == "too_short":
        min_length = ctx.get("min_length")
        actual_length = ctx.get("actual_length")
        if min_length is not None:
            base_ko = f"최소 {min_length}개 이상 필요합니다."
            if actual_length is not None:
                base_ko += f" (현재 {actual_length}개)"
    elif err_type == "too_long":
        max_length = ctx.get("max_length")
        if max_length is not None:
            base_ko = f"최대 {max_length}개까지 가능합니다."
    elif err_type in {"greater_than", "greater_than_equal"}:
        threshold = ctx.get("gt") if err_type == "greater_than" else ctx.get("ge")
        if threshold is not None:
            base_ko = f"값은 {threshold} 보다 {'커야' if err_type == 'greater_than' else '같거나 커야'} 합니다."
    elif err_type in {"less_than", "less_than_equal"}:
        threshold = ctx.get("lt") if err_type == "less_than" else ctx.get("le")
        if threshold is not None:
            base_ko = f"값은 {threshold} 보다 {'작아야' if err_type == 'less_than' else '같거나 작아야'} 합니다."

    return base_ko or raw_msg or "입력값이 올바르지 않습니다."


def _format_error_location(loc: tuple | list) -> str:
    """
    에러가 발생한 위치(loc)를 사람이 읽기 좋은 형태로 변환합니다.

    예:
      ("body", "courses")             → "courses"
      ("body", "courses", 0, "credits") → "courses[0].credits"
      ("query", "dept_name")          → "dept_name"
    """
    if not loc:
        return ""
    # 첫 항목은 보통 "body" / "query" / "path" 라 사용자에겐 의미 없습니다.
    parts = list(loc[1:]) if loc[0] in {"body", "query", "path", "header", "cookie"} else list(loc)
    pieces: list[str] = []
    for p in parts:
        if isinstance(p, int):
            # 리스트 인덱스는 [N] 으로 붙여서 직전 항목에 합칩니다.
            if pieces:
                pieces[-1] = f"{pieces[-1]}[{p}]"
            else:
                pieces.append(f"[{p}]")
        else:
            pieces.append(str(p))
    return ".".join(pieces)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    422 Validation 에러를 한글 메시지로 변환해서 응답합니다.

    응답 예:
      {
        "success": false,
        "error_code": "VALIDATION_ERROR",
        "message": "입력값 검증에 실패했습니다.",
        "details": [
          "courses: 최소 1개 이상 필요합니다. (현재 0개)"
        ]
      }
    """
    details: list[str] = []
    for err in exc.errors():
        loc_str = _format_error_location(err.get("loc", ()))
        ko_msg = _translate_pydantic_error(err)
        if loc_str:
            details.append(f"{loc_str}: {ko_msg}")
        else:
            details.append(ko_msg)

    # 디버그 편의를 위해 로그에는 원본도 남깁니다.
    logger.warning("Validation 에러 — %s", details)

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": "입력값 검증에 실패했습니다. 자세한 내용은 details를 확인해주세요.",
            "details": details,
        },
    )


# ─────────────────────────────────────────
# 📌 라우터 등록
# ─────────────────────────────────────────
# 각 라우터를 앱에 연결 → 라우터에 정의된 API들이 활성화됨
app.include_router(upload.router)     # /api/v1/upload
app.include_router(analyze.router)    # /api/v1/analyze
app.include_router(tracks.router)     # /api/v1/tracks, /api/v1/tracks/by-department, /api/v1/modules/by-department

# ─────────────────────────────────────────
# 📌 프론트엔드 정적 파일 마운트
# ─────────────────────────────────────────
# 기본값은 http://127.0.0.1:8000/frontend/index.html 입니다.
# 클라우드에서는 FRONTEND_DIR / FRONTEND_ROUTE 환경변수로 정적 파일 위치와 경로를 바꿀 수 있습니다.
frontend_dir = config.FRONTEND_DIR

if os.path.exists(frontend_dir):
    app.mount(
        config.FRONTEND_ROUTE,
        StaticFiles(directory=frontend_dir),
        name="frontend",
    )
    logger.info(
        "✅ 프론트엔드 정적 폴더 마운트 완료: %s -> %s",
        config.FRONTEND_ROUTE,
        frontend_dir,
    )
else:
    logger.warning("❌ 프론트엔드 폴더를 찾을 수 없습니다: %s", frontend_dir)
    logger.warning("   (테스트용 프론트엔드 UI를 사용할 수 없습니다.)")


# ─────────────────────────────────────────
# 🚀 서버 시작 시 안내 로그
# ─────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*60)
    print("[System] 트랙길잡이 서버가 시작되었습니다!")
    print("="*60)
    print(f"[Check] 헬스 체크:   {config.PUBLIC_BASE_URL}/api/v1/health")
    print(f"[Docs] API 문서:    {config.PUBLIC_BASE_URL}/docs")
    
    if os.path.exists(frontend_dir):
        print(f"[UI] 프론트 UI:   {config.PUBLIC_BASE_URL}{config.FRONTEND_ROUTE}/index.html")
    else:
        print(f"[Warning] 테스트 UI:   (frontend 폴더 없음) {frontend_dir}")
    
    print(f"[Info] 기준 데이터: {config.TRACK_DATA_SOURCE}")
    print(f"[Info] OCR 모드:    {config.OCR_MODE}")
    print(
        f"[Info] OCR 튜닝:    lang={config.OCR_TESSERACT_LANGS}, "
        f"multi_pass={int(config.OCR_ENABLE_MULTI_PASS)}, "
        f"attempts={config.OCR_MAX_ATTEMPTS}, "
        f"timeout={config.OCR_ATTEMPT_TIMEOUT_SECONDS:.0f}s"
    )
    print(f"[Info] CORS 허용:   {', '.join(config.CORS_ORIGINS)}")
    print("="*60 + "\n")


# ─────────────────────────────────────────
# ❤️ 헬스 체크 엔드포인트
# ─────────────────────────────────────────
@app.get(
    "/api/v1/health",
    tags=["❤️ 서버 상태"],
    summary="서버 상태 확인",
    description="서버가 정상 동작 중인지 확인하는 엔드포인트입니다.",
)
async def health_check():
    """
    서버와 기준 데이터 상태를 확인합니다.

    프론트엔드는 이 API로 다음을 확인할 수 있습니다.
    - FastAPI 서버가 살아 있는지
    - 현재 OCR 모드가 무엇인지
    - PostgreSQL DB가 연결되는지
    - DB에 기준 데이터가 마이그레이션되어 있는지

    ⚠️ 보안상 DB 비밀번호, 접속 문자열, 상세 오류 메시지는 반환하지 않습니다.
    """
    db_status = await run_in_threadpool(check_database_health)
    db_connected = db_status.get("status") == "connected"

    return {
        "status": "healthy" if db_connected else "degraded",
        "message": (
            "🎓 서버와 DB가 정상 동작 중입니다."
            if db_connected
            else "🎓 서버는 동작 중이지만 DB 연결 또는 기준 데이터 확인이 필요합니다."
        ),
        "version": "1.0.0-mvp",
        "ocr_mode": config.OCR_MODE,
        "data_source": config.TRACK_DATA_SOURCE,
        "db": db_status,
    }


# ─────────────────────────────────────────
# 📌 루트 경로 (/)
# ─────────────────────────────────────────
@app.get(
    "/",
    tags=["❤️ 서버 상태"],
    summary="API 안내",
)
async def root():
    """루트 경로 접근 시 API 안내를 반환합니다."""
    frontend_index = os.path.join(frontend_dir, "index.html")
    if os.path.exists(frontend_index):
        return RedirectResponse(url=f"{config.FRONTEND_ROUTE}/index.html")

    return {
        "message": "트랙길잡이 API",
        "docs": "/docs (Swagger UI에서 API를 테스트할 수 있습니다)",
        "health": "/api/v1/health (서버 상태 확인)",
        "endpoints": {
            "POST /api/v1/upload": "성적표 이미지 업로드 + OCR",
            "POST /api/v1/analyze": "트랙 이수 분석 + 추천",
            "GET /api/v1/tracks": "전체 트랙 목록 조회",
            "GET /api/v1/tracks/by-department?dept_name=학과명": "특정 학과 트랙 상세 조회 — 프론트 권장",
            "GET /api/v1/modules/by-department?dept_name=학과명": "특정 학과 모듈/과목 조회 — 프론트 권장",
            "GET /api/v1/tracks/{학과명}": "특정 학과 트랙 상세 조회 — 구 방식 호환",
            f"GET {config.FRONTEND_ROUTE}/index.html": "프론트엔드 UI 페이지",
        }
    }


# ─────────────────────────────────────────
# 🖥️ 프론트엔드 테스트 페이지 서빙
# ─────────────────────────────────────────
# ─────────────────────────────────────────
# 🖥️ 프론트엔드 테스트 페이지 서빙 (이전 버전 호환성 유지용)
# ─────────────────────────────────────────
@app.get("/frontend.html", tags=["UI-Deprecated"], summary="프론트엔드 테스트 페이지 (구 버전)")
async def serve_frontend_legacy():
    """/frontend/index.html로 리다이렉트하거나 직접 서빙합니다."""
    frontend_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"error": "프론트엔드 파일을 찾을 수 없습니다."}


# ─────────────────────────────────────────
# 🏃 직접 실행 시 (python main.py)
# ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 서버를 시작합니다...")
    logger.info("📄 API 문서: %s/docs", config.PUBLIC_BASE_URL)
    logger.info("❤️ 헬스 체크: %s/api/v1/health", config.PUBLIC_BASE_URL)

    # uvicorn 서버 실행
    uvicorn.run(
        "main:app",             # "파일명:앱인스턴스명"
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=config.SERVER_RELOAD,
    )
