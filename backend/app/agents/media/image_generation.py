"""
ImageGenerationAgent — Imagen 3으로 슬라이드별 씬 이미지 생성

흐름:
  슬라이드 텍스트 + image_prompt → Imagen 3 → JPG 이미지 파일
  플랫폼별 화면 비율:
    YouTube/Landscape  : 16:9
    Instagram/Threads  : 1:1
    Shorts/TikTok/Reels: 9:16
"""
import asyncio
import os
from pathlib import Path
from loguru import logger

SCENES_DIR = Path(__file__).parents[3] / "output" / "scenes"
SCENES_DIR.mkdir(parents=True, exist_ok=True)

# 플랫폼 → Imagen aspect_ratio
PLATFORM_ASPECT = {
    "youtube":        "16:9",
    "youtube_shorts": "9:16",
    "instagram":      "1:1",
    "threads":        "1:1",
    "tiktok":         "9:16",
    "linkedin":       "4:3",
    "x":              "16:9",
}


def _build_imagen_prompt(slide_text: str, image_prompt: str, topic: str, language: str = "en") -> str:
    """슬라이드 텍스트 + 이미지 방향 → Imagen 프롬프트 조합

    image_prompt가 충분히 구체적이면 그대로 사용.
    짧거나 부실하면 slide_text 핵심 내용을 보강.
    """
    ip = image_prompt.strip()

    if len(ip) >= 40:
        # 충분히 구체적 — 스타일 suffix만 추가
        base = ip
    elif ip:
        # 짧은 힌트 + 슬라이드 내용 보강
        excerpt = slide_text[:120].strip()
        base = f"{ip}. Scene context: {excerpt}"
    else:
        # 프롬프트 없음 — 슬라이드 전체 내용으로 대체
        base = f"Cinematic visual scene representing: {slide_text[:150].strip()}"

    style_suffix = (
        "Photorealistic, high quality, 8K resolution, dramatic professional lighting, "
        "professional color grading, no text overlay, no watermarks, no logos"
    )
    return f"{base}. {style_suffix}"


async def generate_scene_image(
    slide_text: str,
    image_prompt: str,
    output_path: Path,
    topic: str = "",
    language: str = "en",
    aspect_ratio: str = "16:9",
) -> Path | None:
    """Imagen 3으로 단일 씬 이미지 생성"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)
    prompt = _build_imagen_prompt(slide_text, image_prompt, topic, language)

    logger.info(f"  [Imagen4] 생성: {prompt[:60]}...")

    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                aspect_ratio=aspect_ratio,
                number_of_images=1,
                person_generation="allow_adult",
                output_mime_type="image/jpeg",
                output_compression_quality=90,
            ),
        )

        if not response.generated_images:
            logger.warning("  [Imagen4] 이미지 없음 (안전 필터?)")
            return None

        img_bytes = response.generated_images[0].image.image_bytes
        if img_bytes:
            output_path.write_bytes(img_bytes)
            logger.info(f"  [Imagen4] 저장: {output_path.name} ({len(img_bytes)//1024}KB)")
            return output_path

        return None

    except Exception as e:
        logger.error(f"  [Imagen4] 실패: {e}")
        return None


async def generate_all_scenes(
    slide_texts: list[str],
    image_prompts: list[str],
    topic: str,
    platform: str = "youtube",
    language: str = "en",
    slug: str = "",
) -> list[str]:
    """
    모든 슬라이드 씬 이미지 병렬 생성

    반환: 생성된 이미지 파일 경로 목록 (실패 슬라이드는 None 자리 채움)
    """
    import re
    if not slug:
        slug = re.sub(r"[^\w]", "_", topic)[:25]

    aspect_ratio = PLATFORM_ASPECT.get(platform, "16:9")
    logger.info(f"=== ImageGeneration: '{topic}' [{platform}] {len(slide_texts)}씬 ({aspect_ratio}) ===")

    tasks = []
    paths = []
    for i, (text, prompt) in enumerate(zip(slide_texts, image_prompts)):
        path = SCENES_DIR / f"{slug}_{platform}_{i:02d}.jpg"
        paths.append(path)
        tasks.append(generate_scene_image(
            slide_text=text,
            image_prompt=prompt,
            output_path=path,
            topic=topic,
            language=language,
            aspect_ratio=aspect_ratio,
        ))

    results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r is not None)
    logger.info(f"=== ImageGeneration 완료: {success}/{len(tasks)}장 ===")

    return [str(r) if r else "" for r in results]
