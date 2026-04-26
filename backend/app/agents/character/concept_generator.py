"""
Concept Generator — Character Design Pipeline Stage 3

아키타입 선택 후 구체적인 캐릭터 컨셉 3가지 생성.
이름 / 외형 방향 / 성격 / 대사 스타일 / 이미지 프롬프트 포함.

Role: Claude Sonnet (창의적 캐릭터 설계)
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client


@dataclass
class CharacterConcept:
    index: int
    name: str                        # 캐릭터 이름
    tagline: str                     # 한 줄 소개 ("The historian who makes you feel like you were there")
    backstory: str                   # 캐릭터 배경 (설정)
    personality_summary: str         # 성격 요약
    personality_traits: list[str]    # 성격 특성 목록
    speaking_style: str              # 말투/어조 상세 설명
    example_dialogues: list[str]     # 실제 대사 예시 3개
    visual_direction: str            # 외형 방향 (스타일, 시대, 분위기)
    color_palette: list[str]         # 연상 색상
    image_prompt: str                # Stable Diffusion / Midjourney 프롬프트
    why_this_concept: str            # 이 컨셉이 선택된 아키타입과 어떻게 맞는가
    audience_appeal: str             # 타겟 오디언스에 어떻게 어필하는가


@dataclass
class ConceptOptions:
    series_name: str
    archetype_name: str
    concepts: list[CharacterConcept]
    design_note: str                 # 디자이너 노트 — 세 컨셉의 방향성 차이 설명


class ConceptGenerator:
    """Stage 3: 아키타입 기반 캐릭터 컨셉 3가지 생성"""

    def __init__(self):
        self.llm = get_llm_client("writing")

    async def generate(
        self,
        series_name: str,
        series_category: str,
        market: str,
        language: str,
        selected_archetype: dict,    # ArchetypeOption을 dict로 변환한 것
        audience_research: dict,
    ) -> ConceptOptions | None:

        logger.info(f"[ConceptGenerator] '{series_name}' 캐릭터 컨셉 생성 시작")

        primary = next(
            (p for p in audience_research.get("profiles", []) if p.get("segment") == "Primary"),
            audience_research.get("profiles", [{}])[0] if audience_research.get("profiles") else {}
        )

        lang_note = {
            "ko": "The character will speak Korean. Names can be Korean or English.",
            "en": "The character will speak English. Names should feel natural in English.",
            "ja": "The character will speak Japanese. Names can be Japanese or English.",
        }.get(language, "")

        prompt = f"""You are a world-class character designer for digital media brands.

Series: "{series_name}"
Category: {series_category}
Market: {market}
Language note: {lang_note}

SELECTED ARCHETYPE:
Type: {selected_archetype.get("archetype_name")} ({selected_archetype.get("archetype_kr")})
Core Traits: {", ".join(selected_archetype.get("core_traits", []))}
Tone of Voice: {selected_archetype.get("tone_of_voice")}
Content Style: {selected_archetype.get("content_style")}
Differentiation goal: {selected_archetype.get("differentiation")}

TARGET AUDIENCE:
{primary.get("who_they_are", "")}
Character resonance they want: {primary.get("character_resonance", "")}

Generate 3 DISTINCT character concepts that all embody the selected archetype but with different visual/personality flavors.

The concepts should differ in:
- Visual aesthetic (modern vs historical vs fantastical, etc.)
- Personality flavor (serious vs playful, formal vs casual, etc.)
- Name and backstory feel

For image prompts, write detailed prompts suitable for AI image generation (Midjourney/Stable Diffusion style).

Respond in JSON:
{{
  "concepts": [
    {{
      "index": 0,
      "name": "Character Name",
      "tagline": "One-sentence character essence",
      "backstory": "2-3 sentence character background/origin story",
      "personality_summary": "2-3 sentence personality description",
      "personality_traits": ["trait1", "trait2", "trait3", "trait4", "trait5"],
      "speaking_style": "Detailed description of how they speak — rhythm, vocabulary, quirks",
      "example_dialogues": [
        "Example line 1 — in the actual language they'd speak",
        "Example line 2",
        "Example line 3"
      ],
      "visual_direction": "Detailed visual description — age, appearance, clothing style, setting, mood",
      "color_palette": ["#HEX or color name 1", "#HEX or color name 2", "#HEX or color name 3"],
      "image_prompt": "Detailed Midjourney-style prompt for generating this character. Include style, mood, lighting, composition.",
      "why_this_concept": "How this specific flavor of the archetype fits the series and differentiation goal",
      "audience_appeal": "Why this specific character will resonate with the primary audience"
    }},
    {{
      "index": 1,
      ...
    }},
    {{
      "index": 2,
      ...
    }}
  ],
  "design_note": "Explain the key differentiator between the 3 concepts so the user can make an informed choice"
}}"""

        result = await self.llm.generate_json(prompt)
        if not result:
            logger.error("[ConceptGenerator] LLM 응답 없음")
            return None

        concepts = []
        for c in result.get("concepts", []):
            concepts.append(CharacterConcept(
                index=c.get("index", len(concepts)),
                name=c.get("name", ""),
                tagline=c.get("tagline", ""),
                backstory=c.get("backstory", ""),
                personality_summary=c.get("personality_summary", ""),
                personality_traits=c.get("personality_traits", []),
                speaking_style=c.get("speaking_style", ""),
                example_dialogues=c.get("example_dialogues", []),
                visual_direction=c.get("visual_direction", ""),
                color_palette=c.get("color_palette", []),
                image_prompt=c.get("image_prompt", ""),
                why_this_concept=c.get("why_this_concept", ""),
                audience_appeal=c.get("audience_appeal", ""),
            ))

        options = ConceptOptions(
            series_name=series_name,
            archetype_name=selected_archetype.get("archetype_name", ""),
            concepts=concepts,
            design_note=result.get("design_note", ""),
        )

        logger.info(f"[ConceptGenerator] 완료 — {len(concepts)}개 컨셉 생성")
        return options


def concept_options_to_dict(o: ConceptOptions) -> dict:
    return {
        "series_name": o.series_name,
        "archetype_name": o.archetype_name,
        "concepts": [
            {
                "index": c.index,
                "name": c.name,
                "tagline": c.tagline,
                "backstory": c.backstory,
                "personality_summary": c.personality_summary,
                "personality_traits": c.personality_traits,
                "speaking_style": c.speaking_style,
                "example_dialogues": c.example_dialogues,
                "visual_direction": c.visual_direction,
                "color_palette": c.color_palette,
                "image_prompt": c.image_prompt,
                "why_this_concept": c.why_this_concept,
                "audience_appeal": c.audience_appeal,
            }
            for c in o.concepts
        ],
        "design_note": o.design_note,
    }
