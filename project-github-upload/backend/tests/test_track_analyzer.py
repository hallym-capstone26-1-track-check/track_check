from __future__ import annotations

from services.track_analyzer import analyze_tracks, filter_passing_courses


def _course(name: str, credits: int = 3, grade: str = "A+") -> dict:
    return {"course_name": name, "credits": credits, "grade": grade}


def test_sw_bigdata_ai_track_completed():
    result = analyze_tracks("소프트웨어학부", [_course("데이터사이언스기초"), _course("데이터베이스기초"), _course("인공지능기초"), _course("머신러닝")])
    assert "빅데이터AI융합 트랙" in set(result["completed_tracks"])


def test_total_min_courses_track_can_be_completed_automatically():
    """광고홍보학과 표준전공트랙은 총 6과목 이상 조건을 자동 판별해야 한다."""
    result = analyze_tracks("광고홍보학과", [_course("커뮤니케이션입문"), _course("광고와사회"), _course("광고개론"), _course("홍보개론"), _course("소비자행동원론"), _course("국제마케팅커뮤니케이션")])
    target = next(t for t in result["track_results"] if t["track_name"] == "표준전공트랙")
    assert target["analysis_mode"] == "auto"
    assert target["unsupported_rule_types"] == []
    assert target["is_completed"] is True


def test_retake_and_f_np_stats_are_separated():
    courses = [_course("데이터사이언스기초", grade="F"), _course("데이터사이언스기초", grade="B+"), _course("인공지능기초", grade="NP"), _course("인공지능기초", grade="A+"), _course("머신러닝", grade="F"), _course("빅데이터개론", grade="A0")]
    passing, stats = filter_passing_courses(courses, return_stats=True)
    assert stats["original_course_count"] == 6
    assert stats["unique_course_count"] == 4
    assert stats["retake_removed_count"] == 2
    assert stats["failed_removed_count"] == 1
    assert stats["passing_course_count"] == 3
    assert {course["course_name"] for course in passing} == {"데이터사이언스기초", "인공지능기초", "빅데이터개론"}


def test_analyze_result_excludes_abolished_courses_from_missing_recommendations():
    """폐지 과목은 부족 과목/보완 추천 후보에서 제외해야 한다."""
    result = analyze_tracks("인공지능융합학부", [_course("로봇개론")])
    target = next(t for t in result["track_results"] if t["track_name"] == "로봇인공지능트랙")
    assert "인공지능시스템프로그래밍" not in target["missing_courses"]
    assert all(
        c["course_name"] != "인공지능시스템프로그래밍"
        for c in target["missing_course_details"]
    )



def test_additional_required_courses_is_minimum_not_candidate_count():
    """미이수 후보 과목 수와 실제 추가 필요 과목 수를 분리해야 한다."""
    result = analyze_tracks("소프트웨어학부", [_course("웹프로그래밍")])
    target = next(t for t in result["track_results"] if t["track_name"] == "빅데이터AI융합 트랙")

    # 빅데이터AI융합 트랙은 각 모듈 2과목 이상 조건이다.
    # 후보 과목은 모듈 전체 미이수 과목이라 여러 개일 수 있지만,
    # 실제 충족까지 필요한 최소 과목 수는 4개(빅데이터 2 + 인공지능 2)로 계산되어야 한다.
    assert target["missing_candidate_count"] > target["additional_required_courses"]
    assert target["additional_required_courses"] == 4


def test_politics_module_group_min_courses_total_auto():
    """정치행정학과의 'a,b,c 중 한 과목 이상 수강' 조건은 자동 판별되어야 한다."""
    result = analyze_tracks("정치행정학과", [_course("행정학")])
    target = next(t for t in result["track_results"] if t["track_name"] == "일반행정트랙")

    assert target["analysis_mode"] == "auto"
    assert target["unsupported_rule_types"] == []
    assert target["is_completed"] is True
    assert target["rule_results"][0]["rule_type"] == "module_group_min_courses_total"

    result = analyze_tracks("정치행정학과", [_course("정치학")])
    target = next(t for t in result["track_results"] if t["track_name"] == "일반행정트랙")
    assert target["is_completed"] is False
