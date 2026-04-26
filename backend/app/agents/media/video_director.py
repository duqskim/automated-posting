"""
Video Director Agent — 씬별 시각 연출 강화
역할: ImagePrompter가 생성한 기본 프롬프트 + VideoPlan의 샷 스펙 →
      영화적 연출이 추가된 Imagen/Veo 최적화 프롬프트

일반 영상 제작에서 촬영감독(DOP)이 하는 일:
  1. 각 씬의 조명 방향 결정 (역광, 측광, 정면광)
  2. 색 보정 방향 (LUT 느낌)
  3. 카메라 앵글 (앙각, 부감, 아이레벨)
  4. 화면 구도 (삼분할, 황금비율, 중앙 구도)
  5. 시각적 은유 (데이터 → 실물 오브젝트로 표현 등)
"""
import json
import os
import re
from loguru import logger

from app.agents.media.video_planner import VideoPlan, ShotSpec


async def enhance_prompts_with_direction(
    base_prompts: list[str],
    video_plan: VideoPlan,
    topic: str,
) -> list[str]:
    """
    기본 Imagen 프롬프트 + 샷 스펙 → 영화적 연출 추가된 최종 프롬프트

    Args:
        base_prompts: ImagePrompter가 생성한 기본 프롬프트
        video_plan: VideoPlannerAgent가 생성한 샷 플랜
        topic: 콘텐츠 주제

    Returns:
        연출 강화된 프롬프트 목록 (base_prompts와 동일 길이)
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)

    # 샷 스펙을 인덱스로 빠르게 조회
    shot_map = {s.slide_index: s for s in video_plan.shots}

    # 프롬프트 + 스펙 묶음 생성
    pairs = []
    for i, base in enumerate(base_prompts):
        shot = shot_map.get(i)
        pairs.append({
            "index": i,
            "base_prompt": base,
            "camera_movement": shot.camera_movement if shot else "static",
            "mood": shot.mood if shot else "informative",
            "transition": shot.transition if shot else "cut",
        })

    pairs_text = json.dumps(pairs, ensure_ascii=False, indent=2)

    prompt = f"""You are a cinematographer (DOP) enhancing AI image generation prompts for a YouTube video.

Overall video style: {video_plan.visual_style}
Color theme: {video_plan.color_theme}
Topic: "{topic}"

Base prompts with shot specs:
{pairs_text}

For each prompt, add cinematographic direction without changing the core subject:
1. Lighting: "golden hour side lighting" / "dramatic rim lighting" / "soft diffused studio light" / "neon cyberpunk lighting"
2. Camera angle: "low angle looking up" / "eye level" / "overhead bird's eye" / "Dutch angle"
3. Color grading: "warm amber tones" / "cool blue steel" / "high contrast black and white" / "vibrant saturated colors"
4. Lens effect: "shallow depth of field, bokeh background" / "wide angle lens, slight distortion" / "telephoto compression"
5. Match camera_movement hint into the prompt description

Color theme guidance:
- warm: golden hour, amber, orange tones
- cool: blue steel, cyan, cold white
- high_contrast: deep shadows, bright highlights
- vibrant: saturated colors, bold palette
- neutral: clean, natural, minimal

Return JSON:
{{"enhanced_prompts": ["<enhanced prompt for index 0>", "<enhanced prompt for index 1>", ...]}}

Rules:
- Keep each prompt under 120 words
- Always end with: "photorealistic, 8K, professional cinematography"
- Return ONLY valid JSON"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5),
        )

        text = response.text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"JSON not found: {text[:200]}")

        data = json.loads(match.group())
        enhanced = data.get("enhanced_prompts", [])

        # 길이 맞추기
        while len(enhanced) < len(base_prompts):
            enhanced.append(base_prompts[len(enhanced)])

        logger.info(f"[VideoDirectorAgent] {len(enhanced)}개 프롬프트 연출 강화 완료 (스타일: {video_plan.visual_style})")
        return enhanced[:len(base_prompts)]

    except Exception as e:
        logger.error(f"[VideoDirectorAgent] 실패, 기본 프롬프트 사용: {e}")
        return base_prompts


def apply_shot_spec_to_veo_prompt(base_prompt: str, shot: ShotSpec) -> str:
    """단일 씬: Veo 모션 프롬프트에 샷 스펙 반영"""
    movement_map = {
        "slow_zoom_in": "slow cinematic zoom in",
        "pan_left": "smooth pan left",
        "pan_right": "smooth pan right",
        "static": "static locked-off shot",
        "dolly_forward": "dolly push forward",
        "handheld": "subtle handheld movement",
    }
    movement_desc = movement_map.get(shot.camera_movement, "smooth camera movement")

    mood_map = {
        "energetic": "dynamic energy, vibrant",
        "contemplative": "meditative, slow atmosphere",
        "dramatic": "dramatic tension, cinematic",
        "informative": "clear, professional, informative",
        "inspiring": "uplifting, hopeful, inspiring",
    }
    mood_desc = mood_map.get(shot.mood, "professional")

    return (
        f"{base_prompt.rstrip('.')}. "
        f"{movement_desc}, {mood_desc}. "
        "High quality, photorealistic video."
    )
