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

    async def _publish_youtube(
        self,
        content: PlatformContent,
        dry_run: bool = True,
        video_path: str | None = None,
        srt_paths: dict | None = None,
        metadata: dict | None = None,
    ) -> PublishResult:
        """YouTube 영상 업로드 + SRT 자막"""
        if dry_run:
            logger.info(f"[DRY RUN] YouTube 업로드: {content.hook[:50]}...")
            logger.info(f"  영상: {video_path or '없음'}")
            logger.info(f"  SRT: {list((srt_paths or {}).keys())}")
            return PublishResult(platform="youtube", success=True, post_id="dry_run")

        if not video_path:
            return PublishResult(platform="youtube", success=False, error="영상 파일 경로 없음")

        try:
            from app.agents.publisher.youtube_uploader import (
                upload_video, upload_caption, has_valid_token
            )

            if not has_valid_token():
                return PublishResult(
                    platform="youtube", success=False,
                    error="YouTube 미인증 — python -m app.agents.publisher.youtube_uploader --init-auth 실행 필요"
                )

            # 메타데이터에서 제목/설명/태그 가져오기
            meta = metadata or {}
            title = meta.get("title") or content.hook[:100]
            description_parts = [content.hook]
            if content.body:
                description_parts.append("\n" + "\n\n".join(content.body[:3]))
            if content.caption:
                description_parts.append("\n\n" + content.caption)
            description = "\n".join(description_parts)

            # 챕터 타임스탬프 있으면 설명에 추가
            if meta.get("chapters"):
                description += "\n\n" + "\n".join(meta["chapters"])

            tags = content.hashtags + (meta.get("tags") or [])

            result = await asyncio.to_thread(
                upload_video,
                video_path=video_path,
                title=title,
                description=description,
                tags=tags[:500],
                privacy="private",  # 초기 private으로 업로드 후 검토
            )

            video_id = result["video_id"]
            post_url = result["url"]

            # SRT 자막 업로드 (EN 우선)
            if srt_paths:
                for lang in ("en", "ko", "ja"):
                    srt_path = srt_paths.get(lang)
                    if srt_path:
                        try:
                            await asyncio.to_thread(
                                upload_caption,
                                video_id=video_id,
                                srt_path=srt_path,
                                language=lang,
                            )
                        except Exception as e:
                            logger.warning(f"  [YouTube] {lang} 자막 업로드 실패 (무시): {e}")

            return PublishResult(
                platform="youtube",
                success=True,
                post_id=video_id,
                post_url=post_url,
                published_at=datetime.now(timezone.utc).isoformat(),
            )

        except Exception as e:
            logger.error(f"YouTube 업로드 실패: {e}")
            return PublishResult(platform="youtube", success=False, error=str(e))

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
        video_path: str | None = None,
        srt_paths: dict | None = None,
        metadata: dict | None = None,
    ) -> PublisherResult:
        """전체 플랫폼 발행

        Args:
            video_path: 업로드할 영상 파일 경로 (YouTube용)
            srt_paths: {"en": "/path/en.srt", "ko": "/path/ko.srt"} (YouTube 자막)
            metadata: MetadataAgent 출력 (title, description, tags, chapters)
        """
        logger.info(f"=== Publisher: '{content_plan.topic}' 발행 "
                     f"{'[DRY RUN]' if dry_run else '[LIVE]'} ===")

        results = []
        for i, content in enumerate(content_plan.platform_contents):
            # 시차 발행 (첫 번째 즉시, 이후 stagger_minutes 간격)
            if i > 0 and not dry_run:
                wait = stagger_minutes * 60
                logger.info(f"시차 발행 대기: {stagger_minutes}분")
                await asyncio.sleep(wait)

            if content.platform in ("youtube", "youtube_shorts"):
                result = await self._publish_youtube(
                    content,
                    dry_run=dry_run,
                    video_path=video_path,
                    srt_paths=srt_paths,
                    metadata=metadata,
                )
            elif content.platform == "x":
                result = await self._publish_x(content, dry_run=dry_run)
            elif content.platform == "instagram":
                result = await self._publish_instagram(content, dry_run=dry_run)
            elif content.platform == "linkedin":
                result = await self._publish_linkedin(content, dry_run=dry_run)
            elif content.platform == "threads":
                result = await self._publish_threads(content, dry_run=dry_run)
            else:
                result = await self._publish_generic(content, dry_run=dry_run)

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
