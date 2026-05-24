"""
🔒 privacy_service.py — 개인정보 보호 서비스 + Fernet 암호화/복호화

💡 이 파일의 역할:
   1. OCR 결과에서 이름, 학번 등 개인정보를 감지하고 마스킹 처리
   2. 로그에 민감정보가 기록되지 않도록 방지
   3. Fernet 대칭키 암호화/복호화 기능 제공

💡 개인정보 처리 원칙 (MVP):
   1. 원본 성적표 이미지는 저장하지 않습니다.
   2. OCR 원문과 세부 성적 원문은 로그에 남기지 않습니다.
   3. 분석에 필요한 과목명/학점/성적은 메모리에서만 처리합니다.
   4. 학번, 이름처럼 학생을 직접 식별할 수 있는 값만 기본 암호화 대상으로 둡니다.

💡 암호화 흐름:
   프론트 → 백엔드: 분석에 필요한 값은 평문으로 전달
   백엔드 내부: 평문 상태로 분석/판별 수행
   백엔드 → 프론트: 저장 또는 표시가 필요한 민감 필드만 암호화 가능

💡 Q&A:
   Q: 학과명이나 성적도 기본 암호화 대상이야?
   A: 아니요. 학과명, 과목명, 성적은 판별과 화면 표시가 필요하므로
      기본 암호화 대상에서 제외합니다. 다만 DB 저장을 도입한다면 별도 정책을 다시 정해야 합니다.

   Q: 암호화된 상태에서 조건을 판단해야 해?
   A: 아니요. 판별 로직은 암호화 전 평문 상태에서 수행합니다.
      현재 MVP는 저장하지 않는 설계가 우선입니다.

⚠️ 보안 경고:
   - ENCRYPTION_KEY는 환경변수로 관리해야 합니다!
   - 현재 MVP에서는 서버 시작 시 자동 생성 (서버 재시작 시 키 변경됨)
"""
from __future__ import annotations

import os
import re
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from config import STUDENT_ID_PATTERN, NAME_PATTERN, DEBUG_MODE

logger = logging.getLogger(__name__)

# 기본 암호화 대상입니다.
# 분석/화면 표시가 필요한 dept_name, course_name, credits, grade는 기본 대상에서 제외합니다.
DEFAULT_SENSITIVE_FIELDS: list[str] = [
    "student_id", "name", "student_name", "phone", "birth_date",
]


# ═══════════════════════════════════════════
# 🔐 암호화 키 관리
# ═══════════════════════════════════════════

_ENCRYPTION_KEY: Optional[bytes] = None # 


def _get_encryption_key() -> bytes:
    """
    암호화 키를 반환합니다.

    동작 정책:
    1) 환경변수 ENCRYPTION_KEY 가 있으면 그것을 사용합니다. (권장)
    2) 환경변수가 없는 경우:
       - DEBUG_MODE=True (개발 환경)  → 임시 키 자동 생성 + 강한 경고
       - DEBUG_MODE=False (운영 환경) → 즉시 에러로 차단

    왜 운영에서 차단하나요?
    - 자동 생성 키는 서버를 재시작하면 바뀝니다.
    - 그러면 이전에 암호화한 데이터를 더 이상 복호화할 수 없습니다.
    - 운영 환경에서 이런 상황이 일어나는 것은 데이터 손실과 같습니다.
    - 따라서 운영에서는 명시적으로 환경변수를 설정하도록 강제합니다.

    Raises:
        RuntimeError: 운영 환경(DEBUG_MODE=False)인데 ENCRYPTION_KEY가 없을 때
    """
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY

    env_key = os.environ.get("ENCRYPTION_KEY")
    if env_key:
        _ENCRYPTION_KEY = env_key.encode("utf-8")
        logger.info("암호화 키: 환경변수에서 로드 완료")
        return _ENCRYPTION_KEY

    # 환경변수가 없는 경우 — DEBUG_MODE에 따라 동작이 다릅니다.
    if not DEBUG_MODE:
        # 운영 환경에서는 절대 자동 생성하지 않습니다.
        raise RuntimeError(
            "❌ ENCRYPTION_KEY 환경변수가 설정되지 않았습니다.\n"
            "운영 환경(DEBUG_MODE=False)에서는 암호화 키를 반드시 환경변수로 지정해야 합니다.\n"
            "\n"
            "해결 방법:\n"
            "  1) 키 생성 (한 번만):\n"
            '       python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            "  2) 출력된 키를 환경변수로 설정:\n"
            "       Windows  : set ENCRYPTION_KEY=...\n"
            "       Mac/Linux: export ENCRYPTION_KEY=...\n"
            "  3) 서버 재시작\n"
            "\n"
            "개발 중이라면 DEBUG_MODE=1 로 두면 임시 키가 자동 생성됩니다."
        )

    # 개발 환경 — 임시 키 자동 생성
    _ENCRYPTION_KEY = Fernet.generate_key()
    logger.warning(
        "⚠️ [DEV] 암호화 키가 자동 생성되었습니다. "
        "이 키는 서버 재시작 시 사라집니다 — 이전 암호문은 복호화 불가.\n"
        "      운영 배포 전에 반드시 ENCRYPTION_KEY 환경변수를 설정하고 "
        "DEBUG_MODE=0 으로 전환하세요."
    )
    return _ENCRYPTION_KEY


def _get_fernet() -> Fernet:
    """Fernet 암호화 객체를 반환합니다."""
    return Fernet(_get_encryption_key())


# ═══════════════════════════════════════════
# 🔐 암호화 / 복호화 함수
# ═══════════════════════════════════════════

def encrypt_value(plain_text: str) -> str:
    """
    평문 문자열을 암호화합니다.
    예: "20241234" → "gAAAAABh..." (알아볼 수 없는 문자열)
    """
    if not plain_text:
        return ""
    f = _get_fernet()
    encrypted = f.encrypt(plain_text.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_value(encrypted_text: str) -> str:
    """
    암호화된 문자열을 복호화합니다.
    예: "gAAAAABh..." → "20241234"

    Raises:
        ValueError: 복호화 실패 시 (키 불일치, 데이터 손상 등)
    """
    if not encrypted_text:
        return ""
    try:
        f = _get_fernet()
        decrypted = f.decrypt(encrypted_text.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        raise ValueError(
            "복호화에 실패했습니다. "
            "암호화 키가 변경되었거나 데이터가 손상되었을 수 있습니다."
        )


def encrypt_sensitive_fields(data: dict, fields: list[str] | None = None) -> dict:
    """
    딕셔너리에서 민감한 필드만 골라 암호화합니다.
    암호화된 필드에는 "{필드명}_encrypted": True 표시가 추가됩니다.

    예:
        원본: {"student_id": "20241234", "dept": "소프트웨어학부"}
        결과: {"student_id": "gAAAAABh...", "student_id_encrypted": True, "dept": "소프트웨어학부"}
    """
    if fields is None:
        # MVP에서는 원본 성적표와 과목/성적 데이터를 저장하지 않는 것이 1순위입니다.
        # 기본 암호화 대상은 학생을 직접 식별할 수 있는 값으로 최소화합니다.
        # 학과명(dept_name)이나 성적(grade)은 분석/화면 표시가 필요하므로 기본 암호화 대상에서 제외합니다.
        fields = DEFAULT_SENSITIVE_FIELDS

    encrypted_data = dict(data)
    for field in fields:
        if field in encrypted_data and encrypted_data[field]:
            raw_value = str(encrypted_data[field])
            encrypted_data[field] = encrypt_value(raw_value)
            encrypted_data[f"{field}_encrypted"] = True
    return encrypted_data


def decrypt_sensitive_fields(data: dict, fields: list[str] | None = None) -> dict:
    """
    딕셔너리에서 암호화된 민감 필드를 복호화합니다.
    """
    if fields is None:
        # MVP에서는 원본 성적표와 과목/성적 데이터를 저장하지 않는 것이 1순위입니다.
        # 기본 암호화 대상은 학생을 직접 식별할 수 있는 값으로 최소화합니다.
        # 학과명(dept_name)이나 성적(grade)은 분석/화면 표시가 필요하므로 기본 암호화 대상에서 제외합니다.
        fields = DEFAULT_SENSITIVE_FIELDS

    decrypted_data = dict(data)
    for field in fields:
        if field in decrypted_data and decrypted_data.get(f"{field}_encrypted"):
            try:
                decrypted_data[field] = decrypt_value(str(decrypted_data[field]))
                del decrypted_data[f"{field}_encrypted"]
            except ValueError:
                logger.warning("필드 '%s' 복호화 실패", field)
    return decrypted_data


# ═══════════════════════════════════════════
# 📌 개인정보 마스킹
# ═══════════════════════════════════════════

MASKING_PATTERNS = [
    {
        "name": "학번",
        "pattern": STUDENT_ID_PATTERN,
        "description": "8~10자리 숫자 (학번으로 추정)",
    },
    {
        "name": "전화번호",
        "pattern": r"01[016789]-?\d{3,4}-?\d{4}",
        "description": "휴대폰 번호 패턴",
    },
    {
        "name": "생년월일",
        "pattern": r"\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])",
        "description": "6자리 생년월일 (YYMMDD)",
    },
]


def _mask_phone_number(match: re.Match[str]) -> str:
    """
    전화번호 매칭을 마스킹합니다.

    두 가지 형식을 모두 지원:
    - 하이픈 있음: "010-1234-5678" → "010-****-**78"
    - 하이픈 없음: "01012345678"  → "010****-**78"

    람다 한 줄에 if-else를 끼워 넣으면 슬라이싱이 헷갈려서 의도와 다르게 동작할 수 있어,
    별도 함수로 분리해 케이스를 명확하게 구분합니다.
    """
    raw = match.group(0)
    digits_only = re.sub(r"\D", "", raw)  # 하이픈 등 비숫자 제거

    if len(digits_only) < 10:
        # 형식이 망가진 매칭이면 그냥 원본 유지
        return raw

    head = digits_only[:3]            # "010"
    tail_last_two = digits_only[-2:]  # 마지막 2자리

    if "-" in raw:
        return f"{head}-****-**{tail_last_two}"
    return f"{head}****-**{tail_last_two}"


def _mask_birth_date(match: re.Match[str]) -> str:
    """
    생년월일 6자리(YYMMDD) 중 뒤 4자리(MMDD)를 마스킹합니다.
    예: "990101" → "99****"
    """
    return match.group(0)[:2] + "****"


def mask_personal_info(text: str) -> str:
    """텍스트에서 개인정보를 감지하고 마스킹 처리합니다."""
    masked_text = text

    # 1. 학번 마스킹: "학번: 20241234" → "학번: 2024****"
    masked_text = re.sub(
        r"(학번\s*[:：]\s*)(\d{4})(\d{4,6})",
        lambda m: m.group(1) + m.group(2) + "*" * len(m.group(3)),
        masked_text
    )

    # 2. 이름 마스킹: "이름: 홍길동" → "이름: 홍**"
    masked_text = re.sub(
        r"((?:이름|성명)\s*[:：]\s*)([가-힣])([가-힣]{1,4})",
        lambda m: m.group(1) + m.group(2) + "*" * len(m.group(3)),
        masked_text
    )

    # 3. 범용 패턴 기반 마스킹 (전화번호, 생년월일 등)
    for pattern_info in MASKING_PATTERNS:
        # 학번은 컨텍스트("학번: ")가 있는 경우만 위에서 정밀하게 처리했으므로 여기서는 건너뜁니다.
        if pattern_info["name"] == "학번":
            continue

        if pattern_info["name"] == "전화번호":
            masked_text = re.sub(pattern_info["pattern"], _mask_phone_number, masked_text)
        elif pattern_info["name"] == "생년월일":
            masked_text = re.sub(pattern_info["pattern"], _mask_birth_date, masked_text)

    return masked_text


def remove_personal_info_from_courses(courses: list[dict]) -> list[dict]:
    """과목 리스트에서 개인정보 관련 항목을 제거합니다."""
    cleaned_courses = []
    for course in courses:
        name = course.get("course_name", "")
        if re.fullmatch(r"\d{8,}", name):
            logger.info("개인정보 의심 항목 제거됨 (학번 패턴)")
            continue
        if re.fullmatch(r"[가-힣]{2,3}", name) and course.get("credits", 0) == 0:
            logger.info("개인정보 의심 항목 제거됨 (이름 패턴)")
            continue
        cleaned_courses.append(course)
    return cleaned_courses


def sanitize_for_logging(data):
    """
    로그에 기록하기 전에 민감하거나 불필요하게 자세한 값을 제거/마스킹합니다.

    MVP 원칙:
    - 학번/이름/전화번호 같은 직접 식별 정보는 항상 [REDACTED]
    - 과목명/학점/성적/OCR 점수도 로그에는 남기지 않음
      (성적표 원문을 역추적할 수 있고, 디버그 로그가 너무 자세해지는 것을 방지)
    - dict/list 내부도 재귀적으로 처리
    """
    if isinstance(data, list):
        return [sanitize_for_logging(item) for item in data]

    if not isinstance(data, dict):
        if isinstance(data, str):
            return mask_personal_info(data)
        return data

    sanitized = {}
    sensitive_keys = {
        "student_id", "name", "student_name", "phone", "birth_date",
        "resident_number", "email",
    }
    # 과목명/학점/성적은 분석에는 필요하지만, 로그에는 원문으로 남기지 않습니다.
    course_detail_keys = {
        "course_name", "credits", "credit", "grade", "score", "match_score",
        "raw_text", "ocr_text",
    }

    for key, value in data.items():
        if key in sensitive_keys or key in course_detail_keys:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, (dict, list)):
            sanitized[key] = sanitize_for_logging(value)
        elif isinstance(value, str):
            sanitized[key] = mask_personal_info(value)
        else:
            sanitized[key] = value
    return sanitized
