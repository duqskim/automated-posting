#!/usr/bin/env python3
"""
조선 건국의 비밀 — Veo 클립 재생성 (제대로 된 프롬프트로)

문제: shot_script의 subject_action에 한국어 나레이션 텍스트가 오염됨
해결: 각 씬 이미지를 Gemini Vision으로 보고 실제 영상 모션 프롬프트 생성 후 Veo 재실행
"""

import asyncio
import base64
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import tempfile
from pathlib import Path

BASE = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

CLIPS_DIR  = BASE / "output" / "video" / "clips"
SCENES_DIR = BASE / "output" / "scenes"
AUDIO_DIR  = BASE / "output" / "video" / "audio"
OUT_DIR    = BASE / "output" / "video"
DB_PATH    = BASE / "automated_posting.db"

TOPIC       = "조선_건국의_비밀"
PROJECT_ID  = 8
GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")
NUM_SLIDES  = 19


# ── Gemini Vision으로 씬 이미지 분석 → 모션 프롬프트 생성 ────────

async def generate_motion_prompt_for_image(
    image_path: Path,
    shot_type: str,
    camera_movement: str,
    topic: str,
) -> str:
    """Gemini Vision으로 이미지 보고 Veo 2용 모션 프롬프트 생성"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_KEY)

    mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    image_bytes = image_path.read_bytes()

    camera_hint = camera_movement if camera_movement else "slow push forward"
    style = "cinematic" if shot_type == "DYNAMIC" else "gentle atmospheric"

    instruction = f"""You are a video generation prompt specialist for Veo 2 (Google's AI video model).

Look at this image and write a MOTION PROMPT for generating a 5-8 second video clip.
Topic context: "{topic}"
Intended camera movement: {camera_hint}
Style: {style}

RULES:
- Describe what PHYSICALLY MOVES in the video (camera + subjects + environment)
- Camera movement must be specific: "slow push in", "orbit left", "tilt up", "crane down", "handheld follow"
- Describe what objects/people in the scene are doing (marching, flowing, flickering, etc.)
- Include atmosphere physics: wind on flags/fabric, smoke, fire, dust, light rays
- Write in English, 30-50 words
- DO NOT describe image qualities (no "8K", "cinematic", "depth of field")
- DO NOT mention the image is historical or Korean — just describe the MOTION

Return ONLY the motion prompt, no explanation."""

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                instruction,
            ],
        )
        prompt = response.text.strip()
        # 따옴표나 불필요한 prefix 제거
        prompt = re.sub(r'^["\']+|["\']+$', '', prompt)
        return prompt
    except Exception as e:
        # 폴백: 기본 영어 프롬프트
        return f"{camera_hint}. Scene subjects move naturally. Atmospheric lighting shifts. {style} mood."


# ── Veo 2 클립 생성 ─────────────────────────────────────────────

async def generate_veo_clip(
    image_path: Path,
    prompt: str,
    output_path: Path,
    duration: int = 5,
) -> Path | None:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_KEY)
    mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    print(f"    [Veo2] {prompt[:80]}...")

    try:
        op = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=prompt,
            image=types.Image(image_bytes=image_path.read_bytes(), mime_type=mime),
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
                number_of_videos=1,
                duration_seconds=min(duration, 8),
            ),
        )

        for waited in range(10, 181, 10):
            await asyncio.sleep(10)
            op = await asyncio.to_thread(client.operations.get, op)
            print(f"    [Veo2] 대기 {waited}s...", end="\r")
            if op.done:
                break

        if not op.done:
            print(f"    [Veo2] 타임아웃")
            return None

        videos = op.response.generated_videos
        if not videos:
            print(f"    [Veo2] 영상 없음")
            return None

        video_data = await asyncio.to_thread(client.files.download, file=videos[0].video)
        output_path.write_bytes(video_data)
        print(f"    [Veo2] 저장: {output_path.name} ({len(video_data)//1024}KB)      ")
        return output_path

    except Exception as e:
        print(f"    [Veo2] 실패: {e}")
        return None


# ── Ken Burns 폴백 ───────────────────────────────────────────────

async def generate_kb_clip(
    image_path: Path,
    output_path: Path,
    duration: int = 5,
    effect_index: int = 0,
) -> Path | None:
    KB_EFFECTS = [
        ("zoom_in",   "min(zoom+0.002,1.25)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        ("zoom_out",  "if(eq(on,1),1.25,max(zoom-0.002,1.0))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        ("pan_right", "1.1", f"(iw-iw/zoom)*min(on/{duration*25},1)", "ih/2-(ih/zoom/2)"),
        ("pan_left",  "1.1", f"(iw-iw/zoom)*(1-min(on/{duration*25},1))", "ih/2-(ih/zoom/2)"),
        ("diag_tl",   "min(zoom+0.002,1.25)", f"iw*0.05*min(on/{duration*25},1)", f"ih*0.05*min(on/{duration*25},1)"),
    ]
    label, z, x, y = KB_EFFECTS[effect_index % len(KB_EFFECTS)]
    frames = duration * 25
    vf = f"scale=2560:1440,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s=1280x720:fps=25,fps=25"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image_path),
           "-vf", vf, "-t", str(duration), "-c:v", "libx264", "-preset", "fast",
           "-crf", "23", "-pix_fmt", "yuv420p", str(output_path)]
    proc = await asyncio.create_subprocess_exec(*cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        print(f"    [KB:{label}] 실패: {stderr.decode()[:100]}")
        return None
    return output_path


# ── ffmpeg 유틸 ───────────────────────────────────────────────────

def get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except:
        return 0.0


def concat_list(paths: list[Path], out: Path, reencode: bool = False):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in paths:
            f.write(f"file '{p.resolve()}'\n")
        lf = f.name
    try:
        if reencode:
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lf,
                   "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k", str(out)]
        else:
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lf, "-c", "copy", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        os.unlink(lf)


def mix_audio(video: Path, audio: Path, out: Path):
    cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(video), "-i", str(audio),
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "fast", "-crf", "22",
           "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
           "-shortest", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


# ── 메인 ─────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("Veo 클립 재생성 — 제대로 된 모션 프롬프트 사용")
    print("=" * 60)

    # DB에서 shot_script + frame_image_paths 로드
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT stage_results FROM projects WHERE id=?", (PROJECT_ID,)).fetchone()
    sr = json.loads(row[0])
    shots = sr.get("shot_script", {}).get("shots", [])
    frame_image_paths = sr.get("frame_image_paths", {})
    content = sr.get("content", {})
    platform_contents = content.get("platform_contents", [])
    yt = next((p for p in platform_contents if p.get("platform") == "youtube"), None)
    slide_texts = yt.get("body", []) if yt else []
    conn.close()

    print(f"샷 수: {len(shots)}개 | 슬라이드: {NUM_SLIDES}개")

    # DYNAMIC 샷만 처리
    dynamic_shots = [(i, s) for i, s in enumerate(shots) if s.get("shot_type") == "DYNAMIC"]
    print(f"DYNAMIC 샷: {len(dynamic_shots)}개\n")

    # 이미지 경로 정규화
    def get_image(si: int, fi: int) -> Path | None:
        for key in [f"{si}_{fi}", f"{si},{fi}", str(si) + "_" + str(fi)]:
            v = frame_image_paths.get(key)
            if v:
                p = Path(v)
                if p.exists():
                    return p
        # 직접 파일 탐색
        candidates = list(SCENES_DIR.glob(f"{TOPIC}_*_s{si:02d}_f{fi:02d}.*"))
        if candidates:
            return candidates[0]
        return None

    # Step 1: 프롬프트 생성 (Gemini Vision) - 5개씩 병렬
    print("[1단계] Gemini Vision으로 모션 프롬프트 생성...")
    shot_prompts: dict[int, str] = {}

    async def gen_prompt(idx: int, shot: dict) -> tuple[int, str]:
        si, fi = shot["slide_index"], shot["frame_index"]
        img = get_image(si, fi)
        if not img:
            return idx, f"{shot.get('camera_movement', 'slow push forward')}. Scene unfolds naturally. Atmospheric mood."

        prompt = await generate_motion_prompt_for_image(
            image_path=img,
            shot_type=shot["shot_type"],
            camera_movement=shot.get("camera_movement", ""),
            topic="조선 건국의 비밀 (Founding of Joseon Dynasty)",
        )
        print(f"  s{si:02d}_f{fi:02d}: {prompt[:70]}...")
        return idx, prompt

    # 5개씩 배치 처리
    for batch_start in range(0, len(dynamic_shots), 5):
        batch = dynamic_shots[batch_start:batch_start + 5]
        results = await asyncio.gather(*(gen_prompt(idx, shot) for idx, shot in batch))
        for idx, p in results:
            shot_prompts[idx] = p
        if batch_start + 5 < len(dynamic_shots):
            await asyncio.sleep(1)

    print(f"  프롬프트 생성 완료: {len(shot_prompts)}개\n")

    # Step 2: Veo 클립 생성 (순차 - API 제한)
    print("[2단계] Veo 2 클립 생성...")
    new_clips: dict[tuple, Path] = {}

    for idx, shot in dynamic_shots:
        si, fi = shot["slide_index"], shot["frame_index"]
        img = get_image(si, fi)
        if not img:
            print(f"  s{si:02d}_f{fi:02d}: 이미지 없음 — 스킵")
            continue

        prompt = shot_prompts.get(idx, "slow push forward. Scene unfolds naturally.")
        dur = int(min(shot.get("duration_target", 5), 8))

        veo_out = CLIPS_DIR / f"{TOPIC}_s{si:02d}_f{fi:02d}_veo_v2.mp4"
        final_out = CLIPS_DIR / f"{TOPIC}_s{si:02d}_f{fi:02d}.mp4"

        print(f"\n  s{si:02d}_f{fi:02d} [DYNAMIC {dur}s]:")
        result = await generate_veo_clip(img, prompt, veo_out, dur)

        if result:
            # Veo 성공: final clip 업데이트
            import shutil
            shutil.copy2(veo_out, final_out)
            new_clips[(si, fi)] = final_out
            print(f"    → final clip 업데이트")
        else:
            # Veo 실패 → 스킵 (Ken Burns 폴백 없음 — 시간/비용 낭비)
            print(f"    → 스킵 (기존 클립 유지)")

        # Veo rate limit 방지
        await asyncio.sleep(3)

    print(f"\n클립 생성 완료: {len(new_clips)}개\n")

    # Step 3: 최종 영상 조립
    print("[3단계] 최종 영상 조립...")
    tmp_dir = OUT_DIR / "tmp_final"
    tmp_dir.mkdir(exist_ok=True)

    slide_videos: list[Path] = []

    for si in range(NUM_SLIDES):
        clips = sorted(CLIPS_DIR.glob(f"{TOPIC}_s{si:02d}_f*.mp4"))
        clips = [c for c in clips if not any(
            c.stem.endswith(s) for s in ("_veo", "_veo_v2", "_kb", "_kb_v2", "_kling", "_ext", "_trim")
        )]
        audio = AUDIO_DIR / f"{TOPIC}_s{si:02d}_new.mp3"
        if not audio.exists():
            audio = AUDIO_DIR / f"{TOPIC}_s{si:02d}.mp3"

        if not clips or not audio.exists():
            print(f"  s{si:02d}: 스킵 (클립:{len(clips)} 오디오:{audio.exists()})")
            continue

        silent = tmp_dir / f"s{si:02d}_silent.mp4"
        if len(clips) == 1:
            import shutil
            shutil.copy(clips[0], silent)
        else:
            concat_list(clips, silent)

        out = tmp_dir / f"s{si:02d}_merged.mp4"
        mix_audio(silent, audio, out)
        slide_videos.append(out)

        v_dur = get_duration(silent)
        a_dur = get_duration(audio)
        print(f"  s{si:02d}: {len(clips)}클립 {v_dur:.0f}s + TTS {a_dur:.0f}s")

    full_out = OUT_DIR / f"{TOPIC}_final_v3.mp4"
    concat_list(slide_videos, full_out, reencode=True)

    dur = get_duration(full_out)
    size = full_out.stat().st_size / 1024 / 1024

    # DB 업데이트
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT stage_results FROM projects WHERE id=?", (PROJECT_ID,)).fetchone()
    sr2 = json.loads(row[0])
    sr2["video"] = {
        "platform": "youtube",
        "full_video": str(full_out),
        "duration": round(dur, 1),
        "clips_count": sum(len(list(CLIPS_DIR.glob(f"{TOPIC}_s{si:02d}_f*.mp4"))) for si in range(NUM_SLIDES)),
    }
    conn.execute("UPDATE projects SET stage_results=?, status='passed' WHERE id=?",
                 (json.dumps(sr2), PROJECT_ID))
    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"완료: {full_out.name}")
    print(f"  길이: {dur:.0f}초 ({dur/60:.1f}분) | 크기: {size:.1f}MB")
    print(f"  새 Veo 클립: {len(new_clips)}개")
    print(f"{'='*60}")

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
