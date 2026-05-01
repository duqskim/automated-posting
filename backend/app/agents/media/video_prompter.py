"""
VideoPrompter — Kling AI 전용 영상 생성 프롬프트 생성기

ImagePrompter와 완전히 별개:
  - ImagePrompter: 정적 화면 구도/조명/분위기 → Imagen 4 (이미지)
  - VideoPrompter: 움직임/액션/카메라 동작 → Kling AI (영상)

Kling 프롬프트 원칙:
  - "무엇이" 어떻게 "움직이는지" 묘사 (명사+동사)
  - 카메라 무브먼트 명시 (pan, zoom, dolly, handheld...)
  - 시작 → 끝 상태 변화 묘사 (image_tail 활용 시 더 효과적)
  - 감정/분위기 → 동적 표현 ("dramatically", "slowly", "urgently")
"""
import json
import os
import re
from loguru import logger


async def generate_video_prompts(
    topic: str,
    hook: str,
    body_slides: list[str],
    video_plan_dict: dict | None = None,
    platform: str = "youtube",
    language: str = "en",
) -> list[str]:
    """
    슬라이드 텍스트 + 샷 플랜 → Kling AI 영상 생성 전용 프롬프트

    이미지 프롬프트와 달리, 움직임과 액션을 중심으로 묘사.
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)

    # 샷 플랜에서 슬라이드별 카메라 무브먼트 추출
    shot_map: dict[int, dict] = {}
    if video_plan_dict and video_plan_dict.get("shots"):
        for s in video_plan_dict["shots"]:
            shot_map[s["slide_index"]] = s

    slides_text = "\n".join(
        f"[Slide {i+1}] {slide}"
        + (f" [camera: {shot_map[i]['camera_movement']}, mood: {shot_map[i]['mood']}]"
           if i in shot_map else "")
        for i, slide in enumerate(body_slides)
    )

    aspect_note = "horizontal 16:9" if platform == "youtube" else "vertical 9:16"

    prompt = f"""You are a professional video director writing prompts for Kling AI image-to-video generation.

Topic: "{topic}"
Hook: "{hook}"
Aspect ratio: {aspect_note}

Slides:
{slides_text}

For each slide, write a Kling AI VIDEO GENERATION PROMPT.

CRITICAL RULES for Kling prompts (NOT image prompts):
1. Describe MOTION and ACTION — what is physically moving/happening in the scene
2. Describe CAMERA MOVEMENT explicitly (slow zoom in, pan left, dolly forward, static locked shot, handheld follow)
3. Use action verbs: "warriors marching", "flames flickering", "camera slowly pushing forward"
4. Keep it 30-60 words — concise and action-focused
5. Always include: camera movement + subject action + atmosphere
6. Historical Korean scenes: show people/objects MOVING, not static compositions
7. Avoid describing static image qualities (no "shallow depth of field", "8K", "composition")

GOOD examples:
- "Korean warriors marching through a misty mountain pass, camera slowly tracking alongside from the left, torchlight flickering in darkness, dramatic and tense"
- "Ancient scroll map unrolling on a stone table, camera slowly zooming in from above, ink brushstrokes appear as if being written, ceremonial and reverent atmosphere"
- "Royal court official bowing before a throne, camera tilting down from the ornate ceiling to eye level, golden lanterns swaying, formal and dramatic"

BAD examples (avoid these — these are IMAGE prompts):
- "Cinematic photorealistic Korean palace, volumetric light rays, shallow depth of field, 8K"
- "Ancient architecture with warm amber color palette, golden hour lighting, professional photography"

Return JSON:
{{"video_prompts": ["prompt for slide 1", "prompt for slide 2", ...]}}

Return ONLY valid JSON, no explanation."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7),
        )

        text = response.text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"JSON not found: {text[:200]}")

        data = json.loads(match.group())
        prompts = data.get("video_prompts", [])

        # 슬라이드 수 맞추기 (부족하면 기본값)
        while len(prompts) < len(body_slides):
            i = len(prompts)
            shot = shot_map.get(i, {})
            camera = shot.get("camera_movement", "slow pan")
            mood = shot.get("mood", "cinematic")
            prompts.append(
                f"Historical Korean scene, {camera.replace('_', ' ')}, {mood} atmosphere, "
                f"camera moves slowly through the scene"
            )

        logger.info(f"[VideoPrompter] {len(prompts)}개 Kling 전용 프롬프트 생성 완료")
        return prompts[:len(body_slides)]

    except Exception as e:
        logger.error(f"[VideoPrompter] 실패, 기본 프롬프트 사용: {e}")
        # 실패 시 슬라이드 텍스트 기반 최소 프롬프트
        result = []
        for i, slide in enumerate(body_slides):
            shot = shot_map.get(i, {})
            camera = shot.get("camera_movement", "slow zoom in").replace("_", " ")
            mood = shot.get("mood", "dramatic")
            result.append(
                f"{slide[:80]}, {camera}, {mood} cinematic atmosphere"
            )
        return result
