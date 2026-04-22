"""
Watchdog Agent — 경쟁자 감시 + 민감 이벤트 감지
역할: 경쟁 계정 모니터링, 트렌드 선점, 발행 중단 서킷 브레이커
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from loguru import logger

from app.config.market_profile import MarketProfile


@dataclass
class CompetitorAlert:
    competitor: str
    platform: str
    content_preview: str
    engagement: dict
    detected_at: str


@dataclass
class SensitiveEvent:
    event_type: str  # "national_disaster", "political", "controversy"
    description: str
    severity: str  # "halt", "caution"
    detected_at: str


@dataclass
class WatchdogResult:
    competitor_alerts: list[CompetitorAlert] = field(default_factory=list)
    sensitive_events: list[SensitiveEvent] = field(default_factory=list)
    should_halt: bool = False
    halt_reason: str | None = None


class WatchdogAgent:
    """경쟁자 감시 + 민감 이벤트 감지 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile

        # 시장별 민감 키워드
        self._sensitive_keywords = {
            "ko": ["사망", "참사", "재난", "전쟁", "테러", "지진", "폭발", "대통령 탄핵"],
            "en": ["mass shooting", "terrorist attack", "earthquake", "war declared",
                    "national emergency", "assassination"],
            "ja": ["地震", "津波", "テロ", "戦争", "大災害", "非常事態"],
        }

    async def check_sensitive_events(self, news_headlines: list[str] | None = None) -> list[SensitiveEvent]:
        """민감 이벤트 감지 — 발행 서킷 브레이커"""
        events = []
        keywords = self._sensitive_keywords.get(self.profile.language, [])

        if not news_headlines:
            # TODO: 뉴스 API로 실시간 헤드라인 수집
            return events

        now = datetime.now(timezone.utc).isoformat()
        for headline in news_headlines:
            for keyword in keywords:
                if keyword in headline:
                    events.append(SensitiveEvent(
                        event_type="sensitive_news",
                        description=headline,
                        severity="halt",
                        detected_at=now,
                    ))
                    logger.warning(f"민감 이벤트 감지: {headline}")
                    break

        return events

    async def monitor_competitors(self, competitor_accounts: list[dict]) -> list[CompetitorAlert]:
        """경쟁자 계정 모니터링"""
        alerts = []
        # TODO: 각 플랫폼 API로 경쟁자 최근 콘텐츠 수집
        # 비정상적으로 높은 참여율 → 트렌드 선점 기회
        return alerts

    async def run(
        self,
        competitor_accounts: list[dict] | None = None,
        news_headlines: list[str] | None = None,
    ) -> WatchdogResult:
        """전체 감시 실행"""
        logger.info("=== Watchdog: 감시 실행 ===")

        result = WatchdogResult()

        # 민감 이벤트 체크
        result.sensitive_events = await self.check_sensitive_events(news_headlines)
        if any(e.severity == "halt" for e in result.sensitive_events):
            result.should_halt = True
            result.halt_reason = result.sensitive_events[0].description
            logger.warning(f"발행 중단: {result.halt_reason}")

        # 경쟁자 모니터링
        if competitor_accounts:
            result.competitor_alerts = await self.monitor_competitors(competitor_accounts)

        return result
