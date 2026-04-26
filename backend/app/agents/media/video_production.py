"""
VideoProductionAgent — Veo (Google Flow) + ElevenLabs + moviepy 영상 제작

파이프라인:
  1. scene_clips: 슬라이드별 image_prompt → Veo API → .mp4 클립
  2. narrations: 슬라이드 텍스트 → ElevenLabs TTS → .mp3
  3. assemble: 클립 + 음성 + 자막 → 풀 영상 + 쇼츠
"""
import asyncio
import os
import time
from pathlib import Path
from loguru import logger

OUTPUT_DIR = Path(__file__).parents[3] / "output" / "video"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CLIPS_DIR = OUTPUT_DIR / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = OUTPUT_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ─── Veo 씬 클립 생성 ────────────────────────────────────────

def _veo_motion_prompt(image_prompt: str, slide_text: str) -> str:
    """이미지 방향 + 슬라이드 텍스트 → Veo 모션 프롬프트"""
    base = image_prompt.strip() if image_prompt.strip() else slide_text[:100]
    return (
        f"{base}. "
        "Cinematic camera movement, slow smooth pan or zoom, "
        "dynamic lighting transitions, high quality, photorealistic video"
    )


async def generate_veo_clip(
    image_path: Path,
    image_prompt: str,
    slide_text: str,
    output_path: Path,
    aspect_ratio: str = "16:9",
    duration_seconds: int = 6,
) -> Path | None:
    """Veo 2 이미지→영상 클립 생성 (image-to-video)"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")

    client = genai.Client(api_key=api_key)

    prompt = _veo_motion_prompt(image_prompt, slide_text)
    logger.info(f"  [Veo] 클립 생성: {prompt[:70]}...")

    try:
        img_bytes = image_path.read_bytes()

        # sync 호출을 thread pool에서 실행 (이벤트 루프 블로킹 방지)
        operation = await asyncio.to_thread(
            client.models.generate_videos,
            model="veo-2.0-generate-001",
            prompt=prompt,
            image=types.Image(image_bytes=img_bytes, mime_type="image/jpeg"),
            config=types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_seconds,
                number_of_videos=1,
                person_generation="allow_adult",
            ),
        )

        # 폴링 (최대 5분)
        max_wait = 300
        waited = 0
        while not operation.done:
            await asyncio.sleep(10)
            waited += 10
            operation = await asyncio.to_thread(client.operations.get, operation)
            logger.info(f"    [Veo] 대기 중... {waited}s")
            if waited >= max_wait:
                logger.warning("  [Veo] 타임아웃")
                return None

        if operation.error:
            logger.error(f"  [Veo] 에러: {operation.error}")
            return None

        videos = operation.response.generated_videos if operation.response else []
        if not videos:
            logger.warning("  [Veo] 생성된 영상 없음")
            return None

        video = videos[0].video
        if video.video_bytes:
            output_path.write_bytes(video.video_bytes)
            logger.info(f"  [Veo] 저장 (bytes): {output_path.name} ({len(video.video_bytes)//1024}KB)")
            return output_path
        elif video.uri:
            # URI 다운로드 (httpx로 SSL 인증서 문제 우회)
            import httpx
            async with httpx.AsyncClient(verify=False, follow_redirects=True) as http:
                resp = await http.get(video.uri, headers={"X-Goog-Api-Key": api_key})
                resp.raise_for_status()
                output_path.write_bytes(resp.content)
            logger.info(f"  [Veo] 저장 (URI): {output_path.name} ({len(resp.content)//1024}KB)")
            return output_path

        return None

    except Exception as e:
        logger.error(f"  [Veo] 실패: {e}")
        return None


# ─── ElevenLabs TTS ─────────────────────────────────────────

async def generate_tts(
    text: str,
    output_path: Path,
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Rachel (기본)
) -> Path | None:
    """ElevenLabs TTS로 나레이션 생성"""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        logger.warning("  [TTS] ELEVENLABS_API_KEY 없음 — TTS 스킵")
        return None

    try:
        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=api_key)
        audio = client.generate(
            text=text,
            voice=voice_id,
            model="eleven_multilingual_v2",
        )

        audio_bytes = b"".join(audio) if hasattr(audio, "__iter__") else audio
        output_path.write_bytes(audio_bytes)
        logger.info(f"  [TTS] 저장: {output_path.name}")
        return output_path

    except Exception as e:
        logger.error(f"  [TTS] 실패: {e}")
        return None


# ─── moviepy 조립 ────────────────────────────────────────────

def assemble_video(
    clip_paths: list[Path],
    audio_paths: list[Path | None],
    slide_texts: list[str],
    output_path: Path,
    shorts_path: Path | None = None,
    shorts_slides: int = 3,
) -> dict:
    """클립 + 음성 + 자막 → 풀 영상 + (선택) 쇼츠"""
    from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, TextClip, CompositeVideoClip, vfx

    logger.info(f"  [Assembly] 클립 {len(clip_paths)}개 조립 시작")

    segments = []
    for i, clip_path in enumerate(clip_paths):
        if not clip_path or not clip_path.exists():
            logger.warning(f"  [Assembly] 클립 {i+1} 없음 — 스킵")
            continue

        try:
            clip = VideoFileClip(str(clip_path))

            # 음성 오버레이
            audio_path = audio_paths[i] if i < len(audio_paths) else None
            if audio_path and audio_path.exists():
                audio = AudioFileClip(str(audio_path))
                # 클립 길이를 오디오에 맞게 조정
                if audio.duration > clip.duration:
                    # moviepy v2: loop() 제거됨 → vfx.Loop 사용
                    clip = clip.with_effects([vfx.Loop(duration=audio.duration)])
                else:
                    audio = audio.with_duration(clip.duration)
                clip = clip.with_audio(audio)

            # 자막 오버레이
            text = slide_texts[i] if i < len(slide_texts) else ""
            if text:
                try:
                    txt = TextClip(
                        text=text[:80],
                        font_size=36,
                        color="white",
                        stroke_color="black",
                        stroke_width=2,
                        method="caption",
                        size=(clip.w - 80, None),
                    ).with_position(("center", clip.h - 150)).with_duration(clip.duration)
                    clip = CompositeVideoClip([clip, txt])
                except Exception as e:
                    logger.warning(f"  [Assembly] 자막 오버레이 실패 (폰트 문제): {e}")

            segments.append(clip)
        except Exception as e:
            logger.error(f"  [Assembly] 클립 {i+1} 처리 실패: {e}")

    if not segments:
        return {"error": "조립할 클립 없음"}

    # 풀 영상 합치기
    final = concatenate_videoclips(segments, method="compose")
    final.write_videofile(
        str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None,
        ffmpeg_params=["-movflags", "faststart"],
    )
    logger.info(f"  [Assembly] 풀 영상 저장: {output_path.name} ({final.duration:.1f}초)")

    result = {
        "full_video": str(output_path),
        "duration": round(final.duration, 1),
        "clips_count": len(segments),
    }

    # 쇼츠 버전 (앞부분 N개 슬라이드)
    if shorts_path and len(segments) > shorts_slides:
        try:
            shorts = concatenate_videoclips(segments[:shorts_slides], method="compose")
            shorts.write_videofile(
                str(shorts_path), fps=24, codec="libx264", audio_codec="aac", logger=None,
                ffmpeg_params=["-movflags", "faststart"],
            )
            result["shorts_video"] = str(shorts_path)
            result["shorts_duration"] = round(shorts.duration, 1)
            logger.info(f"  [Assembly] 쇼츠 저장: {shorts_path.name} ({shorts.duration:.1f}초)")
        except Exception as e:
            logger.warning(f"  [Assembly] 쇼츠 생성 실패: {e}")

    return result


# ─── 통합 실행 ───────────────────────────────────────────────

async def produce_video(
    topic: str,
    platform: str,
    slide_texts: list[str],
    image_prompts: list[str],
    scene_image_paths: list[str],  # Step 4에서 생성된 씬 이미지 경로
    aspect_ratio: str = "16:9",
    tts_voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    with_tts: bool = False,
    tts_provider: str = "none",  # "none" | "gemini" | "elevenlabs"
) -> dict:
    """
    Step 4 씬 이미지 → Veo 클립 → moviepy 조립 → 영상

    반환:
        {
          "full_video": "/path/to/full.mp4",
          "shorts_video": "/path/to/shorts.mp4",
          "clip_paths": [...],
          "duration": 42.5,
        }
    """
    import re
    slug = re.sub(r"[^\w]", "_", topic, flags=re.ASCII)[:25]

    logger.info(f"=== VideoProduction: '{topic}' [{platform}] {len(slide_texts)}슬라이드 ===")

    # Step 1: 씬 이미지 → Veo 클립 (순차 — 병렬 시 API rate limit)
    generated_clips = []
    for i, (text, prompt) in enumerate(zip(slide_texts, image_prompts)):
        clip_path = CLIPS_DIR / f"{slug}_{platform}_{i:02d}.mp4"

        # 이미 생성된 클립 재사용
        if clip_path.exists() and clip_path.stat().st_size > 0:
            logger.info(f"  [Veo] 클립 {i+1} 재사용: {clip_path.name}")
            generated_clips.append(clip_path)
            continue

        # 해당 슬라이드의 씬 이미지 찾기
        image_path = None
        if i < len(scene_image_paths) and scene_image_paths[i]:
            p = Path(scene_image_paths[i])
            if p.exists():
                image_path = p

        if not image_path:
            logger.warning(f"  [Veo] 씬 이미지 없음 ({i+1}번) — 스킵")
            generated_clips.append(None)
            continue

        result = await generate_veo_clip(
            image_path=image_path,
            image_prompt=prompt,
            slide_text=text,
            output_path=clip_path,
            aspect_ratio=aspect_ratio,
        )
        generated_clips.append(result)

    logger.info(f"  [Step 1] Veo 클립 완료: {sum(1 for c in generated_clips if c)}개")

    # Step 2: TTS 나레이션
    audio_paths: list[Path | None] = [None] * len(slide_texts)
    if tts_provider == "gemini":
        logger.info(f"  [Step 2] Gemini TTS {len(slide_texts)}개 생성...")
        from app.agents.media.tts_gemini import generate_narrations_gemini
        audio_paths = await generate_narrations_gemini(
            slide_texts=slide_texts,
            slug=slug,
            platform=platform,
        )
    elif tts_provider == "elevenlabs" or with_tts:
        logger.info(f"  [Step 2] ElevenLabs TTS {len(slide_texts)}개 생성...")
        tts_tasks = []
        for i, text in enumerate(slide_texts):
            path = AUDIO_DIR / f"{slug}_{platform}_{i:02d}.mp3"
            tts_tasks.append(generate_tts(text, path, voice_id=tts_voice_id))
        audio_paths = list(await asyncio.gather(*tts_tasks))

    # Step 3: moviepy 조립
    logger.info("  [Step 3] 영상 조립...")
    full_path = OUTPUT_DIR / f"{slug}_{platform}_full.mp4"
    shorts_path = OUTPUT_DIR / f"{slug}_{platform}_shorts.mp4"

    # moviepy는 CPU 집약적 동기 함수 → thread pool에서 실행
    result = await asyncio.to_thread(
        assemble_video,
        clip_paths=[c for c in generated_clips if c],
        audio_paths=audio_paths,
        slide_texts=slide_texts,
        output_path=full_path,
        shorts_path=shorts_path,
    )

    result["clip_paths"] = [str(p) for p in generated_clips if p]

    logger.info(f"=== VideoProduction 완료: {result.get('full_video', 'FAILED')} ===")
    return result
