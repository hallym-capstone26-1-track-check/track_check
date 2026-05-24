"""
이 upload.py 파일은 이미지 업로드 API 라우터입니다.
변경사항:
- scenario 파일명으로 이름 변경 (테스트에서는 Mock 시나리오 자동 감지)
- GET /api/v1/scenarios 를 사용 가능한 Mock 시나리오 목록 반환
"""
from __future__ import annotations

import gc
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from schemas.common_schemas import ApiErrorResponse
from schemas.upload_schemas import CourseItem, UploadResponse
from services.course_normalizer import normalize_course_records
from services.ocr_service import (
    extract_text_from_image,
    get_available_scenarios,
    get_scenario_text,
    parse_ocr_text,
)
from services.privacy_service import mask_personal_info, remove_personal_info_from_courses
from utils.api_response import error_response
from utils.file_validator import (
    FileValidationError,
    validate_file_count,
    validate_total_size,
    validate_uploaded_file,
)
import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["이미지 업로드 & OCR"])


@router.get(
    "/scenarios",
    summary="사용 가능한 Mock OCR 시나리오 목록",
    description="테스트에서 자동으로 시나리오를 감지할 수 있도록 목록을 반환합니다.",
)
async def list_scenarios():
    """Mock 데이터에서 사용 가능한 시나리오 목록을 반환합니다."""
    scenarios = get_available_scenarios()
    return {
        "success": True,
        "scenarios": scenarios,
        "message": f"{len(scenarios)}개의 테스트 시나리오를 사용할 수 있습니다.",
    }


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="성적표 이미지 업로드 및 OCR 처리",
    description=(
        f"한 장 이상의 성적표 이미지를 업로드하면 OCR로 과목 데이터를 추출합니다.\n\n"
        f"**제한 사항**\n"
        f"- 최대 {config.MAX_FILES_COUNT}장 이하 업로드\n"
        f"- 파일 1개당 최대 {config.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB\n"
        f"- 전체 파일 크기 최대 {config.MAX_TOTAL_UPLOAD_BYTES // (1024 * 1024)}MB\n\n"
        f"Mock 데이터에서는 scenario 파일명으로 시나리오를 감지할 수 있습니다.\n\n"
        f"OCR 결과는 임시 정해진 데이터가 아니므로 테스트에서는 사용하지 말고 과목명/이수상태를 확인/수정한 다음 다음 단계 API를 호출하는 방식을 권장합니다."
    ),
    responses={
        400: {"model": ApiErrorResponse, "description": "파일 검증 실패"},
        500: {"model": ApiErrorResponse, "description": "서버 내부 오류"},
    },
)
async def upload_images(
    files: List[UploadFile] = File(
        default=[],
        description=f"성적표 이미지 파일입니다. 여러 장 업로드할 수 있으며 최대 {config.MAX_FILES_COUNT}장까지 가능합니다.",
    ),
    scenario: Optional[str] = Form(
        default=None,
        description="Mock OCR 시나리오 ID (예: sw_ai, ai_medical, dha_smart_exp)",
    ),
):
    """
    성적표 이미지를 받아서 OCR 결과를 과목 리스트로 반환합니다.

    처리 우선순위:
    1) 업로드된 파일이 있으면 파일 검증을 먼저 수행합니다.
       - 파일이 이미지이고 scenario가 있어야 정상 처리됩니다.
       - 로그에는 실제 파일명을 기록하지 않고 image_1, image_2 형식만 사용합니다.
    2) 업로드된 파일이 없고 scenario만 있으면 Mock OCR 텍스트로 테스트합니다.
    """
    # FastAPI에서 파일 입력 없이 빈값으로 넘어오면 filename이 빈 문자열인 파일 객체가 생성될 수 있음
    raw_files = files or []
    uploaded_files = [f for f in raw_files if f.filename and f.filename.strip()]
    has_uploaded_files = len(uploaded_files) > 0

    logger.debug(
        "업로드 요청 수신: 실제 파일 수 %s개 (빈값 객체 포함 %s개, 시나리오 사용 여부: %s)",
        len(uploaded_files), len(raw_files), bool(scenario),
    )

    # 파일도 없고 Mock 시나리오도 없으면 처리를 진행할 수 없습니다.
    if not has_uploaded_files and not scenario:
        return error_response(
            status_code=400,
            error_code="INVALID_FILE_COUNT",
            message="업로드할 이미지 파일이 없거나 Mock 시나리오가 지정되지 않았습니다.",
        )

    # 파일이 있는 경우에만 파일 수 검증을 수행합니다.
    # 파일이 없고 scenario만 있는 Mock 테스트는 적용하지 않습니다.
    if has_uploaded_files:
        try:
            validate_file_count(len(uploaded_files))
        except FileValidationError as e:
            return error_response(
                status_code=400, error_code="INVALID_FILE_COUNT", message=str(e)
            )

    all_raw_texts: list[str] = []
    warnings: list[str] = []
    processed_count = 0
    total_bytes_accumulated = 0
    aborted_due_to_total_size = False
    scenario_text_used = False

    # 1) 파일이 있으면 파일 검증 + OCR을 순서대로 수행합니다.
    if has_uploaded_files:
        for idx, file in enumerate(uploaded_files):
            image_label = f"image_{idx + 1}"
            image_bytes: bytes | None = None

            try:
                # 실제 파일명을 포함한 정보를 포함하므로 로그/응답에 기록하지 않습니다.
                logger.info("이미지 %s/%s 처리 시작: %s", idx + 1, len(uploaded_files), image_label)

                # 파일 검증 수행: MIME, 실제 이미지 여부, 1개당 크기 제한
                image_bytes = await validate_uploaded_file(file)
            except FileValidationError as e:
                warnings.append(f"{image_label}: {str(e)}")
                logger.warning("파일 검증 실패 - %s: %s", image_label, str(e))
                await file.close()
                continue

            # 누적 크기 검증: 모든 업로드 파일의 합계가 제한을 초과 여부
            total_bytes_accumulated += len(image_bytes)
            try:
                validate_total_size(total_bytes_accumulated)
            except FileValidationError as e:
                warnings.append(f"{image_label}: {str(e)}")
                logger.warning("누적 크기 초과 - %s에서 처리를 중단합니다.", image_label)
                del image_bytes
                await file.close()
                aborted_due_to_total_size = True
                break

            try:
                current_raw_text = ""

                # Mock 데이터 + scenario가 있으면 검증을 끝낸 다음에만 scenario 텍스트를 사용합니다.
                # 참고: 이미지 파일이 여러 개여도 두 번째부터는 정상 처리되지 않습니다.
                if config.OCR_MODE == "mock" and scenario:
                    if not scenario_text_used:
                        current_raw_text = get_scenario_text(scenario)
                        scenario_text_used = True
                else:
                    current_raw_text = await run_in_threadpool(extract_text_from_image, image_bytes)

                # OCR 결과가 비어 있어도 검증하고 OCR 시도한 것으로 이미지로 처리합니다.
                processed_count += 1

                if current_raw_text:
                    all_raw_texts.append(f"--- Page {idx + 1}: {image_label} ---\n{current_raw_text}")

                # 가장 무거운 이미지 bytes를 리스트에 유지하지 않고 임시 버퍼에서만 처리합니다.
                del image_bytes
                image_bytes = None

            except Exception as e:
                warnings.append(f"{image_label}: OCR 처리 실패 ({type(e).__name__})")
                logger.error("OCR 처리 실패 - %s: %s", image_label, type(e).__name__)
            finally:
                if image_bytes is not None:
                    del image_bytes
                await file.close()

        # 누적 크기 초과로 break한 경우 남은 파일을 모두 닫습니다.
        if aborted_due_to_total_size:
            for remaining in uploaded_files[idx + 1:]:
                await remaining.close()

    # 2) 파일이 없고 scenario만 있으면 Mock 텍스트를 사용합니다.
    else:
        try:
            scenario_text = get_scenario_text(scenario or config.MOCK_SCENARIO)
            all_raw_texts.append(f"--- Mock Scenario ---\n{scenario_text}")
            scenario_text_used = True
            logger.info("파일 없이 Mock 시나리오로 업로드 API 테스트 실행")
        except Exception as e:
            logger.error("Mock 시나리오 처리 실패: %s", type(e).__name__)
            return error_response(
                status_code=500,
                error_code="MOCK_SCENARIO_FAILED",
                message="Mock 시나리오 처리 중 오류가 발생했습니다.",
                details=[type(e).__name__],
            )

    gc.collect()

    # 3) 전체 텍스트 병합 및 파싱
    combined_raw_text = "\n\n".join(all_raw_texts)

    # 파일이 있었는데 모두 실패한 경우: scenario가 없어야 정상 처리되지 않습니다.
    if has_uploaded_files and processed_count == 0:
        return error_response(
            status_code=400,
            error_code="NO_PROCESSABLE_IMAGES",
            message="처리 가능한 이미지가 없습니다. 파일 형식과 크기를 확인해주세요.",
            details=warnings,
        )

    if not combined_raw_text:
        return error_response(
            status_code=400,
            error_code="NO_TEXT_FOUND",
            message=(
                "이미지에서 글자를 인식하지 못했습니다. "
                "성적표가 선명하게 보이도록 다시 캡처하거나, 직접 입력으로 과목을 추가해주세요."
            ),
            details=warnings,
        )

    all_courses = parse_ocr_text(combined_raw_text, include_score=True)

    # 개인정보 삭제 후 과목명 정규화 및 중복 제거
    cleaned_courses = remove_personal_info_from_courses(all_courses)
    normalized_courses = normalize_course_records(cleaned_courses)
    unique_courses = _deduplicate_courses(normalized_courses)

    if len(unique_courses) == 0:
        warnings.append(
            "OCR 결과에서 과목을 찾지 못했습니다. "
            "이미지 품질을 확인하거나 직접 입력해주세요."
        )
        if has_uploaded_files:
            message = f"{processed_count}개 이미지를 처리했지만 추출된 과목이 없습니다. 매칭된 과목이 없습니다."
        else:
            message = "Mock 시나리오를 처리했지만 추출된 과목이 없습니다. 매칭된 과목이 없습니다."
        next_step = (
            "OCR은 실행되었지만 전공트랙 기준 데이터와 일치하는 과목을 찾지 못했습니다. "
            "이미지 품질을 확인하거나 직접 입력으로 과목을 추가해주세요."
        )
    else:
        if has_uploaded_files:
            message = f"{processed_count}개 이미지에서 {len(unique_courses)}개 과목을 추출했습니다."
        else:
            message = f"Mock 시나리오에서 {len(unique_courses)}개 과목을 추출했습니다."
        next_step = "OCR 결과를 자동 매칭했습니다. 다음 단계에서 과목명/이수상태를 확인/수정해주세요."

    return UploadResponse(
        success=True,
        message=message,
        total_images=processed_count,
        courses=[_to_course_item(c) for c in unique_courses],
        warnings=warnings,
        raw_text=mask_personal_info(combined_raw_text) if config.DEBUG_MODE else None,
        next_step=next_step,
        ocr_mode=config.OCR_MODE,
    )


def _to_course_item(course: dict) -> CourseItem:
    """OCR 내부 score 값을 API 응답의 match_score로 변환합니다."""
    item = dict(course)
    if "match_score" not in item and "score" in item:
        item["match_score"] = item.pop("score")
    return CourseItem(**item)


def _deduplicate_courses(courses: list[dict]) -> list[dict]:
    """동일 과목(과목명+이수상태+성적)의 중복을 제거합니다."""
    seen = set()
    unique = []
    for course in courses:
        key = (
            course.get("course_name", ""),
            course.get("credits", 0),
            course.get("grade", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(course)
    return unique
