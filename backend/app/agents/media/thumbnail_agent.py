"""
Thumbnail Agent — YouTube CTR 최적화 썸네일 생성
역할: 훅 + 리서치 결과 + 콘텐츠 플랜 → 썸네일 텍스트/시각 전략 → Imagen 4 렌더링

YouTube에서 썸네일이 하는 일:
  - 조회수의 80%는 제목+썸네일로 결정됨 (CTR)
  - 클릭율 목표: 5% 이상 (평균 2-4%)
  - 3가지 요소: 강렬한 이미지 + 짧은 텍스트 오버레이 + 감정 유발

CTR 높은 썸네일 공식:
  1. 인물 얼굴 (눈 맞춤) — 가장 효과적이나 AI 생성 어려움
  2. 숫자/통계가 포함된 텍스트 오버레이
  3. 강렬한 색상 대비 (빨강/노랑/파랑)
  4. 감정 유발 키워드 (충격, 비밀, 폭로, 최초)
  5. 전/후 비교 구도
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from loguru import logger


@dataclass
class ThumbnailSpec:
    text_overlay: str        # 썸네일에 올라갈 짧은 텍스트 (15자 이내 권장)
    sub_text: str            # 보조 텍스트
    visual_concept: str      # Imagen 4 프롬프트
    ctr_strategy: str        # CTR 전략 설명
    color_scheme: str        # "high_contrast" | "warm_pop" | "dark_premium" | "bright_clean"


async def generate_thumbnail_spec(
    topic: str,
    hook: str,
    winning_formula_thumbnail_style: str,
    language: str = "ko",
) -> ThumbnailSpec:
    """썸네일 텍스트 + 시각 컨셉 생성 (LLM)"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)

    lang_guide = {
        "ko": "Korean — target 20-35 Korean office workers interested in AI/finance",
        "en": "English — target English-speaking professionals",
        "ja": "Japanese — target Japanese tech/AI enthusiasts",
    }.get(language, "Korean")

    prompt = f"""You are a YouTube thumbnail specialist focused on maximizing CTR (click-through rate).

Topic: "{topic}"
Hook: "{hook}"
Audience: {lang_guide}
Competitor thumbnail style: "{winning_formula_thumbnail_style}"

Design a high-CTR YouTube thumbnail (1280x720, 16:9).

CTR principles:
1. Text overlay must be SHORT (under 15 characters in Korean, under 25 in English)
2. Create curiosity gap or urgency
3. Use numbers when possible ("5가지", "3배", "87%")
4. Emotional trigger words (충격, 비밀, 진짜, 처음 / shocking, secret, revealed)
5. Visual must be dramatic, not generic

Return JSON:
{{
  "text_overlay": "<main text for thumbnail, max 15 chars in Korean>",
  "sub_text": "<secondary text, max 20 chars>",
  "visual_concept": "<Imagen 4 English prompt, 60-100 words, dramatic and eye-catching>",
  "ctr_strategy": "<brief explanation of why this will get clicks>",
  "color_scheme": "high_contrast|warm_pop|dark_premium|bright_clean"
}}

For visual_concept:
- Dramatic lighting (rim light, dramatic shadows)
- Concrete compelling image (not generic)
- Bold colors that pop
- No text in the image (text overlay is separate)
- End with: "YouTube thumbnail style, 16:9, dramatic lighting, highly detailed"

Return ONLY valid JSON."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.8),
        )

        text = response.text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"JSON not found: {text[:200]}")

        data = json.loads(match.group())
        spec = ThumbnailSpec(
            text_overlay=data.get("text_overlay", hook[:15]),
            sub_text=data.get("sub_text", ""),
            visual_concept=data.get("visual_concept", f"Dramatic cinematic scene: {topic}. YouTube thumbnail style, 16:9"),
            ctr_strategy=data.get("ctr_strategy", ""),
            color_scheme=data.get("color_scheme", "high_contrast"),
        )

        logger.info(f"[ThumbnailAgent] 스펙 생성 완료 | 텍스트: '{spec.text_overlay}' | 전략: {spec.ctr_strategy}")
        return spec

    except Exception as e:
        logger.error(f"[ThumbnailAgent] 스펙 생성 실패: {e}")
        return ThumbnailSpec(
            text_overlay=hook[:15],
            sub_text=topic[:20],
            visual_concept=f"Dramatic cinematic scene about {topic}. Bold colors, high contrast. YouTube thumbnail style, 16:9",
            ctr_strategy="fallback",
            color_scheme="high_contrast",
        )


async def render_thumbnail(
    spec: ThumbnailSpec,
    output_path: Path,
    topic: str,
    language: str = "ko",
) -> Path | None:
    """
    ThumbnailSpec → Imagen 4 생성 → 파일 저장

    텍스트 오버레이는 별도 후처리 필요 (pillow 또는 ArtDirector 활용).
    현재는 Imagen으로 배경 이미지만 생성.
    """
    from app.agents.media.image_generation import generate_scene_image

    logger.info(f"[ThumbnailAgent] 썸네일 렌더링 시작: '{spec.text_overlay}'")

    result = await generate_scene_image(
        slide_text=f"{spec.text_overlay} — {topic}",
        image_prompt=spec.visual_concept,
        output_path=output_path,
        topic=topic,
        language=language,
        aspect_ratio="16:9",
    )

    if result:
        logger.info(f"[ThumbnailAgent] 저장 완료: {output_path.name}")
    else:
        logger.warning("[ThumbnailAgent] Imagen 생성 실패")

    return result


def thumbnail_spec_to_dict(spec: ThumbnailSpec) -> dict:
    return {
        "text_overlay": spec.text_overlay,
        "sub_text": spec.sub_text,
        "visual_concept": spec.visual_concept,
        "ctr_strategy": spec.ctr_strategy,
        "color_scheme": spec.color_scheme,
    }
