"""
VideoProductionAgent — Kling AI + ElevenLabs + ffmpeg 영상 제작

파이프라인:
  1. scene_clips: 슬라이드별 image_prompt → Kling AI image-to-video → .mp4 클립
  2. narrations: 슬라이드 텍스트 → Gemini/ElevenLabs TTS → .mp3
  3. assemble: 클립 + 음성 → 풀 영상 + 쇼츠
"""
import asyncio
import base64
import json
import math
import os
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path
from loguru import logger

OUTPUT_DIR = Path(__file__).parents[3] / "output" / "video"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CLIPS_DIR = OUTPUT_DIR / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = OUTPUT_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ─── Kling AI 씬 클립 생성 ───────────────────────────────────

def _kling_jwt(access_key: str, secret_key: str) -> str:
    """Kling API 인증용 JWT 토큰 생성"""
    import jwt
    now = int(time.time())
    payload = {"iss": access_key, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, secret_key, algorithm="HS256")


def _kling_motion_prompt(image_prompt: str, slide_text: str) -> str:
    """VideoPrompter가 생성한 motion 프롬프트 사용, 없으면 슬라이드 텍스트 fallback"""
    return image_prompt.strip() if image_prompt.strip() else slide_text[:100]


async def generate_kling_clip(
    image_path: Path,
    image_prompt: str,
    slide_text: str,
    output_path: Path,
    aspect_ratio: str = "16:9",
    duration: str = "5",  # "5" or "10"
    mode: str = "std",    # "std" or "pro"
    end_image_path: Path | None = None,  # image_tail: 시작→끝 장면 보간 (Google Flow 방식)
) -> Path | None:
    """Kling AI 이미지→영상 클립 생성 (image-to-video)

    end_image_path 제공 시: 시작 이미지 → 끝 이미지 보간 영상 생성 (훨씬 자연스러운 모션)
    """
    import httpx

    from app.settings import settings
    access_key = settings.kling_access_key or os.environ.get("KLING_ACCESS_KEY", "")
    secret_key = settings.kling_secret_key or os.environ.get("KLING_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise ValueError("KLING_ACCESS_KEY / KLING_SECRET_KEY 없음")

    prompt = _kling_motion_prompt(image_prompt, slide_text)
    tail_note = " [+image_tail]" if end_image_path and end_image_path.exists() else ""
    logger.info(f"  [Kling{tail_note}] 클립 생성: {prompt[:70]}...")

    try:
        img_b64 = base64.b64encode(image_path.read_bytes()).decode()

        token = _kling_jwt(access_key, secret_key)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        payload = {
            "model_name": "kling-v1-6",
            "image": img_b64,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "mode": mode,
        }

        # image_tail: 다음 슬라이드 이미지를 end frame으로 → 자연스러운 장면 전환
        if end_image_path and end_image_path.exists():
            payload["image_tail"] = base64.b64encode(end_image_path.read_bytes()).decode()

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.klingai.com/v1/videos/image2video",
                headers=headers,
                json=payload,
            )
        if resp.status_code == 429:
            logger.warning("  [Kling] 429 Rate Limit — Ken Burns fallback으로 전환")
            return None
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            logger.error(f"  [Kling] API 오류: {data.get('message')}")
            return None

        task_id = data["data"]["task_id"]
        logger.info(f"  [Kling] 태스크 생성: {task_id}")

        # 폴링 (최대 5분 — JWT 30분 유효하므로 루프 시작 전 1회만 갱신)
        max_wait = 300
        waited = 0
        token = _kling_jwt(access_key, secret_key)
        async with httpx.AsyncClient(timeout=30) as client:
            while waited < max_wait:
                await asyncio.sleep(10)
                waited += 10

                status_resp = await client.get(
                    f"https://api.klingai.com/v1/videos/image2video/{task_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                status_data = status_resp.json()
                task_status = status_data["data"]["task_status"]
                logger.info(f"    [Kling] 상태: {task_status} ({waited}s)")

                if task_status == "succeed":
                    video_url = status_data["data"]["task_result"]["videos"][0]["url"]
                    dl_resp = await client.get(video_url, follow_redirects=True)
                    dl_resp.raise_for_status()
                    output_path.write_bytes(dl_resp.content)
                    logger.info(f"  [Kling] 저장: {output_path.name} ({len(dl_resp.content)//1024}KB)")
                    return output_path
                elif task_status == "failed":
                    logger.error(f"  [Kling] 생성 실패: {status_data['data'].get('task_status_msg')}")
                    return None

        logger.warning("  [Kling] 타임아웃")
        return None

    except Exception as e:
        logger.error(f"  [Kling] 실패: {e}")
        return None


_KENBURNS_EFFECTS = [
    # (label, z_expr, x_expr, y_expr) — 5초(125프레임) 기준, 25% 줌 or 10% 팬
    ("zoom_in",   "min(zoom+0.002,1.25)", "iw/2-(iw/zoom/2)",          "ih/2-(ih/zoom/2)"),
    ("zoom_out",  "if(eq(on,1),1.25,max(zoom-0.002,1.0))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("pan_right", "1.1",  "(iw-iw/zoom)*min(on/d,1)",           "ih/2-(ih/zoom/2)"),
    ("pan_left",  "1.1",  "(iw-iw/zoom)*(1-min(on/d,1))",       "ih/2-(ih/zoom/2)"),
    ("diag_tl",   "min(zoom+0.002,1.25)", "iw*0.05*min(on/d,1)", "ih*0.05*min(on/d,1)"),
]


async def generate_kenburns_clip(
    image_path: Path,
    output_path: Path,
    duration: int = 5,
    aspect_ratio: str = "16:9",
    effect_index: int = 0,
) -> Path | None:
    """ffmpeg Ken Burns 효과 — Kling 실패 시 fallback (5초 고정, 효과 5종 순환)"""
    if aspect_ratio == "9:16":
        w, h = 720, 1280
    elif aspect_ratio == "1:1":
        w, h = 1080, 1080
    else:
        w, h = 1280, 720

    label, z_expr, x_expr, y_expr = _KENBURNS_EFFECTS[effect_index % len(_KENBURNS_EFFECTS)]
    frames = duration * 25
    zoom_filter = (
        f"scale={w*2}:{h*2},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={frames}:s={w}x{h}:fps=25,"
        f"fps=25"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image_path),
        "-vf", zoom_filter,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"  [KenBurns:{label}] ffmpeg 실패: {stderr.decode()[:200]}")
            return None
        logger.info(f"  [KenBurns:{label}] 저장: {output_path.name}")
        return output_path
    except Exception as e:
        logger.error(f"  [KenBurns] 실패: {e}")
        return None


async def generate_kenburns_sequence(
    image_path: Path,
    output_path: Path,
    audio_duration: float,
    aspect_ratio: str = "16:9",
    start_effect_index: int = 0,
) -> Path | None:
    """TTS 길이에 맞는 Ken Burns 시퀀스 — 5초 클립 N개를 병렬 생성 후 concat"""
    num_clips = max(1, math.ceil(audio_duration / 5))
    parent = output_path.parent / "_kb_tmp"
    parent.mkdir(exist_ok=True)

    try:
        # 모든 클립을 병렬 생성 (독립적인 ffmpeg 프로세스)
        kb_paths = [parent / f"{output_path.stem}_kb{k:02d}.mp4" for k in range(num_clips)]
        results = await asyncio.gather(
            *(
                generate_kenburns_clip(
                    image_path=image_path,
                    output_path=kb_paths[k],
                    duration=5,
                    aspect_ratio=aspect_ratio,
                    effect_index=(start_effect_index + k) % len(_KENBURNS_EFFECTS),
                )
                for k in range(num_clips)
            ),
            return_exceptions=True,
        )
        tmp_clips = [r for r in results if isinstance(r, Path)]

        if not tmp_clips:
            return None

        if len(tmp_clips) == 1:
            shutil.copy2(tmp_clips[0], output_path)
        else:
            # 단순 concat (no xfade — 빠름)
            list_file = parent / f"{output_path.stem}_list.txt"
            list_file.write_text("\n".join(f"file '{p}'" for p in tmp_clips))
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                 "-i", str(list_file), "-c", "copy", str(output_path)],
                check=True, timeout=120,
            )

        logger.info(f"  [KenBurns-seq] {num_clips}클립 병렬 → {output_path.name}")
        return output_path if output_path.exists() else None

    finally:
        shutil.rmtree(parent, ignore_errors=True)


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


# ─── ffmpeg 조립 (빠름 — 프레임 디코딩 없음) ─────────────────

def _get_video_duration(path: Path) -> float:
    """ffprobe로 영상 길이 반환"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def _get_clip_duration(clip_path: Path) -> float:
    """ffprobe로 비디오 스트림 길이만 반환 (오디오 제외)"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", str(clip_path)],
            capture_output=True, text=True, timeout=15,
        )
        streams = json.loads(r.stdout).get("streams", [])
        return float(streams[0].get("duration", 6)) if streams else 6.0
    except Exception:
        return 6.0


def _mix_audio_into_clip(clip_path: Path, audio_path: Path | None, out_path: Path) -> Path:
    """ffmpeg로 클립에 오디오 삽입 — libx264 재인코딩으로 concat 호환성 보장"""
    if audio_path and audio_path.exists():
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-stream_loop", "-1",       # 비디오 무한 루프 (오디오보다 짧을 때 대비)
            "-i", str(clip_path),
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",                # 오디오 끝나면 stop
            str(out_path),
        ]
    else:
        # 오디오 없음 → 무음 트랙 추가 (acrossfade concat 호환성 유지)
        video_dur = _get_clip_duration(clip_path)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(clip_path),
            "-f", "lavfi", "-i", f"aevalsrc=0:channel_layout=stereo:sample_rate=44100:duration={video_dur}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            str(out_path),
        ]

    subprocess.run(cmd, check=True, timeout=120)  # noqa: S603
    return out_path


def _has_audio_stream(path: Path) -> bool:
    """ffprobe로 오디오 스트림 존재 여부 확인"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_streams", "-select_streams", "a:0", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return "codec_type=audio" in r.stdout
    except Exception:
        return False


def _ffmpeg_concat(clip_paths: list[Path], output_path: Path, transition_duration: float = 0.5) -> float:
    """ffmpeg xfade(영상) + acrossfade(오디오) 트랜지션으로 클립들 이어붙임"""
    # 각 클립의 실제 길이 확인 (single-clip path에서도 재사용)
    durations = [_get_video_duration(p) or 5.0 for p in clip_paths]

    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], output_path)
        return durations[0]

    # 오디오 스트림 여부: 모든 클립에 오디오가 있어야 acrossfade 적용
    clips_have_audio = all(_has_audio_stream(p) for p in clip_paths)

    inputs = []
    for p in clip_paths:
        inputs += ["-i", str(p)]

    filter_parts = []
    offset = 0.0
    prev_v = "0:v"
    prev_a = "0:a" if clips_have_audio else None

    for i in range(1, len(clip_paths)):
        offset += durations[i - 1] - transition_duration
        v_out = f"v{i}"
        filter_parts.append(
            f"[{prev_v}][{i}:v]xfade=transition=fade:duration={transition_duration:.3f}:offset={offset:.3f}[{v_out}]"
        )
        prev_v = v_out

        if clips_have_audio:
            a_out = f"a{i}"
            filter_parts.append(
                f"[{prev_a}][{i}:a]acrossfade=d={transition_duration:.3f}[{a_out}]"
            )
            prev_a = a_out

    filter_complex = "; ".join(filter_parts)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_v}]",
    ]
    if clips_have_audio:
        cmd += ["-map", f"[{prev_a}]", "-c:a", "aac", "-b:a", "128k"]
    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, timeout=600)
    return _get_video_duration(output_path)


def assemble_video(
    clip_paths: list[Path],
    audio_paths: list[Path | None],
    output_path: Path,
) -> dict:
    """클립 + 음성 → 풀 영상 (ffmpeg, 빠름)"""
    logger.info(f"  [Assembly] 클립 {len(clip_paths)}개 조립 시작 (ffmpeg concat)")

    tmp_dir = output_path.parent / "_tmp_assembly"
    tmp_dir.mkdir(exist_ok=True)

    merged_clips: list[Path] = []
    for i, clip_path in enumerate(clip_paths):
        if not clip_path or not clip_path.exists():
            logger.warning(f"  [Assembly] 클립 {i+1} 없음 — 스킵")
            continue
        try:
            audio_path = audio_paths[i] if i < len(audio_paths) else None
            merged = tmp_dir / f"merged_{i:03d}.mp4"
            _mix_audio_into_clip(clip_path, audio_path, merged)
            merged_clips.append(merged)
        except Exception as e:
            logger.error(f"  [Assembly] 클립 {i+1} 오디오 삽입 실패: {e}")
            merged_clips.append(clip_path)  # 오디오 없이 원본 사용

    if not merged_clips:
        return {"error": "조립할 클립 없음"}

    # 풀 영상
    duration = _ffmpeg_concat(merged_clips, output_path)
    logger.info(f"  [Assembly] 풀 영상 완료: {output_path.name} ({duration:.1f}초)")

    result = {
        "full_video": str(output_path),
        "duration": round(duration, 1),
        "clips_count": len(merged_clips),
    }

    # 쇼츠는 assemble_video에서 자동 생성하지 않음
    # 롱폼 완성 후 ShortsExtractor를 별도 단계로 실행해야 함

    # 임시 파일 정리
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


# ─── 신규: ShotFrame 멀티샷 파이프라인 ──────────────────────────

async def _produce_video_multiframe(
    topic: str,
    platform: str,
    slide_texts: list[str],
    shot_script_dict: dict,
    frame_image_paths: dict,   # (slide_idx, frame_idx) or str keys → path
    frame_motion_prompts: list[str],
    aspect_ratio: str,
    tts_provider: str,
    tts_voice_id: str,
    with_tts: bool,
    bgm_category: str,
    slug: str,
) -> dict:
    """ShotFrame 기반 멀티샷 영상 생성

    흐름:
      1. TTS 생성 (슬라이드별)
      2. 샷별 클립 생성 (VideoGenerator)
      3. 슬라이드별 클립 concat → 슬라이드 영상
      4. 슬라이드 영상 + TTS 믹싱
      5. 전체 슬라이드 concat → 풀 영상
    """
    from app.agents.media.cinematic_shot_planner import ShotScript
    from app.agents.media.video_generator import generate_all_shot_clips

    shot_script = ShotScript.from_dict(shot_script_dict)
    n_slides = len(slide_texts)

    logger.info(
        f"  [MultiFrame] {shot_script.total_shots}개 샷으로 {n_slides}슬라이드 생성 시작"
    )

    # ── Step 1: TTS ────────────────────────────────────────────
    audio_paths: list[Path | None] = [None] * n_slides
    if tts_provider == "gemini":
        from app.agents.media.tts_gemini import generate_narrations_gemini
        logger.info(f"  [MultiFrame] Gemini TTS {n_slides}개 생성...")
        audio_paths = await generate_narrations_gemini(
            slide_texts=slide_texts, slug=slug, platform=platform,
        )
    elif tts_provider == "elevenlabs" or with_tts:
        logger.info(f"  [MultiFrame] ElevenLabs TTS {n_slides}개 생성...")
        tts_tasks = [
            generate_tts(text, AUDIO_DIR / f"{slug}_{platform}_{i:02d}.mp3", voice_id=tts_voice_id)
            for i, text in enumerate(slide_texts)
        ]
        audio_paths = list(await asyncio.gather(*tts_tasks))

    # ── Step 2: 샷별 클립 생성 ──────────────────────────────────
    logger.info(f"  [MultiFrame] 샷 클립 생성 시작...")

    # frame_image_paths key 정규화: str → tuple
    normalized_paths: dict = {}
    for k, v in frame_image_paths.items():
        if isinstance(k, str) and "_" in str(k):
            parts = str(k).split("_")
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                normalized_paths[(int(parts[0]), int(parts[1]))] = v
                continue
        if isinstance(k, (list, tuple)) and len(k) == 2:
            normalized_paths[(int(k[0]), int(k[1]))] = v
            continue
        normalized_paths[k] = v

    shot_clips = await generate_all_shot_clips(
        shot_script=shot_script,
        frame_image_paths=normalized_paths,
        motion_prompts=frame_motion_prompts,
        clips_dir=CLIPS_DIR,
        slug=slug,
        aspect_ratio=aspect_ratio,
    )

    # ── Step 3+4: 슬라이드별 클립 concat + TTS 믹싱 ──────────────
    logger.info(f"  [MultiFrame] 슬라이드별 조립 시작...")
    slide_merged: list[Path] = []
    tmp_dir = OUTPUT_DIR / f"_mf_{slug}"
    tmp_dir.mkdir(exist_ok=True)

    try:
        for si in range(n_slides):
            slide_shots = shot_script.shots_for_slide(si)
            slide_clip_paths = []
            for shot in slide_shots:
                clip = shot_clips.get((shot.slide_index, shot.frame_index))
                if clip and clip.exists():
                    slide_clip_paths.append(clip)

            if not slide_clip_paths:
                logger.warning(f"  [MultiFrame] 슬라이드 {si+1} 클립 없음 — 스킵")
                continue

            # 슬라이드 내 클립 concat
            slide_video = tmp_dir / f"slide_{si:02d}_concat.mp4"
            _ffmpeg_concat(slide_clip_paths, slide_video, transition_duration=0.3)
            if not slide_video.exists():
                continue

            # TTS 믹싱
            audio_path = audio_paths[si] if si < len(audio_paths) else None
            merged = tmp_dir / f"slide_{si:02d}_merged.mp4"
            try:
                _mix_audio_into_clip(slide_video, audio_path, merged)
                slide_merged.append(merged)
            except Exception as e:
                logger.error(f"  [MultiFrame] 슬라이드 {si+1} 오디오 삽입 실패: {e}")
                slide_merged.append(slide_video)

        if not slide_merged:
            return {"error": "조립할 슬라이드 없음"}

        # ── Step 5: 전체 concat ─────────────────────────────────
        full_path = OUTPUT_DIR / f"{slug}_{platform}_full.mp4"
        duration = _ffmpeg_concat(slide_merged, full_path, transition_duration=0.5)
        logger.info(f"  [MultiFrame] 풀 영상 완료: {full_path.name} ({duration:.1f}초)")

        result = {
            "full_video": str(full_path),
            "duration": round(duration, 1),
            "clips_count": sum(1 for c in shot_clips.values() if c),
        }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # BGM 믹싱
    if bgm_category != "none" and result.get("full_video"):
        try:
            from app.agents.media.bgm_manager import select_bgm, mix_bgm_into_video
            bgm_path = await asyncio.to_thread(
                select_bgm, bgm_category, result.get("duration", 60.0), slug
            )
            if bgm_path:
                bgm_output = OUTPUT_DIR / f"{slug}_{platform}_bgm.mp4"
                mixed = await asyncio.to_thread(
                    mix_bgm_into_video, Path(result["full_video"]), bgm_path, bgm_output
                )
                if mixed:
                    result["full_video"] = str(mixed)
                    result["bgm_category"] = bgm_category
        except Exception as e:
            logger.warning(f"  [MultiFrame] BGM 실패 (무시): {e}")

    logger.info(f"=== VideoProduction (MultiFrame) 완료: {result.get('full_video', 'FAILED')} ===")
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
    tts_provider: str = "none",   # "none" | "gemini" | "elevenlabs"
    bgm_category: str = "none",   # "none" | "cinematic" | "ambient" | "upbeat" | "dramatic"
    video_plan_dict: dict | None = None,  # VideoPlannerAgent 결과 (구버전 호환)
    video_prompts: list[str] | None = None,  # 렌더 단계에서 캐시된 Kling 전용 프롬프트
    shot_script_dict: dict | None = None,    # CinematicShotPlanner 결과 (신버전)
    frame_image_paths: dict | None = None,   # (slide_idx, frame_idx) → path (신버전)
    frame_motion_prompts: list[str] | None = None,  # 샷별 모션 프롬프트 (신버전)
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
    # 유니코드 정규화 후 ASCII 변환, 불가 시 원본 그대로 (한국어 포함)
    ascii_topic = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode()
    slug_base = ascii_topic if ascii_topic.strip() else topic
    slug = re.sub(r"[^\w]", "_", slug_base)[:25].strip("_") or "video"

    logger.info(f"=== VideoProduction: '{topic}' [{platform}] {len(slide_texts)}슬라이드 (Kling AI) ===")

    # ── 신규: ShotFrame 기반 파이프라인 ─────────────────────────
    if shot_script_dict and frame_image_paths:
        return await _produce_video_multiframe(
            topic=topic,
            platform=platform,
            slide_texts=slide_texts,
            shot_script_dict=shot_script_dict,
            frame_image_paths=frame_image_paths,
            frame_motion_prompts=frame_motion_prompts or [],
            aspect_ratio=aspect_ratio,
            tts_provider=tts_provider,
            tts_voice_id=tts_voice_id,
            with_tts=with_tts,
            bgm_category=bgm_category,
            slug=slug,
        )

    # ── 구버전 호환: 슬라이드당 1 클립 ───────────────────────────
    # video_plan에서 샷 스펙 로드
    shot_map: dict = {}
    if video_plan_dict and video_plan_dict.get("shots"):
        from app.agents.media.video_director import apply_shot_spec_to_veo_prompt
        from app.agents.media.video_planner import ShotSpec
        for shot_data in video_plan_dict["shots"]:
            try:
                shot_map[shot_data["slide_index"]] = ShotSpec(**shot_data)
            except Exception:
                pass
        logger.info(f"  [VideoDirector] 샷 스펙 {len(shot_map)}개 로드")

    # Step 1: TTS 먼저 생성 (Ken Burns duration 결정을 위해 클립보다 앞에)
    audio_paths: list[Path | None] = [None] * len(slide_texts)
    if tts_provider == "gemini":
        logger.info(f"  [Step 1] Gemini TTS {len(slide_texts)}개 생성...")
        from app.agents.media.tts_gemini import generate_narrations_gemini
        audio_paths = await generate_narrations_gemini(
            slide_texts=slide_texts,
            slug=slug,
            platform=platform,
        )
    elif tts_provider == "elevenlabs" or with_tts:
        logger.info(f"  [Step 1] ElevenLabs TTS {len(slide_texts)}개 생성...")
        tts_tasks = []
        for i, text in enumerate(slide_texts):
            path = AUDIO_DIR / f"{slug}_{platform}_{i:02d}.mp3"
            tts_tasks.append(generate_tts(text, path, voice_id=tts_voice_id))
        audio_paths = list(await asyncio.gather(*tts_tasks))

    # Step 2a: Kling 전용 영상 프롬프트 확보
    # 렌더 단계에서 캐시된 prompts가 있으면 재사용, 없으면 VideoPrompter 호출
    if video_prompts and len(video_prompts) >= len(slide_texts):
        logger.info(f"  [Step 2a] 캐시된 Kling 프롬프트 {len(video_prompts)}개 재사용")
    else:
        logger.info("  [Step 2a] VideoPrompter: Kling 전용 영상 프롬프트 생성...")
        try:
            from app.agents.media.video_prompter import generate_video_prompts
            video_prompts = await generate_video_prompts(
                topic=topic,
                hook=slide_texts[0] if slide_texts else topic,
                body_slides=slide_texts,
                video_plan_dict=video_plan_dict,
                platform=platform,
            )
            logger.info(f"  [VideoPrompter] {len(video_prompts)}개 Kling 프롬프트 생성 완료")
            logger.info(f"  [VideoPrompter] 샘플: {video_prompts[0][:80]}..." if video_prompts else "")
        except Exception as e:
            logger.warning(f"  [VideoPrompter] 실패, image_prompts 사용: {e}")
            video_prompts = image_prompts  # fallback

    # Step 2b: 씬 이미지 → Kling 클립 (순차 — 병렬 시 API rate limit)
    generated_clips = []
    for i, (text, v_prompt) in enumerate(zip(slide_texts, video_prompts)):
        clip_path = CLIPS_DIR / f"{slug}_{platform}_{i:02d}.mp4"

        # 해당 슬라이드의 씬 이미지 찾기
        image_path = None
        if i < len(scene_image_paths) and scene_image_paths[i]:
            p = Path(scene_image_paths[i])
            if p.exists():
                image_path = p

        if not image_path:
            logger.warning(f"  [Kling] 씬 이미지 없음 ({i+1}번) — 스킵")
            generated_clips.append(None)
            continue

        # image_tail: 다음 슬라이드 이미지 → 자연스러운 장면 전환 보간
        end_image_path = None
        if i + 1 < len(scene_image_paths) and scene_image_paths[i + 1]:
            next_p = Path(scene_image_paths[i + 1])
            if next_p.exists():
                end_image_path = next_p

        clip_result = await generate_kling_clip(
            image_path=image_path,
            image_prompt=v_prompt,
            slide_text=text,
            output_path=clip_path,
            aspect_ratio=aspect_ratio,
            end_image_path=end_image_path,
        )

        # Kling 실패 시 Ken Burns 시퀀스 fallback
        if clip_result is None:
            audio_path = audio_paths[i] if i < len(audio_paths) else None
            audio_dur = _get_video_duration(audio_path) if audio_path and audio_path.exists() else 5.0
            logger.info(f"  → Ken Burns fallback: 슬라이드 {i+1} ({audio_dur:.0f}초 커버)")
            clip_result = await generate_kenburns_sequence(
                image_path=image_path,
                output_path=clip_path,
                audio_duration=audio_dur,
                aspect_ratio=aspect_ratio,
                start_effect_index=i,
            )

        generated_clips.append(clip_result)

        # Kling rate limit 방지: 클립 간 5초 대기
        if i < len(slide_texts) - 1:
            await asyncio.sleep(5)

    logger.info(f"  [Step 2] 클립 완료: {sum(1 for c in generated_clips if c)}개")

    # Step 3: 영상 조립
    logger.info("  [Step 3] 영상 조립...")
    full_path = OUTPUT_DIR / f"{slug}_{platform}_full.mp4"

    # 롱폼 영상만 생성 — 쇼츠는 별도 단계(ShortsExtractor)로 분리
    result = await asyncio.to_thread(
        assemble_video,
        clip_paths=[c for c in generated_clips if c],
        audio_paths=audio_paths,
        output_path=full_path,
    )

    result["clip_paths"] = [str(p) for p in generated_clips if p]

    # Step 4: BGM 믹싱
    if bgm_category != "none" and result.get("full_video"):
        logger.info(f"  [Step 4] BGM 믹싱 시작: {bgm_category}")
        try:
            from app.agents.media.bgm_manager import select_bgm, mix_bgm_into_video
            full_path_obj = Path(result["full_video"])
            duration = result.get("duration", 60.0)
            bgm_path = await asyncio.to_thread(select_bgm, bgm_category, duration, slug)
            if bgm_path:
                bgm_output = OUTPUT_DIR / f"{slug}_{platform}_bgm.mp4"
                mixed = await asyncio.to_thread(mix_bgm_into_video, full_path_obj, bgm_path, bgm_output)
                if mixed:
                    result["full_video"] = str(mixed)
                    result["bgm_category"] = bgm_category
                    logger.info(f"  [BGM] 믹싱 완료 → {bgm_output.name}")
        except Exception as e:
            logger.warning(f"  [BGM] 실패 (BGM 없이 계속): {e}")

    logger.info(f"=== VideoProduction 완료: {result.get('full_video', 'FAILED')} ===")
    return result
