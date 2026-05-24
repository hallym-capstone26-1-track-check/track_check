from __future__ import annotations

from services.test_case_service import get_generated_case, get_generated_scenarios
from services.track_analyzer import analyze_tracks


def test_generated_test_cases_cover_all_departments_and_tracks():
    """DB 기준 30개 학과 / 110개 트랙에 대해 2개씩 테스트 케이스가 생성되어야 한다."""
    scenarios = get_generated_scenarios()
    assert len(scenarios) == 220
    assert len({s["dept"] for s in scenarios}) == 30
    assert len({s["track_id"] for s in scenarios}) == 110

    for track_id in {s["track_id"] for s in scenarios}:
        kinds = {s["kind"] for s in scenarios if s["track_id"] == track_id}
        assert kinds == {"complete", "missing"}


def test_complete_generated_cases_finish_auto_tracks_or_mark_manual_review():
    """충족형은 자동 판별 트랙이면 완료되어야 하고, 수동검토 트랙이면 적어도 분석 결과가 깨지지 않아야 한다."""
    for scenario in get_generated_scenarios():
        if scenario["kind"] != "complete":
            continue

        case = get_generated_case(scenario["key"])
        result = analyze_tracks(case["dept"], case["courses"])
        target = next(t for t in result["track_results"] if t["track_id"] == case["track_id"])

        if target["analysis_mode"] == "auto" and not target["manual_review_items"] and not target["unsupported_rule_types"]:
            assert target["is_completed"] is True, (case["dept"], case["track_name"])
        else:
            assert target["completion_rate"] >= 0


def test_missing_generated_cases_are_not_completed():
    """부족형 케이스는 해당 트랙이 완료 처리되면 안 된다."""
    for scenario in get_generated_scenarios():
        if scenario["kind"] != "missing":
            continue

        case = get_generated_case(scenario["key"])
        result = analyze_tracks(case["dept"], case["courses"])
        target = next(t for t in result["track_results"] if t["track_id"] == case["track_id"])
        assert target["is_completed"] is False, (case["dept"], case["track_name"])
