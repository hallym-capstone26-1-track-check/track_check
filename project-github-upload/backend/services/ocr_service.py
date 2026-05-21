"""
🔍 ocr_service.py — OCR 처리 서비스 (mock + Tesseract 연결 포인트)

💡 이 파일의 역할:
   1. 성적표 이미지에서 텍스트를 추출 (OCR)
   2. 추출된 텍스트를 구조화된 과목 리스트로 변환
   3. Mock 모드에서는 가짜 데이터로 테스트 가능

💡 Mock 시나리오:
   프론트에서 시나리오를 선택할 수 있도록, /api/v1/upload에 scenario 파라미터를
   전달하면 해당 시나리오의 Mock 데이터를 반환합니다.

💡 여러 장 업로드 시 주의점:
   - 페이지 순서가 중요할 수 있음 (성적표가 여러 장일 때)
   - 현재는 순서대로 OCR 처리 후 합치는 방식
   - 같은 과목이 여러 장에 나오면 중복 제거됨 (upload.py에서 처리)

💡 실제 Tesseract를 붙일 때 바뀌는 부분:
   - _run_tesseract() 함수만 수정하면 됨
   - parse_ocr_text()와 나머지 로직은 그대로 유지 가능
   - Tesseract 대신 다른 OCR (Google Vision, Naver Clova 등)을 쓸 수도 있음
     → _run_tesseract() 대신 _run_google_ocr() 같은 함수를 만들면 됨
"""
from __future__ import annotations

import logging
import re
from cachetools import cached, TTLCache
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

from config import (
    MOCK_SCENARIO,
    OCR_COMBINE_TOP_TEXTS,
    OCR_ATTEMPT_TIMEOUT_SECONDS,
    OCR_ENABLE_MULTI_PASS,
    OCR_MAX_ATTEMPTS,
    OCR_MODE,
    OCR_TESSERACT_LANGS,
    TESSERACT_CMD,
)
from services.course_normalizer import normalize_course_name
from services.grade_normalizer import GRADE_TOKEN_PATTERN, normalize_grade_text, is_valid_grade
from services.test_case_service import (
    build_mock_ocr_text,
    get_generated_case,
    get_generated_scenarios,
)
from rapidfuzz import fuzz
from db import get_connection

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 📌 Mock 시나리오 데이터
# ═══════════════════════════════════════════
# 각 시나리오는 성적표 OCR 결과를 시뮬레이션합니다.
# 프론트에서 시나리오를 선택하면 해당 데이터가 반환됩니다.

MOCK_SCENARIOS: dict[str, dict] = {
    # ── 소프트웨어학부 시나리오들 ──
    "sw_ai": {
        "label": "소프트웨어학부 — 빅데이터AI 과목 이수",
        "dept": "소프트웨어학부",
        "text": """\
학번: 20241234
이름: 홍길동

교과목명                    학점  성적
데이터사이언스기초            3    A+
데이터베이스기초              3    B+
데이터베이스시스템            3    A0
빅데이터개론                  3    B0
인공지능기초                  3    A+
머신러닝                      3    B+
""",
    },
    "sw_iot": {
        "label": "소프트웨어학부 — IoT 과목 이수",
        "dept": "소프트웨어학부",
        "text": """\
학번: 20241235
이름: 이영희

교과목명                    학점  성적
IOT네트워크                   3    A+
IOT플랫폼설계                 3    B0
임베디드시스템                3    A0
디지털통신                    3    B+
통신네트워크시스템            3    A0
시스템보안                    3    B0
""",
    },
    "sw_mixed": {
        "label": "소프트웨어학부 — 여러 트랙 혼합 이수",
        "dept": "소프트웨어학부",
        "text": """\
학번: 20241237
이름: 박민준

교과목명                    학점  성적
데이터사이언스기초            3    A+
인공지능기초                  3    A+
IOT네트워크                   3    B+
웹프로그래밍                  3    A0
정보보호론                    3    A0
오픈소스SW의이해              3    B0
데이터베이스기초              3    -
머신러닝                      3    -
디지털통신                    3    -
임베디드시스템                3    -
""",
    },
    "sw_f_grade": {
        "label": "소프트웨어학부 — F학점/NP 포함 (필터링 테스트)",
        "dept": "소프트웨어학부",
        "text": """\
학번: 20241242
이름: 김재수강

교과목명                    학점  성적
데이터사이언스기초            3    F
데이터사이언스기초            3    B+
데이터베이스기초              3    A0
인공지능기초                  3    NP
인공지능기초                  3    A+
머신러닝                      3    F
빅데이터개론                  3    A0
""",
    },
    "sw_empty": {
        "label": "소프트웨어학부 — 과목 없음 (빈 성적표)",
        "dept": "소프트웨어학부",
        "text": """\
학번: 20241236
이름: 김철수

교과목명    학점  성적
""",
    },

    # ── 인공지능융합학부 시나리오들 ──
    "ai_medical": {
        "label": "인공지능융합학부 — 의료인공지능트랙 이수 중",
        "dept": "인공지능융합학부",
        "text": """\
학번: 20241250
이름: 정의료

교과목명                    학점  성적
의료인공지능                  3    A+
의료영상처리                  3    A0
인공지능데이터베이스          3    B+
인공지능데이터분석            3    A+
바이오신호처리및분석          3    B0
건강과질병의측정과분석        3    A0
의료정보학                    3    B+
""",
    },
    "ai_robot": {
        "label": "인공지능융합학부 — 로봇인공지능트랙 이수 중",
        "dept": "인공지능융합학부",
        "text": """\
학번: 20241251
이름: 이로봇

교과목명                    학점  성적
파이썬프로그래밍              3    A+
머신러닝프로그래밍            3    A0
신호처리                      3    B+
디지털이미지프로세싱          3    A+
로봇개론                      3    B0
센서공학                      3    A0
""",
    },

    # ── 디지털인문예술전공 시나리오들 ──
    "dha_smart_exp": {
        "label": "디지털인문예술전공 — 스마트경험디자인트랙 이수 중",
        "dept": "디지털인문예술전공",
        "text": """\
학번: 20241260
이름: 김디자인

교과목명                    학점  성적
AI이해의기초                  3    A+
융합형인재를위한코딩기초      3    B+
AI디자인                      3    A0
디자인씽킹기초                3    A+
UX디자인                      3    A0
서비스디자인                  3    B+
사회혁신디자인                3    A0
""",
    },
    "dha_ai_content": {
        "label": "디지털인문예술전공 — AI콘텐츠디자인트랙 이수 중",
        "dept": "디지털인문예술전공",
        "text": """\
학번: 20241261
이름: 박콘텐츠

교과목명                    학점  성적
AI이해의기초                  3    A+
융합형인재를위한코딩기초      3    A0
AI디자인                      3    B+
디지털디자인1                 3    A0
디지털디자인2                 3    B+
디지털디자인3                 3    A+
디지털디자인4                 3    B0
""",
    },
    "dha_ai_service": {
        "label": "디지털인문예술전공 — AI서비스개발트랙 이수 중",
        "dept": "디지털인문예술전공",
        "text": """\
학번: 20241262
이름: 최서비스

교과목명                    학점  성적
서비스디자인                  3    A+
사회혁신디자인                3    A0
경험디자인의고급과정2         3    B+
인문데이터마이닝              3    A0
지역혁신연구방법론            3    B+
인문DB설계                    3    A+
디지털문화콘텐츠마케팅        3    A0
UX디자인                      3    B+
""",
    },

    # ── 기타 학과 시나리오 ──
    "knu_full": {
        "label": "국어국문학전공 — 국어학 과목 집중 이수",
        "dept": "국어국문학전공",
        "text": """\
학번: 20241238
이름: 최수아

교과목명            학점  성적
국어학개론            3    A+
국어학강독            3    A0
국어음운론            3    B+
국어형태론            3    A+
훈민정음의이해        3    B+
한국어교육의이해      3    A0
국어통사론            3    B0
""",
    },
    "econ_entrepreneur": {
        "label": "경제학과 — 기업가 트랙 이수 중",
        "dept": "경제학과",
        "text": """\
학번: 20241270
이름: 한경제

교과목명                    학점  성적
경제학원론(미시)              3    A+
경제학원론(거시)              3    A0
경제와수학적분석              3    B+
미시경제학Ⅰ                  3    A+
미시경제학Ⅱ                  3    B0
거시경제학Ⅰ                  3    A0
국제무역론                    3    B+
시장구조와기업전략            3    A0
""",
    },
}


# ═══════════════════════════════════════════
# 📌 OCR 실행 함수
# ═══════════════════════════════════════════

def get_available_scenarios() -> list[dict]:
    """
    프론트에서 사용 가능한 Mock 시나리오 목록을 반환합니다.

    기본으로 직접 작성한 시나리오(MOCK_SCENARIOS)를 먼저 보여주고,
    그 아래에 DB 기준 데이터로 자동 생성한 전체 학과/트랙 테스트 케이스를 붙입니다.

    Returns:
        list[dict]: [{key, label, dept, ...}, ...]
    """
    hand_written = [
        {
            "key": key,
            "label": val["label"],
            "dept": val["dept"],
            "track_id": "",
            "track_name": "",
            "kind": "manual",
            "course_count": 0,
        }
        for key, val in MOCK_SCENARIOS.items()
    ]
    return hand_written + get_generated_scenarios()


def run_ocr(
    image_bytes: bytes,
    filename: str = "unknown",
    scenario: str | None = None,
) -> list[dict]:
    """
    이미지에서 OCR을 수행하고 과목 리스트를 반환합니다.

    Args:
        image_bytes: 이미지 바이너리 데이터
        filename: 파일명 (로그용)
        scenario: Mock 시나리오 키 (None이면 config.py의 MOCK_SCENARIO 사용)

    Returns:
        list[dict]: 과목 리스트 [{course_name, credits, grade}, ...]
    """
    logger.info(
        "OCR 처리 시작 — 파일크기: %sbytes, 모드: %s",
        len(image_bytes), OCR_MODE,
    )

    if OCR_MODE == "tesseract":
        raw_text = _run_tesseract(image_bytes)
    else:
        raw_text = _run_mock_ocr(image_bytes, scenario)

    courses = parse_ocr_text(raw_text)
    logger.info("OCR 처리 완료 — 추출된 과목 수: %s개", len(courses))
    return courses


def get_scenario_text(scenario: str) -> str:
    """시나리오 키에 해당하는 Mock OCR 텍스트를 반환합니다."""
    return _run_mock_ocr(b"", scenario)


def extract_text_from_image(image_bytes: bytes) -> str:
    """
    이미지에서 텍스트를 추출합니다.
    OCR_MODE에 따라 Tesseract 또는 Mock을 사용합니다.
    """
    if OCR_MODE == "tesseract":
        if len(image_bytes) < 500:
            logger.info("이미지 크기가 매우 작아 Tesseract 처리를 스킵합니다. (더미 이미지로 간주)")
            return ""
        return _run_tesseract(image_bytes)
    elif OCR_MODE == "mock":
        return _run_mock_ocr(image_bytes, None)
    return ""


def _run_mock_ocr(image_bytes: bytes, scenario: str | None = None) -> str:
    """Mock OCR: 시나리오에 따라 가짜 성적 텍스트를 반환합니다."""
    chosen = scenario or MOCK_SCENARIO

    # 1) 기존에 직접 작성한 대표 시나리오 먼저 확인
    scenario_data = MOCK_SCENARIOS.get(chosen)
    if scenario_data is not None:
        logger.info("Mock OCR 실행 — 수동 시나리오: %s", chosen)
        return scenario_data["text"]

    # 2) DB 기준 데이터 기반 자동 생성 시나리오 확인
    generated_case = get_generated_case(chosen)
    if generated_case is not None:
        logger.info("Mock OCR 실행 — 자동 생성 테스트 케이스: %s", chosen)
        return build_mock_ocr_text(generated_case)

    # 3) 알 수 없는 값이면 기본 시나리오로 fallback
    logger.warning("알 수 없는 시나리오 '%s' → 기본값(sw_ai) 사용", chosen)
    return MOCK_SCENARIOS["sw_ai"]["text"]


def _resize_image_for_ocr(image: Image.Image, min_width: int = 1800) -> Image.Image:
    """Tesseract가 작은 글씨를 더 잘 읽도록 저해상도 이미지를 확대합니다."""
    width, height = image.size
    if width <= 0 or height <= 0 or width >= min_width:
        return image

    scale = min(min_width / width, 3.0)
    new_width = int(width * scale)
    new_height = int(height * scale)

    if new_width * new_height > 16_000_000:
        raise ValueError("이미지 비율이 비정상적으로 커서 처리할 수 없습니다.")

    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def _preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    OCR 정확도를 높이기 위한 이미지 전처리.
    (팀원 gil_track 코드의 preprocess_image_for_ocr 로직 이식)
    """

    # EXIF 회전 보정
    image = ImageOps.exif_transpose(image)
    # 흑백 변환
    image = image.convert("L")
    # 대비 자동 조정
    image = ImageOps.autocontrast(image)
    # 샤프닝
    image = image.filter(ImageFilter.SHARPEN)

    return _resize_image_for_ocr(image, min_width=1800)


def _build_ocr_image_variants(image: Image.Image) -> dict[str, Image.Image]:
    """
    성적표 이미지 품질 편차에 대응하기 위한 전처리 후보를 만듭니다.

    - gray: 기본 확대/흑백/대비/샤프닝
    - contrast: 흐린 스캔과 연한 글씨 보정
    - threshold: 배경 잡음이 많은 사진 보정
    """
    base = _preprocess_image_for_ocr(image)
    variants: dict[str, Image.Image] = {"gray": base}

    contrast = ImageEnhance.Contrast(base).enhance(1.7)
    contrast = ImageEnhance.Sharpness(contrast).enhance(1.5)
    variants["contrast"] = contrast.filter(ImageFilter.MedianFilter(size=3))

    threshold_base = variants["contrast"]
    variants["threshold"] = threshold_base.point(
        lambda pixel: 255 if pixel > 165 else 0,
        mode="1",
    ).convert("L")

    return variants


def _combine_ocr_texts(texts: list[str]) -> str:
    """여러 OCR 결과에서 중복 줄을 제거해 하나의 텍스트로 합칩니다."""
    combined_lines: list[str] = []
    seen: set[str] = set()

    for text in texts:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            key = compact_text_for_matching(stripped)
            if not key or key in seen:
                continue
            combined_lines.append(stripped)
            seen.add(key)

    return "\n".join(combined_lines)


def _score_tesseract_text(text: str) -> tuple[int, float]:
    """
    OCR 결과를 과목 매칭 관점에서 평가합니다.

    단순 글자 수보다 DB 과목으로 몇 개나 안정적으로 매칭되는지가 실제 사용자 경험에 중요합니다.
    """
    if not text.strip():
        return 0, 0.0

    try:
        courses = parse_ocr_text(text, include_score=True)
    except Exception as exc:
        logger.debug("OCR 후보 텍스트 점수 계산 실패: %s", type(exc).__name__)
        return 0, 0.0

    if not courses:
        return 0, 0.0

    average_score = sum(float(course.get("score", 0) or 0) for course in courses) / len(courses)
    return len(courses), average_score


def _run_tesseract(image_bytes: bytes) -> str:
    """
    실제 Tesseract OCR을 실행합니다.

    💡 실제 OCR을 붙일 때 이 함수만 수정하면 됩니다.
    💡 Tesseract 대신 다른 OCR을 사용할 경우:
       이 함수의 내부만 교체하면 됩니다. (인터페이스는 동일)
    """
    try:
        import io
        import time

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        source_image = Image.open(io.BytesIO(image_bytes))
        variants = _build_ocr_image_variants(source_image)
        source_image.close()

        # PSM 6: 단일 텍스트 블록, PSM 4: 세로 열/표 구조, PSM 11: 흩어진 텍스트.
        common_config = "-c preserve_interword_spaces=1 -c user_defined_dpi=300"
        attempt_plan = [
            ("gray", "psm6", f"--oem 3 --psm 6 {common_config}"),
            ("contrast", "psm4", f"--oem 3 --psm 4 {common_config}"),
            ("threshold", "psm6", f"--oem 3 --psm 6 {common_config}"),
            ("contrast", "psm11", f"--oem 3 --psm 11 {common_config}"),
            ("gray", "psm3", f"--oem 3 --psm 3 {common_config}"),
        ]
        if not OCR_ENABLE_MULTI_PASS:
            attempt_plan = attempt_plan[:1]
        attempt_plan = attempt_plan[:OCR_MAX_ATTEMPTS]

        start_time = time.time()
        attempts: list[dict] = []
        for variant_name, psm_name, tesseract_config in attempt_plan:
            variant = variants.get(variant_name)
            if variant is None:
                continue

            try:
                text = pytesseract.image_to_string(
                    variant,
                    lang=OCR_TESSERACT_LANGS,
                    config=tesseract_config,
                    timeout=OCR_ATTEMPT_TIMEOUT_SECONDS,
                )
            except RuntimeError as exc:
                logger.warning(
                    "Tesseract OCR 시도 시간 초과 (%s/%s, %.1fs): %s",
                    variant_name,
                    psm_name,
                    OCR_ATTEMPT_TIMEOUT_SECONDS,
                    exc,
                )
                continue

            course_count, average_score = _score_tesseract_text(text)
            attempts.append({
                "name": f"{variant_name}/{psm_name}",
                "text": text,
                "course_count": course_count,
                "average_score": average_score,
                "text_length": len(text),
            })

        for variant in variants.values():
            variant.close()

        duration = time.time() - start_time
        if not attempts:
            return ""

        attempts.sort(
            key=lambda item: (
                item["course_count"],
                item["average_score"],
                item["text_length"],
            ),
            reverse=True,
        )
        selected_attempts = [
            item for item in attempts if item["course_count"] > 0
        ][:OCR_COMBINE_TOP_TEXTS]
        if not selected_attempts:
            selected_attempts = attempts[:1]

        combined_text = _combine_ocr_texts([item["text"] for item in selected_attempts])
        if not combined_text.strip():
            combined_text = selected_attempts[0]["text"]

        best = attempts[0]
        logger.info(
            "Tesseract OCR 실행 완료 (소요시간: %.2fs, best=%s, 과목=%s개, 평균점수=%.1f)",
            duration,
            best["name"],
            best["course_count"],
            best["average_score"],
        )
        logger.debug("Tesseract OCR 완료 — 텍스트 길이: %d자", len(combined_text))
        return combined_text
    except ImportError:
        # OCR_MODE == "tesseract"인데 패키지가 없으면 조용히 넘기지 않고 오류를 발생시킵니다.
        # Mock으로 대체하면 사용자가 "OCR이 됐다"고 착각할 수 있기 때문입니다.
        # 개발 환경에서만 mock fallback이 필요하다면 OCR_MODE를 "mock"으로 설정하세요.
        raise RuntimeError(
            "OCR_MODE=tesseract 로 설정됐지만 Pillow 또는 pytesseract가 설치되지 않았습니다.\n"
            "해결 방법:\n"
            "  1) pip install Pillow pytesseract  # Python 패키지 설치\n"
            "  2) Tesseract 엔진 설치 (README.md 참고)\n"
            "  또는 config.py에서 OCR_MODE = 'mock' 으로 변경하세요."
        )
    except Exception as e:
        logger.exception("Tesseract OCR 실패 — 상세 오류:")
        raise RuntimeError(
            f"OCR 처리 오류: {type(e).__name__}: {str(e)}. "
            "Tesseract 설치 여부와 config.py의 TESSERACT_CMD 경로를 확인하세요."
        )


# ═══════════════════════════════════════════
# 📌 OCR 텍스트 파싱 (gil_track 방식 적용)
# ═══════════════════════════════════════════

OCR_MATCH_THRESHOLD = 70
OCR_EXCLUDED_TERMS = {
    "이수구분", "교과목명", "학점", "성적", "등급", "평점", "년도", "학기",
    "전공", "교양", "일반교양", "공통전선", "공통전필", "전공선택", "전공필수", "기초교양", "신청과목", "신청학점", "평점합계", "평점평균"
}

COURSE_PREFIX_TOKENS = {
    "공동전선", "공통전선", "공동전필", "공통전필",
    "일반선택", "일반교양", "복수전공", "복수전공1", "복수전공2",
    "전공", "전공선택", "전공필수", "필수", "선택", "교양", "기초교양", "교필", "교선",
    "전심", "전기", "부전공", "일선",
}

COURSE_SUFFIX_TOKENS = {"완료"}

@cached(cache=TTLCache(maxsize=1, ttl=3600))
def _get_cached_course_catalog():
    """DB에서 전체 과목과 별칭을 한 번만 가져와서 캐싱합니다."""
    logger.info("과목 카탈로그 메모리 캐싱 중 (gil_track 방식)...")
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # 과목명과 학점 가져오기 (동일 과목 중복 시 학점이 가장 큰 것 우선)
            cur.execute("SELECT course_name, MAX(credits) as credit FROM v_all_courses GROUP BY course_name")
            course_rows = [{"course_name": r["course_name"], "credit": r["credit"] or 3} for r in cur.fetchall()]

            cur.execute("SELECT alias_name, canonical_name FROM course_aliases")
            aliases = cur.fetchall()

        alias_map = {}
        for a in aliases:
            canonical = a["canonical_name"]
            if canonical not in alias_map:
                alias_map[canonical] = []
            alias_map[canonical].append(a["alias_name"])

        return course_rows, alias_map
    except Exception as e:
        logger.exception("DB 과목 카탈로그 로드에 실패했습니다.")
        raise RuntimeError(
            "DB 과목 카탈로그 로드에 실패했습니다. DB 연결과 마이그레이션 상태를 확인하세요."
        ) from e
    finally:
        if conn is not None:
            conn.close()

def clean_text_for_matching(text: str) -> str:
    if not text: return ""
    # 1. 기본적인 기호 변환
    text = text.replace("Ⅰ", "I").replace("Ⅱ", "II").replace("Ⅲ", "III")
    text = text.replace("｜", "I").replace("|", "I")
    
    # 2. 과목명 앞의 쓰레기 데이터(OCR 노이즈) 제거
    # 기호로 시작하는 경우 제거 (예: ".:오디세이" -> "오디세이")
    text = re.sub(r"^[\s.,:;!?'\"\]\[\)\(]+", "", text)
    # 영문+기호로 시작하는 경우 제거 (예: "ere,디지털", "BEAM,머신러닝" -> "디지털", "머신러닝")
    text = re.sub(r"^[a-zA-Z]+[\s.,:;!?'\"\]\[\)\(]+", "", text)
    # 이수구분 키워드가 기호나 영문과 결합되어 잘못 인식된 경우 제거 (예: "복수전공'1Coe자료구조" -> "자료구조")
    text = re.sub(r"^(복수전공\d?|공동전선|공동전필|공통전선|공통전필|일반선택|전공선택|교양필수|일반교양)[a-zA-Z\s.,:;!?'\"\]\[\)\(]*", "", text)
    
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-zA-Z가-힣/+\-]", "", text)
    return text

def compact_text_for_matching(text: str) -> str:
    text = clean_text_for_matching(text)
    text = re.sub(r"[/+\-]", "", text)
    text = text.replace("vriar", "vrar")
    text = text.replace("vr1ar", "vrar")
    return text

def extract_course_candidates(raw_text: str):
    candidates = []
    seen = set()

    for line in raw_text.splitlines():
        line = line.strip()
        if len(line) < 2:
            continue

        normalized_line = clean_text_for_matching(line)
        if not normalized_line:
            continue

        if normalized_line in {clean_text_for_matching(term) for term in OCR_EXCLUDED_TERMS}:
            continue

        # 표 OCR 결과는 열 사이가 공백 여러 개로 분리되는 경우가 많다.
        parts = re.split(r"\s{2,}|\t|,|;", line)
        parts.append(line)

        for part in parts:
            part = part.strip()
            normalized_part = clean_text_for_matching(part)

            if len(normalized_part) < 3:
                continue

            if normalized_part in {clean_text_for_matching(term) for term in OCR_EXCLUDED_TERMS}:
                continue

            if re.fullmatch(r"[0-9.\-/]+", normalized_part):
                continue

            # 이수구분 같은 짧은 행정 용어가 과목 후보로 들어오는 것을 줄인다.
            if not re.search(r"[가-힣a-zA-Z]", normalized_part):
                continue

            if normalized_part not in seen:
                candidates.append({
                    "text": part,
                    "normalized": normalized_part,
                    "original_line": line,
                })
                seen.add(normalized_part)

    return candidates


def _extract_structured_course_rows(raw_text: str, include_score: bool = False) -> list[dict]:
    """
    DB 카탈로그에 없는 교양·공통 과목도 표 형태 OCR에서 보존합니다.

    예:
      공동전선 머신러닝프로그래밍 01 3 최종환 완료 A+
      2024 1 공동전선 인공지능데이터베이스 3 Ao 정일택
    """
    rows: list[dict] = []
    seen: set[str] = set()

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        normalized_line = clean_text_for_matching(stripped)
        if not normalized_line:
            continue
        if any(term in normalized_line for term in {"신청과목", "신청학점", "취득학점", "평점합계", "평점평균"}):
            continue

        tokens = stripped.split()
        if len(tokens) < 2:
            continue

        grade_index = None
        for index, token in enumerate(tokens):
            if GRADE_TOKEN_PATTERN.fullmatch(token) and is_valid_grade(token):
                grade_index = index

        search_end = grade_index if grade_index is not None else len(tokens)
        credit_index = None
        for index in range(search_end - 1, -1, -1):
            if re.fullmatch(r"[1-6]", tokens[index]):
                credit_index = index
                break

        if credit_index is None:
            continue

        name_tokens = tokens[:credit_index]
        while name_tokens and (
            re.fullmatch(r"\d{4}", name_tokens[0])
            or name_tokens[0] in COURSE_PREFIX_TOKENS
            or re.fullmatch(r"\d", name_tokens[0])
        ):
            name_tokens.pop(0)

        while name_tokens and (
            name_tokens[-1] in COURSE_SUFFIX_TOKENS
            or re.fullmatch(r"\d{2}", name_tokens[-1])
        ):
            name_tokens.pop()

        raw_course_name = "".join(name_tokens)
        # 1. 과목명 시작 부분의 쓰레기 기호 제거 (예: ".:오디세이" -> "오디세이")
        raw_course_name = re.sub(r"^[\s.,:;!?'\"\]\[\)\(-]+", "", raw_course_name)
        # 2. 영문+기호 혼합 노이즈 제거 (예: "BEAM,머신러닝" -> "머신러닝")
        raw_course_name = re.sub(r"^[A-Za-z]+[\s.,:;!?'\"\]\[\)\(-]+(?=[가-힣])", "", raw_course_name)
        # 3. 이수구분 노이즈 제거
        raw_course_name = re.sub(r"^(복수전공\d?|공동전선|공동전필|공통전선|공통전필|일반선택|전공선택|전공필수|교양필수|일반교양|기초교양)[A-Za-z\s.,:;!?'\"\]\[\)\(-]*(?=[가-힣])", "", raw_course_name)

        course_name = normalize_course_name(raw_course_name)
        if not course_name:
            continue
            
        # 한글이 포함되지 않은 경우, 정상적인 영문 과목명 패턴이 아니면 쓰레기로 간주
        if not re.search(r"[가-힣]", course_name):
            if not re.fullmatch(r"[a-zA-Z\s]+[0-9]?", course_name):
                continue
        if clean_text_for_matching(course_name) in {
            clean_text_for_matching(term) for term in OCR_EXCLUDED_TERMS
        }:
            continue

        grade = ""
        if grade_index is not None:
            grade = normalize_grade_text(tokens[grade_index])

        item = {
            "course_name": course_name,
            "credits": int(tokens[credit_index]),
            "grade": grade,
        }
        if include_score:
            item["score"] = 75

        if course_name in seen:
            for existing in rows:
                if existing["course_name"] == course_name:
                    if item.get("grade") and not existing.get("grade"):
                        existing["grade"] = item["grade"]
                    if include_score and item.get("score", 0) > existing.get("score", 0):
                        existing["score"] = item["score"]
                    break
            continue

        rows.append(item)
        seen.add(course_name)

    return rows

def find_alias_match(course_name: str, raw_text: str, candidates: list, alias_map: dict):
    aliases = alias_map.get(course_name, [])
    if not aliases:
        return None

    compact_full_text = compact_text_for_matching(raw_text)

    for alias in aliases:
        compact_alias = compact_text_for_matching(alias)

        if compact_alias and compact_alias in compact_full_text:
            for candidate in candidates:
                if compact_alias in compact_text_for_matching(candidate["text"]):
                    return candidate  # Return candidate dict instead of just text
            return {"text": alias, "original_line": raw_text} # Fallback

    return None


def _find_catalog_match_for_text(
    text: str,
    course_rows: list[dict],
    alias_map: dict,
) -> tuple[dict | None, float]:
    """OCR이 한두 글자 틀린 구조화 행도 DB 과목명으로 보정합니다."""
    normalized_text = clean_text_for_matching(text)
    compact_text = compact_text_for_matching(text)
    if not normalized_text:
        return None, 0.0

    best_course = None
    best_score = 0.0

    for course in course_rows:
        course_name = course["course_name"]
        comparison_names = [course_name, *alias_map.get(course_name, [])]

        for comparison_name in comparison_names:
            normalized_course = clean_text_for_matching(comparison_name)
            compact_course = compact_text_for_matching(comparison_name)
            if not normalized_course:
                continue

            if normalized_text == normalized_course or compact_text == compact_course:
                score = 100.0
            else:
                length_gap = abs(len(normalized_course) - len(normalized_text))
                length_limit = max(2, len(normalized_course) // 3)
                ratio_score = fuzz.ratio(normalized_course, normalized_text)
                token_score = fuzz.token_sort_ratio(normalized_course, normalized_text)
                
                # ★ 부분 매칭(partial_ratio)은 OCR 텍스트가 DB 과목명보다 길 때만 허용합니다.
                # (OCR 조각인 "프로그래밍"이 "웹프로그래밍"에 100점으로 매칭되는 가짜 점수 방지)
                if len(normalized_text) >= len(normalized_course):
                    partial_score = fuzz.partial_ratio(normalized_course, normalized_text)
                else:
                    partial_score = 0
                    
                compact_score = fuzz.ratio(compact_course, compact_text)
                if length_gap <= length_limit:
                    score = max(ratio_score, token_score, partial_score, compact_score)
                else:
                    score = max(ratio_score, token_score, compact_score)

            if score > best_score:
                best_score = float(score)
                best_course = course

    return best_course, best_score


def _canonicalize_structured_rows(
    structured_rows: list[dict],
    course_rows: list[dict],
    alias_map: dict,
    include_score: bool = False,
) -> list[dict]:
    """구조화 추출 결과의 과목명을 DB의 canonical 과목명으로 맞춥니다."""
    canonicalized: list[dict] = []

    for item in structured_rows:
        best_course, best_score = _find_catalog_match_for_text(
            item.get("course_name", ""),
            course_rows,
            alias_map,
        )
        if best_course is None or best_score < max(OCR_MATCH_THRESHOLD, 82):
            continue

        source_normalized = clean_text_for_matching(item.get("course_name", ""))
        source_compact = compact_text_for_matching(item.get("course_name", ""))
        matched_names = [best_course["course_name"], *alias_map.get(best_course["course_name"], [])]
        is_exact_or_alias = any(
            source_normalized == clean_text_for_matching(name)
            or source_compact == compact_text_for_matching(name)
            for name in matched_names
        )
        target_normalized = clean_text_for_matching(best_course["course_name"])
        prefix_length = 2 if min(len(source_normalized), len(target_normalized)) >= 6 else 1
        has_same_prefix = (
            bool(source_normalized)
            and bool(target_normalized)
            and source_normalized[:prefix_length] == target_normalized[:prefix_length]
        )
        
        # ★ 점수가 매우 높으면(90점 이상) 앞글자가 조금 달라도 노이즈로 간주하고 매칭 허용
        if not is_exact_or_alias and not has_same_prefix and best_score < 90:
            continue

        mapped = dict(item)
        mapped["course_name"] = best_course["course_name"]
        mapped["credits"] = best_course.get("credit") or mapped.get("credits", 3)
        if include_score:
            mapped["score"] = max(float(mapped.get("score", 0) or 0), round(best_score, 1))
        canonicalized.append(mapped)

    return canonicalized


def _is_substring_of_matched(course_name: str, matched_names: set[str]) -> bool:
    """
    이미 매칭된 더 긴 과목명의 부분 문자열인지 검사합니다.

    예: matched_names에 "머신러닝프로그래밍"이 있을 때
        "머신러닝"은 부분 문자열이므로 True를 반환합니다.
        "디지털신호처리"와 "신호처리"처럼 서로 다른 과목이 잘못 매칭되는 것도 방지합니다.
    """
    compact_name = compact_text_for_matching(course_name)
    normalized_name = clean_text_for_matching(course_name)
    if not compact_name:
        return False

    for matched in matched_names:
        compact_matched = compact_text_for_matching(matched)
        normalized_matched = clean_text_for_matching(matched)
        if compact_matched == compact_name or normalized_matched == normalized_name:
            continue  # 자기 자신은 건너뜁니다
        # 더 긴 과목명 안에 현재 과목명이 포함되어 있으면 중복으로 판단
        if compact_name in compact_matched or normalized_name in normalized_matched:
            return True
    return False


def parse_ocr_text(raw_text: str, include_score: bool = False) -> list[dict]:
    """
    OCR로 추출된 텍스트에서 과목을 검출합니다.

    [중요 수정] 과목명을 길이가 긴 순서대로 먼저 매칭합니다.
    이렇게 하면 "머신러닝프로그래밍"을 먼저 찾아내고,
    그 다음에 "머신러닝"을 찾을 때 이미 매칭된 더 긴 과목명의 부분 문자열이면 건너뜁니다.
    "디지털신호처리"와 "신호처리" 같이 이름이 겹치는 서로 다른 과목도 정확하게 구분합니다.
    """
    try:
        course_rows, alias_map = _get_cached_course_catalog()
    except Exception:
        logger.warning("과목 카탈로그를 불러올 수 없어 OCR 매칭을 건너뜁니다.")
        return []
    if not course_rows:
        return []

    candidates = extract_course_candidates(raw_text)
    normalized_full_text = clean_text_for_matching(raw_text)
    compact_full_text = compact_text_for_matching(raw_text)

    # ★ 핵심 수정: 과목명을 길이가 긴 순서대로 정렬하여 매칭합니다.
    # "머신러닝프로그래밍"(9글자)을 "머신러닝"(4글자)보다 먼저 검사합니다.
    sorted_course_rows = sorted(
        course_rows,
        key=lambda c: len(clean_text_for_matching(c["course_name"])),
        reverse=True,
    )

    detected = []
    matched_course_names: set[str] = set()  # 이미 매칭 확정된 과목명 추적

    for course in sorted_course_rows:
        course_name = course["course_name"]
        normalized_course = clean_text_for_matching(course_name)
        compact_course = compact_text_for_matching(course_name)

        best_score = 0
        best_candidate = None
        alias_match_cand = find_alias_match(course_name, raw_text, candidates, alias_map)

        if alias_match_cand:
            best_score = 97
            best_candidate = alias_match_cand
        elif normalized_course and len(normalized_course) >= 4 and normalized_course in normalized_full_text:
            best_score = 100
            for cand in candidates:
                if normalized_course in cand["normalized"]:
                    best_candidate = cand
                    break
        elif compact_course and len(compact_course) >= 4 and compact_course in compact_full_text:
            best_score = 98
            for cand in candidates:
                if compact_course in compact_text_for_matching(cand["text"]):
                    best_candidate = cand
                    break
        else:
            for candidate in candidates:
                normalized_candidate = candidate["normalized"]
                compact_candidate = compact_text_for_matching(candidate["text"])

                if not normalized_candidate:
                    continue

                length_gap = abs(len(normalized_course) - len(normalized_candidate))
                length_limit = max(2, len(normalized_course) // 3)

                ratio_score = fuzz.ratio(normalized_course, normalized_candidate)
                token_score = fuzz.token_sort_ratio(normalized_course, normalized_candidate)
                
                # ★ 가짜 부분 매칭 방지 (위와 동일)
                if len(normalized_candidate) >= len(normalized_course):
                    partial_score = fuzz.partial_ratio(normalized_course, normalized_candidate)
                else:
                    partial_score = 0
                    
                compact_score = fuzz.ratio(compact_course, compact_candidate)

                if length_gap <= length_limit:
                    score = max(ratio_score, token_score, partial_score, compact_score)
                else:
                    score = max(ratio_score, token_score, compact_score)

                if score > best_score:
                    best_score = score
                    best_candidate = candidate

        best_text = best_candidate["text"] if best_candidate else ""

        course_length = len(normalized_course)
        is_exact_contained = (
            len(normalized_course) >= 4
            and normalized_course in normalized_full_text
        )
        is_compact_contained = (
            len(compact_course) >= 4
            and compact_course in compact_full_text
        )
        is_high_confidence = best_score >= 90
        is_medium_confidence = (
            best_score >= max(OCR_MATCH_THRESHOLD, 82)
            and course_length >= 6
            and clean_text_for_matching(best_text)[:2] == normalized_course[:2]
        )

        if is_exact_contained or is_compact_contained or is_high_confidence or is_medium_confidence:
            # ★ 핵심 수정: 이미 매칭된 더 긴 과목명의 부분 문자열이면 건너뜁니다.
            # 예: "머신러닝프로그래밍"이 이미 매칭됐으면 "머신러닝"은 건너뜁니다.
            # 단, 정확히 해당 과목명이 텍스트에 독립적으로 존재하는 경우는 허용합니다.
            if _is_substring_of_matched(course_name, matched_course_names):
                # 후보 텍스트가 정확히 이 과목명과 일치하는지 확인
                # (예: 텍스트에 "머신러닝"이라는 과목이 별도로 존재하는 경우)
                has_independent_match = False
                if best_candidate:
                    cand_normalized = clean_text_for_matching(best_candidate["text"])
                    cand_compact = compact_text_for_matching(best_candidate["text"])
                    # 후보 텍스트가 이 과목명과 거의 같은 길이여야 독립적 매칭으로 봅니다
                    if (cand_normalized == normalized_course
                        or cand_compact == compact_course
                        or (len(cand_normalized) > 0
                            and abs(len(cand_normalized) - len(normalized_course)) <= 2
                            and fuzz.ratio(cand_normalized, normalized_course) >= 90)):
                        has_independent_match = True

                if not has_independent_match:
                    logger.debug(
                        "부분 문자열 과목 건너뜀: '%s'는 이미 매칭된 더 긴 과목명의 일부입니다.",
                        course_name,
                    )
                    continue

            # 성적 추출 (해당 과목이 발견된 라인에서 성적 패턴 검색)
            extracted_grade = ""
            if best_candidate and best_candidate.get("original_line"):
                line_to_search = best_candidate["original_line"]
                grade_matches = GRADE_TOKEN_PATTERN.findall(line_to_search)
                if grade_matches:
                    # 보통 성적은 라인의 끝부분에 위치하므로 마지막 매칭값을 사용합니다.
                    extracted_grade = normalize_grade_text(grade_matches[-1])

            item = {
                "course_name": course_name,
                "credits": course["credit"],
                "grade": extracted_grade,
            }
            if include_score:
                item["score"] = round(best_score, 1)
            detected.append(item)
            matched_course_names.add(course_name)

    detected.sort(key=lambda item: (-item.get("score", 0), item["course_name"]))

    unique = []
    seen = set()

    for item in detected:
        if item["course_name"] not in seen:
            unique.append(item)
            seen.add(item["course_name"])

    structured_rows = _canonicalize_structured_rows(
        _extract_structured_course_rows(raw_text, include_score=include_score),
        course_rows,
        alias_map,
        include_score=include_score,
    )
    structured_names = {
        compact_text_for_matching(item["course_name"]) for item in structured_rows
    }

    # ★ fuzzy 매칭 결과를 유지하되, 구조화 표에서 발견된 더 긴 과목명의 부분 문자열이면 제거합니다.
    # 예: 표에서 "머신러닝프로그래밍"을 찾았는데 fuzzy가 "머신러닝"을 또 찾은 경우 제거.
    unique = [
        item
        for item in unique
        if compact_text_for_matching(item["course_name"]) in structured_names
        or not any(
            compact_text_for_matching(item["course_name"]) != structured_name
            and compact_text_for_matching(item["course_name"]) in structured_name
            for structured_name in structured_names
        )
    ]

    # 구조화 추출 결과를 기준으로 보충 (fuzzy에서 못 찾은 과목 추가)
    unique_by_name = {item["course_name"]: item for item in unique}
    for item in structured_rows:
        existing = unique_by_name.get(item["course_name"])
        if existing is not None:
            if item.get("grade") and not existing.get("grade"):
                existing["grade"] = item["grade"]
            if include_score and item.get("score", 0) > existing.get("score", 0):
                existing["score"] = item["score"]
            continue

        unique.append(item)
        unique_by_name[item["course_name"]] = item

    logger.info("텍스트 파싱 완료 — %s개 과목 추출", len(unique))
    return unique

def merge_detected_courses(detected_groups: list[list[dict]]) -> list[dict]:
    """여러 페이지의 OCR 결과를 병합합니다. (점수가 더 높은 과목 유지)"""
    course_map = {}

    for detected_courses in detected_groups:
        for course in detected_courses:
            course_name = course["course_name"]
            current = course_map.get(course_name)

            if current is None or course["score"] > current.get("score", 0):
                course_map[course_name] = course

    merged = list(course_map.values())
    merged.sort(key=lambda item: (-item.get("score", 0), item["course_name"]))
    return merged
