"""
🌟 track_recommender.py — 트랙 후보 산정 로직

후보 산정 기준은 MVP 기준으로 단순하게 유지합니다.
- 이수율이 높을수록 우선 후보로 정렬
- 추가로 필요한 과목 수가 적을수록 우선 후보로 정렬
- 수동 확인이 필요한 트랙은 약간 감점
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_incomplete_tracks(track_results: list[dict]) -> list[dict]:
    """
    미완료 트랙 전체를 화면 표시용 목록으로 변환합니다.

    recommended_tracks는 "현재 이수 내역과 실제로 겹치는 추천 후보"만 담고,
    이 함수의 결과는 0% 트랙까지 포함한 "전체 미완료 트랙"으로 사용합니다.
    """
    incomplete_tracks = [t for t in track_results if not t.get("is_completed", False)]

    scored_tracks = []
    for track in incomplete_tracks:
        score = _calculate_recommendation_score(track)
        additional_required = _get_additional_required_courses(track)
        missing_candidate_count = track.get(
            "missing_candidate_count",
            len(track.get("missing_courses", [])),
        )
        scored_tracks.append({
            "track_id": track.get("track_id", ""),
            "track_name": track.get("track_name", ""),
            "completion_rate": track.get("completion_rate", 0.0),
            # 기존 프론트 호환 필드입니다. 이제 의미는 '추가 필요 과목 수'입니다.
            "remaining_courses": additional_required,
            "additional_required_courses": additional_required,
            "missing_candidate_count": missing_candidate_count,
            # missing_courses는 후보 문구 숫자가 아니라 화면 표시용 후보 목록입니다.
            "missing_courses": track.get("missing_courses", []),
            # 정렬 후 1순위/2순위 이하 문구를 다르게 만들기 위해 원본 트랙을 잠시 보관합니다.
            "_source_track": track,
            "_score": score,
        })

    scored_tracks.sort(key=lambda x: x["_score"], reverse=True)

    result = []
    for index, item in enumerate(scored_tracks, start=1):
        source_track = item.pop("_source_track")
        # 전체 미완료 목록에서는 rank를 내려주지 않습니다.
        # rank는 실제 추천 후보(recommended_tracks)에서만 의미가 있습니다.
        item["reason"] = _generate_recommendation_reason(source_track, rank=index)
        result.append({k: v for k, v in item.items() if k != "_score"})

    logger.info("미완료 트랙 %s개 생성 완료", len(result))
    return result


def recommend_tracks(track_results: list[dict], top_n: int = 3) -> list[dict]:
    """미완료 트랙 중 현재 이수 내역과 실제로 겹치는 후보 트랙만 산정합니다."""
    incomplete_tracks = build_incomplete_tracks(track_results)
    positive_tracks = [
        track for track in incomplete_tracks
        if float(track.get("completion_rate", 0.0) or 0.0) > 0
    ]

    recommendations = []
    for index, item in enumerate(positive_tracks[:top_n], start=1):
        recommendation = dict(item)
        source_track = next(
            t for t in track_results
            if t.get("track_id", "") == recommendation.get("track_id", "")
        )
        recommendation["rank"] = index
        recommendation["reason"] = _generate_recommendation_reason(source_track, rank=index)
        recommendations.append(recommendation)

    logger.info("후보 트랙 %s개 생성 완료", len(recommendations))
    return recommendations


def _get_additional_required_courses(track: dict) -> int:
    """
    후보 문구에 사용할 '추가 필요 과목 수'를 반환합니다.

    예전에는 len(missing_courses)를 사용했는데, 이 값은 '후보 과목 전체'라서
    실제로 필요한 과목 수보다 크게 보일 수 있었습니다.
    """
    value = track.get("additional_required_courses")
    if value is None:
        return len(track.get("missing_courses", []))
    return max(0, int(value))


def _calculate_recommendation_score(track: dict) -> float:
    completion_rate = track.get("completion_rate", 0.0)
    additional_required = _get_additional_required_courses(track)
    manual_penalty = 0.15 if track.get("analysis_mode") in {"partial", "manual"} else 0.0

    # 추가 필요 과목이 적을수록 점수를 높게 줍니다.
    remaining_score = max(0.0, 1.0 - (additional_required / 10))
    score = (completion_rate * 0.7) + (remaining_score * 0.3) - manual_penalty
    return round(score, 4)


def _generate_recommendation_reason(track: dict, rank: int = 1) -> str:
    """
    후보 선정 근거 문구를 만듭니다.

    - 이수율이 0%인 트랙은 후보 트랙 탭에 보이더라도 일반 카드처럼 보이도록 문구를 비웁니다.
    - 이수율이 0%를 초과한 후보 중 1순위에만 "현재 이수 내역과 가장 가까운 후보" 문구를 사용합니다.
    - 2순위 이하에는 "이수 현황 기준 검토 후보"라고 표시해서 모든 카드가 1등처럼 보이는 문제를 막습니다.
    """
    completion_rate = float(track.get("completion_rate", 0.0) or 0.0)

    # 사용자가 전혀 걸친 과목이 없는 0% 트랙은 후보 강조 문구를 붙이지 않습니다.
    # 프론트에서는 이 값이 빈 문자열이면 일반 카드처럼 표시하면 됩니다.
    if completion_rate <= 0:
        return ""

    additional_required = _get_additional_required_courses(track)
    satisfied_rules = track.get("satisfied_rules", 0)
    total_rules = track.get("total_rules", 0)
    manual_needed = bool(track.get("manual_review_items") or track.get("unsupported_rule_types"))

    if rank == 1:
        prefix = "현재 이수 내역과 가장 가까운 후보입니다."
    else:
        prefix = "이수 현황 기준 검토 후보입니다."

    reason = (
        f"{prefix}\n"
        f"전체 판별 기준 {total_rules}개 중 {satisfied_rules}개를 충족했으며, "
        f"추가 필요 과목은 {additional_required}개입니다."
    )
    if manual_needed:
        reason += "\n단, 일부 조건은 수동 확인이 필요합니다."
    return reason
