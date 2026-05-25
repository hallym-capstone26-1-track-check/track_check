"""
📊 track_analyzer.py — 트랙 이수 판별 + 모듈 현황 (트랙 조건 기준)

💡 모듈 현황 표시 방식:
   - "전체 과목 대비 이수" 가 아니라
   - "해당 트랙의 조건 대비 이수" 로 표시
   - 예: 의료인공지능 모듈 조건이 "3학점 이상" → 3/3학점(충족) or 0/3학점(미충족)
"""
from __future__ import annotations

import logging
from typing import Optional  # get_department_data 반환 타입 힌트에서 사용

from services.course_normalizer import normalize_course_name, normalize_course_records
from services.course_note_service import build_course_detail
from services.grade_normalizer import normalize_grade_text
from services.data_loader import load_track_rules

logger = logging.getLogger(__name__)

FAILING_GRADES: set[str] = {"F", "NP"}
GRADE_PRIORITY: dict[str, int] = {
    "A+": 12, "A0": 11, "A": 11,
    "B+": 10, "B0": 9, "B": 9,
    "C+": 8, "C0": 7, "C": 7,
    "D+": 6, "D0": 5, "D": 5,
    "P": 4, "F": 1, "NP": 0, "": 3,
}

SUPPORTED_RULE_TYPES: set[str] = {
    "required_courses_all", "module_min_courses", "module_all_courses",
    "module_min_credits", "track_min_credits", "total_min_courses",
    "module_group_min_courses_total", "module_course_indexes_all",
}

def get_department_data(dept_name: str) -> Optional[dict]:
    data = load_track_rules()
    for college in data.get("colleges", []):
        for dept in college.get("departments", []):
            if dept["dept_name"] == dept_name:
                return dept
    return None


# ═══════════════════════════════════════════
# F학점/NP 필터링 + 재수강 처리
# ═══════════════════════════════════════════

def _sum_credits(courses: list[dict]) -> int:
    """과목 리스트의 학점 합계를 안전하게 계산합니다."""
    total = 0
    for course in courses:
        try:
            total += int(course.get("credits", 0) or 0)
        except (TypeError, ValueError):
            # schema에서 1차 검증하지만, 서비스 레이어에서도 방어적으로 처리합니다.
            continue
    return total


def filter_passing_courses(
    courses: list[dict],
    return_stats: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """
    F/NP 제거, 재수강 시 최고 성적만 유지합니다.

    return_stats=True이면 프론트 표시용 통계도 함께 반환합니다.
    - retake_removed_count: 재수강 중복으로 제외된 기록 수
    - failed_removed_count: 최고 성적 기준으로도 F/NP라 제외된 과목 수
    """
    best: dict[str, dict] = {}
    for course in courses:
        name = course.get("course_name", "")
        grade = normalize_grade_text(course.get("grade", ""))
        pri = GRADE_PRIORITY.get(grade, 3)

        # 서비스 레이어로 직접 들어온 데이터도 성적 표기를 정리합니다.
        # 예: AO -> A0. /analyze API는 schema에서 한 번 더 보정하지만,
        # 테스트나 내부 호출까지 안전하게 처리하기 위한 방어 코드입니다.
        normalized_course = dict(course)
        normalized_course["grade"] = grade

        if name in best:
            old_grade = normalize_grade_text(best[name].get("grade", ""))
            if pri > GRADE_PRIORITY.get(old_grade, 3):
                best[name] = normalized_course
        else:
            best[name] = normalized_course

    result = []
    failed_removed = 0
    for name, course in best.items():
        grade = normalize_grade_text(course.get("grade", ""))
        if grade in FAILING_GRADES:
            failed_removed += 1
            continue
        result.append(course)

    retake_removed = len(courses) - len(best)
    if failed_removed > 0:
        logger.info("F/NP 과목 %s개 제외", failed_removed)
    if retake_removed > 0:
        logger.info("재수강 중복 기록 %s개 정리", retake_removed)

    stats = {
        "original_course_count": len(courses),
        "unique_course_count": len(best),
        "passing_course_count": len(result),
        "retake_removed_count": retake_removed,
        "failed_removed_count": failed_removed,
        "filtered_count": retake_removed + failed_removed,
    }
    if return_stats:
        return result, stats
    return result


# ═══════════════════════════════════════════
# 메인 분석
# ═══════════════════════════════════════════

def analyze_tracks(dept_name: str, student_courses: list[dict]) -> dict:
    dept_data = get_department_data(dept_name)
    if dept_data is None:
        return {
            "dept_name": dept_name, "track_results": [],
            "completed_tracks": [], "module_results": [],
            "error": f"'{dept_name}' 학과를 찾을 수 없습니다. 정확한 학과명을 입력해주세요.",
        }

    normalized = normalize_course_records(student_courses)
    passing, filter_stats = filter_passing_courses(normalized, return_stats=True)

    # 제출 학점과 실제 판별에 쓰인 인정 학점을 분리합니다.
    # F/NP, 재수강 중복 제거가 있으면 두 값이 달라질 수 있습니다.
    submitted_credits = _sum_credits(normalized)
    recognized_credits = _sum_credits(passing)
    credit_summary = {
        "submitted_credits": submitted_credits,
        "recognized_credits": recognized_credits,
        "excluded_credits": max(0, submitted_credits - recognized_credits),
    }

    student_names: set[str] = {c["course_name"] for c in passing}
    module_stats = _calc_module_stats(dept_data, passing)

    # 트랙 분석
    track_results = []
    completed_tracks = []
    for track in dept_data.get("tracks", []):
        r = _analyze_single_track(track, student_names, module_stats)
        track_results.append(r)
        if r["is_completed"]:
            completed_tracks.append(r["track_name"])

    # 학과 전체 필수 조건(global_note)을 추가 확인 항목으로 삽입
    # "이수"가 포함된 경우만 사용자 노출 조건으로 처리 (내부 개발 메모 제외)
    global_note = dept_data.get("global_note", "").strip()
    if global_note and "이수" in global_note:
        global_note_rule = {
            "rule_type": "raw_text_requirement",
            "description": "학과 필수 교과목 별도 이수",
            "satisfied": False,
            "current_value": 0,
            "required_value": 0,
            "shortage_count": 0,
            "shortage_credits": 0,
            "missing_courses": [],
            "remaining_courses": [],
            "all_courses": [],
            "taken_courses": [],
            "evaluation_status": "manual_review",
            "note": global_note,
            "manual_review_items": ["학과 필수 교과목 별도 이수"],
            "missing_course_details": [],
            "taken_course_details": [],
            "remaining_course_details": [],
            "all_course_details": [],
        }
        for r in track_results:
            r["rule_results"].append(global_note_rule)

    # 모듈 현황 — 트랙 조건 기준으로
    module_results = _calc_module_results_by_track(dept_data, module_stats)

    # F/NP 필터링 + 재수강 정리 정보
    filtered_info = {}
    if filter_stats["filtered_count"] > 0:
        messages = []
        if filter_stats["retake_removed_count"] > 0:
            messages.append(f"재수강 중복 {filter_stats['retake_removed_count']}건을 정리했습니다")
        if filter_stats["failed_removed_count"] > 0:
            messages.append(f"F/NP {filter_stats['failed_removed_count']}개 과목을 이수 미완료로 처리했습니다")
        filtered_info = {
            **filter_stats,
            "message": ", ".join(messages) + ".",
        }

    return {
        "dept_name": dept_name,
        "track_results": track_results,
        "completed_tracks": completed_tracks,
        "module_stats": module_stats,
        "module_results": module_results,
        "filtered_info": filtered_info,
        "credit_summary": credit_summary,
    }


# ═══════════════════════════════════════════
# 모듈 통계
# ═══════════════════════════════════════════

def _calc_module_stats(dept_data: dict, student_courses: list[dict]) -> dict:
    student_names = {c["course_name"] for c in student_courses}
    credit_map = {c["course_name"]: c.get("credits", 0) for c in student_courses}
    stats = {}
    for m in dept_data.get("modules", []):
        mk = m["module_key"]
        all_courses = [normalize_course_name(c["course_name"]) for c in m.get("courses", [])]
        mod_credits = {normalize_course_name(c["course_name"]): c.get("credits", 0) for c in m.get("courses", [])}

        # 과목별 비고/학점 상세 정보 수집
        # - course_notes: 기존 프론트 호환을 위한 {과목명: 비고 원문}
        # - course_note_details: 새 프론트용 {과목명: note_type/warning_level 포함 메타데이터}
        # - all_course_details: 과목 칩 렌더링에 바로 쓸 수 있는 상세 리스트
        course_notes = {}
        course_note_details = {}
        all_course_details = []
        for c in m.get("courses", []):
            cname = normalize_course_name(c["course_name"])
            note = c.get("note", "") or c.get("remark", "") or ""
            credits = c.get("credits", 0)
            detail = build_course_detail(cname, credits, note)
            all_course_details.append(detail)
            if detail["has_note"]:
                course_notes[cname] = detail["note"]
                course_note_details[cname] = detail

        taken = [c for c in all_courses if c in student_names]
        taken_cr = sum(mod_credits.get(c, credit_map.get(c, 3)) for c in taken)
        total_cr = sum(mod_credits.values())
        stats[mk] = {
            "module_name": m.get("module_name", ""),
            "taken_courses": taken, "taken_count": len(taken), "taken_credits": taken_cr,
            "all_courses": all_courses, "total_courses": len(all_courses), "total_credits": total_cr,
            "course_credits": mod_credits,
            "course_notes": course_notes,
            "course_note_details": course_note_details,
            "all_course_details": all_course_details,
        }
    return stats


def _build_course_detail_map(module_stats: dict) -> dict[str, dict]:
    """모든 모듈의 과목 상세 정보를 {과목명: 상세 dict} 형태로 모읍니다."""
    detail_map: dict[str, dict] = {}
    for st in module_stats.values():
        for detail in st.get("all_course_details", []):
            name = detail.get("course_name", "")
            if name and name not in detail_map:
                detail_map[name] = detail
    return detail_map


def _details_for_courses(course_names: list[str], detail_map: dict[str, dict]) -> list[dict]:
    """과목명 리스트를 프론트 렌더링용 상세 과목 리스트로 변환합니다."""
    details = []
    for name in course_names:
        detail = detail_map.get(name)
        if detail is None:
            # 학생 입력 과목이 기준 데이터에 없는 경우에도 응답 구조는 유지합니다.
            detail = build_course_detail(name, 0, "")
        details.append(detail)
    return details


def _filter_unrecommended_courses(course_names: list[str], detail_map: dict[str, dict]) -> list[str]:
    """화면의 보완/추천 후보에서 폐지 과목은 제외합니다."""
    result = []
    for name in course_names:
        detail = detail_map.get(name, {})
        if detail.get("note_type") == "abolished":
            continue
        result.append(name)
    return result


def _estimate_min_course_count_for_credits(
    shortage_credits: int,
    candidate_courses: list[str],
    course_credits: dict[str, int],
) -> int:
    """
    부족 학점을 채우기 위해 최소 몇 과목이 더 필요한지 추정합니다.

    - 보통 한림대 전공 과목은 3학점이 많지만, 러시아어처럼 4학점 과목도 있습니다.
    - 그래서 단순히 `부족 학점 / 3`으로 계산하지 않고,
      후보 과목의 실제 학점을 큰 순서대로 더해 최소 과목 수를 구합니다.
    - 후보 학점 정보가 없으면 안전하게 3학점으로 계산합니다.
    """
    if shortage_credits <= 0:
        return 0

    credits = sorted(
        [max(1, int(course_credits.get(course, 3))) for course in candidate_courses],
        reverse=True,
    )
    if not credits:
        return 0

    total = 0
    count = 0
    for credit in credits:
        total += credit
        count += 1
        if total >= shortage_credits:
            return count
    return count


def _aggregate_additional_required_courses(rule_results: list[dict]) -> int:
    """
    추천 문구에 쓸 '추가 필요 과목 수'를 계산합니다.

    중요 포인트:
    - missing_courses는 화면에 보여줄 '미이수 후보 과목 전체'입니다.
      예: 4과목짜리 모듈에서 2과목 이상 조건이면 후보는 4개일 수 있습니다.
    - additional_required_courses는 조건 충족까지 필요한 '최소 과목 수'입니다.
      위 예시에서는 4가 아니라 2가 되어야 합니다.

    여러 규칙이 겹치는 트랙에서는 과대 계산을 막기 위해
    '필수 과목 부족 수', '모듈별 부족 수 합계', '트랙 전체 부족 수' 중 가장 큰 값을 사용합니다.
    완벽한 시간표/대체과목 최적화는 아니지만, MVP 추천 문구에는 이 방식이 가장 안전합니다.
    """
    required_shortage = 0
    module_shortage_sum = 0
    whole_track_shortage = 0

    for result in rule_results:
        if result.get("satisfied"):
            continue
        if result.get("evaluation_status") != "supported":
            continue

        count = max(0, int(result.get("shortage_count", 0)))
        rule_type = result.get("rule_type", "")

        if rule_type == "required_courses_all":
            required_shortage += count
        elif rule_type in {"module_min_courses", "module_all_courses", "module_min_credits"}:
            module_shortage_sum += count
        elif rule_type in {"total_min_courses", "track_min_credits", "module_group_min_courses_total"}:
            whole_track_shortage = max(whole_track_shortage, count)
        else:
            whole_track_shortage = max(whole_track_shortage, count)

    return max(required_shortage, module_shortage_sum, whole_track_shortage)


# ═══════════════════════════════════════════
# 모듈 현황 — 트랙 조건 기준
# ═══════════════════════════════════════════

def _calc_module_results_by_track(dept_data: dict, module_stats: dict) -> list[dict]:
    """
    각 모듈별로, 해당 모듈이 포함된 트랙의 조건을 기준으로 현황을 표시.
    
    예: 의료인공지능 모듈(c)의 조건이 module_min_credits=3 이면
        → required: 3학점, current: 6학점(이수), 충족 여부 표시
    """
    results = []
    # 모듈별로 어떤 조건이 적용되는지 수집
    module_conditions: dict[str, list[dict]] = {}

    for track in dept_data.get("tracks", []):
        for rule in track.get("rules", []):
            mk = rule.get("module_key", "")
            if mk and mk in module_stats:
                if mk not in module_conditions:
                    module_conditions[mk] = []
                module_conditions[mk].append({
                    "track_name": track.get("track_name", ""),
                    "rule_type": rule.get("type", ""),
                    "value": rule.get("value", 0),
                })

    detail_map = _build_course_detail_map(module_stats)

    for m in dept_data.get("modules", []):
        mk = m["module_key"]
        st = module_stats.get(mk, {})
        conditions = module_conditions.get(mk, [])

        # 해당 모듈에 적용되는 가장 대표적인 조건 선택
        # (여러 트랙에서 같은 모듈을 참조할 수 있으므로 가장 큰 조건 사용)
        req_type = ""
        req_value = 0
        req_label = ""
        is_satisfied = False

        if conditions:
            # 가장 큰 조건 선택 (여러 트랙에서 참조 시)
            best = max(conditions, key=lambda x: x["value"])
            req_type = best["rule_type"]
            req_value = best["value"]

            if req_type == "module_min_credits":
                req_label = f"{req_value}학점 이상"
                is_satisfied = st.get("taken_credits", 0) >= req_value
                current = st.get("taken_credits", 0)
            elif req_type == "module_min_courses":
                req_label = f"{req_value}과목 이상"
                is_satisfied = st.get("taken_count", 0) >= req_value
                current = st.get("taken_count", 0)
            elif req_type == "module_all_courses":
                req_label = f"전 과목 이수 ({st.get('total_courses', 0)}과목)"
                req_value = st.get("total_courses", 0)
                is_satisfied = st.get("taken_count", 0) >= req_value
                current = st.get("taken_count", 0)
            else:
                req_label = f"조건 {req_value}"
                current = st.get("taken_count", 0)
        else:
            # 어떤 트랙에도 포함되지 않은 모듈
            req_label = "트랙 조건 없음"
            current = st.get("taken_count", 0)
            req_value = st.get("total_courses", 0)

        # 이수율 계산 (조건 대비)
        if req_value > 0:
            rate = round(min(current / req_value, 1.0), 2)
        else:
            rate = 0.0

        not_taken = [c for c in st.get("all_courses", []) if c not in set(st.get("taken_courses", []))]
        taken_details = _details_for_courses(st.get("taken_courses", []), detail_map)
        not_taken_details = _details_for_courses(not_taken, detail_map)
        all_details = _details_for_courses(st.get("all_courses", []), detail_map)

        results.append({
            "module_key": mk,
            "module_name": st.get("module_name", ""),
            "is_completed": is_satisfied,
            "taken_count": st.get("taken_count", 0),
            "total_courses": st.get("total_courses", 0),
            "taken_credits": st.get("taken_credits", 0),
            "total_credits": st.get("total_credits", 0),
            "completion_rate": rate,
            "taken_courses": st.get("taken_courses", []),
            "not_taken_courses": not_taken,
            "taken_course_details": taken_details,
            "not_taken_course_details": not_taken_details,
            "all_course_details": all_details,
            # 트랙 조건 정보 (프론트 표시용)
            "requirement_type": req_type,
            "requirement_value": req_value,
            "requirement_label": req_label,
            "current_value": current,
            "related_tracks": [c["track_name"] for c in conditions],
            "course_notes": st.get("course_notes", {}),  # 기존 호환용 비고 원문
            "course_note_details": st.get("course_note_details", {}),
        })

    return results


# ═══════════════════════════════════════════
# 트랙 분석
# ═══════════════════════════════════════════

def _analyze_single_track(track: dict, student_names: set[str], module_stats: dict) -> dict:
    rules = track.get("rules", [])
    rule_results = []
    all_missing = []
    all_taken = []
    supported = []
    detail_map = _build_course_detail_map(module_stats)
    manual_items = list(dict.fromkeys(track.get("manual_review_items", [])))
    unsupported = [
        rule_type for rule_type in dict.fromkeys(track.get("unsupported_rule_types", []))
        if rule_type not in SUPPORTED_RULE_TYPES
    ]

    for rule in rules:
        r = _check_rule(rule, track, student_names, module_stats)

        # 프론트 표시용 상세 데이터 생성
        # - taken_course_details: 이미 이수한 과목 → 초록색 칩
        # - missing_course_details: 아직 조건을 못 채운 경우 안 들은 과목 → 빨간색 칩
        # - remaining_course_details: 조건은 이미 채웠지만 모듈에 남은 선택 가능 과목 → 회색 칩
        r["missing_courses"] = r.get("missing_courses", [])
        r["remaining_courses"] = r.get("remaining_courses", [])
        r["missing_course_details"] = _details_for_courses(r.get("missing_courses", []), detail_map)
        r["taken_course_details"] = _details_for_courses(r.get("taken_courses", []), detail_map)
        r["remaining_course_details"] = _details_for_courses(r.get("remaining_courses", []), detail_map)
        r["all_course_details"] = _details_for_courses(r.get("all_courses", []), detail_map)
        rule_results.append(r)
        if r["evaluation_status"] == "supported":
            supported.append(r)
        if not r["satisfied"]:
            all_missing.extend(r.get("missing_courses", []))
        if r.get("taken_courses"):
            all_taken.extend(r["taken_courses"])
        if r["evaluation_status"] in {"partial", "manual_review"} and r.get("note"):
            # 수동 검토 항목은 규칙 타입별로 저장 위치가 다를 수 있으므로 모두 수집한다.
            for item in (
                rule.get("manual_review_courses", [])
                + rule.get("items", [])
                + r.get("manual_review_items", [])
            ):
                if item not in manual_items:
                    manual_items.append(item)

    all_missing = _filter_unrecommended_courses(list(dict.fromkeys(all_missing)), detail_map)
    all_taken = list(dict.fromkeys(all_taken))
    additional_required_courses = _aggregate_additional_required_courses(rule_results)
    missing_candidate_count = len(all_missing)

    n = len(supported)
    if n > 0:
        s = 0.0
        for r in supported:
            if r["satisfied"]:
                s += 1.0
            else:
                cur = float(r.get("current_value", 0))
                req = float(r.get("required_value", 0))
                if req > 0 and cur > 0:
                    s += min(cur / req, 1.0)
        rate = round(s / n, 2)
    else:
        rate = 0.0

    manual_needed = bool(manual_items or unsupported)
    completed = n > 0 and all(r["satisfied"] for r in supported) and not manual_needed

    return {
        "track_id": track.get("track_id", ""),
        "track_name": track.get("track_name", ""),
        "is_completed": completed,
        "completion_rate": rate,
        "total_rules": len(rule_results),
        "satisfied_rules": sum(1 for r in rule_results if r["satisfied"]),
        "rule_results": rule_results,
        # missing_courses는 화면 표시용 '미이수 후보 과목 전체'입니다.
        # additional_required_courses는 추천 문구용 '충족까지 추가로 필요한 최소 과목 수'입니다.
        "missing_courses": all_missing,
        "missing_candidate_count": missing_candidate_count,
        "additional_required_courses": additional_required_courses,
        "taken_courses": all_taken,
        "missing_course_details": _details_for_courses(all_missing, detail_map),
        "taken_course_details": _details_for_courses(all_taken, detail_map),
        "analysis_mode": track.get("analysis_mode", "auto"),
        "unsupported_rule_types": unsupported,
        "manual_review_items": manual_items,
    }


def _check_rule(rule: dict, track: dict, student_names: set[str], module_stats: dict) -> dict:
    rt = rule.get("type", "")

    if rt == "required_courses_all":
        required = [normalize_course_name(c) for c in rule.get("courses", [])]
        manual_rc = list(dict.fromkeys(rule.get("manual_review_courses", [])))
        auto_req = [c for c in required if c not in manual_rc]
        taken = [c for c in auto_req if c in student_names]
        missing = [c for c in auto_req if c not in student_names]
        status = "partial" if manual_rc else "supported"
        note = ""
        if manual_rc:
            note = "수동 검토 필요: " + ", ".join(manual_rc)
        shortage_count = len(missing)
        course_label = ", ".join(required)
        return {"rule_type": rt, "description": f"필수 과목({course_label}) 이수",
                "satisfied": len(missing) == 0 and not manual_rc,
                "current_value": len(taken), "required_value": len(required),
                "shortage_count": shortage_count, "shortage_credits": shortage_count * 3,
                "missing_courses": missing, "taken_courses": taken,
                "evaluation_status": status, "note": note}

    if rt == "module_min_courses":
        mk = rule.get("module_key", "")
        val = rule.get("value", 0)
        st = module_stats.get(mk, {})
        tc = st.get("taken_count", 0)
        all_courses = st.get("all_courses", [])
        taken = st.get("taken_courses", [])
        not_taken = [c for c in all_courses if c not in student_names]
        is_satisfied = tc >= val
        mn = st.get("module_name", mk)

        # missing_courses는 프론트에서 보여줄 후보 전체를 내려보냅니다.
        # shortage_count는 추천 문구에 쓸 최소 추가 필요 과목 수입니다.
        shortage_count = max(0, val - tc)
        return {
            "rule_type": rt,
            "description": f"'{mn}' 모듈에서 {val}과목 이상 이수",
            "satisfied": is_satisfied,
            "current_value": tc,
            "required_value": val,
            "shortage_count": shortage_count,
            "shortage_credits": shortage_count * 3,
            "missing_courses": not_taken if not is_satisfied else [],
            "remaining_courses": not_taken if is_satisfied else [],
            "all_courses": all_courses,
            "taken_courses": taken,
            "evaluation_status": "supported",
            "note": "",
        }

    if rt == "module_all_courses":
        mk = rule.get("module_key", "")
        st = module_stats.get(mk, {})
        all_courses = st.get("all_courses", [])
        total = st.get("total_courses", 0)
        tc = st.get("taken_count", 0)
        not_taken = [c for c in all_courses if c not in student_names]
        is_satisfied = tc >= total
        mn = st.get("module_name", mk)
        shortage_count = max(0, total - tc)
        return {
            "rule_type": rt,
            "description": f"'{mn}' 모듈 전 과목 이수 ({total}과목)",
            "satisfied": is_satisfied,
            "current_value": tc,
            "required_value": total,
            "shortage_count": shortage_count,
            "shortage_credits": shortage_count * 3,
            "missing_courses": not_taken if not is_satisfied else [],
            "remaining_courses": not_taken if is_satisfied else [],
            "all_courses": all_courses,
            "taken_courses": st.get("taken_courses", []),
            "evaluation_status": "supported",
            "note": "",
        }

    if rt == "module_min_credits":
        mk = rule.get("module_key", "")
        val = rule.get("value", 0)
        st = module_stats.get(mk, {})
        tc = st.get("taken_credits", 0)
        all_courses = st.get("all_courses", [])
        taken = st.get("taken_courses", [])
        not_taken = [c for c in all_courses if c not in student_names]
        is_satisfied = tc >= val
        mn = st.get("module_name", mk)
        shortage_credits = max(0, val - tc)
        shortage_count = _estimate_min_course_count_for_credits(
            shortage_credits,
            not_taken,
            st.get("course_credits", {}),
        )
        return {
            "rule_type": rt,
            "description": f"'{mn}' 모듈에서 {val}학점 이상 이수",
            "satisfied": is_satisfied,
            "current_value": tc,
            "required_value": val,
            "shortage_count": shortage_count,
            "shortage_credits": shortage_credits,
            "missing_courses": not_taken if not is_satisfied else [],
            "remaining_courses": not_taken if is_satisfied else [],
            "all_courses": all_courses,
            "taken_courses": taken,
            "evaluation_status": "supported",
            "note": "",
        }

    if rt == "track_min_credits":
        val = rule.get("value", 0)
        total = sum(module_stats.get(mk, {}).get("taken_credits", 0) for mk in track.get("module_keys", []))
        candidate_courses: list[str] = []
        course_credits: dict[str, int] = {}
        taken_courses: list[str] = []
        for mk in track.get("module_keys", []):
            st = module_stats.get(mk, {})
            taken_courses.extend(st.get("taken_courses", []))
            course_credits.update(st.get("course_credits", {}))
            candidate_courses.extend([
                c for c in st.get("all_courses", [])
                if c not in student_names
            ])
        candidate_courses = list(dict.fromkeys(candidate_courses))
        taken_courses = list(dict.fromkeys(taken_courses))
        shortage_credits = max(0, val - total)
        shortage_count = _estimate_min_course_count_for_credits(
            shortage_credits,
            candidate_courses,
            course_credits,
        )
        is_satisfied = total >= val
        return {"rule_type": rt, "description": f"트랙 전체에서 {val}학점 이상 이수",
                "satisfied": is_satisfied, "current_value": total, "required_value": val,
                "shortage_count": shortage_count, "shortage_credits": shortage_credits,
                "missing_courses": candidate_courses if not is_satisfied else [],
                "remaining_courses": candidate_courses if is_satisfied else [],
                "all_courses": candidate_courses + taken_courses, "taken_courses": taken_courses,
                "evaluation_status": "supported", "note": ""}

    if rt == "module_group_min_courses_total":
        module_keys = rule.get("module_keys") or track.get("module_keys", [])
        val = int(rule.get("value", 0) or 0)
        taken_courses: list[str] = []
        all_courses: list[str] = []
        module_names: list[str] = []
        for mk in module_keys:
            st = module_stats.get(mk, {})
            module_names.append(st.get("module_name") or mk)
            taken_courses.extend(st.get("taken_courses", []))
            all_courses.extend(st.get("all_courses", []))

        taken_courses = list(dict.fromkeys(taken_courses))
        all_courses = list(dict.fromkeys(all_courses))
        not_taken = [c for c in all_courses if c not in student_names]
        current = len(taken_courses)
        is_satisfied = current >= val
        module_label = ", ".join(module_names)
        shortage_count = max(0, val - current)
        return {
            "rule_type": rt,
            "description": f"{module_label} 중 총 {val}과목 이상 이수",
            "satisfied": is_satisfied,
            "current_value": current,
            "required_value": val,
            "shortage_count": shortage_count,
            "shortage_credits": shortage_count * 3,
            "missing_courses": not_taken if not is_satisfied else [],
            "remaining_courses": not_taken if is_satisfied else [],
            "all_courses": all_courses,
            "taken_courses": taken_courses,
            "evaluation_status": "supported",
            "note": "",
        }

    if rt == "total_min_courses":
        val = rule.get("value", 0)
        total_taken = 0
        at, ant, all_courses = [], [], []
        required_courses: set[str] = set()
        if rule.get("exclude_required_courses"):
            for track_rule in track.get("rules", []):
                if track_rule.get("type") == "required_courses_all":
                    required_courses.update(normalize_course_name(c) for c in track_rule.get("courses", []))
        for mk in track.get("module_keys", []):
            st = module_stats.get(mk, {})
            module_taken = [c for c in st.get("taken_courses", []) if c not in required_courses]
            module_all = [c for c in st.get("all_courses", []) if c not in required_courses]
            total_taken += len(module_taken)
            at.extend(module_taken)
            all_courses.extend(module_all)
            ant.extend([c for c in module_all if c not in student_names])
        at = list(dict.fromkeys(at))
        ant = list(dict.fromkeys(ant))
        all_courses = list(dict.fromkeys(all_courses))
        is_satisfied = total_taken >= val
        shortage_count = max(0, val - total_taken)
        description = (
            f"필수 과목 외 트랙 내 추가 {val}과목 이상 이수"
            if rule.get("exclude_required_courses")
            else f"트랙 전체에서 {val}과목 이상 이수"
        )
        return {
            "rule_type": rt,
            "description": description,
            "satisfied": is_satisfied,
            "current_value": total_taken,
            "required_value": val,
            "shortage_count": shortage_count,
            "shortage_credits": shortage_count * 3,
            "missing_courses": ant if not is_satisfied else [],
            "remaining_courses": ant if is_satisfied else [],
            "all_courses": all_courses,
            "taken_courses": at,
            "evaluation_status": "supported",
            "note": "",
        }

    if rt == "module_course_indexes_all":
        mk = rule.get("module_key", "")
        indexes = [int(i) for i in rule.get("indexes", [])]
        st = module_stats.get(mk, {})
        all_courses = st.get("all_courses", [])
        required = [
            all_courses[index - 1]
            for index in indexes
            if 1 <= index <= len(all_courses)
        ]
        taken = [c for c in required if c in student_names]
        missing = [c for c in required if c not in student_names]
        module_name = st.get("module_name", mk)
        index_label = ", ".join(str(i) for i in indexes)
        course_label = ", ".join(required)
        return {
            "rule_type": rt,
            "description": f"'{module_name}' 모듈 {index_label}번 과목({course_label}) 이수",
            "satisfied": len(missing) == 0,
            "current_value": len(taken),
            "required_value": len(required),
            "shortage_count": len(missing),
            "shortage_credits": len(missing) * 3,
            "missing_courses": missing,
            "remaining_courses": [],
            "all_courses": required,
            "taken_courses": taken,
            "evaluation_status": "supported",
            "note": "",
        }

    if rt == "required_items_raw":
        # 가이드북의 필수 교과목 칸이 실제 과목명이 아니라
        # "임상간호이론교과목"처럼 범주/설명형 문구로 적힌 경우이다.
        # 성적표 과목명과 1:1 매칭할 수 없으므로 MVP에서는 수동 확인으로 표시한다.
        items = list(dict.fromkeys(rule.get("items", [])))
        return {
            "rule_type": rt,
            "description": "범주형 필수 조건 수동 확인",
            "satisfied": False,
            "current_value": 0,
            "required_value": len(items),
            "shortage_count": 0,
            "shortage_credits": 0,
            "missing_courses": [],
            "remaining_courses": [],
            "all_courses": [],
            "taken_courses": [],
            "evaluation_status": "manual_review",
            "note": track.get("note") or ("가이드북의 필수 조건이 정확한 과목명이 아닌 범주명입니다: " + ", ".join(items)),
            "manual_review_items": items,
        }

    return {"rule_type": rt, "description": f"수동 검토 필요: {rt}",
            "satisfied": False, "current_value": 0, "required_value": rule.get("value", 0),
            "shortage_count": 0, "shortage_credits": 0,
            "missing_courses": [], "remaining_courses": [], "all_courses": [], "taken_courses": [],
            "evaluation_status": "manual_review",
            "note": track.get("note") or "자동 판별 불가. 학과 사무실에 확인하세요."}
