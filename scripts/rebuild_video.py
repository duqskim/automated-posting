#!/usr/bin/env python3
"""
조선 건국의 비밀 — TTS 재생성 + 최종 영상 조립 스크립트

1. DB에서 나레이션 텍스트 읽기
2. ElevenLabs로 새 TTS 생성 (y1NhmBYYU2Qohn8eR3YT, VoiceSettings 적용)
3. 기존 Veo/Ken Burns 클립 + 새 TTS → 최종 영상
"""

import asyncio
import os
import sqlite3
import subprocess
import sys
import tempfile
import json
import re
import unicodedata
from pathlib import Path

BASE = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

CLIPS_DIR = BASE / "output" / "video" / "clips"
AUDIO_DIR = BASE / "output" / "video" / "audio"
OUT_DIR   = BASE / "output" / "video"
DB_PATH   = BASE / "automated_posting.db"

TOPIC     = "조선_건국의_비밀"
PROJECT_ID = 8
VOICE_ID  = "y1NhmBYYU2Qohn8eR3YT"
NUM_SLIDES = 19


# ── 텍스트 전처리 ────────────────────────────────────────────

def preprocess_tts_text(text: str) -> str:
    """자연스러운 호흡/멈춤을 위한 텍스트 전처리"""
    # 이미 잘 쓰인 문어체이므로 최소한의 처리만
    text = text.strip()
    # 줄바꿈을 두 칸 공백으로 (ElevenLabs pause)
    text = re.sub(r'\n+', '  ', text)
    # 마침표/물음표/느낌표 뒤에 두 칸 공백 보장
    text = re.sub(r'([.?!])\s*', r'\1  ', text)
    # 중복 공백 정리
    text = re.sub(r'  +', '  ', text)
    return text.strip()


# ── TTS 생성 ─────────────────────────────────────────────────

async def generate_tts_batch(texts: list[str]) -> list[Path | None]:
    """19개 TTS를 병렬 생성"""
    from elevenlabs import ElevenLabs, VoiceSettings

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("[ERROR] ELEVENLABS_API_KEY 없음")
        return [None] * len(texts)

    client = ElevenLabs(api_key=api_key)

    async def gen_one(i: int, text: str) -> Path | None:
        out = AUDIO_DIR / f"{TOPIC}_s{i:02d}_new.mp3"
        try:
            processed = preprocess_tts_text(text)
            audio = client.text_to_speech.convert(
                voice_id=VOICE_ID,
                text=processed,
                model_id="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    stability=0.35,
                    similarity_boost=0.80,
                    style=0.45,
                    use_speaker_boost=True,
                ),
            )
            audio_bytes = b"".join(audio) if hasattr(audio, "__iter__") else audio
            out.write_bytes(audio_bytes)
            print(f"  [TTS] s{i:02d} 완료 ({len(audio_bytes)//1024}KB)")
            return out
        except Exception as e:
            print(f"  [TTS] s{i:02d} 실패: {e}")
            return None

    # 병렬 생성 (API 과부하 방지: 5개씩 배치)
    results = []
    for batch_start in range(0, len(texts), 5):
        batch = texts[batch_start:batch_start + 5]
        batch_results = await asyncio.gather(
            *(gen_one(batch_start + j, text) for j, text in enumerate(batch))
        )
        results.extend(batch_results)
        if batch_start + 5 < len(texts):
            await asyncio.sleep(2)  # 배치 간 짧은 대기

    return results


# ── ffmpeg 헬퍼 ──────────────────────────────────────────────

def get_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def concat_clips(clip_paths: list[Path], out_path: Path, reencode_audio: bool = False) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")
        list_file = f.name

    try:
        if reencode_audio:
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                   "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                   str(out_path)]
        else:
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                   "-c", "copy", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"concat 실패: {result.stderr[-300:]}")
    finally:
        os.unlink(list_file)


def mix_audio(video_path: Path, audio_path: Path, out_path: Path) -> None:
    """비디오 + 오디오 믹싱, 오디오 길이에 맞춤"""
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"믹싱 실패: {result.stderr[-200:]}")


# ── DB 업데이트 ──────────────────────────────────────────────

def update_db(full_video_path: Path, duration: float, clips_count: int):
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT stage_results FROM projects WHERE id=?", (PROJECT_ID,)).fetchone()
    sr = json.loads(row[0]) if row else {}

    sr["video"] = {
        "platform": "youtube",
        "full_video": str(full_video_path),
        "shorts_video": None,
        "duration": round(duration, 1),
        "clips_count": clips_count,
    }

    conn.execute(
        "UPDATE projects SET stage_results=?, status='passed' WHERE id=?",
        (json.dumps(sr), PROJECT_ID)
    )
    conn.commit()
    conn.close()
    print(f"  [DB] stage_results 업데이트 완료")


# ── 메인 ─────────────────────────────────────────────────────

async def main():
    print("=" * 50)
    print("조선 건국의 비밀 — TTS 재생성 + 최종 조립")
    print("=" * 50)

    # 1. DB에서 나레이션 텍스트 로드
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT stage_results FROM projects WHERE id=?", (PROJECT_ID,)).fetchone()
    sr = json.loads(row[0])
    content = sr.get("content", {})
    platform_contents = content.get("platform_contents", [])
    yt = next((p for p in platform_contents if p.get("platform") == "youtube"), None)
    if not yt:
        print("[ERROR] YouTube 콘텐츠 없음")
        return
    slide_texts = yt.get("body", [])
    conn.close()
    print(f"\n[1] 나레이션 텍스트 {len(slide_texts)}개 로드")

    # 2. TTS 재생성
    print(f"\n[2] ElevenLabs TTS 재생성 (voice={VOICE_ID[:8]}...)")
    audio_paths = await generate_tts_batch(slide_texts)
    success = sum(1 for p in audio_paths if p)
    print(f"    완료: {success}/{len(slide_texts)}")

    # TTS 실패 슬라이드는 기존 파일로 폴백
    final_audio: list[Path | None] = []
    for i, p in enumerate(audio_paths):
        if p and p.exists():
            final_audio.append(p)
        else:
            fallback = AUDIO_DIR / f"{TOPIC}_s{i:02d}.mp3"
            if fallback.exists():
                print(f"  s{i:02d}: 기존 TTS 파일 사용")
                final_audio.append(fallback)
            else:
                print(f"  s{i:02d}: TTS 없음")
                final_audio.append(None)

    # 3. 슬라이드별 클립 concat + 오디오 믹싱
    print(f"\n[3] 슬라이드별 조립...")
    tmp_dir = OUT_DIR / "tmp_rebuild"
    tmp_dir.mkdir(exist_ok=True)

    slide_videos: list[Path] = []
    total_clips = 0

    for si in range(NUM_SLIDES):
        clips = sorted(CLIPS_DIR.glob(f"{TOPIC}_s{si:02d}_f*.mp4"))
        # 서픽스 파일 제외 (최종 클립만)
        clips = [c for c in clips if not any(
            c.stem.endswith(s) for s in ("_veo", "_kb", "_kling", "_ext", "_trim")
        )]

        audio_path = final_audio[si] if si < len(final_audio) else None

        if not clips:
            print(f"  s{si:02d}: 클립 없음 — 스킵")
            continue
        if not audio_path:
            print(f"  s{si:02d}: 오디오 없음 — 스킵")
            continue

        # 클립 concat (무음)
        silent = tmp_dir / f"{TOPIC}_s{si:02d}_silent.mp4"
        if len(clips) == 1:
            import shutil
            shutil.copy(clips[0], silent)
        else:
            concat_clips(clips, silent)

        v_dur = get_duration(silent)
        a_dur = get_duration(audio_path)

        # 오디오 믹싱
        slide_out = tmp_dir / f"{TOPIC}_s{si:02d}_final.mp4"
        mix_audio(silent, audio_path, slide_out)
        slide_videos.append(slide_out)
        total_clips += len(clips)

        src = "Veo" if (CLIPS_DIR / f"{TOPIC}_s{si:02d}_f00_veo.mp4").exists() else "KB"
        print(f"  s{si:02d} [{src}] {len(clips)}클립 {v_dur:.0f}s + TTS {a_dur:.0f}s → {slide_out.name}")

    print(f"\n  완료: {len(slide_videos)}/19 슬라이드")

    # 4. 최종 concat
    print(f"\n[4] 최종 영상 조립...")
    full_out = OUT_DIR / f"{TOPIC}_final_v2.mp4"
    concat_clips(slide_videos, full_out, reencode_audio=True)

    dur = get_duration(full_out)
    size_mb = full_out.stat().st_size / 1024 / 1024

    print(f"\n{'='*50}")
    print(f"완료: {full_out.name}")
    print(f"  길이: {dur:.1f}초 ({dur/60:.1f}분)")
    print(f"  크기: {size_mb:.1f} MB")
    print(f"  클립: {total_clips}개")
    print(f"{'='*50}")

    # 5. DB 업데이트
    update_db(full_out, dur, total_clips)

    # 임시 파일 정리
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
