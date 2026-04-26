"""
Audience Researcher — Character Design Pipeline Stage 1

타겟 오디언스를 심층 분석한다.
  - 누가 이 콘텐츠를 보는가 (인구통계 + 심리통계)
  - 어떤 캐릭터/진행자에 반응하는가
  - 이 공간에서 성공한 채널 패턴
  - 화이트스페이스 (빈자리)

Role: Gemini Pro (대규모 분석 + 인터넷 지식 활용)
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client


@dataclass
class AudienceProfile:
    segment: str           # "Primary", "Secondary", "Tertiary"
    who_they_are: str      # 한 줄 설명
    demographics: str      # 나이/지역/직업
    psychographics: str    # 가치관/두려움/욕구
    content_behavior: str  # 어떻게 콘텐츠를 소비하는가
    character_resonance: str  # 어떤 캐릭터/진행자에 끌리는가
    platforms: list[str] = field(default_factory=list)


@dataclass
class AudienceResearch:
    series_category: str
    market: str
    profiles: list[AudienceProfile]
    competitive_landscape: str   # 성공한 유사 채널 분석
    content_gap: str             # 현재 이 공간에 없는 것
    key_insight: str             # 가장 중요한 단 하나의 인사이트
    recommended_primary: str     # 가장 집중해야 할 타겟


class AudienceResearcher:
    """Stage 1: 타겟 오디언스 심층 분석"""

    def __init__(self):
        self.llm = get_llm_client("research")

    async def research(
        self,
        series_name: str,
        series_category: str,   # history, finance, kids, drama, custom
        market: str,            # global, kr, us, jp
        language: str,          # en, ko, ja
        description: str = "",
    ) -> AudienceResearch | None:

        logger.info(f"[AudienceResearcher] '{series_name}' 오디언스 리서치 시작")

        market_context = {
            "global": "English-language YouTube content targeting international audience",
            "kr": "Korean-language SNS content targeting Korean domestic audience",
            "us": "English-language content targeting North American audience",
            "jp": "Japanese-language content targeting Japanese audience",
        }.get(market, market)

        category_context = {
            "history": "educational history storytelling content",
            "finance": "personal finance and investment education",
            "kids": "children's educational content",
            "drama": "drama fact-check and entertainment analysis",
            "science": "science and technology education",
            "custom": "general educational/entertainment content",
        }.get(series_category, series_category)

        prompt = f"""You are a world-class audience research specialist with deep expertise in YouTube content strategy and creator economics.

Series: "{series_name}"
Type: {category_context}
Distribution: {market_context}
Description: {description or "Not specified"}

Research the TARGET AUDIENCE for this content series. Think deeply about WHO actually watches this type of content and WHY.

Analyze:
1. THREE distinct audience segments (Primary / Secondary / Tertiary)
2. Real YouTube channels/creators succeeding in this space RIGHT NOW — what works for them
3. What's MISSING in this space (the gap this series could fill)
4. The single most important insight for character design

For the competitive landscape, think about channels like:
- For history: Kings & Generals, Oversimplified, Extra History, Toldinstone, History Buffs
- For Korean content: Asian Boss, VICE Asia, Seoulistic, Korea Heritage Channel
- For cross-cultural: NativLang, Langfocus, Tom Scott

Respond in JSON:
{{
  "profiles": [
    {{
      "segment": "Primary",
      "who_they_are": "one-sentence description",
      "demographics": "age range, countries, occupations",
      "psychographics": "values, fears, desires, motivations",
      "content_behavior": "how they discover and consume content, viewing habits",
      "character_resonance": "what kind of presenter/character they are drawn to — be very specific",
      "platforms": ["youtube", "reddit", ...]
    }},
    {{
      "segment": "Secondary",
      ...
    }},
    {{
      "segment": "Tertiary",
      ...
    }}
  ],
  "competitive_landscape": "Analysis of 3-4 successful channels in this space. What character/presenter strategy do they use? What works? Be specific with channel names and why they succeed.",
  "content_gap": "What NOBODY is doing well in this space right now. The specific opportunity.",
  "key_insight": "The single most important insight for designing a character that will resonate with this audience. One powerful sentence.",
  "recommended_primary": "Which of the three segments should be the primary focus and why"
}}"""

        result = await self.llm.generate_json(prompt)
        if not result:
            logger.error("[AudienceResearcher] LLM 응답 없음")
            return None

        profiles = []
        for p in result.get("profiles", []):
            profiles.append(AudienceProfile(
                segment=p.get("segment", ""),
                who_they_are=p.get("who_they_are", ""),
                demographics=p.get("demographics", ""),
                psychographics=p.get("psychographics", ""),
                content_behavior=p.get("content_behavior", ""),
                character_resonance=p.get("character_resonance", ""),
                platforms=p.get("platforms", []),
            ))

        research = AudienceResearch(
            series_category=series_category,
            market=market,
            profiles=profiles,
            competitive_landscape=result.get("competitive_landscape", ""),
            content_gap=result.get("content_gap", ""),
            key_insight=result.get("key_insight", ""),
            recommended_primary=result.get("recommended_primary", ""),
        )

        logger.info(f"[AudienceResearcher] 완료 — {len(profiles)}개 오디언스 프로파일")
        return research


def audience_research_to_dict(r: AudienceResearch) -> dict:
    return {
        "series_category": r.series_category,
        "market": r.market,
        "profiles": [
            {
                "segment": p.segment,
                "who_they_are": p.who_they_are,
                "demographics": p.demographics,
                "psychographics": p.psychographics,
                "content_behavior": p.content_behavior,
                "character_resonance": p.character_resonance,
                "platforms": p.platforms,
            }
            for p in r.profiles
        ],
        "competitive_landscape": r.competitive_landscape,
        "content_gap": r.content_gap,
        "key_insight": r.key_insight,
        "recommended_primary": r.recommended_primary,
    }
