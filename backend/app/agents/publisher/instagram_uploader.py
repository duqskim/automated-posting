"""
Instagram 캐러셀 발행 모듈

흐름:
  1. 로컬 이미지 → Cloudinary 업로드 → 공개 URL
  2. 각 이미지 URL로 Meta Graph API 미디어 컨테이너 생성
  3. 카러셀 컨테이너 생성 (캡션 + 해시태그 포함)
  4. 컨테이너 발행

환경변수:
  INSTAGRAM_ACCOUNT_ID  — Instagram 비즈니스 계정 ID
  INSTAGRAM_ACCESS_TOKEN — Meta Graph API 액세스 토큰 (long-lived)
  CLOUDINARY_CLOUD_NAME
  CLOUDINARY_API_KEY
  CLOUDINARY_API_SECRET

Meta Graph API 제한:
  - 캐러셀: 최대 10장 (1장이면 단일 이미지로 자동 전환)
  - 하루 발행 상한: 25회
  - 이미지 URL은 공개 접근 가능해야 함 (Cloudinary 사용)
"""
import os
import time
from pathlib import Path
from loguru import logger


def _get_required_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise ValueError(f"{key} 환경변수 없음 — .env 파일에 설정해주세요")
    return val


def upload_to_cloudinary(image_path: str | Path, folder: str = "automated_posting") -> str:
    """로컬 이미지 → Cloudinary 업로드 → 공개 URL 반환"""
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=_get_required_env("CLOUDINARY_CLOUD_NAME"),
        api_key=_get_required_env("CLOUDINARY_API_KEY"),
        api_secret=_get_required_env("CLOUDINARY_API_SECRET"),
    )

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일 없음: {image_path}")

    result = cloudinary.uploader.upload(
        str(image_path),
        folder=folder,
        resource_type="image",
    )
    url = result.get("secure_url")
    logger.debug(f"[Cloudinary] {image_path.name} → {url}")
    return url


def _graph_post(endpoint: str, data: dict) -> dict:
    """Meta Graph API POST 요청"""
    import requests

    token = _get_required_env("INSTAGRAM_ACCESS_TOKEN")
    base = "https://graph.instagram.com/v21.0"

    resp = requests.post(
        f"{base}/{endpoint}",
        params={"access_token": token},
        json=data,
        timeout=30,
    )
    result = resp.json()
    if "error" in result:
        raise RuntimeError(f"Meta Graph API 오류: {result['error']}")
    return result


def _create_image_container(account_id: str, image_url: str, is_carousel_item: bool = True) -> str:
    """단일 이미지 미디어 컨테이너 생성 → container_id 반환"""
    data = {
        "image_url": image_url,
        "is_carousel_item": is_carousel_item,
    }
    result = _graph_post(f"{account_id}/media", data)
    return result["id"]


def _create_carousel_container(
    account_id: str,
    children: list[str],
    caption: str,
) -> str:
    """캐러셀 미디어 컨테이너 생성 → container_id 반환"""
    data = {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
    }
    result = _graph_post(f"{account_id}/media", data)
    return result["id"]


def _publish_container(account_id: str, container_id: str) -> str:
    """미디어 컨테이너 발행 → post_id 반환"""
    result = _graph_post(f"{account_id}/media_publish", {"creation_id": container_id})
    return result["id"]


def publish_carousel(
    image_paths: list[str | Path],
    caption: str,
    hashtags: list[str] | None = None,
    cloudinary_folder: str = "automated_posting",
    max_images: int = 10,
) -> dict:
    """
    Instagram 캐러셀 발행 (이미지 최대 10장)

    Args:
        image_paths: 로컬 이미지 파일 경로 목록
        caption: 포스트 캡션 (해시태그 포함 가능)
        hashtags: 해시태그 목�� (caption 뒤에 자동 추가)
        cloudinary_folder: Cloudinary 업로드 폴더
        max_images: 최대 이미지 수 (Instagram 제한 10)

    Returns:
        {"post_id": "...", "url": "...", "images_count": N}
    """
    account_id = _get_required_env("INSTAGRAM_ACCOUNT_ID")

    # 최대 10장으로 제한
    paths = image_paths[:max_images]
    if not paths:
        raise ValueError("업로드할 이미지 없음")

    # 캡션 + 해시태그 조합
    if hashtags:
        tag_line = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
        full_caption = f"{caption}\n\n{tag_line}" if caption else tag_line
    else:
        full_caption = caption

    full_caption = full_caption[:2200]  # Instagram 캡션 최대 2200자

    logger.info(f"[Instagram] {len(paths)}장 캐러셀 발행 시작")

    # Step 1: Cloudinary 업로드
    image_urls = []
    for i, path in enumerate(paths):
        url = upload_to_cloudinary(path, folder=cloudinary_folder)
        image_urls.append(url)
        logger.info(f"  [Cloudinary] {i+1}/{len(paths)} 업로드 완료")

    if len(image_urls) == 1:
        # 단일 이미지 포스트
        container_id = _create_image_container(account_id, image_urls[0], is_carousel_item=False)
        _graph_post(f"{account_id}/media", {"image_url": image_urls[0], "caption": full_caption})
        # 단일 이미지는 다른 엔드포인트 사용
        data = {"image_url": image_urls[0], "caption": full_caption}
        container_result = _graph_post(f"{account_id}/media", data)
        container_id = container_result["id"]
    else:
        # Step 2: 각 이미지 컨테이너 생성
        child_ids = []
        for url in image_urls:
            cid = _create_image_container(account_id, url, is_carousel_item=True)
            child_ids.append(cid)
            time.sleep(0.5)  # API rate limit 방지

        # Step 3: 캐러셀 컨테이너 생성
        container_id = _create_carousel_container(account_id, child_ids, full_caption)

    # Step 4: 발행 (컨테이너 처리 대기 — 보통 수 초)
    time.sleep(3)
    post_id = _publish_container(account_id, container_id)

    post_url = f"https://www.instagram.com/p/{post_id}/"
    logger.info(f"[Instagram] 발행 완료: {post_url}")

    return {
        "post_id": post_id,
        "url": post_url,
        "images_count": len(image_urls),
    }
