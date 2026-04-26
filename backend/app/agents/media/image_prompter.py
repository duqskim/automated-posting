"""
ImagePrompter — 슬라이드 텍스트 → Imagen 4 최적화 프롬프트 전문 생성

역할:
  카피라이터가 작성한 슬라이드 본문을 받아서,
  Imagen 4에 최적화된 씬 프롬프트를 별도로 생성.

  카피라이터는 글쓰기 전문가 → 이미지 방향은 러프하게만 제안
  이 에이전트는 시각화 전문가 → Imagen이 실제로 잘 생성하는 형태로 변환

특징:
  - 항상 영어로 출력 (Imagen은 영어 프롬프트 성능이 압도적)
  - 슬라이드당 60-100단어 목표
  - 인물 묘사 최소화 (안전 필터 우회)
  - 구체적 오브젝트, 질감, 조명, 구도 명시
  - 모델: Gemini 2.5 Flash (빠르고 저렴)
"""
import os
import json
import re
import asyncio
from loguru import logger


async def generate_image_prompts(
    topic: str,
    hook: str,
    body_slides: list[str],
    rough_prompts: list[str] | None = None,
    language: str = "en",
    platform: str = "youtube",
    character: dict | None = None,
) -> list[str]:
    """
    슬라이드 본문 → Imagen 4 최적화 프롬프트 목록

    Args:
        topic: 콘텐츠 주제
        hook: 훅 텍스트 (전체 방향 파악용)
        body_slides: 슬라이드 텍스트 목록
        rough_prompts: 카피라이터가 생성한 러프한 이미지 힌트 (참고용)
        language: 콘텐츠 언어
        platform: 플랫폼 (화면 비율 힌트)

    Returns:
        슬라이드 수와 동일한 길이의 영어 Imagen 프롬프트 목록
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)

    aspect_note = {
        "youtube": "16:9 landscape",
        "youtube_shorts": "9:16 vertical",
        "instagram": "1:1 square",
        "tiktok": "9:16 vertical",
    }.get(platform, "16:9 landscape")

    slides_text = "\n".join(
        f"[Slide {i+1}] {slide}"
        + (f"\n  (rough hint: {rough_prompts[i]})" if rough_prompts and i < len(rough_prompts) and rough_prompts[i] else "")
        for i, slide in enumerate(body_slides)
    )

    character_note = ""
    if character:
        char_name = character.get("name", "")
        char_visual = character.get("visual_description", "")
        char_base_prompt = character.get("base_image_prompt", "")
        char_ref = character.get("reference_image_url", "")
        bible = character.get("bible") or {}
        char_appearance = bible.get("visual_description") or char_visual
        if char_base_prompt or char_appearance:
            character_note = f"""
CHARACTER TO FEATURE: {char_name}
Visual appearance: {char_appearance}
Base image style: {char_base_prompt}

For EACH slide, show {char_name} as the narrator/presenter in the scene.
The character should appear consistently across all slides.
Integrate the character naturally into each scene (e.g., pointing at data, standing in front of relevant background, gesturing while explaining).
"""

    prompt = f"""You are a professional visual director specializing in AI image generation (Imagen 4).

Content topic: "{topic}"
Hook: "{hook}"
Platform aspect ratio: {aspect_note}
{character_note}
Slides to visualize:
{slides_text}

Generate one detailed Imagen 4 image generation prompt for EACH slide.

Rules:
- Output in JSON: {{"prompts": ["prompt for slide 1", "prompt for slide 2", ...]}}
- ALWAYS write prompts in ENGLISH regardless of slide language
- 60-100 words per prompt
- Structure each prompt: [specific subject/scene with concrete details] + [visual style] + [camera angle/composition] + [lighting/atmosphere]
- Extract specific nouns from the slide: exact years, names, places, objects, numbers
- Minimize human faces/people (use hands, silhouettes, objects, environments instead) to avoid safety filters
- Match the emotional tone of each slide
- For historical content: use dramatic cinematic photography, museum-quality lighting
- For data/statistics: use abstract visualization, charts as physical objects in 3D space
- For comparison: split-frame compositions, contrasting lighting
- For modern/tech content: clean minimalist, neon accents, high-tech environments
- No text, watermarks, or logos in the scene description
- End each prompt with: "photorealistic, 8K, professional photography"

Return ONLY the JSON object, no explanation."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7),
        )

        text = response.text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            raise ValueError(f"JSON not found: {text[:200]}")

        data = json.loads(match.group())
        prompts = data.get("prompts", [])

        # 슬라이드 수 맞추기
        while len(prompts) < len(body_slides):
            i = len(prompts)
            fallback = rough_prompts[i] if rough_prompts and i < len(rough_prompts) and rough_prompts[i] else ""
            prompts.append(
                fallback if len(fallback) >= 30
                else f"Cinematic scene illustrating: {body_slides[i][:100]}. Photorealistic, 8K, professional photography"
            )

        logger.info(f"[ImagePrompter] {len(prompts)}개 프롬프트 생성 완료")
        return prompts[:len(body_slides)]

    except Exception as e:
        logger.error(f"[ImagePrompter] 실패: {e}")
        # 실패 시 rough_prompts 또는 간단한 기본값 반환
        result = []
        for i, slide in enumerate(body_slides):
            fallback = (rough_prompts[i] if rough_prompts and i < len(rough_prompts) else "") or \
                       f"Cinematic scene: {slide[:80]}. Photorealistic, 8K"
            result.append(fallback)
        return result
