"""
Researcher Agent — 주제 기반 동적 리서치
역할: 주제 → 키워드 확장 → 플랫폼별 상위 콘텐츠 분석 → winning formula 추출
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile


@dataclass
class TopContent:
    platform: str
    title: str
    url: str | None = None
    engagement: dict | None = None  # views, likes, saves, etc.
    hook_used: str | None = None
    format_notes: str | None = None


@dataclass
class WinningFormula:
    hook_patterns: list[str]
    content_structure: str
    avg_length: str
    hashtag_strategy: str
    thumbnail_style: str
    content_gaps: list[str]  # 경쟁자가 놓친 각도


@dataclass
class ResearchResult:
    topic: str
    keywords: list[str]
    top_content: list[TopContent]
    winning_formula: WinningFormula
    raw_data: dict = field(default_factory=dict)


class ResearcherAgent:
    """주제 기반 동적 리서치 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile
        self.llm = get_llm_client("research")

    async def expand_keywords(self, topic: str) -> list[str]:
        """주제 → 관련 키워드 15~20개 확장"""
        prompt = f"""주제: "{topic}"
시장: {self.profile.display_name} ({self.profile.language})
타겟 플랫폼: {', '.join(self.profile.active_platforms)}

이 주제와 관련된 검색 키워드를 15~20개 생성해주세요.
- 사람들이 실제로 검색할 법한 키워드
- 롱테일 키워드 포함
- {self.profile.language} 언어로

JSON 형식으로 응답:
{{"keywords": ["키워드1", "키워드2", ...]}}"""

        result = await self.llm.generate_json(prompt)
        if result and "keywords" in result:
            logger.info(f"키워드 확장 완료: {len(result['keywords'])}개")
            return result["keywords"]
        return [topic]

    async def analyze_top_content(self, topic: str, keywords: list[str]) -> list[TopContent]:
        """플랫폼별 상위 콘텐츠 분석"""
        platforms = self.profile.active_platforms
        platform_list = ", ".join(platforms)

        prompt = f"""주제: "{topic}"
관련 키워드: {', '.join(keywords[:10])}
분석 대상 플랫폼: {platform_list}
시장: {self.profile.display_name}

각 플랫폼에서 이 주제로 가장 성공한 콘텐츠 패턴을 분석해주세요.
실제 존재할 법한 상위 콘텐츠의 특징을 분석하세요:

JSON 형식으로 응답:
{{
  "top_content": [
    {{
      "platform": "플랫폼명",
      "title": "성공한 콘텐츠 제목/훅 예시",
      "hook_used": "사용된 훅 패턴 설명",
      "format_notes": "포맷 특징 (길이, 구조, 비주얼)",
      "engagement": {{"estimated_views": "예상 조회수 범위", "key_metric": "핵심 성과 지표"}}
    }}
  ]
}}

각 플랫폼당 2~3개, 총 {len(platforms) * 2}~{len(platforms) * 3}개를 분석해주세요."""

        result = await self.llm.generate_json(prompt)
        if result and "top_content" in result:
            contents = []
            for item in result["top_content"]:
                contents.append(TopContent(
                    platform=item.get("platform", ""),
                    title=item.get("title", ""),
                    hook_used=item.get("hook_used"),
                    format_notes=item.get("format_notes"),
                    engagement=item.get("engagement"),
                ))
            logger.info(f"상위 콘텐츠 분석 완료: {len(contents)}개")
            return contents
        return []

    async def extract_winning_formula(
        self, topic: str, top_content: list[TopContent]
    ) -> WinningFormula:
        """상위 콘텐츠에서 winning formula 추출"""
        content_summary = "\n".join([
            f"- [{c.platform}] {c.title} | 훅: {c.hook_used} | 포맷: {c.format_notes}"
            for c in top_content
        ])

        prompt = f"""주제: "{topic}"
시장: {self.profile.display_name}
훅 스타일 기본값: {self.profile.hook_style}

아래는 이 주제로 성공한 상위 콘텐츠 분석 결과입니다:
{content_summary}

이 데이터를 바탕으로 winning formula를 추출해주세요:

JSON 형식으로 응답:
{{
  "hook_patterns": ["성공한 훅 패턴 1", "패턴 2", "패턴 3"],
  "content_structure": "성공한 콘텐츠의 공통 구조 설명",
  "avg_length": "최적 길이/슬라이드 수/트윗 수",
  "hashtag_strategy": "성공한 해시태그 전략",
  "thumbnail_style": "성공한 썸네일 스타일 설명",
  "content_gaps": ["경쟁자가 놓친 각도 1", "빈틈 2", "빈틈 3"]
}}"""

        result = await self.llm.generate_json(prompt)
        if result:
            return WinningFormula(
                hook_patterns=result.get("hook_patterns", []),
                content_structure=result.get("content_structure", ""),
                avg_length=result.get("avg_length", ""),
                hashtag_strategy=result.get("hashtag_strategy", ""),
                thumbnail_style=result.get("thumbnail_style", ""),
                content_gaps=result.get("content_gaps", []),
            )
        return WinningFormula(
            hook_patterns=self.profile.hook_examples[:3],
            content_structure="",
            avg_length="",
            hashtag_strategy="",
            thumbnail_style="",
            content_gaps=[],
        )

    async def research(self, topic: str) -> ResearchResult:
        """전체 리서치 파이프라인 실행"""
        logger.info(f"=== Researcher Agent: '{topic}' 리서치 시작 ({self.profile.display_name}) ===")

        # 1. 키워드 확장
        keywords = await self.expand_keywords(topic)

        # 2. 상위 콘텐츠 분석
        top_content = await self.analyze_top_content(topic, keywords)

        # 3. Winning formula 추출
        winning_formula = await self.extract_winning_formula(topic, top_content)

        result = ResearchResult(
            topic=topic,
            keywords=keywords,
            top_content=top_content,
            winning_formula=winning_formula,
        )

        logger.info(f"리서치 완료: {len(keywords)}개 키워드, "
                     f"{len(top_content)}개 상위 콘텐츠, "
                     f"{len(winning_formula.hook_patterns)}개 훅 패턴, "
                     f"{len(winning_formula.content_gaps)}개 빈틈 발견")

        return result
