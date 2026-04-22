"""
Publisher Agent — 멀티플랫폼 발행 + 예약 + 타임존 변환
역할: 콘텐츠 + 미디어 → 각 플랫폼 API로 발행
"""
import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from loguru import logger

from app.config.market_profile import MarketProfile
from app.agents.writer.copywriter import ContentPlan, PlatformContent
from app.agents.media.art_director import ArtDirectorResult
from app.agents.media.producer import ProducerResult


@dataclass
class PublishResult:
    platform: str
    success: bool
    post_url: str | None = None
    post_id: str | None = None
    error: str | None = None
    published_at: str | None = None
    scheduled_for: str | None = None


@dataclass
class PublisherResult:
    results: list[PublishResult] = field(default_factory=list)
    total: int = 0
    success_count: int = 0
    fail_count: int = 0


class PublisherAgent:
    """멀티플랫폼 발행 에이전트"""

    def __init__(self, market_profile: MarketProfile, sns_credentials: dict | None = None):
        self.profile = market_profile
        self.credentials = sns_credentials or {}

    async def _publish_x(self, content: PlatformContent, dry_run: bool = True) -> PublishResult:
        """X (Twitter) 스레드 발행"""
        if dry_run:
            logger.info(f"[DRY RUN] X 스레드: {len(content.body)}개 트윗")
            for i, tweet in enumerate(content.body[:3], 1):
                logger.info(f"  트윗{i}: {tweet[:60]}...")
            return PublishResult(platform="x", success=True, post_id="dry_run")

        try:
            import tweepy
            creds = self.credentials.get("x", {})
            client = tweepy.Client(
                consumer_key=creds.get("api_key"),
                consumer_secret=creds.get("api_secret"),
                access_token=creds.get("access_token"),
                access_token_secret=creds.get("access_secret"),
                wait_on_rate_limit=True,
            )

            tweets = content.body
            hashtag_line = " ".join(f"#{h}" for h in content.hashtags)
            if hashtag_line:
                tweets[-1] = f"{tweets[-1]}\n\n{hashtag_line}"

            # 첫 트윗
            first = client.create_tweet(text=tweets[0][:280])
            tweet_ids = [first.data["id"]]

            # 나머지 트윗 (리플라이 체인)
            for tweet_text in tweets[1:]:
                await asyncio.sleep(2)
                reply = client.create_tweet(
                    text=tweet_text[:280],
                    in_reply_to_tweet_id=tweet_ids[-1],
                )
                tweet_ids.append(reply.data["id"])

            return PublishResult(
                platform="x",
                success=True,
                post_id=tweet_ids[0],
                post_url=f"https://x.com/i/web/status/{tweet_ids[0]}",
                published_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            logger.error(f"X 발행 실패: {e}")
            return PublishResult(platform="x", success=False, error=str(e))

    async def _publish_instagram(self, content: PlatformContent, dry_run: bool = True) -> PublishResult:
        """Instagram 캐러셀 발행 (Cloudinary + Meta Graph API)"""
        if dry_run:
            logger.info(f"[DRY RUN] Instagram 캐러셀: {len(content.body)}장")
            return PublishResult(platform="instagram", success=True, post_id="dry_run")

        # Meta Graph API 구현 필요
        return PublishResult(platform="instagram", success=False, error="Instagram API 미구현")

    async def _publish_youtube(self, content: PlatformContent, dry_run: bool = True) -> PublishResult:
        """YouTube 영상 업로드"""
        if dry_run:
            logger.info(f"[DRY RUN] YouTube 업로드: {content.hook[:50]}...")
            return PublishResult(platform="youtube", success=True, post_id="dry_run")

        return PublishResult(platform="youtube", success=False, error="YouTube API 미구현")

    async def _publish_linkedin(self, content: PlatformContent, dry_run: bool = True) -> PublishResult:
        """LinkedIn 포스트"""
        if dry_run:
            body_text = "\n\n".join(content.body)
            logger.info(f"[DRY RUN] LinkedIn: {body_text[:100]}...")
            return PublishResult(platform="linkedin", success=True, post_id="dry_run")

        return PublishResult(platform="linkedin", success=False, error="LinkedIn API 미구현")

    async def _publish_threads(self, content: PlatformContent, dry_run: bool = True) -> PublishResult:
        """Threads 포스트"""
        if dry_run:
            logger.info(f"[DRY RUN] Threads: {content.hook[:50]}...")
            return PublishResult(platform="threads", success=True, post_id="dry_run")

        return PublishResult(platform="threads", success=False, error="Threads API 미구현")

    async def _publish_generic(self, content: PlatformContent, dry_run: bool = True) -> PublishResult:
        """기타 플랫폼 (dry_run만 지원)"""
        if dry_run:
            logger.info(f"[DRY RUN] {content.platform}: {content.hook[:50]}...")
            return PublishResult(platform=content.platform, success=True, post_id="dry_run")

        return PublishResult(
            platform=content.platform, success=False,
            error=f"{content.platform} API 미구현",
        )

    async def publish(
        self,
        content_plan: ContentPlan,
        art_result: ArtDirectorResult | None = None,
        producer_result: ProducerResult | None = None,
        dry_run: bool = True,
        stagger_minutes: int = 30,
    ) -> PublisherResult:
        """전체 플랫폼 발행"""
        logger.info(f"=== Publisher: '{content_plan.topic}' 발행 "
                     f"{'[DRY RUN]' if dry_run else '[LIVE]'} ===")

        publisher_map = {
            "x": self._publish_x,
            "instagram": self._publish_instagram,
            "youtube": self._publish_youtube,
            "youtube_shorts": self._publish_youtube,
            "linkedin": self._publish_linkedin,
            "threads": self._publish_threads,
        }

        results = []
        for i, content in enumerate(content_plan.platform_contents):
            # 시차 발행 (첫 번째 즉시, 이후 stagger_minutes 간격)
            if i > 0 and not dry_run:
                wait = stagger_minutes * 60
                logger.info(f"시차 발행 대기: {stagger_minutes}분")
                await asyncio.sleep(wait)

            publisher_fn = publisher_map.get(content.platform, self._publish_generic)
            result = await publisher_fn(content, dry_run=dry_run)
            results.append(result)

            status = "OK" if result.success else "FAIL"
            logger.info(f"  [{content.platform}] {status}"
                         f"{f' — {result.post_url}' if result.post_url else ''}")

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        final = PublisherResult(
            results=results,
            total=len(results),
            success_count=success_count,
            fail_count=fail_count,
        )

        logger.info(f"Publisher 완료: {success_count}/{len(results)} 성공")
        return final
