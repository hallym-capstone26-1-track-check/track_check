"""
⚙️ config.py — 프로젝트 설정값 모음
"""
from __future__ import annotations

import os
import platform


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} 환경변수는 정수여야 합니다. 현재 값: {raw}")


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"{name} 환경변수는 숫자여야 합니다. 현재 값: {raw}")


def _csv_env(name: str, default: list[str]) -> list[str]:
    """콤마로 구분된 환경변수를 list[str]로 변환합니다.

    예: CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
    환경변수가 비어 있으면 default를 그대로 사용합니다.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]

ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
ALLOWED_MIME_TYPES: set[str] = {
    "image/jpeg", "image/png", "image/bmp", "image/tiff", "image/webp",
}
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024     # 파일 1개당 최대 10MB
MAX_FILES_COUNT: int = 5                         # 한 번에 최대 5장 (성적표는 보통 1~3장이면 충분)
MAX_TOTAL_UPLOAD_BYTES: int = 30 * 1024 * 1024   # 한 요청 합산 최대 30MB (메모리 보호)

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
TRACK_DATA_SOURCE: str = os.environ.get("TRACK_DATA_SOURCE", "db").strip().lower() or "db"
if TRACK_DATA_SOURCE != "db":
    raise RuntimeError(
        "TRACK_DATA_SOURCE는 이제 db만 지원합니다. "
        "PostgreSQL 기준 데이터를 사용하려면 TRACK_DATA_SOURCE=db로 설정하세요."
    )
PROJECT_DIR: str = os.path.abspath(os.path.join(BASE_DIR, ".."))

FRONTEND_ROUTE: str = os.environ.get("FRONTEND_ROUTE", "/frontend").strip() or "/frontend"
if not FRONTEND_ROUTE.startswith("/"):
    FRONTEND_ROUTE = f"/{FRONTEND_ROUTE}"
FRONTEND_ROUTE = FRONTEND_ROUTE.rstrip("/") or "/frontend"

_frontend_dir_raw = os.environ.get(
    "FRONTEND_DIR",
    os.path.join(PROJECT_DIR, "frontend", "dist"),
).strip()
FRONTEND_DIR: str = (
    os.path.abspath(_frontend_dir_raw)
    if os.path.isabs(_frontend_dir_raw)
    else os.path.abspath(os.path.join(BASE_DIR, _frontend_dir_raw))
)

PUBLIC_BASE_URL: str = os.environ.get(
    "PUBLIC_BASE_URL",
    "http://127.0.0.1:8000",
).strip().rstrip("/")

SERVER_HOST: str = os.environ.get("SERVER_HOST", "127.0.0.1").strip() or "127.0.0.1"
SERVER_PORT: int = _int_env("SERVER_PORT", _int_env("PORT", 8000))
SERVER_RELOAD: bool = _bool_env("SERVER_RELOAD", True)

DB_POOL_MIN: int = _int_env("DB_POOL_MIN", 1)
DB_POOL_MAX: int = _int_env("DB_POOL_MAX", 10)

STUDENT_ID_PATTERN: str = r"\d{8,10}"
NAME_PATTERN: str = r"[가-힣]{2,5}"

# 개발 중 프론트엔드 주소만 허용합니다.
# ⚠️ 보안상 "*" 전체 허용은 쓰지 않습니다.
#
# 발표/팀원 PC 테스트에서 포트가 달라질 수 있으므로 자주 쓰는 로컬 주소를 넉넉히 허용합니다.
# 필요하면 환경변수 CORS_ORIGINS로 덮어쓸 수 있습니다.
# 예: CORS_ORIGINS=http://localhost:5173,http://192.168.0.10:5173
CORS_ORIGINS: list[str] = _csv_env("CORS_ORIGINS", [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
])

# ⚠️ 보안 가드: "*" 와일드카드는 허용하지 않음.
# allow_credentials=True 와 결합되면 모든 사이트가 사용자 쿠키를 들고 우리 API를 호출 가능 → 심각한 CSRF/탈취 위험.
# 환경변수에 실수로 "*" 가 들어와도 서버 시작 시점에 즉시 막아 사고를 예방합니다.
if "*" in CORS_ORIGINS:
    raise RuntimeError(
        "❌ CORS_ORIGINS 에 '*' 와일드카드가 포함되어 있습니다.\n"
        "   allow_credentials=True 와 결합되면 보안 사고가 발생할 수 있어 차단합니다.\n"
        "   프론트엔드 주소를 명시적으로 지정해주세요.\n"
        "   예: CORS_ORIGINS=http://localhost:5173,http://localhost:3000"
    )

# Tesseract 실행 파일 경로
# 환경변수 TESSERACT_CMD가 있으면 우선 사용,
# 없으면 OS별 기본 경로 사용 (Windows: 설치 경로, Mac/Linux: PATH에서 자동 탐색)
TESSERACT_CMD: str = os.environ.get(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if platform.system() == "Windows"
    else "tesseract",  # Mac/Linux는 PATH에 있으면 그냥 "tesseract"로 동작
)

# OCR 모드: "mock" 또는 "tesseract"
# 발표/시연 때 코드 수정 없이 환경변수만 바꿔서 전환할 수 있게 합니다.
# Windows 예: set OCR_MODE=tesseract
# Mac/Linux 예: export OCR_MODE=tesseract
OCR_MODE: str = os.environ.get("OCR_MODE", "mock").strip().lower() or "mock"

# Tesseract OCR 튜닝값입니다.
# 정확도 개선을 위해 한 이미지에 대해 몇 가지 전처리/페이지분할 조합을 시도할 수 있습니다.
# 클라우드 무료 인스턴스에서 느리면 OCR_ENABLE_MULTI_PASS=0 또는 OCR_MAX_ATTEMPTS=1로 줄이면 됩니다.
OCR_TESSERACT_LANGS: str = os.environ.get("OCR_TESSERACT_LANGS", "kor+eng").strip() or "kor+eng"
OCR_ENABLE_MULTI_PASS: bool = _bool_env("OCR_ENABLE_MULTI_PASS", True)
OCR_MAX_ATTEMPTS: int = max(1, _int_env("OCR_MAX_ATTEMPTS", 4))
OCR_COMBINE_TOP_TEXTS: int = max(1, _int_env("OCR_COMBINE_TOP_TEXTS", 2))
OCR_ATTEMPT_TIMEOUT_SECONDS: float = max(3.0, _float_env("OCR_ATTEMPT_TIMEOUT_SECONDS", 15.0))

# Mock 시나리오 예시:
# "sw_ai" | "sw_iot" | "sw_empty" | "sw_mixed" | "knu_full"
# "tourism_leisure" | "media_ai_journalism" | "sw_duplicate"
# Windows 예: set MOCK_SCENARIO=sw_duplicate
MOCK_SCENARIO: str = os.environ.get("MOCK_SCENARIO", "sw_ai").strip() or "sw_ai"

# ─────────────────────────────────────────
# 🐛 디버그 모드 (개발 vs 운영 분기)
# ─────────────────────────────────────────
# 환경변수 DEBUG_MODE 가 "1" / "true" / "yes" 면 켜짐.
# 기본값은 "1" (개발 편의 우선).
# 운영 배포 시에는 환경변수에서 "0" 또는 "false"로 명시적으로 꺼야 합니다.
#
# 이 값이 켜져 있을 때만 동작하는 기능:
# - /api/v1/decrypt 엔드포인트 (테스트용 복호화) 등록
# - 일부 디버그 로그 노출
#
# ⚠️ 운영 배포 체크리스트:
#   set DEBUG_MODE=0   (Windows)
#   export DEBUG_MODE=0  (Mac/Linux)
DEBUG_MODE: bool = _bool_env("DEBUG_MODE", True)
