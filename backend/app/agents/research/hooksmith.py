"""
Hooksmith Agent — 훅 생성 전문
역할: winning formula 기반으로 훅 3~5개 + 썸네일 카피 생성
원칙: 훅 먼저, 콘텐츠 나중 (MrBeast 방식)
"""
import re
from dataclasses import dataclass
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile
from app.agents.research.agent import ResearchResult


def _extract_stats(text: str) -> list[str]:
    """훅 텍스트에서 숫자/통계 추출"""
    patterns = [
        r'\d+\.?\d*%',   # 87%, 47.3%
        r'\d+만\s*명',    # 10만 명
        r'\d+억',         # 100억
        r'\$[\d,]+',      # $1,000
        r'\d+ million',   # 5 million
        r'\d+ billion',   # 2 billion
    ]
    results = []
    for p in patterns:
        results.extend(re.findall(p, text, re.IGNORECASE))
    return results


def _stat_in_research(stat: str, research: ResearchResult) -> bool:
    """리서치 데이터에 해당 통계가 존재하는지 확인"""
    search_corpus = " ".join([
        " ".join(research.keywords),
        " ".join(c.title or "" for c in research.top_content),
        " ".join(c.hook_used or "" for c in research.top_content),
        " ".join(research.winning_formula.hook_patterns),
        " ".join(research.winning_formula.content_gaps),
        str(research.raw_data),
    ])
    return stat in search_corpus


@dataclass
class Hook:
    text: str
    style: str  # data, result, contrarian, curiosity, urgency
    score: float  # 0~1 (Quality Gate에서 평가)
    platform_fit: list[str]  # 어떤 플랫폼에 적합한지


@dataclass
class ThumbnailCopy:
    main_text: str
    sub_text: str | None = None
    style_note: str | None = None


@dataclass
class HookResult:
    hooks: list[Hook]
    thumbnail_copies: list[ThumbnailCopy]
    recommended_hook_index: int  # 추천 훅 인덱스


class HooksmithAgent:
    """훅 생성 전문 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile
        self.llm = get_llm_client("hooksmith")

    async def generate_hooks(self, research: ResearchResult) -> HookResult:
        """리서치 결과 기반 훅 3~5개 생성"""
        logger.info(f"=== Hooksmith Agent: '{research.topic}' 훅 생성 ===")

        hook_examples = "\n".join([f"- {h}" for h in self.profile.hook_examples])
        winning_patterns = "\n".join([f"- {p}" for p in research.winning_formula.hook_patterns])
        content_gaps = "\n".join([f"- {g}" for g in research.winning_formula.content_gaps])
        platforms = ", ".join(self.profile.active_platforms)

        LANG_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese"}
        lang_name = LANG_NAMES.get(self.profile.language, self.profile.language)

        prompt = f"""Topic: "{research.topic}"
Market: {self.profile.display_name}
Language: {lang_name}
Tone: {self.profile.tone}
Hook style: {self.profile.hook_style}
Target platforms: {platforms}

Hook patterns that work in this market:
{hook_examples}

Winning patterns from research:
{winning_patterns}

Gaps competitors are missing:
{content_gaps}

Create 5 hooks and 3 thumbnail copies based on the above.

Rules:
- Hooks must be within {self.profile.get_text_limit()}
- Each hook uses a different style (data, result, contrarian, curiosity, urgency)
- Thumbnail copy in {self.profile.thumbnail.style} style
- WRITE ENTIRELY IN {lang_name.upper()} — every word
- Numbers in hooks MUST come from the research data above — NEVER invent statistics
- If no verified number exists for this topic, use a curiosity/contrarian hook instead of a data hook
- NEVER fabricate percentages, counts, or statistics not present in research
- At least 1 hook must exploit a competitor gap

JSON format:
{{
  "hooks": [
    {{
      "text": "hook text",
      "style": "data|result|contrarian|curiosity|urgency",
      "platform_fit": ["instagram", "youtube"]
    }}
  ],
  "thumbnail_copies": [
    {{
      "main_text": "main text",
      "sub_text": "sub text (optional)",
      "style_note": "style note"
    }}
  ],
  "recommended_hook_index": 0
}}"""

        result = await self.llm.generate_json(prompt, temperature=0.9)

        if result:
            hooks = [
                Hook(
                    text=h["text"],
                    style=h.get("style", "curiosity"),
                    score=0.0,  # Quality Gate에서 평가
                    platform_fit=h.get("platform_fit", self.profile.active_platforms),
                )
                for h in result.get("hooks", [])
            ]

            thumbnail_copies = [
                ThumbnailCopy(
                    main_text=t["main_text"],
                    sub_text=t.get("sub_text"),
                    style_note=t.get("style_note"),
                )
                for t in result.get("thumbnail_copies", [])
            ]

            # 훅 팩트 검증: data 스타일 훅의 통계 수치를 리서치 데이터와 대조
            for hook in hooks:
                if hook.style == "data":
                    stats = _extract_stats(hook.text)
                    if stats:
                        unverified = [s for s in stats if not _stat_in_research(s, research)]
                        if unverified:
                            hook.score = 0.2  # 미검증 통계 → 낮은 점수
                            logger.warning(
                                f"[Hooksmith] ⚠️ 미검증 통계 발견 — '{hook.text}' / 수치: {unverified}"
                                f" → 큐리오시티/반직관 훅 사용 권장"
                            )
                        else:
                            hook.score = 0.9  # 리서치 데이터에서 확인된 수치
                    else:
                        hook.score = 0.6  # 숫자 없는 data 훅
                else:
                    hook.score = 0.7  # 비-data 스타일 (curiosity, contrarian, urgency, result)

            hook_result = HookResult(
                hooks=hooks,
                thumbnail_copies=thumbnail_copies,
                recommended_hook_index=result.get("recommended_hook_index", 0),
            )

            logger.info(f"훅 {len(hooks)}개, 썸네일 카피 {len(thumbnail_copies)}개 생성 완료")
            logger.info(f"추천 훅: [{hooks[hook_result.recommended_hook_index].style}] "
                         f"{hooks[hook_result.recommended_hook_index].text}")

            return hook_result

        # 폴백: 기본 훅
        logger.warning("LLM 훅 생성 실패, 기본 훅 사용")
        return HookResult(
            hooks=[Hook(
                text=research.topic,
                style="curiosity",
                score=0.0,
                platform_fit=self.profile.active_platforms,
            )],
            thumbnail_copies=[ThumbnailCopy(main_text=research.topic)],
            recommended_hook_index=0,
        )
