import pytest
from services.privacy_service import sanitize_for_logging

def test_sanitize_for_logging_dict():
    data = {
        "student_id": "20241234",
        "name": "홍길동",
        "course_name": "인공지능",
        "grade": "A+",
        "phone": "010-1234-5678"
    }
    sanitized = sanitize_for_logging(data)
    assert sanitized["student_id"] == "[REDACTED]"
    assert sanitized["name"] == "[REDACTED]"
    assert sanitized["phone"] == "[REDACTED]"
    # 과목명/성적도 로그에는 남기지 않습니다.
    assert sanitized["course_name"] == "[REDACTED]"
    assert sanitized["grade"] == "[REDACTED]"

def test_sanitize_for_logging_list():
    data = [
        {"student_id": "20241234", "name": "홍길동"},
        {"student_id": "20245678", "name": "김철수"}
    ]
    sanitized = sanitize_for_logging(data)
    assert sanitized[0]["student_id"] == "[REDACTED]"
    assert sanitized[1]["student_id"] == "[REDACTED]"
    assert sanitized[0]["name"] == "[REDACTED]"
    assert sanitized[1]["name"] == "[REDACTED]"

def test_sanitize_for_logging_nested():
    data = {
        "metadata": {
            "type": "test"
        },
        "student_id": "20241234"
    }
    sanitized = sanitize_for_logging(data)
    assert sanitized["student_id"] == "[REDACTED]"
    assert sanitized["metadata"]["type"] == "test"


def test_sanitize_for_logging_redacts_nested_courses():
    data = {
        "dept_name": "소프트웨어학부",
        "courses": [
            {"course_name": "인공지능기초", "credits": 3, "grade": "A+", "match_score": 97.0}
        ],
    }
    sanitized = sanitize_for_logging(data)
    assert sanitized["dept_name"] == "소프트웨어학부"
    assert sanitized["courses"][0]["course_name"] == "[REDACTED]"
    assert sanitized["courses"][0]["credits"] == "[REDACTED]"
    assert sanitized["courses"][0]["grade"] == "[REDACTED]"
    assert sanitized["courses"][0]["match_score"] == "[REDACTED]"
