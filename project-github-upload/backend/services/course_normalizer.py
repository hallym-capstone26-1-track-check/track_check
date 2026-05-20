"""
🧩 course_normalizer.py — 안전한 과목명 정규화 / 명시적 alias 매핑

이 파일의 역할
- 프론트엔드 또는 OCR에서 받은 과목명을 track_rules.json의 공식 과목명과 비교할 수 있게 정리합니다.

중요한 설계 원칙
- 유사도 기반 자동 추측은 하지 않습니다.
  예: "인공지능"을 "인공지능기초"로 멋대로 바꾸지 않습니다.
- 아래처럼 표기만 다른 경우만 같은 과목으로 인정합니다.
  예: "인공 지능기초" → "인공지능기초"
  예: "무기화학I", "무기화학Ⅰ", "무기화학１" → 같은 비교 key
  예: "VR／AR／게임 제작기초" → "VR/AR/게임제작기초"
- 의미가 달라질 수 있는 보정은 track_rules.json의 course_aliases에 명시된 경우만 허용합니다.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

from config import TRACK_RULES_JSON_PATH
from services.data_loader import load_track_rules


# ═══════════════════════════════════════════
# 📌 정규화용 문자 처리 규칙
# ═══════════════════════════════════════════

# OCR/복붙 과정에서 눈에 잘 안 보이는 문자들
INVISIBLE_CHARS_PATTERN = re.compile(r"[\u200B-\u200D\uFEFF]")

# 여러 종류의 하이픈/대시를 일반 하이픈(-)으로 통일
HYPHEN_TRANSLATION = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    "－": "-",
})

# 여러 종류의 슬래시를 일반 슬래시(/)로 통일
SLASH_TRANSLATION = str.maketrans({
    "／": "/",
    "∕": "/",
    "⁄": "/",
})


def _normalize_trailing_roman_numbers(value: str) -> str:
    """
    과목명 끝에 붙는 로마 숫자 표기를 비교용 숫자로 통일합니다.

    예:
    - 무기화학Ⅰ / 무기화학I / 무기화학ⅰ / 무기화학１ → 무기화학1
    - 재료과학개론II / 재료과학개론Ⅱ / 재료과학개론２ → 재료과학개론2

    주의:
    - AI, IoT 같은 단어 안의 I는 바꾸지 않습니다.
    - '한글 뒤 + 문자열 끝'에 붙은 i/ii/iii 정도만 처리합니다.
    """
    value = re.sub(r"(?<=[가-힣])iii$", "3", value)
    value = re.sub(r"(?<=[가-힣])ii$", "2", value)
    value = re.sub(r"(?<=[가-힣])i$", "1", value)
    return value


def normalize_course_key(text: str) -> str:
    """
    과목명 비교용 key를 만듭니다.

    이 함수는 화면에 보여줄 과목명을 만드는 함수가 아닙니다.
    공식 과목명과 사용자가 입력한 과목명을 '안전하게 비교'하기 위한 내부 key만 만듭니다.

    처리하는 것:
    - 전각/반각 문자 통일: １ → 1, Ａ → A
    - 이상한 공백/보이지 않는 문자 제거
    - 띄어쓰기 제거: 인공 지능기초 → 인공지능기초
    - 하이픈/슬래시 통일
    - 영어 대소문자 통일: iot → IoT 비교 가능
    - 과목명 끝의 로마 숫자 통일: Ⅰ/I/ⅰ/１ → 1

    처리하지 않는 것:
    - 비슷해 보이는 다른 과목으로 자동 추측
      예: 인공지능 → 인공지능기초 는 절대 자동 인정하지 않음
    """
    if text is None:
        return ""

    value = str(text)

    # 1. 유니코드 정규화
    #    예: 전각 숫자 １ → 1, 로마숫자 Ⅰ → I, 전각 슬래시 ／ → /
    value = unicodedata.normalize("NFKC", value)

    # 2. 눈에 안 보이는 문자 제거
    value = INVISIBLE_CHARS_PATTERN.sub("", value)

    # 3. 하이픈/슬래시 통일
    value = value.translate(HYPHEN_TRANSLATION)
    value = value.translate(SLASH_TRANSLATION)

    # 4. 앞뒤 공백 제거 후 모든 공백 제거
    #    예: 인 공지능 기 초 → 인공지능기초
    value = value.strip()
    value = re.sub(r"\s+", "", value)

    # 5. 영어 대소문자 차이 제거
    #    예: iot네트워크, IOT네트워크, IoT네트워크를 같은 key로 비교
    value = value.casefold()

    # 6. 끝 로마 숫자 표기 통일
    value = _normalize_trailing_roman_numbers(value)

    return value


def _clean_display_name(text: str) -> str:
    """
    매칭 실패 시 사용자 입력값을 최소한으로만 정리해서 반환합니다.

    공식 과목명으로 인정하지 못한 경우에도 원문을 너무 많이 바꾸면 사용자가 헷갈립니다.
    따라서 앞뒤/중복 공백, 전각 문자, 하이픈/슬래시 정도만 정리합니다.
    """
    if text is None:
        return ""

    value = unicodedata.normalize("NFKC", str(text))
    value = INVISIBLE_CHARS_PATTERN.sub("", value)
    value = value.translate(HYPHEN_TRANSLATION)
    value = value.translate(SLASH_TRANSLATION)
    value = " ".join(value.strip().split())
    return value


# ═══════════════════════════════════════════
# 📌 데이터 로드
# ═══════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_normalization_assets() -> tuple[dict[str, str], dict[str, str]]:
    """
    track_rules.json에서 alias 맵과 공식 과목 카탈로그를 로드합니다.

    Returns:
        (alias_map, course_catalog)
        - alias_map: {비교용 key: 공식 과목명}
        - course_catalog: {비교용 key: 공식 과목명}
    """
    data = load_track_rules()

    # 1. 명시적 alias 맵 로드
    #    의미가 바뀔 수 있는 매핑은 반드시 track_rules.json에 직접 적혀 있어야 합니다.
    alias_map: dict[str, str] = {}
    for raw_name, canonical_name in data.get("course_aliases", {}).items():
        alias_map[normalize_course_key(raw_name)] = canonical_name

    # 2. 전체 공식 과목 카탈로그 구축
    course_catalog: dict[str, str] = {}
    for college in data.get("colleges", []):
        for dept in college.get("departments", []):
            for module in dept.get("modules", []):
                for course in module.get("courses", []):
                    course_name = course.get("course_name", "").strip()
                    key = normalize_course_key(course_name)
                    if key:
                        # 같은 key가 중복될 경우 먼저 나온 공식 과목명을 유지합니다.
                        course_catalog.setdefault(key, course_name)

    return alias_map, course_catalog


# ═══════════════════════════════════════════
# 📌 메인 정규화 함수
# ═══════════════════════════════════════════

def normalize_course_name(course_name: str) -> str:
    """
    과목명을 안전하게 공식 과목명으로 정규화합니다.

    처리 순서:
    1. 입력값을 비교용 key로 변환
    2. course_aliases에 명시된 alias인지 확인
    3. 공식 과목 카탈로그와 key가 정확히 일치하는지 확인
    4. 매칭 실패 시 자동 추측 없이 최소 정리된 입력값 반환

    예:
    - "인공지능 기초" → "인공지능기초"
    - "인 공지능 기 초" → "인공지능기초"
    - "무기화학I" → "무기화학Ⅰ"
    - "무기화학１" → "무기화학Ⅰ"
    - "인공지능" → "인공지능"  # 인공지능기초로 추측하지 않음
    """
    if not course_name:
        return ""

    alias_map, course_catalog = _load_normalization_assets()
    key = normalize_course_key(course_name)

    # 1. 명시적 alias 우선
    if key in alias_map:
        canonical_name = alias_map[key]
        canonical_key = normalize_course_key(canonical_name)
        return course_catalog.get(canonical_key, canonical_name)

    # 2. 공식 과목명과 안전한 key exact match
    if key in course_catalog:
        return course_catalog[key]

    # 3. 유사도 추측은 하지 않음
    return _clean_display_name(course_name)


def normalize_course_record(course: dict) -> dict:
    """과목 레코드의 course_name을 정규화합니다."""
    normalized = dict(course)
    normalized["course_name"] = normalize_course_name(course.get("course_name", ""))
    return normalized


def normalize_course_records(courses: list[dict]) -> list[dict]:
    """과목 레코드 리스트 전체를 정규화합니다."""
    return [normalize_course_record(course) for course in courses]
