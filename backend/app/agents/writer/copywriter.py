"""
Copywriter Agent — 플랫폼별 독립 콘텐츠 생성
역할: 훅 + 리서치 → 플랫폼별 "재해석" 콘텐츠 (리포맷 ✕)
원칙: 같은 주제라도 플랫폼마다 완전히 다른 콘텐츠 (VaynerMedia 방식)
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile
from app.agents.research.agent import ResearchResult
from app.agents.research.hooksmith import HookResult


@dataclass
class PlatformContent:
    platform: str
    hook: str
    body: list[str]  # 슬라이드별 / 트윗별 / 단락별
    caption: str
    hashtags: list[str]
    cta: str  # Call to Action
    metadata: dict = field(default_factory=dict)  # 플랫폼별 추가 데이터


@dataclass
class ContentPlan:
    topic: str
    market: str
    master_narrative: str  # 전체 스토리 요약
    platform_contents: list[PlatformContent]
    thumbnail_text: str


class CopywriterAgent:
    """플랫폼별 독립 콘텐츠 생성 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile
        self.llm = get_llm_client("writing")

    async def _generate_platform_content(
        self,
        platform: str,
        topic: str,
        hook: str,
        research: ResearchResult,
        series_context: str | None = None,
    ) -> PlatformContent | None:
        """단일 플랫폼용 콘텐츠 생성 (독립 LLM 호출)"""

        # 플랫폼별 포맷 지침
        format_guides = {
            "instagram": f"""Instagram 캐러셀 (7~10 슬라이드):
- 슬라이드 1: 훅 (반드시 "{hook}" 사용)
- 슬라이드 2: 두 번째 훅 (독립적으로 알고리즘 노출 가능)
- 슬라이드 3~(N-1): 핵심 내용 (슬라이드당 포인트 1개, {self.profile.get_text_limit()})
- 마지막 슬라이드: CTA + 핵심 요약
- 해시태그: {self.profile.hashtag.count}개""",

            "youtube": f"""YouTube 롱폼 대본 (10~15분):
- 인트로: 훅 (첫 30초 안에 시청자 잡기, "{hook}")
- 구조: 문제 제기 → 해결 과정 → 핵심 인사이트 → 결론
- B-roll 큐 표시: [B-ROLL: 설명]
- 나레이션 톤: {self.profile.tone}""",

            "youtube_shorts": f"""YouTube Shorts 대본 (30~45초):
- 첫 1.5초: 패턴 인터럽트 ("{hook}")
- 핵심 포인트 1~2개만
- 마지막: 루프 유도 또는 CTA""",

            "x": f"""X 스레드 (6~8 트윗):
- 트윗 1: 훅 ("{hook}", 더보기 전 첫 줄이 전부)
- 트윗 2~(N-1): 포인트 1개씩, 250자 이내
- 마지막 트윗: 핵심 교훈 + 팔로우/북마크 CTA
- 외부 링크는 마지막 트윗에만
- 해시태그: {self.profile.hashtag.count}개 이하""",

            "linkedin": f"""LinkedIn 텍스트 포스트 (1300자 이내):
- 첫 줄: 훅 ("{hook}", "더 보기" 전에 보이는 유일한 줄)
- 짧은 단락, 줄바꿈 활용
- 개인 경험/관점 포함
- 전문적이지만 접근 가능한 톤
- CTA: 의견 요청 or 공유 유도
- 해시태그: 3~5개 (하단에 배치)""",

            "threads": f"""Threads 포스트 (500자 이내):
- 훅: "{hook}"
- 캐주얼한 톤
- 1~2개 핵심 포인트
- 이미지/캐러셀 첨부 가능""",

            "newsletter": f"""뉴스레터 (800~1500자):
- 제목: "{hook}" 변형
- 인트로: 왜 이게 중요한지 1~2문장
- 본문: 3~5개 핵심 포인트, 각각 2~3문장
- 결론: 액션 아이템 1~2개
- PS: 다음 주 예고 or 추가 리소스""",

            "naver_blog": f"""네이버 블로그 포스트 (1500~2500자):
- SEO 최적화 제목
- 소제목(H2, H3) 활용
- 핵심 키워드 자연스럽게 배치
- 이미지 설명 태그 포함
- 본문 중간에 요약 박스""",
        }

        format_guide = format_guides.get(platform, f"{platform} 플랫폼에 적합한 포맷으로")

        series_prompt = ""
        if series_context:
            series_prompt = f"\n\n시리즈 컨텍스트 (이전 회차 참조):\n{series_context}"

        prompt = f"""주제: "{topic}"
시장: {self.profile.display_name}
언어: {self.profile.language}
톤: {self.profile.tone}
정보 밀도: {self.profile.info_density}
면책 조항: {self.profile.content_rules.disclaimer_finance}
AI 표기: {self.profile.content_rules.ai_disclosure}

리서치에서 발견한 성공 구조:
{research.winning_formula.content_structure}
{series_prompt}

포맷 지침:
{format_guide}

규칙:
- 반드시 {self.profile.language}로 작성
- 톤: {self.profile.tone}
- 구체적 숫자 사용 (47.3% O, 약 50% X)
- 재테크 관련이면 면책 조항 포함
- AI 표기 포함

JSON 형식으로 응답:
{{
  "hook": "실제 사용할 훅 텍스트",
  "body": ["본문 파트1 (슬라이드/트윗/단락)", "파트2", ...],
  "caption": "캡션 (Instagram/YouTube 등)",
  "hashtags": ["해시태그1", "해시태그2"],
  "cta": "Call to Action 텍스트"
}}"""

        result = await self.llm.generate_json(prompt)
        if result:
            return PlatformContent(
                platform=platform,
                hook=result.get("hook", hook),
                body=result.get("body", []),
                caption=result.get("caption", ""),
                hashtags=result.get("hashtags", []),
                cta=result.get("cta", ""),
            )
        return None

    async def write(
        self,
        research: ResearchResult,
        hook_result: HookResult,
        target_platforms: list[str],
        series_context: str | None = None,
    ) -> ContentPlan:
        """전체 콘텐츠 생성 파이프라인"""
        logger.info(f"=== Copywriter Agent: '{research.topic}' 콘텐츠 생성 ===")
        logger.info(f"타겟 플랫폼: {', '.join(target_platforms)}")

        # 추천 훅 선택
        best_hook = hook_result.hooks[hook_result.recommended_hook_index]

        # 플랫폼별 독립 생성
        platform_contents = []
        for platform in target_platforms:
            # 플랫폼에 가장 적합한 훅 선택
            platform_hook = best_hook.text
            for hook in hook_result.hooks:
                if platform in hook.platform_fit:
                    platform_hook = hook.text
                    break

            logger.info(f"  [{platform}] 생성 중... (훅: {platform_hook[:30]}...)")
            content = await self._generate_platform_content(
                platform=platform,
                topic=research.topic,
                hook=platform_hook,
                research=research,
                series_context=series_context,
            )
            if content:
                platform_contents.append(content)
                logger.info(f"  [{platform}] 완료: {len(content.body)}개 파트")
            else:
                logger.warning(f"  [{platform}] 생성 실패")

        plan = ContentPlan(
            topic=research.topic,
            market=self.profile.market,
            master_narrative=research.winning_formula.content_structure,
            platform_contents=platform_contents,
            thumbnail_text=hook_result.thumbnail_copies[0].main_text if hook_result.thumbnail_copies else research.topic,
        )

        logger.info(f"콘텐츠 생성 완료: {len(platform_contents)}/{len(target_platforms)} 플랫폼")
        return plan
