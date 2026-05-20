from __future__ import annotations

from services.course_normalizer import normalize_course_name


def test_normalizer_fixes_safe_spacing_and_unicode_only():
    """띄어쓰기/이상한 공백/전각 문자처럼 표기만 다른 경우는 공식 과목명으로 맞춘다."""
    assert normalize_course_name("인공 지능기초") == "인공지능기초"
    assert normalize_course_name("인 공지능 기 초") == "인공지능기초"
    assert normalize_course_name("인공지능\u3000기초") == "인공지능기초"
    assert normalize_course_name("VR／AR／게임 제작기초") == "VR/AR/게임제작기초"


def test_normalizer_unifies_roman_number_variants():
    """Ⅰ/I/ⅰ/１처럼 같은 번호를 뜻하는 표기는 같은 과목으로 본다."""
    assert normalize_course_name("무기화학Ⅰ") == "무기화학Ⅰ"
    assert normalize_course_name("무기화학I") == "무기화학Ⅰ"
    assert normalize_course_name("무기화학ⅰ") == "무기화학Ⅰ"
    assert normalize_course_name("무기화학１") == "무기화학Ⅰ"


def test_normalizer_does_not_guess_broader_or_similar_names():
    """비슷해 보인다는 이유만으로 다른 공식 과목명으로 자동 추측하면 안 된다."""
    assert normalize_course_name("인공지능") == "인공지능"
    assert normalize_course_name("데이터베이스") == "데이터베이스"
    assert normalize_course_name("웹") == "웹"
