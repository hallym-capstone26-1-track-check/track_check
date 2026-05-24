from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image
from unittest.mock import patch

from main import app

client = TestClient(app)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    # DB가 꺼져 있어도 서버 상태 내용을 읽을 수 있도록 HTTP 200을 유지합니다.
    # DB 연결 성공 시 healthy, DB 연결 실패 시 degraded입니다.
    assert body["status"] in {"healthy", "degraded"}
    assert "db" in body
    assert "ocr_mode" in body


@patch("routers.upload.config.OCR_MODE", "mock")
@patch("services.ocr_service.OCR_MODE", "mock")
def test_upload_accepts_multiple_real_images_with_mock_ocr():
    files = [("files", ("page1.png", _png_bytes(), "image/png")), ("files", ("page2.png", _png_bytes(), "image/png"))]
    response = client.post("/api/v1/upload", files=files, data={"scenario": "sw_ai"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["total_images"] == 2
    assert len(body["courses"]) >= 4


def test_upload_rejects_fake_image_even_if_mime_says_image():
    files = [("files", ("fake.png", b"not-a-real-image", "image/png"))]
    response = client.post("/api/v1/upload", files=files, data={"scenario": "sw_ai"})
    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "NO_PROCESSABLE_IMAGES"
    assert "실제 이미지 파일로 확인되지 않습니다" in body["details"][0]


def test_analyze_endpoint_total_min_courses_auto():
    payload = {"dept_name": "광고홍보학과", "courses": [{"course_name": "커뮤니케이션입문", "credits": 3, "grade": "A+"}, {"course_name": "광고와사회", "credits": 3, "grade": "A+"}, {"course_name": "광고개론", "credits": 3, "grade": "A+"}, {"course_name": "홍보개론", "credits": 3, "grade": "A+"}, {"course_name": "소비자행동원론", "credits": 3, "grade": "A+"}, {"course_name": "국제마케팅커뮤니케이션", "credits": 3, "grade": "A+"}]}
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    target = next(t for t in body["track_results"] if t["track_name"] == "표준전공트랙")
    assert target["analysis_mode"] == "auto"
    assert target["is_completed"] is True


def test_tracks_detail_includes_course_note_metadata():
    response = client.get("/api/v1/tracks/인공지능융합학부")
    assert response.status_code == 200
    body = response.json()
    courses = [course for module in body["modules"] for course in module["courses"]]
    target = next(course for course in courses if course["course_name"] == "인공지능시스템프로그래밍")
    assert target["has_note"] is True
    assert target["note"] == "2026-1학기 교과목 폐지"
    assert target["note_type"] == "abolished"
    assert target["warning_level"] == "danger"


def test_analyze_endpoint_includes_course_note_details():
    payload = {
        "dept_name": "인공지능융합학부",
        "courses": [{"course_name": "로봇개론", "credits": 3, "grade": "A+"}],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    target = next(t for t in body["track_results"] if t["track_name"] == "로봇인공지능트랙")
    detail = next(c for c in target["missing_course_details"] if c["course_name"] == "인공지능시스템프로그래밍")
    assert detail["has_note"] is True
    assert detail["note_type"] == "abolished"



def test_tracks_detail_excludes_major_required_and_elective_from_note_icons():
    """전공필수/전공선택은 단순 구분 정보라서 경고 아이콘 대상이 아니어야 한다."""
    response = client.get("/api/v1/tracks/간호학과")
    assert response.status_code == 200
    body = response.json()

    courses = [course for module in body["modules"] for course in module["courses"]]
    required = next(course for course in courses if course["course_name"] == "기초간호학Ⅰ")
    elective = next(course for course in courses if course["course_name"] == "기초간호과학입문")

    assert required["has_note"] is False
    assert required["note"] == ""
    assert required["note_type"] is None
    assert required["warning_level"] is None

    assert elective["has_note"] is False
    assert elective["note"] == ""
    assert elective["note_type"] is None
    assert elective["warning_level"] is None


@patch("routers.upload.config.OCR_MODE", "mock")
def test_upload_warns_when_ocr_extracts_zero_courses():
    files = [("files", ("empty.png", _png_bytes(), "image/png"))]
    response = client.post("/api/v1/upload", files=files, data={"scenario": "sw_empty"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["courses"] == []
    assert "추출된 과목이 없습니다" in body["message"]
    assert any("OCR 결과에서 과목을 찾지 못했습니다" in warning for warning in body["warnings"])


@patch("routers.upload.config.OCR_MODE", "tesseract")
@patch("routers.upload.extract_text_from_image")
def test_upload_handles_ocr_exception_gracefully(mock_extract_text):
    """OCR 모듈에서 예외가 발생하더라도 서버가 다운되지 않고 warning으로 처리되어야 한다."""
    # upload.py는 run_ocr가 아니라 extract_text_from_image를 호출합니다.
    # 그래서 현재 코드와 맞는 함수 위치를 patch해야 합니다.
    mock_extract_text.side_effect = RuntimeError("Tesseract is not installed")

    files = [("files", ("error_case.png", _png_bytes(), "image/png"))]
    response = client.post("/api/v1/upload", files=files)

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "NO_PROCESSABLE_IMAGES"
    assert any("OCR 처리 실패" in warning for warning in body["details"])


def test_recommendation_reason_uses_additional_required_courses_phrase():
    payload = {
        "dept_name": "소프트웨어학부",
        "courses": [{"course_name": "웹프로그래밍", "credits": 3, "grade": "A+"}],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    first = body["recommended_tracks"][0]
    assert "추가 필요 과목" in first["reason"]
    assert "미이수 과목" not in first["reason"]
    assert first["remaining_courses"] == first["additional_required_courses"]




def test_recommendation_reason_prefix_only_positive_recommendations():
    payload = {
        "dept_name": "소프트웨어학부",
        "courses": [{"course_name": "웹프로그래밍", "credits": 3, "grade": "A+"}],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    recommendations = body["recommended_tracks"]
    incomplete_tracks = body["incomplete_tracks"]
    assert recommendations
    assert incomplete_tracks

    positive_recommendations = [r for r in recommendations if r["completion_rate"] > 0]
    zero_incomplete_tracks = [r for r in incomplete_tracks if r["completion_rate"] <= 0]

    # 0% 트랙은 추천 후보가 아니라 전체 미완료 트랙 목록에서 일반 카드처럼 보여줍니다.
    assert zero_incomplete_tracks
    assert all(r["completion_rate"] > 0 for r in recommendations)

    assert positive_recommendations[0]["reason"].startswith("현재 이수 내역과 가장 가까운 후보입니다.")

    for rec in positive_recommendations[1:]:
        assert rec["reason"].startswith("이수 현황 기준 검토 후보입니다.")
        assert "현재 이수 내역과 가장 가까운 후보입니다." not in rec["reason"]

    for rec in zero_incomplete_tracks:
        assert rec["reason"] == ""


def test_tracks_query_endpoint_handles_dept_name_with_slash():
    """학과명에 '/'가 들어가도 query parameter 방식은 안전하게 조회되어야 한다."""
    dept_name = "언론방송융합미디어전공 / 디지털미디어콘텐츠전공"
    response = client.get("/api/v1/tracks/by-department", params={"dept_name": dept_name})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["dept_name"] == dept_name
    assert len(body["tracks"]) >= 1
    assert len(body["modules"]) >= 1


def test_modules_query_endpoint_returns_course_note_map():
    response = client.get("/api/v1/modules/by-department", params={"dept_name": "인공지능융합학부"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["dept_name"] == "인공지능융합학부"
    assert "인공지능시스템프로그래밍" in body["course_note_map"]


def test_legacy_modules_path_is_not_swallowed_by_detail_path():
    """구 방식 /tracks/{dept_name}/modules도 계속 동작해야 한다."""
    response = client.get("/api/v1/tracks/인공지능융합학부/modules")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["dept_name"] == "인공지능융합학부"
    assert "modules" in body
    assert "all_course_names" in body


@patch("routers.upload.config.OCR_MODE", "mock")
@patch("services.ocr_service.OCR_MODE", "mock")
def test_upload_response_includes_next_step_message():
    files = [("files", ("page1.png", _png_bytes(), "image/png"))]
    response = client.post("/api/v1/upload", files=files, data={"scenario": "sw_ai"})
    assert response.status_code == 200
    body = response.json()
    assert "next_step" in body
    assert "확인" in body["next_step"]
    assert "수정" in body["next_step"]


@patch("routers.upload.config.OCR_MODE", "mock")
def test_upload_response_includes_match_score():
    files = [("files", ("page1.png", _png_bytes(), "image/png"))]
    response = client.post("/api/v1/upload", files=files, data={"scenario": "sw_ai"})
    assert response.status_code == 200
    body = response.json()
    assert body["courses"]
    assert "match_score" in body["courses"][0]


def test_openapi_uses_track_response_models():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec["paths"]
    assert "/api/v1/tracks/by-department" in paths
    assert "/api/v1/modules/by-department" in paths
    assert "TracksListResponse" in spec["components"]["schemas"]
    assert "DepartmentTracksResponse" in spec["components"]["schemas"]
    assert "DepartmentModulesResponse" in spec["components"]["schemas"]


def test_analyze_rejects_course_with_blank_credit():
    """과목명이 있는데 학점이 비어 있으면 백엔드가 최종 방어선으로 거절해야 한다."""
    payload = {
        "dept_name": "소프트웨어학부",
        "courses": [
            {"course_name": "오픈소스SW의이해", "credits": "", "grade": "B0"},
        ],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_rejects_course_with_zero_credit():
    """학점 0은 이수 학점 계산에 쓸 수 없으므로 거절한다."""
    payload = {
        "dept_name": "소프트웨어학부",
        "courses": [
            {"course_name": "오픈소스SW의이해", "credits": 0, "grade": "B0"},
        ],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_does_not_count_module_name_as_course_name():
    """'인공지능'은 모듈명일 수 있으므로 '인공지능기초'로 자동 인정하면 안 된다."""
    payload = {
        "dept_name": "소프트웨어학부",
        "courses": [
            {"course_name": "인공지능", "credits": 3, "grade": "A+"},
        ],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    target = next(t for t in body["track_results"] if t["track_name"] == "빅데이터AI융합 트랙")
    assert "인공지능기초" not in target["taken_courses"]


def test_analyze_rejects_unknown_department():
    """존재하지 않는 학과명으로 요청 시 404를 반환해야 한다."""
    payload = {
        "dept_name": "없는학과",
        "courses": [
            {"course_name": "파이썬", "credits": 3, "grade": "A+"},
        ],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "DEPARTMENT_NOT_FOUND"


def test_analyze_rejects_empty_courses_list():
    """빈 과목 리스트로 요청 시 422를 반환해야 한다."""
    payload = {
        "dept_name": "소프트웨어학부",
        "courses": [],
    }
    response = client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "VALIDATION_ERROR"
