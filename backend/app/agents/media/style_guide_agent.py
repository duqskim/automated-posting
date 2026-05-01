"""
StyleGuideAgent — 영상 전체의 시각적 일관성 유지

역할:
  - 촬영 전 전체 비주얼 스타일 가이드 1회 생성
  - 모든 이미지 프롬프트에 동일한 prefix/suffix 적용
  - 캐릭터가 있으면 등장 슬라이드 전반에서 동일한 외모 유지

핵심 원칙:
  - 이미지 생성 AI는 프롬프트가 조금만 달라도 캐릭터/의상/색감이 바뀜
  - StyleGuide의 art_style_token + character_descriptions를
    모든 이미지 프롬프트 앞에 prefix로 삽입 → 일관성 보장
"""
import json
import os
import re
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class StyleGuide:
    art_style_token: str          # "Korean historical drama, Netflix Joseon, warm amber"
    world_description: str        # "Joseon dynasty (1392-1897), royal court politics"
    color_palette_hex: list[str]  # ["#C8860A", "#8B1A1A", "#1A1A2E"]
    color_description: str        # "warm amber golds, deep crimson, midnight blue"
    character_descriptions: dict[str, str]  # {name: "tall man, black gat hat, white jeogori"}
    mandatory_prefix: str         # 모든 프롬프트 앞에 추가
    mandatory_suffix: str         # 모든 프롬프트 뒤에 추가


# 기본 한국 역사 스타일 가이드 (LLM 실패 시 fallback)
_DEFAULT_STYLE = StyleGuide(
    art_style_token="Korean historical drama, Netflix Joseon style",
    world_description="Joseon dynasty Korea, 14th-19th century",
    color_palette_hex=["#C8860A", "#8B1A1A", "#1A1A2E"],
    color_description="warm amber golds, deep crimson, midnight blue shadows",
    character_descriptions={},
    mandatory_prefix="",
    mandatory_suffix=(
        "cinematic photorealistic, Korean historical drama aesthetic, "
        "warm amber and golden hour color palette, volumetric light rays, "
        "Netflix historical drama cinematography, 8K, professional photography, "
        "no text overlay, no watermarks, no logos"
    ),
)


class StyleGuideAgent:
    """영상 전체 비주얼 스타일 가이드 1회 생성"""

    async def generate(
        self,
        topic: str,
        hook: str,
        platform: str = "youtube",
        character: dict | None = None,
    ) -> StyleGuide:
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("[StyleGuideAgent] GEMINI_API_KEY 없음 — 기본 스타일 사용")
            return _DEFAULT_STYLE

        client = genai.Client(api_key=api_key)

        char_context = ""
        if character:
            char_name = character.get("name", "")
            char_visual = character.get("visual_description", "") or character.get("bible", {}).get("visual_description", "")
            if char_name and char_visual:
                char_context = f"\nHOST CHARACTER: {char_name}\nAppearance: {char_visual}\n"

        prompt = f"""You are a visual director creating a STYLE BIBLE for a video series.

Topic: "{topic}"
Hook: "{hook}"
Platform: {platform}
{char_context}

Create a concise visual style guide that ensures consistency across ALL images in this video.

For Korean historical/educational content, the mandatory aesthetic is:
- Architecture: Korean palace (경복궁-style), hanok rooftops, stone walls with curved eaves, wooden pillars
- Clothing: Hanbok, joseon-era armor, traditional Korean garments
- Landscape: Korean mountain ranges, pine forests, stone-paved roads
- NEVER European castles, Western armor, Roman columns

Return JSON:
{{
  "art_style_token": "<8-15 word style descriptor for this specific topic>",
  "world_description": "<historical period and setting, 10-20 words>",
  "color_palette_hex": ["#XXXXXX", "#XXXXXX", "#XXXXXX"],
  "color_description": "<describe the palette in words, 10-15 words>",
  "character_descriptions": {{
    "{character.get('name', '') if character else 'none'}": "<precise visual description if character exists, else omit>"
  }},
  "mandatory_prefix": "<visual context that MUST appear at start of every prompt, 15-25 words>",
  "mandatory_suffix": "<technical quality suffix for every prompt, include: cinematic photorealistic, Korean historical drama, warm amber palette, volumetric light, 8K>"
}}

Return ONLY valid JSON."""

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

            # 캐릭터 설명에서 "none" 키 제거
            char_desc = {k: v for k, v in data.get("character_descriptions", {}).items() if k != "none" and v}

            guide = StyleGuide(
                art_style_token=data.get("art_style_token", _DEFAULT_STYLE.art_style_token),
                world_description=data.get("world_description", _DEFAULT_STYLE.world_description),
                color_palette_hex=data.get("color_palette_hex", _DEFAULT_STYLE.color_palette_hex),
                color_description=data.get("color_description", _DEFAULT_STYLE.color_description),
                character_descriptions=char_desc,
                mandatory_prefix=data.get("mandatory_prefix", ""),
                mandatory_suffix=data.get("mandatory_suffix", _DEFAULT_STYLE.mandatory_suffix),
            )

            logger.info(f"[StyleGuideAgent] 스타일 가이드 완성: {guide.art_style_token}")
            if guide.character_descriptions:
                logger.info(f"  캐릭터 설명: {list(guide.character_descriptions.keys())}")
            return guide

        except Exception as e:
            logger.error(f"[StyleGuideAgent] 실패, 기본 스타일 사용: {e}")
            return _DEFAULT_STYLE
