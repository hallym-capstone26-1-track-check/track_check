"""
🧪 test_case_service.py — 전체 학과/트랙용 Mock OCR 테스트 케이스 생성기

이 파일의 역할
1. DB 기준 데이터에 들어있는 학과/트랙을 읽는다.
2. 각 트랙마다 프론트에서 바로 선택 가능한 테스트 케이스를 만든다.
3. 서버 실행 중 메모리에서만 테스트 케이스를 생성한다.

왜 별도 파일로 뺐나?
- ocr_service.py에 200개가 넘는 시나리오를 직접 적으면 관리가 어렵다.
- DB 기준 데이터가 수정되면 테스트 케이스도 자동으로 같이 바뀌게 하기 위해서다.
"""
from __future__ import annotations

from functools import lru_cache

from services.data_loader import load_track_rules as _load_rules


PASSING_GRADE = "A0"


def get_generated_scenarios() -> list[dict]:
    """
    프론트 드롭다운에서 보여줄 테스트 케이스 목록을 반환한다.

    반환 예시:
    {
      "key": "gen_001_complete",
      "label": "국어국문학전공 — 한국어교육트랙 — 충족형",
      "dept": "국어국문학전공",
      "track_name": "한국어교육트랙",
      "kind": "complete"
    }
    """
    return [
        {
            "key": case["key"],
            "label": case["label"],
            "dept": case["dept"],
            "track_id": case["track_id"],
            "track_name": case["track_name"],
            "kind": case["kind"],
            "course_count": len(case["courses"]),
        }
        for case in _generate_cases()
    ]


def get_generated_case(key: str) -> dict | None:
    """scenario key로 테스트 케이스 하나를 찾는다."""
    for case in _generate_cases():
        if case["key"] == key:
            return case
    return None


def build_mock_ocr_text(case: dict) -> str:
    """
    생성된 테스트 케이스를 OCR 결과처럼 보이는 텍스트로 바꾼다.

    upload.py는 실제 OCR이든 Mock OCR이든 최종적으로 텍스트를 파싱한다.
    그래서 여기서는 성적표에서 추출된 것 같은 텍스트 형식으로 만들어준다.
    """
    lines = [
        "학번: 20269999",
        "이름: 테스트학생",
        f"학과: {case['dept']}",
        f"테스트트랙: {case['track_name']}",
        "",
        "교과목명                    학점  성적",
    ]
    for course in case["courses"]:
        # 과목명과 학점 사이에 공백 2칸 이상을 넣어야 parse_ocr_text()가 안정적으로 읽는다.
        lines.append(f"{course['course_name']:<28}  {course['credits']}    {course['grade']}")
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=1)
def _generate_cases() -> tuple[dict, ...]:
    """
    모든 트랙에 대해 2개씩 테스트 케이스를 만든다.

    1) 충족형
       - 자동 판별 가능한 규칙을 최대한 만족하도록 과목을 채운다.
       - 단, 비교과/포트폴리오/수동검토 조건은 자동으로 완료 처리할 수 없다.

    2) 부족형
       - 충족형에서 과목 하나를 일부러 빼서 부족 과목 표시를 테스트한다.
    """
    rules = _load_rules()
    cases: list[dict] = []
    seq = 1

    for college in rules.get("colleges", []):
        college_name = college.get("college_name", "")
        for dept in college.get("departments", []):
            dept_name = dept.get("dept_name", "")
            modules = {m.get("module_key"): m for m in dept.get("modules", [])}

            for track in dept.get("tracks", []):
                complete_courses = _build_courses_for_track(track, modules)
                complete_note = _label_suffix_for_track(track)

                cases.append({
                    "key": f"gen_{seq:03d}_complete",
                    "label": f"{dept_name} — {track.get('track_name', '')} — 충족형{complete_note}",
                    "dept": dept_name,
                    "college": college_name,
                    "track_id": track.get("track_id", ""),
                    "track_name": track.get("track_name", ""),
                    "kind": "complete",
                    "courses": complete_courses,
                })
                seq += 1

                missing_courses = _make_missing_case_courses(complete_courses, track, modules)
                cases.append({
                    "key": f"gen_{seq:03d}_missing",
                    "label": f"{dept_name} — {track.get('track_name', '')} — 부족형",
                    "dept": dept_name,
                    "college": college_name,
                    "track_id": track.get("track_id", ""),
                    "track_name": track.get("track_name", ""),
                    "kind": "missing",
                    "courses": missing_courses,
                })
                seq += 1

    return tuple(cases)


def _label_suffix_for_track(track: dict) -> str:
    """자동 판별이 어려운 트랙이면 프론트 라벨에 표시한다."""
    if track.get("manual_review_items") or track.get("unsupported_rule_types"):
        return " / 수동확인 포함"
    if track.get("analysis_mode") not in (None, "", "auto"):
        return " / 부분자동"
    return ""


def _build_courses_for_track(track: dict, modules: dict[str, dict]) -> list[dict]:
    """트랙 규칙을 보고 충족형 테스트 과목 목록을 만든다."""
    selected: dict[str, dict] = {}

    def add_course(course: dict | None) -> None:
        if not course:
            return
        name = course.get("course_name", "").strip()
        if not name:
            return
        # 같은 과목이 여러 모듈에 있을 수 있으므로 과목명 기준으로 중복 제거한다.
        selected[name] = {
            "course_name": name,
            "credits": int(course.get("credits", 3) or 3),
            "grade": PASSING_GRADE,
        }

    def add_first_courses(module_key: str, count: int) -> None:
        module = modules.get(module_key, {})
        for course in module.get("courses", [])[:max(0, count)]:
            add_course(course)

    def add_all_courses(module_key: str) -> None:
        module = modules.get(module_key, {})
        for course in module.get("courses", []):
            add_course(course)

    def add_until_credits(module_key: str, min_credits: int) -> None:
        module = modules.get(module_key, {})
        current = 0
        for course in module.get("courses", []):
            add_course(course)
            current += int(course.get("credits", 3) or 3)
            if current >= min_credits:
                break

    def find_course_by_name(course_name: str) -> dict | None:
        for module in modules.values():
            for course in module.get("courses", []):
                if course.get("course_name") == course_name:
                    return course
        # track_rules에 필수 과목명이 있지만 module courses에 없는 경우가 있을 수 있다.
        # 이 경우에도 파싱/응답 테스트는 되도록 3학점 과목으로 넣어준다.
        return {"course_name": course_name, "credits": 3}

    # 1) 필수 과목 먼저 추가
    for rule in track.get("rules", []):
        if rule.get("type") == "required_courses_all":
            for course_name in rule.get("courses", []):
                add_course(find_course_by_name(course_name))

    # 2) 모듈/트랙 조건 충족에 필요한 과목 추가
    for rule in track.get("rules", []):
        rule_type = rule.get("type")
        module_key = rule.get("module_key", "")
        value = int(rule.get("value", 0) or 0)

        if rule_type == "module_min_courses":
            add_first_courses(module_key, value)
        elif rule_type == "module_all_courses":
            add_all_courses(module_key)
        elif rule_type == "module_min_credits":
            add_until_credits(module_key, value)
        elif rule_type == "module_group_min_courses_total":
            _add_module_group_min_courses_total(rule, modules, selected, value)
        elif rule_type == "total_min_courses":
            _add_total_min_courses(track, modules, selected, value)
        elif rule_type == "track_min_credits":
            _add_track_min_credits(track, modules, selected, value)

    # 3) 규칙이 거의 없는 트랙을 대비해 트랙 조합 모듈에서 최소 1과목 추가
    if not selected:
        for module_key in track.get("module_keys", []):
            module = modules.get(module_key, {})
            if module.get("courses"):
                add_course(module["courses"][0])
                break

    return list(selected.values())


def _add_module_group_min_courses_total(
    rule: dict,
    modules: dict[str, dict],
    selected: dict[str, dict],
    min_count: int,
) -> None:
    """지정된 여러 모듈 묶음에서 총 N과목 이상 조건을 만족할 때까지 과목을 추가한다."""
    module_keys = list(rule.get("module_keys", []))
    current = sum(
        1
        for course in selected.values()
        if any(
            course.get("course_name") == candidate.get("course_name")
            for mk in module_keys
            for candidate in modules.get(mk, {}).get("courses", [])
        )
    )
    if current >= min_count:
        return

    for module_key in module_keys:
        for course in modules.get(module_key, {}).get("courses", []):
            name = course.get("course_name", "")
            if name and name not in selected:
                selected[name] = {
                    "course_name": name,
                    "credits": int(course.get("credits", 3) or 3),
                    "grade": PASSING_GRADE,
                }
                current += 1
            if current >= min_count:
                return


def _add_total_min_courses(
    track: dict,
    modules: dict[str, dict],
    selected: dict[str, dict],
    min_count: int,
) -> None:
    """트랙 전체 N과목 이상 조건을 만족할 때까지 과목을 추가한다."""
    if len(selected) >= min_count:
        return
    for module_key in track.get("module_keys", []):
        for course in modules.get(module_key, {}).get("courses", []):
            name = course.get("course_name", "")
            if name and name not in selected:
                selected[name] = {
                    "course_name": name,
                    "credits": int(course.get("credits", 3) or 3),
                    "grade": PASSING_GRADE,
                }
            if len(selected) >= min_count:
                return


def _add_track_min_credits(
    track: dict,
    modules: dict[str, dict],
    selected: dict[str, dict],
    min_credits: int,
) -> None:
    """트랙 전체 N학점 이상 조건을 만족할 때까지 과목을 추가한다."""
    def total_credits() -> int:
        return sum(int(c.get("credits", 0) or 0) for c in selected.values())

    if total_credits() >= min_credits:
        return
    for module_key in track.get("module_keys", []):
        for course in modules.get(module_key, {}).get("courses", []):
            name = course.get("course_name", "")
            if name and name not in selected:
                selected[name] = {
                    "course_name": name,
                    "credits": int(course.get("credits", 3) or 3),
                    "grade": PASSING_GRADE,
                }
            if total_credits() >= min_credits:
                return


def _make_missing_case_courses(
    complete_courses: list[dict],
    track: dict,
    modules: dict[str, dict],
) -> list[dict]:
    """
    부족형 케이스를 만든다.

    원칙:
    - 분석 API는 courses가 최소 1개 있어야 하므로 빈 목록은 만들지 않는다.
    - 가능하면 해당 트랙의 핵심 조건과 무관한 과목 1개만 넣어서 부족 상태를 만든다.
    - 피할 과목이 없으면 첫 과목을 F로 넣어, F/NP 필터링 + 부족 과목 표시를 동시에 확인한다.
    """

    def as_course(course: dict, grade: str = PASSING_GRADE) -> dict:
        return {
            "course_name": course.get("course_name", ""),
            "credits": int(course.get("credits", 3) or 3),
            "grade": grade,
        }

    def first_course_from_modules(module_keys: list[str], banned_names: set[str]) -> dict | None:
        for module_key in module_keys:
            for course in modules.get(module_key, {}).get("courses", []):
                name = course.get("course_name", "")
                if name and name not in banned_names:
                    return as_course(course)
        return None

    track_module_keys = list(track.get("module_keys", []))

    # 1) 필수 과목 조건이 있으면, 필수 과목은 일부러 빼고 다른 과목 1개만 넣는다.
    for rule in track.get("rules", []):
        if rule.get("type") == "required_courses_all":
            required_names = {str(name) for name in rule.get("courses", [])}
            candidate = first_course_from_modules(track_module_keys, required_names)
            if candidate:
                return [candidate]
            # 필수 외 과목이 없으면 필수 과목 1개를 F로 넣어 부족 처리한다.
            for module_key in track_module_keys:
                for course in modules.get(module_key, {}).get("courses", []):
                    return [as_course(course, grade="F")]

    # 2) 모듈 조건이 있으면, 그 모듈이 아닌 다른 트랙 모듈 과목을 넣는다.
    for rule in track.get("rules", []):
        module_key = rule.get("module_key")
        if module_key:
            other_keys = [mk for mk in track_module_keys if mk != module_key]
            candidate = first_course_from_modules(other_keys, set())
            if candidate:
                return [candidate]
            # 다른 모듈이 없으면 해당 모듈 첫 과목을 F로 넣는다.
            candidate_f = first_course_from_modules([module_key], set())
            if candidate_f:
                candidate_f["grade"] = "F"
                return [candidate_f]

    # 3) 여러 모듈 묶음에서 최소 과목 수를 요구하는 조건은 F로 넣어 부족 상태를 만든다.
    for rule in track.get("rules", []):
        if rule.get("type") == "module_group_min_courses_total":
            candidate = first_course_from_modules(rule.get("module_keys", track_module_keys), set())
            if candidate:
                candidate["grade"] = "F"
                return [candidate]

    # 4) 트랙 전체 과목/학점 조건만 있으면 첫 과목 1개만 넣는다.
    candidate = first_course_from_modules(track_module_keys, set())
    if candidate:
        return [candidate]

    # 5) fallback: 충족형에서 첫 과목만 F로 바꾼다.
    if complete_courses:
        c = dict(complete_courses[0])
        c["grade"] = "F"
        return [c]

    return []
