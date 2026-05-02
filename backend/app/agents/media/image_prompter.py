"""
ImagePrompter — 슬라이드/ShotFrame → Imagen 4 최적화 프롬프트 생성

두 가지 모드:
  1. generate_image_prompts(): 슬라이드 단위 (1 프롬프트/슬라이드) — 기존 방식
  2. generate_multiframe_prompts(): ShotFrame 단위 (1 프롬프트/샷) — 신규 방식
     - ShotFrame의 shot_size, camera_start, composition_hint 반영
     - StyleGuide의 art_style_token + character_descriptions prefix 적용
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
        char_ref_url = character.get("reference_image_url", "")
        bible = character.get("bible") or {}
        char_appearance = bible.get("visual_description") or char_visual
        if char_base_prompt or char_appearance:
            ref_line = f"\nReference image URL (match this appearance exactly): {char_ref_url}" if char_ref_url else ""
            character_note = f"""
HOST CHARACTER: {char_name}
Visual appearance: {char_appearance}
Base image style: {char_base_prompt}{ref_line}

CHARACTER APPEARANCE RULES (very important):
- Slides 1 and last slide: show {char_name} as the on-screen host in the scene
- All other slides: focus on IMMERSIVE HISTORICAL SCENES without the character
- Historical content slides must feel like National Geographic or BBC documentary cinematography
- Do NOT force the character into every slide — the historical scene itself should be the star
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
- Structure each prompt: [specific subject/scene with concrete details] + [Korean/East Asian setting] + [camera angle/composition] + [lighting/atmosphere] + [style]
- Extract specific nouns from the slide: exact years, names, places, objects, numbers
- Minimize human faces/people (use hands, silhouettes, objects, environments instead) to avoid safety filters
- Match the emotional tone of each slide

MANDATORY KOREAN/EAST ASIAN AESTHETIC (apply to EVERY prompt without exception):
- Architecture: Korean palace (경복궁-style), hanok rooftops, stone walls with curved eaves, wooden pillars, hanji paper screens
- Clothing/objects: Hanbok fabric, joseon-era armor, bronze vessels, celadon pottery, ink brushes, royal seals
- Landscape: Korean mountain ranges, pine forests, rice paddies, stone-paved roads, Han River
- People (when needed): East Asian facial features, Korean historical dress
- NEVER generate European castles, Western armor, Roman columns, or any non-East-Asian architecture

MANDATORY STYLE (apply to EVERY prompt, always append at the end):
"cinematic photorealistic, Korean historical drama aesthetic, warm amber and golden hour color palette, volumetric light rays, Netflix historical drama cinematography, 8K, professional photography"

- For historical scenes: dramatic wide-angle establishing shots, ancient artifacts close-up, royal court interiors with volumetric light — make the viewer feel they are THERE (National Geographic / BBC + Netflix Joseon style)
- For data/statistics: use East Asian symbolic objects (abacus, jade tablets, scroll maps) as physical metaphors
- No text, watermarks, or logos in the scene

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


async def rewrite_prompt(
    current_prompt: str,
    correction_intent: str,
    slide_text: str,
    topic: str = "",
    character: dict | None = None,
) -> str:
    """
    이미지 프롬프트 협업 수정

    사용자의 수정 의도(correction_intent)를 반영해 현재 프롬프트를 다시 씁니다.

    Args:
        current_prompt: 현재 Imagen 4 프롬프트 (영문)
        correction_intent: 사용자 수정 요청 (자유 언어 — 한국어/영어 모두 가능)
        slide_text: 해당 슬라이드 원문 (컨텍스트용)
        topic: 전체 콘텐츠 주제
        character: 캐릭터 정보 (일관성 유지용)

    Returns:
        수정된 Imagen 4 프롬프트 (영문)
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)

    char_note = ""
    if character:
        char_name = character.get("name", "")
        char_ref = character.get("reference_image_url", "")
        bible = character.get("bible") or {}
        char_visual = bible.get("visual_description") or character.get("visual_description", "")
        if char_name or char_visual:
            char_note = f"\nCharacter to maintain: {char_name} — {char_visual}"
            if char_ref:
                char_note += f"\nReference URL: {char_ref}"

    prompt = f"""You are an expert Imagen 4 prompt engineer doing a targeted rewrite.

Topic: "{topic}"
Slide text: "{slide_text[:200]}"
{char_note}

Current prompt:
{current_prompt}

User's correction request: "{correction_intent}"

Rewrite the prompt to incorporate the correction while preserving:
- The same scene/setting and historical accuracy
- The same mandatory style suffix (cinematic photorealistic, Korean historical drama aesthetic, etc.)
- The same composition structure (camera angle, lighting, atmosphere)
- Only change what the user specifically asked for

Return ONLY the rewritten prompt in English (60-100 words). No explanation, no JSON, just the prompt text."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5),
        )
        rewritten = response.text.strip().strip('"').strip()
        logger.info(f"[ImagePrompter] 프롬프트 재작성 완료 ({len(rewritten)}자)")
        return rewritten
    except Exception as e:
        logger.error(f"[ImagePrompter] 재작성 실패: {e}")
        return current_prompt


async def generate_multiframe_prompts(
    topic: str,
    shot_script,        # ShotScript (imported lazily to avoid circular deps)
    style_guide,        # StyleGuide
    body_slides: list[str],
    character: dict | None = None,
) -> list[str]:
    """
    ShotFrame 단위 Imagen 프롬프트 생성 (신규 멀티샷 파이프라인용)

    shot_script.shots 순서와 동일한 프롬프트 목록 반환.
    StyleGuide.mandatory_prefix/suffix를 모든 프롬프트에 적용.
    ShotFrame.shot_size + camera_start + composition_hint → 구도/앵글 반영.
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)
    shots = shot_script.shots

    # StyleGuide prefix / suffix
    style_prefix = style_guide.mandatory_prefix or ""
    style_suffix = style_guide.mandatory_suffix or (
        "cinematic photorealistic, Korean historical drama aesthetic, "
        "warm amber color palette, volumetric light rays, 8K, no text overlay"
    )
    art_token = style_guide.art_style_token or "Korean historical drama"

    # 캐릭터 일관성 지침
    char_note = ""
    if character:
        char_name = character.get("name", "")
        bible = character.get("bible") or {}
        char_visual = bible.get("visual_description") or character.get("visual_description", "")
        char_base_prompt = character.get("base_image_prompt", "")
        if char_name or char_visual:
            char_note = f"\nHOST CHARACTER — maintain exact appearance in every shot featuring them:"
            char_note += f"\nName: {char_name}"
            if char_visual:
                char_note += f"\nAppearance: {char_visual}"
            if char_base_prompt:
                char_note += f"\nBase image style: {char_base_prompt}"
    elif style_guide.character_descriptions:
        descs = "; ".join(f"{k}: {v}" for k, v in style_guide.character_descriptions.items())
        char_note = f"\nCHARACTER CONSISTENCY (always match exactly): {descs}"

    shots_info = "\n".join(
        f"[Shot {idx+1}] Slide {s.slide_index+1}, Frame {s.frame_index+1}\n"
        f"  Type:{s.shot_type} | Size:{s.shot_size} | Composition:{s.composition_hint}\n"
        f"  Camera angle: {s.camera_start}\n"
        f"  Subject action hint: {s.subject_action[:80]}\n"
        f"  Slide text: {body_slides[s.slide_index][:150] if s.slide_index < len(body_slides) else ''}"
        for idx, s in enumerate(shots)
    )

    prompt = f"""You are a professional visual director generating Imagen 4 image prompts.

Topic: "{topic}"
Art style: {art_token}
World: {style_guide.world_description}
Color palette: {style_guide.color_description}
{char_note}

Shot list to visualize:
{shots_info}

For each shot, write one Imagen 4 IMAGE GENERATION prompt (static image, NOT video).

Rules:
- Output JSON: {{"prompts": ["prompt for shot 1", "prompt for shot 2", ...]}}
- ALWAYS write in ENGLISH
- 60-100 words per prompt
- Structure: [camera angle + shot size] + [specific subject/setting] + [composition] + [lighting/atmosphere] + [style]
- shot_size to camera angle mapping:
    extreme_wide → aerial or panoramic establishing view
    wide → full scene with architecture/landscape prominent
    medium → subject visible with environment context
    close_up → subject fills frame, environment blurred
    extreme_close_up → detail shot, single object/face feature
- Use ShotFrame's camera_start for the angle ("low angle", "aerial", "eye level", etc.)
- Extract concrete details from slide text: dates, names, places, objects
- Minimize faces/people — use hands, silhouettes, objects, environments
- Match shot_type to visual density:
    DYNAMIC → action-ready composition, subject positioned to move
    ATMOSPHERIC → wide, open, peaceful, environmental
    STATIC_GRAPHIC → clean flat surface with the graphic/map/diagram prominent

MANDATORY STYLE (append to EVERY prompt):
"{style_suffix}"

Return ONLY the JSON object."""

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

        # 수 맞추기
        while len(prompts) < len(shots):
            i = len(prompts)
            shot = shots[i]
            slide_text = body_slides[shot.slide_index][:100] if shot.slide_index < len(body_slides) else topic
            prompts.append(
                f"{style_prefix} {shot.camera_start} view. "
                f"Cinematic scene: {slide_text}. {style_suffix}"
            )

        logger.info(f"[ImagePrompter] multiframe {len(prompts)}개 프롬프트 생성 완료")
        return prompts[:len(shots)]

    except Exception as e:
        logger.error(f"[ImagePrompter] multiframe 실패: {e}")
        result = []
        for shot in shots:
            slide_text = body_slides[shot.slide_index][:100] if shot.slide_index < len(body_slides) else topic
            result.append(
                f"{shot.camera_start} angle. Cinematic scene: {slide_text}. {style_suffix}"
            )
        return result
