"""
Analyst Agent — 성과 수집 + 피드백 루프
역할: 발행된 콘텐츠 성과 추적 → winning content → few-shot 피드백
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile


@dataclass
class PostMetrics:
    platform: str
    post_id: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    bookmarks: int = 0
    click_through_rate: float = 0.0
    engagement_rate: float = 0.0


@dataclass
class PerformanceInsight:
    top_performing_hooks: list[str]
    top_performing_formats: list[str]
    improvement_suggestions: list[str]
    recommended_topics: list[str]


@dataclass
class AnalystResult:
    metrics: list[PostMetrics] = field(default_factory=list)
    insights: PerformanceInsight | None = None
    few_shot_examples: list[dict] = field(default_factory=list)  # 다음 생성 시 주입할 예시


class AnalystAgent:
    """성과 분석 + 피드백 루프 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile
        self.llm = get_llm_client("analysis")

    async def collect_metrics(self, post_ids: dict[str, str]) -> list[PostMetrics]:
        """플랫폼별 성과 지표 수집"""
        logger.info(f"=== Analyst: {len(post_ids)}개 포스트 성과 수집 ===")

        metrics = []
        # TODO: 각 플랫폼 API로 성과 수집
        # 현재는 구조만 구현

        return metrics

    async def analyze_performance(
        self, metrics: list[PostMetrics], recent_contents: list[dict]
    ) -> PerformanceInsight:
        """성과 분석 + 인사이트 추출"""
        if not metrics:
            return PerformanceInsight(
                top_performing_hooks=[],
                top_performing_formats=[],
                improvement_suggestions=["데이터 수집 후 분석 가능"],
                recommended_topics=[],
            )

        # 상위 콘텐츠 추출
        sorted_metrics = sorted(metrics, key=lambda m: m.engagement_rate, reverse=True)
        top_posts = sorted_metrics[:5]

        kpi_order = self.profile.kpi_priority.get(
            top_posts[0].platform if top_posts else "instagram",
            ["saves", "shares", "comments"],
        )

        metrics_summary = "\n".join([
            f"- [{m.platform}] 조회 {m.views}, 좋아요 {m.likes}, "
            f"저장 {m.saves}, 공유 {m.shares}, 참여율 {m.engagement_rate:.1%}"
            for m in top_posts
        ])

        prompt = f"""아래는 최근 발행된 콘텐츠의 성과 데이터입니다.
시장: {self.profile.display_name}
KPI 우선순위: {', '.join(kpi_order)}

성과 데이터:
{metrics_summary}

분석해주세요:
1. 가장 성과 좋은 훅 패턴은?
2. 어떤 포맷이 가장 잘 작동했나?
3. 개선 제안 3가지
4. 다음에 다루면 좋을 주제 3가지

JSON:
{{
  "top_performing_hooks": ["패턴1", "패턴2"],
  "top_performing_formats": ["포맷1"],
  "improvement_suggestions": ["제안1", "제안2", "제안3"],
  "recommended_topics": ["주제1", "주제2", "주제3"]
}}"""

        result = await self.llm.generate_json(prompt)
        if result:
            return PerformanceInsight(**result)

        return PerformanceInsight(
            top_performing_hooks=[],
            top_performing_formats=[],
            improvement_suggestions=["분석 실패, 수동 확인 필요"],
            recommended_topics=[],
        )

    def extract_few_shot_examples(
        self, metrics: list[PostMetrics], contents: list[dict]
    ) -> list[dict]:
        """상위 콘텐츠를 few-shot 예시로 추출 (다음 생성 시 주입)"""
        if not metrics or not contents:
            return []

        # 참여율 기준 상위 3개
        sorted_metrics = sorted(metrics, key=lambda m: m.engagement_rate, reverse=True)
        top_ids = [m.post_id for m in sorted_metrics[:3]]

        examples = []
        for content in contents:
            if content.get("post_id") in top_ids:
                examples.append({
                    "hook": content.get("hook", ""),
                    "platform": content.get("platform", ""),
                    "engagement_rate": next(
                        (m.engagement_rate for m in sorted_metrics if m.post_id == content["post_id"]),
                        0,
                    ),
                    "body_preview": content.get("body", [""])[0][:200],
                })

        logger.info(f"Few-shot 예시 {len(examples)}개 추출 (자기 진화 루프)")
        return examples

    async def run(self, post_ids: dict[str, str], recent_contents: list[dict]) -> AnalystResult:
        """전체 분석 파이프라인"""
        metrics = await self.collect_metrics(post_ids)
        insights = await self.analyze_performance(metrics, recent_contents)
        few_shots = self.extract_few_shot_examples(metrics, recent_contents)

        return AnalystResult(
            metrics=metrics,
            insights=insights,
            few_shot_examples=few_shots,
        )
