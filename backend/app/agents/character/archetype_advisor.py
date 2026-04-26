"""
Archetype Advisor — Character Design Pipeline Stage 2

오디언스 리서치 결과를 바탕으로 3가지 아키타입 추천.
Jung의 12 아키타입 + 현대 콘텐츠 크리에이터 분석 결합.

Role: Claude Sonnet (창의적 판단 + 캐릭터 감각)
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client


@dataclass
class ArchetypeOption:
    index: int
    archetype_name: str          # "The Sage", "The Explorer", "The Jester"
    archetype_kr: str            # "현자", "탐험가", "광대"
    why_fits: str                # 이 오디언스에 왜 맞는가
    core_traits: list[str]       # 핵심 성격 특성 3~5개
    tone_of_voice: str           # 말투/어조 방향
    content_style: str           # 콘텐츠 스타일
    real_examples: list[str]     # 실존 채널/크리에이터 예시
    strengths: list[str]         # 강점
    risks: list[str]             # 위험/단점
    fit_score: int               # 오디언스 적합도 0~100
    differentiation: str         # 경쟁 채널과 차별화 포인트


@dataclass
class ArchetypeAdvice:
    series_name: str
    options: list[ArchetypeOption]
    recommendation: str          # 어떤 아키타입을 추천하는가 + 이유
    hybrid_note: str             # 두 아키타입 혼합 가능성


class ArchetypeAdvisor:
    """Stage 2: 오디언스 맞춤 아키타입 3가지 추천"""

    def __init__(self):
        self.llm = get_llm_client("writing")  # Claude — 캐릭터 창의성

    async def advise(
        self,
        series_name: str,
        series_category: str,
        market: str,
        audience_research: dict,   # AudienceResearch를 dict로 변환한 것
    ) -> ArchetypeAdvice | None:

        logger.info(f"[ArchetypeAdvisor] '{series_name}' 아키타입 분석 시작")

        # 오디언스 리서치 핵심 요약
        primary = next(
            (p for p in audience_research.get("profiles", []) if p.get("segment") == "Primary"),
            audience_research.get("profiles", [{}])[0] if audience_research.get("profiles") else {}
        )

        prompt = f"""You are a character design expert specializing in digital content creators and brand mascots.

Series: "{series_name}"
Category: {series_category}
Market: {market}

AUDIENCE RESEARCH SUMMARY:
Primary Audience: {primary.get("who_they_are", "")}
Demographics: {primary.get("demographics", "")}
Psychographics: {primary.get("psychographics", "")}
Character Resonance: {primary.get("character_resonance", "")}

Competitive Landscape: {audience_research.get("competitive_landscape", "")}
Content Gap: {audience_research.get("content_gap", "")}
Key Insight: {audience_research.get("key_insight", "")}

Based on Jung's 12 archetypes (Innocent, Everyman, Hero, Outlaw, Explorer, Creator, Ruler, Magician, Lover, Caregiver, Jester, Sage) and modern content creator analysis, recommend 3 distinct archetype options for this series' host character.

Each archetype must:
1. Directly address the character resonance the audience wants
2. Fill the identified content gap
3. Be differentiated from existing competitors
4. Be executable as a consistent on-camera/on-page persona

Respond in JSON:
{{
  "options": [
    {{
      "index": 0,
      "archetype_name": "The Sage",
      "archetype_kr": "현자",
      "why_fits": "Why this archetype fits THIS specific audience and market",
      "core_traits": ["trait1", "trait2", "trait3", "trait4"],
      "tone_of_voice": "Specific description of how this character speaks and communicates",
      "content_style": "How content would be structured and delivered with this archetype",
      "real_examples": ["Channel/Creator Name — why they exemplify this", "..."],
      "strengths": ["strength1", "strength2", "strength3"],
      "risks": ["risk1", "risk2"],
      "fit_score": 85,
      "differentiation": "What makes this DIFFERENT from the competitor channels mentioned"
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
  "recommendation": "Recommend ONE specific option and explain why it's the best fit for this series right now. Be decisive.",
  "hybrid_note": "If there's a compelling case for blending two archetypes, describe it. Otherwise state 'Pure archetype recommended'."
}}"""

        result = await self.llm.generate_json(prompt)
        if not result:
            logger.error("[ArchetypeAdvisor] LLM 응답 없음")
            return None

        options = []
        for o in result.get("options", []):
            options.append(ArchetypeOption(
                index=o.get("index", len(options)),
                archetype_name=o.get("archetype_name", ""),
                archetype_kr=o.get("archetype_kr", ""),
                why_fits=o.get("why_fits", ""),
                core_traits=o.get("core_traits", []),
                tone_of_voice=o.get("tone_of_voice", ""),
                content_style=o.get("content_style", ""),
                real_examples=o.get("real_examples", []),
                strengths=o.get("strengths", []),
                risks=o.get("risks", []),
                fit_score=o.get("fit_score", 0),
                differentiation=o.get("differentiation", ""),
            ))

        advice = ArchetypeAdvice(
            series_name=series_name,
            options=options,
            recommendation=result.get("recommendation", ""),
            hybrid_note=result.get("hybrid_note", ""),
        )

        logger.info(f"[ArchetypeAdvisor] 완료 — {len(options)}개 아키타입 옵션")
        return advice


def archetype_advice_to_dict(a: ArchetypeAdvice) -> dict:
    return {
        "series_name": a.series_name,
        "options": [
            {
                "index": o.index,
                "archetype_name": o.archetype_name,
                "archetype_kr": o.archetype_kr,
                "why_fits": o.why_fits,
                "core_traits": o.core_traits,
                "tone_of_voice": o.tone_of_voice,
                "content_style": o.content_style,
                "real_examples": o.real_examples,
                "strengths": o.strengths,
                "risks": o.risks,
                "fit_score": o.fit_score,
                "differentiation": o.differentiation,
            }
            for o in a.options
        ],
        "recommendation": a.recommendation,
        "hybrid_note": a.hybrid_note,
    }
