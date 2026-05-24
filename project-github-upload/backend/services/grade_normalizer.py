"""
🎓 grade_normalizer.py — 성적 문자열 정규화 유틸

이 파일의 역할
- OCR 또는 프론트 입력에서 들어온 성적 표기를 백엔드 내부 표기로 통일합니다.
- 특히 OCR이 숫자 0을 알파벳 O/o로 잘못 읽는 문제를 보정합니다.

예:
- Ao, AO, A０ → A0
- Bo, BO → B0
- P, NP, F는 그대로 유지
"""
from __future__ import annotations

import re
import unicodedata


# 백엔드에서 정상 성적으로 인정하는 값입니다.
# A/B/C/D 단독 표기는 혹시 성적표가 A0 대신 A처럼 들어오는 경우를 위한 방어용입니다.
VALID_GRADES: set[str] = {
    "A+", "A0", "A",
    "B+", "B0", "B",
    "C+", "C0", "C",
    "D+", "D0", "D",
    "F", "P", "NP", "",
}


# OCR 원문에서 성적 후보를 찾을 때 사용하는 패턴입니다.
# 주의: AI, DESIGN 같은 영어 단어 안의 A/D를 성적으로 오인하지 않도록
# 앞뒤에 영문/숫자/한글이 붙은 경우는 제외합니다.
GRADE_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9가-힣])(?:NP|[A-D](?:[+0O])?|F|P|-)(?![A-Za-z0-9가-힣])",
    re.IGNORECASE,
)


_FRONTEND_GRADE_MAP: dict[str, str] = {
    "미이수(F)": "F",
    "NON-PASS": "NP",
    "PASS": "P",
    "이수": "",
}


def normalize_grade_text(value) -> str:
    """
    성적 문자열을 백엔드 내부 표기로 통일합니다.

    Args:
        value: OCR 또는 프론트에서 들어온 성적 값

    Returns:
        str: 정규화된 성적 문자열

    예:
        "Ao" -> "A0"
        "BO" -> "B0"
        " a+ " -> "A+"
        "미이수(F)" -> "F"
        "Non-pass" -> "NP"
        None -> ""
    """
    if value is None:
        return ""

    grade = unicodedata.normalize("NFKC", str(value))
    grade = grade.strip().upper()
    grade = re.sub(r"\s+", "", grade)

    if grade == "-":
        return ""

    # 프론트 표시용 문자열 → 백엔드 내부 코드 변환
    if grade in _FRONTEND_GRADE_MAP:
        return _FRONTEND_GRADE_MAP[grade]

    # OCR에서 숫자 0이 알파벳 O로 읽히는 경우 보정
    if re.fullmatch(r"[A-D]O", grade):
        grade = f"{grade[0]}0"

    return grade


def is_valid_grade(value) -> bool:
    """정규화 후 백엔드가 처리 가능한 성적인지 확인합니다."""
    return normalize_grade_text(value) in VALID_GRADES
