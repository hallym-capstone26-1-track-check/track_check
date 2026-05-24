"""
🔍 file_validator.py — 업로드된 파일의 안전성을 검사하는 도구

💡 왜 파일 검증이 필요한가?
   - 악의적인 사용자가 실행파일(.exe)을 이미지로 위장해서 업로드할 수 있음
   - 너무 큰 파일을 올려서 서버를 다운시킬 수 있음
   - 확장자뿐 아니라 실제 파일 내용(MIME type)도 체크해야 안전함

💡 수정 포인트:
   - 허용 확장자/MIME 타입을 바꾸고 싶으면 → config.py 수정
   - 파일 크기 제한을 바꾸고 싶으면 → config.py의 MAX_FILE_SIZE_BYTES 수정
"""
from __future__ import annotations

import io
import os
from fastapi import UploadFile

# 같은 프로젝트의 config.py에서 설정값을 가져옴
from config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_COUNT,
    MAX_TOTAL_UPLOAD_BYTES,
)


class FileValidationError(Exception):
    """파일 검증 실패 시 발생하는 커스텀 에러"""
    pass


def _validate_image_content(content: bytes) -> None:
    """
    파일 확장자/MIME만 믿지 않고, 실제 이미지로 열리는지 검사합니다.

    초보자 핵심:
    - 확장자와 MIME type은 조작될 수 있습니다.
    - Pillow의 Image.verify()로 이미지 구조 자체가 정상인지 한 번 더 확인합니다.
    - 원본 이미지는 저장하지 않고 메모리에서만 확인합니다.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            image.verify()
    except Exception:
        raise FileValidationError(
            "실제 이미지 파일로 확인되지 않습니다. "
            "파일이 손상되었거나 이미지가 아닌 파일일 수 있습니다."
        )


async def validate_uploaded_file(file: UploadFile) -> bytes:
    """
    업로드된 파일 1개를 검증하고, 통과하면 파일 내용(bytes)을 반환합니다.

    검증 순서:
    1. 파일명이 있는지 확인
    2. 확장자가 허용 목록에 있는지 확인
    3. MIME 타입이 이미지인지 확인
    4. 파일 크기가 제한 이내인지 확인
    5. Pillow로 실제 이미지 파일인지 확인

    Args:
        file: FastAPI의 UploadFile 객체 (프론트에서 업로드한 파일)

    Returns:
        bytes: 검증을 통과한 파일의 바이너리 데이터

    Raises:
        FileValidationError: 검증 실패 시
    """

    # ── 1단계: 파일명 확인 ──
    if not file.filename:
        raise FileValidationError("파일명이 없습니다.")

    # ── 2단계: 확장자 확인 ──
    # os.path.splitext("성적표.png") → ("성적표", ".png")
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()  # 대소문자 통일 (.PNG → .png)

    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"허용되지 않는 파일 확장자입니다: {ext}. "
            f"허용 확장자: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # ── 3단계: MIME 타입 확인 ──
    # MIME 타입: 파일의 "실제 종류"를 나타내는 표준 (예: image/png)
    if not file.content_type or file.content_type not in ALLOWED_MIME_TYPES:
        raise FileValidationError(
            f"허용되지 않는 파일 형식입니다: {file.content_type or '(알 수 없음)'}. "
            f"이미지 파일만 업로드해주세요."
        )

    # ── 4단계: 파일 내용 읽기 + 크기 확인 ──
    # await = 비동기 읽기 (파일이 클 수 있으므로 서버가 멈추지 않도록)
    content = await file.read()

    if len(content) > MAX_FILE_SIZE_BYTES:
        # 크기를 MB로 변환해서 사용자에게 보여줌
        size_mb = len(content) / (1024 * 1024)
        max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise FileValidationError(
            f"파일 크기가 너무 큽니다: {size_mb:.1f}MB. "
            f"최대 {max_mb:.0f}MB까지 허용됩니다."
        )

    if len(content) == 0:
        raise FileValidationError("빈 파일입니다.")

    # ── 5단계: 실제 이미지 내용 검증 ──
    # 파일명/Content-Type만 조작된 가짜 이미지 업로드를 막기 위한 최소 보안 장치입니다.
    _validate_image_content(content)

    return content


def validate_file_count(count: int) -> None:
    """
    업로드된 파일 수가 제한 이내인지 확인합니다.

    Args:
        count: 업로드된 파일 수

    Raises:
        FileValidationError: 파일 수 초과 시
    """
    if count == 0:
        raise FileValidationError("업로드된 파일이 없습니다.")

    if count > MAX_FILES_COUNT:
        raise FileValidationError(
            f"한 번에 최대 {MAX_FILES_COUNT}개까지 업로드 가능합니다. "
            f"(현재: {count}개)"
        )


def validate_total_size(total_bytes: int) -> None:
    """
    한 요청에 들어온 모든 파일의 합산 크기가 제한 이내인지 확인합니다.

    왜 필요한가?
    - 파일 1개당 크기 제한(MAX_FILE_SIZE_BYTES)만 있으면 사용자가 큰 파일을 여러 장 올려서
      서버 메모리를 한 번에 크게 점유할 수 있습니다.
    - 예: 10MB × 5장 = 50MB가 한 요청에서 동시에 메모리에 적재됨.
    - 발표용 노트북처럼 메모리가 넉넉하지 않은 환경에서는 OOM(메모리 부족) 위험이 있습니다.

    Args:
        total_bytes: 모든 업로드 파일의 크기 합계

    Raises:
        FileValidationError: 합산 크기 초과 시
    """
    if total_bytes > MAX_TOTAL_UPLOAD_BYTES:
        size_mb = total_bytes / (1024 * 1024)
        max_mb = MAX_TOTAL_UPLOAD_BYTES / (1024 * 1024)
        raise FileValidationError(
            f"전체 업로드 크기가 너무 큽니다: {size_mb:.1f}MB. "
            f"한 요청에 합쳐서 최대 {max_mb:.0f}MB까지 허용됩니다."
        )
