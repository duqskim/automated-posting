"""
VideoGenerator — 멀티 서비스 영상 클립 생성

샷 타입에 따라 최적 도구 선택:
  DYNAMIC      → Kling AI image-to-video (실제 모션)
                 Kling 실패/잔액부족 시 → Google Veo 2 fallback
                 Veo 실패 시 → Ken Burns fallback
  ATMOSPHERIC  → Ken Burns (의도적 카메라 드리프트, 풍경/분위기용)
  STATIC_GRAPHIC → ffmpeg 느린 팬/줌 (지도, 다이어그램용)

image_tail 규칙:
  - 연속된 두 샷이 같은 scene_id이면 image_tail 적용 (부드러운 장면 전환)
  - 슬라이드 경계는 절대 image_tail 사용 안 함
  - 다른 scene_id는 하드컷 (image_tail 없음)

클립 길이:
  - Kling: 항상 5초 생성. duration_target > 5s면 Veo/KB로 연장, < 5s면 trim
  - Veo 2: 5~8초 생성. Kling 대체 또는 보완
  - Ken Burns: duration_target 만큼 생성 (5초 클립 N개 concat)
  - ffmpeg: duration_target 만큼 생성
"""
import asyncio
import math
import os
import shutil
import subprocess
import time
import base64
from pathlib import Path
from loguru import logger


# ─── Kling AI ─────────────────────────────────────────────────

def _kling_jwt(access_key: str, secret_key: str) -> str:
    import jwt
    now = int(time.time())
    return jwt.encode({"iss": access_key, "exp": now + 1800, "nbf": now - 5}, secret_key, algorithm="HS256")


async def _kling_clip(
    image_path: Path,
    motion_prompt: str,
    output_path: Path,
    aspect_ratio: str = "16:9",
    tail_image_path: Path | None = None,
) -> Path | None:
    """Kling AI image-to-video — 항상 5초 클립 생성"""
    import httpx
    from app.settings import settings

    access_key = settings.kling_access_key or os.environ.get("KLING_ACCESS_KEY", "")
    secret_key = settings.kling_secret_key or os.environ.get("KLING_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise ValueError("KLING_ACCESS_KEY / KLING_SECRET_KEY 없음")

    tail_note = " [+tail]" if tail_image_path and tail_image_path.exists() else ""
    logger.info(f"  [Kling{tail_note}] {motion_prompt[:70]}...")

    try:
        img_b64 = base64.b64encode(image_path.read_bytes()).decode()
        token = _kling_jwt(access_key, secret_key)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        payload = {
            "model_name": "kling-v1-6",
            "image": img_b64,
            "prompt": motion_prompt,
            "duration": "5",
            "aspect_ratio": aspect_ratio,
            "mode": "std",
        }
        if tail_image_path and tail_image_path.exists():
            payload["image_tail"] = base64.b64encode(tail_image_path.read_bytes()).decode()

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.klingai.com/v1/videos/image2video",
                headers=headers, json=payload,
            )

        if resp.status_code == 429:
            logger.warning("  [Kling] 429 Rate Limit")
            return None
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            logger.error(f"  [Kling] API 오류: {data.get('message')}")
            return None

        task_id = data["data"]["task_id"]

        # 폴링 (최대 5분)
        token = _kling_jwt(access_key, secret_key)  # 루프 전 1회만 갱신
        async with httpx.AsyncClient(timeout=30) as client:
            for waited in range(10, 301, 10):
                await asyncio.sleep(10)
                status_resp = await client.get(
                    f"https://api.klingai.com/v1/videos/image2video/{task_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                status_data = status_resp.json()
                task_status = status_data["data"]["task_status"]
                logger.info(f"    [Kling] {task_status} ({waited}s)")

                if task_status == "succeed":
                    video_url = status_data["data"]["task_result"]["videos"][0]["url"]
                    dl = await client.get(video_url, follow_redirects=True)
                    dl.raise_for_status()
                    output_path.write_bytes(dl.content)
                    logger.info(f"  [Kling] 저장: {output_path.name} ({len(dl.content)//1024}KB)")
                    return output_path
                elif task_status == "failed":
                    logger.error(f"  [Kling] 생성 실패: {status_data['data'].get('task_status_msg')}")
                    return None

        logger.warning("  [Kling] 타임아웃")
        return None

    except Exception as e:
        logger.error(f"  [Kling] 실패: {e}")
        return None


# ─── Google Veo 2 ─────────────────────────────────────────────

async def _veo_clip(
    image_path: Path,
    motion_prompt: str,
    output_path: Path,
    aspect_ratio: str = "16:9",
    duration_seconds: int = 5,
) -> Path | None:
    """Google Veo 2 image-to-video — Gemini API 키로 접근"""
    import os
    try:
        from google import genai
        from google.genai import types as gtypes

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("  [Veo] GEMINI_API_KEY 없음")
            return None

        logger.info(f"  [Veo2] 클립 생성: {motion_prompt[:70]}...")

        client = genai.Client(api_key=api_key)
        image_bytes = image_path.read_bytes()

        # 이미지 MIME 타입 감지
        mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

        op = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=motion_prompt,
            image=gtypes.Image(image_bytes=image_bytes, mime_type=mime),
            config=gtypes.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
                duration_seconds=min(duration_seconds, 8),  # Veo 최대 8초
            ),
        )

        # 폴링 (최대 3분)
        for waited in range(10, 181, 10):
            await asyncio.sleep(10)
            op = await asyncio.to_thread(client.operations.get, op)
            logger.info(f"    [Veo2] 대기 중... {waited}s")
            if op.done:
                break

        if not op.done:
            logger.warning("  [Veo2] 타임아웃")
            return None

        videos = op.response.generated_videos
        if not videos:
            logger.error("  [Veo2] 생성된 영상 없음")
            return None

        video_data = await asyncio.to_thread(client.files.download, file=videos[0].video)
        output_path.write_bytes(video_data)
        logger.info(f"  [Veo2] 저장: {output_path.name} ({len(video_data)//1024}KB)")
        return output_path

    except Exception as e:
        logger.error(f"  [Veo2] 실패: {e}")
        return None


# ─── Ken Burns ────────────────────────────────────────────────

# KB 효과: (label, zoom_expr, x_expr_template, y_expr_template)
# {F} → 실제 프레임 수로 치환 (d 변수 사용 안 함 — ffmpeg 버전 호환)
_KB_EFFECTS = [
    ("zoom_in",   "min(zoom+0.002,1.25)", "iw/2-(iw/zoom/2)",                   "ih/2-(ih/zoom/2)"),
    ("zoom_out",  "if(eq(on,1),1.25,max(zoom-0.002,1.0))", "iw/2-(iw/zoom/2)",  "ih/2-(ih/zoom/2)"),
    ("pan_right", "1.1",  "(iw-iw/zoom)*min(on/{F},1)",                          "ih/2-(ih/zoom/2)"),
    ("pan_left",  "1.1",  "(iw-iw/zoom)*(1-min(on/{F},1))",                      "ih/2-(ih/zoom/2)"),
    ("diag_tl",   "min(zoom+0.002,1.25)", "iw*0.05*min(on/{F},1)",               "ih*0.05*min(on/{F},1)"),
]


async def _kenburns_clip(
    image_path: Path,
    output_path: Path,
    duration: int = 5,
    aspect_ratio: str = "16:9",
    effect_index: int = 0,
) -> Path | None:
    """ffmpeg Ken Burns 효과 — 5초 고정 클립"""
    w, h = {"9:16": (720, 1280), "1:1": (1080, 1080)}.get(aspect_ratio, (1280, 720))
    label, z_expr, x_expr_tpl, y_expr_tpl = _KB_EFFECTS[effect_index % len(_KB_EFFECTS)]
    frames = duration * 25
    x_expr = x_expr_tpl.replace("{F}", str(frames))
    y_expr = y_expr_tpl.replace("{F}", str(frames))
    vf = (
        f"scale={w*2}:{h*2},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={w}x{h}:fps=25,"
        f"fps=25"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image_path),
        "-vf", vf,
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
            logger.error(f"  [KB:{label}] ffmpeg 실패: {stderr.decode()[:200]}")
            return None
        return output_path
    except Exception as e:
        logger.error(f"  [KB] 실패: {e}")
        return None


async def _kenburns_sequence(
    image_path: Path,
    output_path: Path,
    duration: float,
    aspect_ratio: str = "16:9",
    start_effect: int = 0,
) -> Path | None:
    """Ken Burns 시퀀스 — duration(초)를 커버하는 5초 클립 N개 concat"""
    num = max(1, math.ceil(duration / 5))
    tmp = output_path.parent / f"_kb_{output_path.stem}"
    tmp.mkdir(exist_ok=True)

    try:
        clips = [tmp / f"kb{k:02d}.mp4" for k in range(num)]
        results = await asyncio.gather(
            *(
                _kenburns_clip(image_path, clips[k], 5, aspect_ratio, (start_effect + k) % len(_KB_EFFECTS))
                for k in range(num)
            ),
            return_exceptions=True,
        )
        valid = [r for r in results if isinstance(r, Path)]
        if not valid:
            return None
        if len(valid) == 1:
            shutil.copy2(valid[0], output_path)
        else:
            list_f = tmp / "list.txt"
            list_f.write_text("\n".join(f"file '{p}'" for p in valid))
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                 "-i", str(list_f), "-c", "copy", str(output_path)],
                check=True, timeout=120,
            )
        return output_path if output_path.exists() else None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─── ffmpeg 느린 팬 (STATIC_GRAPHIC) ─────────────────────────

async def _static_graphic_clip(
    image_path: Path,
    output_path: Path,
    duration: float,
    aspect_ratio: str = "16:9",
) -> Path | None:
    """지도/다이어그램용 — 느린 좌→우 팬 후 살짝 줌인"""
    w, h = {"9:16": (720, 1280), "1:1": (1080, 1080)}.get(aspect_ratio, (1280, 720))
    frames = int(duration * 25)
    vf = (
        f"scale={w*2}:{h*2},"
        f"zoompan=z='1.05':x='(iw-iw/zoom)*min(on/{frames},1)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={w}x{h}:fps=25,"
        f"fps=25"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image_path),
        "-vf", vf,
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
            logger.error(f"  [StaticGraphic] ffmpeg 실패: {stderr.decode()[:200]}")
            return None
        return output_path
    except Exception as e:
        logger.error(f"  [StaticGraphic] 실패: {e}")
        return None


# ─── 트리밍 헬퍼 ───────────────────────────────────────────────

async def _trim_clip(clip_path: Path, duration: float, output_path: Path) -> Path:
    """클립을 duration(초)로 trim"""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(clip_path),
        "-t", str(duration),
        "-c", "copy",
        str(output_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return output_path if output_path.exists() else clip_path


async def _concat_two(clip_a: Path, clip_b: Path, output_path: Path) -> Path:
    """두 클립 stream_copy concat"""
    tmp = output_path.parent / f"_list_{output_path.stem}.txt"
    tmp.write_text(f"file '{clip_a}'\nfile '{clip_b}'")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(tmp),
            "-c", "copy", str(output_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    finally:
        tmp.unlink(missing_ok=True)
    return output_path if output_path.exists() else clip_a


# ─── 통합 샷 클립 생성 ─────────────────────────────────────────

from app.agents.media.cinematic_shot_planner import ShotScript, ShotFrame


async def generate_shot_clip(
    shot: ShotFrame,
    image_path: Path,
    motion_prompt: str,
    output_path: Path,
    aspect_ratio: str,
    tail_image_path: Path | None = None,  # image_tail: 같은 scene_id의 다음 샷 이미지
    kb_effect_index: int = 0,
) -> Path | None:
    """ShotFrame 1개 → 클립 1개 (shot_type에 따라 도구 선택)"""
    dur = max(3.0, shot.duration_target)

    if shot.shot_type == "DYNAMIC":
        # 1. Kling 시도
        kling_out = output_path.with_name(output_path.stem + "_kling.mp4")
        kling_result = await _kling_clip(image_path, motion_prompt, kling_out, aspect_ratio, tail_image_path)

        if kling_result:
            if dur <= 5.0:
                return await _trim_clip(kling_result, dur, output_path)
            else:
                # Kling 5s + Veo/KB 연장
                extend_dur = dur - 5.0
                ext_out = output_path.with_name(output_path.stem + "_ext.mp4")
                veo_ext = await _veo_clip(image_path, motion_prompt, ext_out, aspect_ratio, min(int(extend_dur), 8))
                if veo_ext:
                    return await _concat_two(kling_result, veo_ext, output_path)
                kb_result = await _kenburns_sequence(image_path, ext_out, extend_dur, aspect_ratio, kb_effect_index)
                if kb_result:
                    return await _concat_two(kling_result, kb_result, output_path)
                shutil.copy2(kling_result, output_path)
                return output_path

        # 2. Kling 실패 → Veo 2 fallback
        logger.info(f"  [VideoGenerator] Kling 실패 → Veo 2 fallback (slide {shot.slide_index+1}, shot {shot.frame_index+1})")
        veo_out = output_path.with_name(output_path.stem + "_veo.mp4")
        veo_result = await _veo_clip(image_path, motion_prompt, veo_out, aspect_ratio, min(int(dur), 8))

        if veo_result:
            if dur <= 8.0:
                return await _trim_clip(veo_result, dur, output_path)
            else:
                # Veo 8s + KB 연장
                extend_dur = dur - 8.0
                kb_out = output_path.with_name(output_path.stem + "_kb.mp4")
                kb_result = await _kenburns_sequence(image_path, kb_out, extend_dur, aspect_ratio, kb_effect_index)
                if kb_result:
                    return await _concat_two(veo_result, kb_result, output_path)
                shutil.copy2(veo_result, output_path)
                return output_path

        # Kling, Veo 모두 실패 → 스킵 (Ken Burns 폴백 없음 — 시간/비용 낭비)
        logger.warning(f"  [VideoGenerator] Kling+Veo 모두 실패, 클립 스킵 (slide {shot.slide_index+1}, shot {shot.frame_index+1})")
        return None

    elif shot.shot_type == "ATMOSPHERIC":
        return await _kenburns_sequence(image_path, output_path, dur, aspect_ratio, kb_effect_index)

    else:  # STATIC_GRAPHIC
        return await _static_graphic_clip(image_path, output_path, dur, aspect_ratio)


async def generate_all_shot_clips(
    shot_script: ShotScript,
    frame_image_paths: dict,  # key: (slide_index, frame_index) | str "si_fi" → path str
    motion_prompts: list[str],   # 1 per shot, indexed same as shot_script.shots
    clips_dir: Path,
    slug: str,
    aspect_ratio: str,
) -> dict:
    """모든 ShotFrame → 클립 dict: (slide_index, frame_index) → Path"""
    # key 정규화 헬퍼
    def get_img(si: int, fi: int) -> Path | None:
        for key in [(si, fi), f"{si}_{fi}", f"slide_{si:02d}_shot_{fi:02d}"]:
            v = frame_image_paths.get(key)
            if v:
                p = Path(v)
                if p.exists():
                    return p
        return None

    results: dict = {}
    kb_counter = 0  # Ken Burns 효과 인덱스 (전체 순환)

    for idx, shot in enumerate(shot_script.shots):
        si, fi = shot.slide_index, shot.frame_index
        image_path = get_img(si, fi)

        if not image_path:
            logger.warning(f"  [VideoGenerator] 이미지 없음: slide {si+1} shot {fi+1} — 스킵")
            results[(si, fi)] = None
            continue

        # image_tail: 같은 scene_id의 다음 샷 이미지 (슬라이드 경계 넘지 않음)
        tail_path = None
        if idx + 1 < len(shot_script.shots):
            next_shot = shot_script.shots[idx + 1]
            if (next_shot.scene_id == shot.scene_id
                    and next_shot.slide_index == si):
                tail_path = get_img(next_shot.slide_index, next_shot.frame_index)

        motion_prompt = motion_prompts[idx] if idx < len(motion_prompts) else ""
        out_path = clips_dir / f"{slug}_s{si:02d}_f{fi:02d}.mp4"

        clip = await generate_shot_clip(
            shot=shot,
            image_path=image_path,
            motion_prompt=motion_prompt,
            output_path=out_path,
            aspect_ratio=aspect_ratio,
            tail_image_path=tail_path,
            kb_effect_index=kb_counter,
        )
        results[(si, fi)] = clip

        if clip:
            logger.info(f"  [VideoGenerator] slide {si+1} shot {fi+1} ({shot.shot_type}) → {out_path.name}")
        else:
            logger.warning(f"  [VideoGenerator] slide {si+1} shot {fi+1} 실패")

        if shot.shot_type in ("DYNAMIC", "ATMOSPHERIC"):
            kb_counter += 1

        # Kling rate limit 방지: DYNAMIC 샷 후 5초 대기
        if shot.shot_type == "DYNAMIC" and idx < len(shot_script.shots) - 1:
            await asyncio.sleep(5)

    logger.info(f"[VideoGenerator] {sum(1 for p in results.values() if p)}/{len(results)} 클립 완료")
    return results
