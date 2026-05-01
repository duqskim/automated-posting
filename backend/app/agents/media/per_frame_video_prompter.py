"""
PerFrameVideoPrompter — ShotFrame 기반 Kling AI 전용 모션 프롬프트 생성

video_prompter.py 대체:
  - 슬라이드 단위(1 프롬프트/슬라이드) → 샷 단위(1 프롬프트/ShotFrame)
  - 각 ShotFrame의 camera_start + camera_movement + subject_action + physics 조합

Kling 프롬프트 원칙:
  - "[카메라 시작 위치]. [카메라 이동 방향+속도+끝 상태]. [피사체 동작]. [물리 요소]. [분위기]"
  - 명사+동사 조합: "warriors march", "flames flicker", "camera pushes in"
  - 30-60 단어 목표
  - 정적 이미지 표현 금지 ("8K", "composition", "shallow depth of field" → 이미지 프롬프트용)
"""
import json
import os
import re
from loguru import logger

from app.agents.media.cinematic_shot_planner import ShotScript, ShotFrame


def _build_motion_prompt(shot: ShotFrame) -> str:
    """ShotFrame → Kling 모션 프롬프트 직접 생성 (LLM 없이)"""
    parts = []

    if shot.camera_start:
        parts.append(shot.camera_start.rstrip("."))

    if shot.camera_movement:
        parts.append(shot.camera_movement.rstrip("."))

    if shot.subject_action:
        parts.append(shot.subject_action.rstrip("."))

    if shot.physics_elements and shot.physics_elements.lower() not in ("none", "ambient light", ""):
        parts.append(shot.physics_elements.rstrip("."))

    if shot.emotional_arc:
        arc = shot.emotional_arc.lower()
        parts.append(f"{arc} atmosphere")

    return ". ".join(parts)


async def generate_per_frame_prompts(
    shot_script: ShotScript,
    topic: str,
    platform: str = "youtube",
) -> list[str]:
    """
    ShotScript → Kling AI 전용 모션 프롬프트 목록 (순서: shot_script.shots 순)

    DYNAMIC 샷만 실제 Kling에 사용되지만, 모든 샷에 대해 생성
    (ATMOSPHERIC → Ken Burns 효과 선택에 감정/방향 힌트로 활용)
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[PerFrameVideoPrompter] GEMINI_API_KEY 없음 — 직접 생성")
        return [_build_motion_prompt(s) for s in shot_script.shots]

    client = genai.Client(api_key=api_key)

    aspect_note = "vertical 9:16" if platform in ("youtube_shorts", "tiktok", "instagram") else "horizontal 16:9"

    shots_text = "\n".join(
        f"[Slide {s.slide_index+1}, Shot {s.frame_index+1}] "
        f"Type:{s.shot_type} | Size:{s.shot_size} | Duration:{s.duration_target:.0f}s\n"
        f"  Camera: {s.camera_start} → {s.camera_movement}\n"
        f"  Action: {s.subject_action}\n"
        f"  Physics: {s.physics_elements}\n"
        f"  Mood: {s.emotional_arc}"
        for s in shot_script.shots
    )

    prompt = f"""You are a Kling AI video generation specialist writing motion prompts.

Topic: "{topic}"
Aspect ratio: {aspect_note}

Shot plan:
{shots_text}

For each shot, write a Kling AI VIDEO GENERATION PROMPT (motion only, NOT image description).

FORMAT: "[camera start position]. [camera movement direction+speed+ending state]. [subject physical action]. [physics elements]. [mood] atmosphere."

CRITICAL RULES:
1. MOTION ONLY — what physically MOVES in these 5 seconds
2. Camera movement MUST be explicit (slow push in, pan left, static locked, handheld follow, orbit right)
3. Subject action = specific physical motion (not appearance): "warriors march", "scroll unfurls", "flames leap"
4. Physics: moving elements (smoke, fabric, water, sparks, light rays flickering)
5. 30-50 words per prompt
6. NEVER describe image qualities: no "8K", "composition", "depth of field", "volumetric lighting"
7. For ATMOSPHERIC shots: gentle camera drift, ambient physics, peaceful movement
8. For STATIC_GRAPHIC shots: slow pan across the graphic, minimal motion

GOOD examples:
- "Low angle ground level. Camera slowly tilts up to reveal palace gate as torchlight flickers. Warriors march in formation through gate, armor glinting. Smoke rises from torches, silk banners sway. Tense and dramatic atmosphere."
- "Eye level, medium distance. Camera slowly pushes in to close-up of calligraphy brush. Royal scribe's hand moves deliberately across scroll, ink flowing. Paper rustles slightly. Reverent and ceremonial atmosphere."
- "Aerial high angle. Camera slowly dolls down and forward into crowd below. Thousands of people move as one, lanterns floating upward. Dawn light spreads across the scene. Epic and inspiring atmosphere."

Return JSON:
{{"motion_prompts": ["prompt for shot 1", "prompt for shot 2", ...]}}

Return ONLY valid JSON, one prompt per shot in order."""

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
        prompts = data.get("motion_prompts", [])

        # 수 맞추기
        while len(prompts) < len(shot_script.shots):
            prompts.append(_build_motion_prompt(shot_script.shots[len(prompts)]))

        logger.info(f"[PerFrameVideoPrompter] {len(prompts)}개 모션 프롬프트 생성 완료")
        return prompts[:len(shot_script.shots)]

    except Exception as e:
        logger.error(f"[PerFrameVideoPrompter] 실패, 직접 생성: {e}")
        return [_build_motion_prompt(s) for s in shot_script.shots]
