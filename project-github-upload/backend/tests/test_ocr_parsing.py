from __future__ import annotations

from schemas.analyze_schemas import CourseInput
from services.ocr_service import parse_ocr_text
from services.track_analyzer import filter_passing_courses


def _course_map(courses: list[dict]) -> dict[str, dict]:
    return {course["course_name"]: course for course in courses}


def test_parse_ocr_text_handles_grade_history_format_with_professor_after_grade():
    """이미지 1: 이수학기별 성적내역 형식도 과목명/학점/성적만 추출해야 한다."""
    raw_text = """
    년도 학기 이수구분 교과목명 학점 성적 담당교수 비고
    2024 1 공동전선 인공지능데이터베이스 3 Ao 정일택
    2024 1 일반선택 디지털리터러시의시작 1 P 특별시험
    신청학점 19 취득학점 19 평점평균 4.50
    """

    courses = parse_ocr_text(raw_text)
    by_name = _course_map(courses)

    assert by_name["인공지능데이터베이스"] == {
        "course_name": "인공지능데이터베이스",
        "credits": 3,
        "grade": "A0",
    }
    assert "디지털리터러시의시작" not in by_name
    assert len(courses) == 1


def test_unknown_course_is_excluded_from_final_courses():
    """
    DB/기준 데이터에 없는 과목은 OCR이 읽었더라도
    최종 분석 대상 courses에는 포함하지 않는다.
    """
    text = "디지털리터러시의시작 3 A+"

    courses = parse_ocr_text(text)
    course_names = [course["course_name"] for course in courses]

    assert "디지털리터러시의시작" not in course_names


def test_parse_ocr_text_handles_current_course_list_format_with_section_number():
    """이미지 2: 수강내역 형식의 분반/교수/완료 값을 제거해야 한다."""
    raw_text = """
    교과목명 분반 학점 담당교수 기말강의평가 성적조회
    공동전선 머신러닝프로그래밍 01 3 최종환 완료 A+
    공동전선 웨어러블센서와기계학습 01 3 정인철 완료 BO
    복수전공1 C프로그래밍 03 3 김은주 완료 A+
    일반선택 오디세이세미나3 15 1 정인철 완료 P
    일반교양 종교문화사책 3 성요례 A+
    필수 오디세이세미나1 1 원동욱 P
    """

    courses = parse_ocr_text(raw_text)
    by_name = _course_map(courses)

    assert by_name["머신러닝프로그래밍"]["credits"] == 3
    assert by_name["머신러닝프로그래밍"]["grade"] == "A+"

    assert by_name["웨어러블센서와기계학습"]["credits"] == 3
    assert by_name["웨어러블센서와기계학습"]["grade"] == "B0"

    assert "C프로그래밍" not in by_name
    assert by_name["웹프로그래밍"]["credits"] == 3
    assert by_name["웹프로그래밍"]["grade"] == "A+"

    assert "오디세이세미나3" not in by_name

    # "일반교양", "필수"는 과목명이 아니라 이수구분이므로 제거되어야 합니다.
    assert "종교문화사책" not in by_name
    assert "오디세이세미나1" not in by_name
    assert len(courses) == 3


def test_course_input_normalizes_ocr_grade_typo():
    """분석 API 스키마에서도 Ao/AO/Bo 같은 OCR 오인식 성적을 보정해야 한다."""
    course = CourseInput(course_name="인공지능데이터베이스", credits=3, grade="Ao")
    assert course.grade == "A0"


def test_parse_ocr_text_treats_dash_grade_as_empty_grade():
    """Mock 성적표의 '-' 성적은 성적 미입력으로 추출되어야 한다."""
    raw_text = """
    교과목명 학점 성적
    데이터베이스기초 3 -
    머신러닝 3 -
    """

    courses = parse_ocr_text(raw_text)
    by_name = _course_map(courses)

    assert by_name["데이터베이스기초"] == {
        "course_name": "데이터베이스기초",
        "credits": 3,
        "grade": "",
    }
    assert by_name["머신러닝"] == {
        "course_name": "머신러닝",
        "credits": 3,
        "grade": "",
    }


def test_parse_ocr_text_canonicalizes_structured_ocr_typo():
    raw_text = "\uc778\uacf5\uc9c0\ub2a5\uae30\uc870 3 P"

    courses = parse_ocr_text(raw_text)
    by_name = _course_map(courses)

    assert "\uc778\uacf5\uc9c0\ub2a5\uae30\ucd08" in by_name
    assert "\uc778\uacf5\uc9c0\ub2a5\uae30\uc870" not in by_name


def test_filter_passing_courses_uses_normalized_grade_for_retake_priority():
    """서비스 레이어 직접 호출에서도 AO가 A0로 처리되어 재수강 최고 성적 선택이 깨지지 않아야 한다."""
    courses = [
        {"course_name": "인공지능기초", "credits": 3, "grade": "AO"},
        {"course_name": "인공지능기초", "credits": 3, "grade": "B+"},
    ]

    passing = filter_passing_courses(courses)
    assert len(passing) == 1
    assert passing[0]["grade"] == "A0"
