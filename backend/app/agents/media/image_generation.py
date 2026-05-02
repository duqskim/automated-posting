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

# 동시 이미지 생성 제한 — API quota 과부하 방지
# Imagen4: 분당 10 RPM 제한, OpenAI: billing 보호
_IMAGE_SEMAPHORE = asyncio.Semaphore(4)

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
        "Cinematic photorealistic, Korean historical drama aesthetic, "
        "warm amber and golden hour color palette, volumetric light rays, "
        "Netflix historical drama cinematography, 8K, professional photography, "
        "no text overlay, no watermarks, no logos"
    )
    return f"{base}. {style_suffix}"


# OpenAI aspect ratio 매핑
_DALLE3_SIZE = {
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "1:1":  "1024x1024",
    "4:3":  "1792x1024",
}
_GPT_IMAGE_SIZE = {
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "1:1":  "1024x1024",
    "4:3":  "1536x1024",
}


async def _generate_with_openai(prompt: str, output_path: Path, aspect_ratio: str = "16:9", model: str = "gpt-image-1") -> Path | None:
    """OpenAI 이미지 생성 — gpt-image-1 (기본) 또는 dall-e-3"""
    import httpx, base64

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning(f"  [{model}] OPENAI_API_KEY 없음 — 스킵")
        return None

    is_gpt = model == "gpt-image-1"
    size = (_GPT_IMAGE_SIZE if is_gpt else _DALLE3_SIZE).get(aspect_ratio, "1536x1024" if is_gpt else "1792x1024")
    logger.info(f"  [{model}] 생성 ({size}): {prompt[:60]}...")

    payload: dict = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
    }
    if is_gpt:
        payload["quality"] = "medium"  # low / medium / high
    else:
        payload["quality"] = "standard"
        payload["response_format"] = "b64_json"

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        img_bytes = base64.b64decode(data["data"][0]["b64_json"])
        output_path.write_bytes(img_bytes)
        logger.info(f"  [{model}] 저장: {output_path.name} ({len(img_bytes)//1024}KB)")
        return output_path

    except Exception as e:
        logger.error(f"  [{model}] 실패: {e}")
        return None


async def _generate_with_gemini_native(prompt: str, output_path: Path, model: str = "gemini-2.0-flash-exp") -> Path | None:
    """Gemini 네이티브 이미지 생성 (response_modalities=IMAGE)"""
    from google import genai
    from google.genai import types
    import base64

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning(f"  [{model}] GEMINI_API_KEY 없음")
        return None

    logger.info(f"  [{model}] 네이티브 이미지 생성: {prompt[:60]}...")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                img_bytes = part.inline_data.data
                if isinstance(img_bytes, str):
                    img_bytes = base64.b64decode(img_bytes)
                output_path.write_bytes(img_bytes)
                logger.info(f"  [{model}] 저장: {output_path.name} ({len(img_bytes)//1024}KB)")
                return output_path

        logger.warning(f"  [{model}] 이미지 파트 없음")
        return None

    except Exception as e:
        logger.error(f"  [{model}] 실패: {e}")
        return None


async def generate_scene_image(
    slide_text: str,
    image_prompt: str,
    output_path: Path,
    topic: str = "",
    language: str = "en",
    aspect_ratio: str = "16:9",
    image_provider: str = "auto",  # "auto"|"imagen"|"gemini-flash"|"gemini-pro"|"gpt-image-1"|"dalle"
) -> Path | None:
    """씬 이미지 생성
    image_provider:
      "auto"        — Imagen 4 우선, 쿼터 초과 시 gpt-image-1 폴백
      "imagen"      — Imagen 4 전용
      "gemini-flash"— Gemini 2.0 Flash 네이티브 이미지 생성
      "gemini-pro"  — Gemini 2.5 Pro 네이티브 이미지 생성
      "gpt-image-1" — gpt-image-1 전용 (권장)
      "dalle"       — DALL-E 3 전용
    """
    async with _IMAGE_SEMAPHORE:
        return await _generate_scene_image_inner(
            slide_text, image_prompt, output_path, topic, language, aspect_ratio, image_provider
        )


async def _generate_scene_image_inner(
    slide_text: str,
    image_prompt: str,
    output_path: Path,
    topic: str = "",
    language: str = "en",
    aspect_ratio: str = "16:9",
    image_provider: str = "auto",
) -> Path | None:
    prompt = _build_imagen_prompt(slide_text, image_prompt, topic, language)

    if image_provider == "gemini-flash":
        return await _generate_with_gemini_native(prompt, output_path, model="gemini-2.5-flash-image")

    if image_provider == "gemini-pro":
        return await _generate_with_gemini_native(prompt, output_path, model="gemini-3-pro-image-preview")

    # gpt-image-1 전용
    if image_provider == "gpt-image-1":
        return await _generate_with_openai(prompt, output_path, aspect_ratio, model="gpt-image-1")

    # DALL-E 3 전용
    if image_provider == "dalle":
        return await _generate_with_openai(prompt, output_path, aspect_ratio, model="dall-e-3")

    # Imagen 4 시도 (auto or imagen)
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        logger.info(f"  [Imagen4] 생성: {prompt[:60]}...")
        try:
            client = genai.Client(api_key=api_key)
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

            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                if img_bytes:
                    output_path.write_bytes(img_bytes)
                    logger.info(f"  [Imagen4] 저장: {output_path.name} ({len(img_bytes)//1024}KB)")
                    return output_path

            logger.warning("  [Imagen4] 이미지 없음 (안전 필터?)")

        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logger.warning("  [Imagen4] 쿼터 초과")
            else:
                logger.error(f"  [Imagen4] 실패: {e}")

        if image_provider == "imagen":
            return None  # imagen 전용이면 폴백 없이 종료

        logger.info("  → gpt-image-1 폴백")

    return await _generate_with_openai(prompt, output_path, aspect_ratio, model="gpt-image-1")


async def generate_all_scenes(
    slide_texts: list[str],
    image_prompts: list[str],
    topic: str,
    platform: str = "youtube",
    language: str = "en",
    slug: str = "",
    image_provider: str = "auto",
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
            image_provider=image_provider,
        ))

    results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r is not None)
    logger.info(f"=== ImageGeneration 완료: {success}/{len(tasks)}장 ===")

    return [str(r) if r else "" for r in results]


async def generate_all_frames(
    shot_script,           # ShotScript (imported lazily)
    body_slides: list[str],
    image_prompts: list[str],   # 1 per ShotFrame (same order as shot_script.shots)
    topic: str,
    platform: str = "youtube",
    slug: str = "",
    image_provider: str = "auto",
) -> dict:
    """
    ShotFrame 단위 이미지 병렬 생성 (신규 멀티샷 파이프라인용)

    반환: dict with keys (slide_index, frame_index) and str path values
    파일명: {slug}_{platform}_s{slide:02d}_f{frame:02d}.jpg
    """
    import re
    if not slug:
        slug = re.sub(r"[^\w]", "_", topic)[:25]

    shots = shot_script.shots
    aspect_ratio = PLATFORM_ASPECT.get(platform, "16:9")
    logger.info(
        f"=== ImageGeneration (multiframe): '{topic}' [{platform}] "
        f"{len(shots)}프레임 ({aspect_ratio}) ==="
    )

    tasks = []
    keys = []
    for idx, shot in enumerate(shots):
        si, fi = shot.slide_index, shot.frame_index
        path = SCENES_DIR / f"{slug}_{platform}_s{si:02d}_f{fi:02d}.jpg"
        slide_text = body_slides[si] if si < len(body_slides) else ""
        prompt = image_prompts[idx] if idx < len(image_prompts) else ""
        keys.append((si, fi))
        tasks.append(generate_scene_image(
            slide_text=slide_text,
            image_prompt=prompt,
            output_path=path,
            topic=topic,
            language="en",
            aspect_ratio=aspect_ratio,
            image_provider=image_provider,
        ))

    results = await asyncio.gather(*tasks)

    frame_paths = {}
    success = 0
    for (si, fi), result in zip(keys, results):
        if result:
            frame_paths[(si, fi)] = str(result)
            success += 1
        else:
            frame_paths[(si, fi)] = ""

    logger.info(f"=== ImageGeneration (multiframe) 완료: {success}/{len(tasks)}장 ===")
    return frame_paths
