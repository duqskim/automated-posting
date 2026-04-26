"""
Bible Writer — Character Design Pipeline Stage 5

선택된 컨셉 + 비주얼 확정 후 완성된 Character Bible 작성.
Character Bible = 이 캐릭터의 모든 것을 담은 IP 설계 문서.

Role: Claude Sonnet (캐릭터 IP 문서화)
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client


@dataclass
class CharacterBible:
    # 기본 정보
    name: str
    series_name: str
    archetype: str
    tagline: str

    # 정체성
    origin_story: str            # 캐릭터의 탄생/배경 (상세)
    mission: str                 # 왜 이 콘텐츠를 만드는가 (캐릭터 내부 동기)
    worldview: str               # 세계관/철학

    # 성격 시스템
    core_personality: list[str]  # 핵심 성격 5가지
    positive_traits: list[str]   # 장점
    flaws: list[str]             # 결점 (완벽하지 않아야 인간적)
    quirks: list[str]            # 독특한 버릇/특성

    # 목소리와 어조
    voice_description: str       # 음성/어조 상세 (TTS 가이드 포함)
    vocabulary_style: str        # 어휘 선택 패턴
    phrase_patterns: list[str]   # 자주 쓰는 표현/패턴
    forbidden_phrases: list[str] # 절대 쓰지 않는 표현
    example_scripts: list[dict]  # 시나리오별 대사 예시 (situation + dialogue)

    # 비주얼 가이드
    visual_description: str      # 외형 상세 설명
    signature_elements: list[str]  # 시그니처 요소 (특정 의상, 소품 등)
    color_palette: list[str]
    base_image_prompt: str       # 확정된 이미지 생성 프롬프트

    # 콘텐츠 행동 가이드
    content_dos: list[str]       # 해야 할 것
    content_donts: list[str]     # 하지 말아야 할 것
    topic_reactions: dict        # 특정 토픽에 어떻게 반응하는가

    # 성장/진화 방향
    character_arc: str           # 장기적 캐릭터 성장 방향
    future_directions: list[str] # 향후 캐릭터 확장 아이디어


class BibleWriter:
    """Stage 5: 완성된 Character Bible 작성"""

    def __init__(self):
        self.llm = get_llm_client("character_design")  # Opus — IP 창작

    async def write(
        self,
        series_name: str,
        series_category: str,
        market: str,
        language: str,
        selected_concept: dict,      # CharacterConcept을 dict로
        selected_archetype: dict,    # ArchetypeOption을 dict로
        audience_research: dict,
        selected_image_url: str = "",
    ) -> CharacterBible | None:

        logger.info(f"[BibleWriter] '{selected_concept.get('name')}' 캐릭터 바이블 작성 시작")

        primary = next(
            (p for p in audience_research.get("profiles", []) if p.get("segment") == "Primary"),
            audience_research.get("profiles", [{}])[0] if audience_research.get("profiles") else {}
        )

        lang_note = {
            "ko": "Write all character voice/dialogue examples in Korean.",
            "en": "Write all character voice/dialogue examples in English.",
            "ja": "Write all character voice/dialogue examples in Japanese.",
        }.get(language, "Write examples in the series' primary language.")

        prompt = f"""You are a senior IP developer and character designer creating a definitive Character Bible.

This document will be the single source of truth for this character across all content, now and in the future.

SERIES: "{series_name}" ({series_category})
MARKET: {market}
LANGUAGE NOTE: {lang_note}

SELECTED CHARACTER:
Name: {selected_concept.get("name")}
Tagline: {selected_concept.get("tagline")}
Archetype: {selected_archetype.get("archetype_name")} — {selected_archetype.get("archetype_kr")}
Backstory: {selected_concept.get("backstory")}
Personality: {selected_concept.get("personality_summary")}
Speaking Style: {selected_concept.get("speaking_style")}
Visual Direction: {selected_concept.get("visual_direction")}

TARGET AUDIENCE:
{primary.get("who_they_are", "")}
They want: {primary.get("character_resonance", "")}

Create a COMPREHENSIVE Character Bible. Be specific and actionable — this document must let anyone recreate the character consistently.

Respond in JSON:
{{
  "origin_story": "Detailed 3-4 sentence origin/backstory with specific details that make the character feel real",
  "mission": "Why this character exists and what drives them to create this content — internal motivation",
  "worldview": "How they see the world, what they believe in, their philosophy",
  "core_personality": ["trait1", "trait2", "trait3", "trait4", "trait5"],
  "positive_traits": ["trait1", "trait2", "trait3"],
  "flaws": ["flaw1 — makes them relatable", "flaw2"],
  "quirks": ["quirk1 — specific behavior or habit", "quirk2", "quirk3"],
  "voice_description": "Detailed voice/tone description including pace, warmth, authority level, humor style. Include TTS direction (e.g., 'warm, measured pace, slight dramatic pause before reveals').",
  "vocabulary_style": "What words they favor, what they avoid, formality level, any cultural references",
  "phrase_patterns": [
    "Opening signature phrase they use",
    "Transition phrase",
    "Closing/CTA phrase",
    "Excitement expression",
    "Doubt/skepticism expression"
  ],
  "forbidden_phrases": ["phrase they'd never say 1", "phrase 2"],
  "example_scripts": [
    {{
      "situation": "Opening a new episode",
      "dialogue": "Full example opening in the character's voice"
    }},
    {{
      "situation": "Explaining a complex fact",
      "dialogue": "How they break down difficult information"
    }},
    {{
      "situation": "Connecting history to present day",
      "dialogue": "How they bridge past and present"
    }},
    {{
      "situation": "Fact-checking a drama scene",
      "dialogue": "How they handle corrections with humor/respect"
    }}
  ],
  "visual_description": "Complete visual description — appearance, typical outfit, setting/background, props",
  "signature_elements": ["element1 — always present in visuals", "element2"],
  "color_palette": ["primary color", "secondary color", "accent color"],
  "base_image_prompt": "Complete, detailed Midjourney-style prompt for generating consistent character images",
  "content_dos": [
    "DO: specific behavior 1",
    "DO: specific behavior 2",
    "DO: specific behavior 3",
    "DO: specific behavior 4"
  ],
  "content_donts": [
    "DON'T: specific prohibition 1",
    "DON'T: specific prohibition 2",
    "DON'T: specific prohibition 3"
  ],
  "topic_reactions": {{
    "controversial_history": "How the character handles disputed historical events",
    "drama_inaccuracies": "How they respond to K-drama historical errors — tone and approach",
    "audience_questions": "How they engage with viewer questions",
    "errors_corrections": "How they handle being wrong or correcting themselves"
  }},
  "character_arc": "Long-term vision for how this character evolves over 1-3 years of content",
  "future_directions": [
    "Future expansion idea 1 (e.g., merchandise, spinoff, live events)",
    "Future expansion idea 2",
    "Future expansion idea 3"
  ]
}}"""

        result = await self.llm.generate_json(prompt, max_tokens=16384)
        if not result:
            logger.error("[BibleWriter] LLM 응답 없음")
            return None

        bible = CharacterBible(
            name=selected_concept.get("name", ""),
            series_name=series_name,
            archetype=selected_archetype.get("archetype_name", ""),
            tagline=selected_concept.get("tagline", ""),
            origin_story=result.get("origin_story", ""),
            mission=result.get("mission", ""),
            worldview=result.get("worldview", ""),
            core_personality=result.get("core_personality", []),
            positive_traits=result.get("positive_traits", []),
            flaws=result.get("flaws", []),
            quirks=result.get("quirks", []),
            voice_description=result.get("voice_description", ""),
            vocabulary_style=result.get("vocabulary_style", ""),
            phrase_patterns=result.get("phrase_patterns", []),
            forbidden_phrases=result.get("forbidden_phrases", []),
            example_scripts=result.get("example_scripts", []),
            visual_description=result.get("visual_description", ""),
            signature_elements=result.get("signature_elements", []),
            color_palette=result.get("color_palette", []),
            base_image_prompt=result.get("base_image_prompt", selected_concept.get("image_prompt", "")),
            content_dos=result.get("content_dos", []),
            content_donts=result.get("content_donts", []),
            topic_reactions=result.get("topic_reactions", {}),
            character_arc=result.get("character_arc", ""),
            future_directions=result.get("future_directions", []),
        )

        logger.info(f"[BibleWriter] 완료 — '{bible.name}' 캐릭터 바이블 완성")
        return bible


def bible_to_dict(b: CharacterBible) -> dict:
    return {
        "name": b.name,
        "series_name": b.series_name,
        "archetype": b.archetype,
        "tagline": b.tagline,
        "origin_story": b.origin_story,
        "mission": b.mission,
        "worldview": b.worldview,
        "core_personality": b.core_personality,
        "positive_traits": b.positive_traits,
        "flaws": b.flaws,
        "quirks": b.quirks,
        "voice_description": b.voice_description,
        "vocabulary_style": b.vocabulary_style,
        "phrase_patterns": b.phrase_patterns,
        "forbidden_phrases": b.forbidden_phrases,
        "example_scripts": b.example_scripts,
        "visual_description": b.visual_description,
        "signature_elements": b.signature_elements,
        "color_palette": b.color_palette,
        "base_image_prompt": b.base_image_prompt,
        "content_dos": b.content_dos,
        "content_donts": b.content_donts,
        "topic_reactions": b.topic_reactions,
        "character_arc": b.character_arc,
        "future_directions": b.future_directions,
    }
