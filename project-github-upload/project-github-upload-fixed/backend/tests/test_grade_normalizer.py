import pytest
from services.grade_normalizer import normalize_grade_text

def test_normalize_grade_text():
    # Valid grades
    assert normalize_grade_text("A+") == "A+"
    assert normalize_grade_text("A0") == "A0"
    assert normalize_grade_text("B+") == "B+"
    assert normalize_grade_text("F") == "F"
    assert normalize_grade_text("P") == "P"
    assert normalize_grade_text("NP") == "NP"

    # OCR mistakes - O instead of 0
    assert normalize_grade_text("AO") == "A0"
    assert normalize_grade_text("BO") == "B0"
    assert normalize_grade_text("CO") == "C0"
    assert normalize_grade_text("DO") == "D0"

    # OCR mistakes - lowercase
    assert normalize_grade_text("a+") == "A+"
    assert normalize_grade_text("f") == "F"

    # Empty
    assert normalize_grade_text("") == ""
    assert normalize_grade_text(None) == ""
