"""
Producer Agent — 영상 제작 (숏폼 + 롱폼)
역할: 나레이션(ElevenLabs) → 클립 제작(moviepy) → 롱폼/숏폼 조립
"""
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from app.settings import settings
from app.config.market_profile import MarketProfile
from app.agents.writer.copywriter import ContentPlan
from app.agents.media.art_director import ArtDirectorResult, ImageAsset

OUTPUT_DIR = Path(__file__).parents[3] / "output" / "videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = Path(__file__).parents[3] / "output" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AudioAsset:
    file_path: Path
    duration_sec: float
    text: str
    section_index: int


@dataclass
class VideoAsset:
    file_path: Path
    duration_sec: float
    video_type: str  # "longform", "shortform", "clip"
    platform: str
    width: int
    height: int


@dataclass
class ProducerResult:
    audio_files: list[AudioAsset] = field(default_factory=list)
    video_files: list[VideoAsset] = field(default_factory=list)
    longform: VideoAsset | None = None
    shortform: VideoAsset | None = None


class ProducerAgent:
    """영상 제작 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile

    async def generate_narration(
        self, texts: list[str], project_slug: str
    ) -> list[AudioAsset]:
        """ElevenLabs TTS로 나레이션 생성"""
        if not settings.elevenlabs_api_key:
            logger.warning("ElevenLabs API 키 없음, 나레이션 스킵")
            return []

        audio_assets = []

        try:
            from elevenlabs import AsyncElevenLabs

            client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)

            # 언어별 기본 보이스 ID
            voice_map = {
                "ko": "jBpfAIEEiiSp5FdERfwz",  # Korean voice
                "en": "JBFqnCBsd6RMkjVDRZzb",   # English voice
                "ja": "bIHbv24MWmeRgasZH58o",    # Japanese voice
            }
            voice_id = voice_map.get(self.profile.language, voice_map["en"])

            for i, text in enumerate(texts):
                if not text.strip():
                    continue

                audio = await client.text_to_speech.convert(
                    voice_id=voice_id,
                    text=text,
                    model_id="eleven_multilingual_v2",
                )

                filename = AUDIO_DIR / f"{project_slug}_narration_{i+1:02d}.mp3"
                audio_bytes = b""
                async for chunk in audio:
                    audio_bytes += chunk

                filename.write_bytes(audio_bytes)

                audio_assets.append(AudioAsset(
                    file_path=filename,
                    duration_sec=len(audio_bytes) / 16000,  # 대략적 추정
                    text=text[:100],
                    section_index=i,
                ))
                logger.info(f"나레이션 {i+1}/{len(texts)} 생성: {filename.name}")

        except ImportError:
            logger.warning("elevenlabs 패키지 미설치, 나레이션 스킵")
        except Exception as e:
            logger.error(f"나레이션 생성 실패: {e}")

        return audio_assets

    async def assemble_video(
        self,
        images: list[ImageAsset],
        audio_files: list[AudioAsset],
        project_slug: str,
        video_type: str = "longform",
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> VideoAsset | None:
        """이미지 + 나레이션 → 영상 조립"""
        try:
            from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
        except ImportError:
            logger.warning("moviepy 미설치, 영상 조립 스킵")
            return None

        if not images:
            logger.warning("이미지 없음, 영상 조립 스킵")
            return None

        clips = []
        default_duration = 4.0  # 나레이션 없을 때 기본 슬라이드 지속 시간

        for i, img in enumerate(images):
            duration = default_duration
            audio_clip = None

            # 매칭되는 나레이션이 있으면 그 길이에 맞춤
            if i < len(audio_files) and audio_files[i].file_path.exists():
                try:
                    audio_clip = AudioFileClip(str(audio_files[i].file_path))
                    duration = audio_clip.duration + 0.5  # 여유 0.5초
                except Exception:
                    pass

            # 이미지 클립 생성 (Ken Burns 효과: 살짝 줌인)
            clip = (
                ImageClip(str(img.file_path))
                .resized((width, height))
                .with_duration(duration)
            )

            if audio_clip:
                clip = clip.with_audio(audio_clip)

            clips.append(clip)

        if not clips:
            return None

        # 전체 영상 조립
        final = concatenate_videoclips(clips, method="compose")

        filename = OUTPUT_DIR / f"{project_slug}_{video_type}.mp4"

        # 비동기로 렌더링 (blocking 작업)
        await asyncio.to_thread(
            final.write_videofile,
            str(filename),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )

        total_duration = sum(c.duration for c in clips)
        logger.info(f"영상 조립 완료: {filename.name} ({total_duration:.1f}초)")

        # 메모리 정리
        for clip in clips:
            clip.close()
        final.close()

        return VideoAsset(
            file_path=filename,
            duration_sec=total_duration,
            video_type=video_type,
            platform="all",
            width=width,
            height=height,
        )

    async def produce(
        self,
        content_plan: ContentPlan,
        art_result: ArtDirectorResult,
        project_slug: str,
    ) -> ProducerResult:
        """전체 영상 제작 파이프라인"""
        logger.info(f"=== Producer: '{content_plan.topic}' 영상 제작 시작 ===")

        result = ProducerResult()

        # 1. 나레이션 생성 (마스터 스크립트에서)
        narration_texts = []
        for content in content_plan.platform_contents:
            if content.platform in ("youtube", "youtube_shorts", "tiktok"):
                narration_texts = content.body
                break

        if not narration_texts:
            # 첫 번째 플랫폼 콘텐츠에서 텍스트 추출
            if content_plan.platform_contents:
                narration_texts = content_plan.platform_contents[0].body

        result.audio_files = await self.generate_narration(narration_texts, project_slug)

        # 2. 롱폼 영상 (세로형 - YouTube Shorts/Reels/TikTok 겸용)
        if art_result.slides:
            result.longform = await self.assemble_video(
                images=art_result.slides,
                audio_files=result.audio_files,
                project_slug=project_slug,
                video_type="longform",
                width=1080,
                height=1920,
            )
            if result.longform:
                result.video_files.append(result.longform)

        # 3. 숏폼 (훅 + 핵심 1~2개만 — 30~45초)
        if len(art_result.slides) >= 3:
            short_slides = [art_result.slides[0]]  # 훅
            short_slides.extend(art_result.slides[1:3])  # 핵심 2개
            short_audio = result.audio_files[:3] if result.audio_files else []

            result.shortform = await self.assemble_video(
                images=short_slides,
                audio_files=short_audio,
                project_slug=project_slug,
                video_type="shortform",
                width=1080,
                height=1920,
            )
            if result.shortform:
                result.video_files.append(result.shortform)

        logger.info(f"Producer 완료: 나레이션 {len(result.audio_files)}개, "
                     f"영상 {len(result.video_files)}개")
        return result
