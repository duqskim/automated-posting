#!/usr/bin/env python3
"""
조선 건국의 비밀 — 최종 영상 조립 스크립트
API 호출 없음. 기존 Ken Burns 클립 + ElevenLabs TTS 오디오만 사용.

동작:
  1. 슬라이드별 클립(s{i}_f*.mp4) concat → 무음 슬라이드 영상
  2. 무음 슬라이드 영상 + TTS 오디오 믹싱 (오디오 길이 맞춤)
  3. 19개 슬라이드 영상 → full.mp4
"""

import subprocess
import tempfile
import os
import glob
from pathlib import Path

CLIPS_DIR  = Path("/Users/sol/.gemini/antigravity/playground/automated-posting/backend/output/video/clips")
AUDIO_DIR  = Path("/Users/sol/.gemini/antigravity/playground/automated-posting/backend/output/video/audio")
OUT_DIR    = Path("/Users/sol/.gemini/antigravity/playground/automated-posting/backend/output/video")
TOPIC      = "조선_건국의_비밀"
NUM_SLIDES = 19


def run(cmd: list[str], desc: str = "") -> subprocess.CompletedProcess:
    print(f"  > {desc or ' '.join(cmd[:4])}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg failed: {desc}")
    return result


def get_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def concat_clips(clip_paths: list[Path], out_path: Path) -> None:
    """여러 클립을 순서대로 이어붙임 (concat demuxer 사용)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
        list_file = f.name

    try:
        run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
             "-c", "copy", str(out_path)],
            f"concat {len(clip_paths)} clips → {out_path.name}"
        )
    finally:
        os.unlink(list_file)


def mix_audio(video_path: Path, audio_path: Path, out_path: Path) -> None:
    """
    오디오 길이에 맞춰 영상 조립:
    - 영상이 짧으면 마지막 프레임으로 패딩 (stream_loop -1 + shortest)
    - 영상이 길면 오디오 끝에서 자름
    """
    run(
        ["ffmpeg", "-y",
         "-stream_loop", "-1", "-i", str(video_path),
         "-i", str(audio_path),
         "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "fast", "-crf", "23",
         "-c:a", "aac", "-b:a", "192k",
         "-shortest",
         str(out_path)],
        f"mix audio → {out_path.name}"
    )


def main():
    tmp_dir = OUT_DIR / "tmp_assembly"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    slide_videos: list[Path] = []

    for si in range(NUM_SLIDES):
        slide_id = f"s{si:02d}"
        audio_path = AUDIO_DIR / f"{TOPIC}_{slide_id}.mp3"

        # 이 슬라이드의 클립 목록 (정렬)
        clip_pattern = str(CLIPS_DIR / f"{TOPIC}_{slide_id}_f*.mp4")
        clips = sorted(glob.glob(clip_pattern))

        if not clips:
            print(f"[SKIP] {slide_id}: 클립 없음")
            continue

        if not audio_path.exists():
            print(f"[SKIP] {slide_id}: 오디오 없음 ({audio_path.name})")
            continue

        print(f"\n[{slide_id}] 클립 {len(clips)}개 + 오디오 조립")

        # 1. 클립 concat (무음)
        silent_path = tmp_dir / f"{TOPIC}_{slide_id}_silent.mp4"
        if len(clips) == 1:
            # 단일 클립은 복사만
            import shutil
            shutil.copy(clips[0], silent_path)
        else:
            concat_clips([Path(c) for c in clips], silent_path)

        dur_video = get_duration(silent_path)
        dur_audio = get_duration(audio_path)
        print(f"  영상: {dur_video:.1f}s  오디오: {dur_audio:.1f}s")

        # 2. 오디오 믹싱
        slide_out = tmp_dir / f"{TOPIC}_{slide_id}_final.mp4"
        mix_audio(silent_path, audio_path, slide_out)

        slide_videos.append(slide_out)
        print(f"  완료: {slide_out.name}")

    if not slide_videos:
        print("[ERROR] 조립할 슬라이드가 없습니다.")
        return

    print(f"\n[최종] {len(slide_videos)}개 슬라이드 → full.mp4")

    # 3. 전체 concat
    full_out = OUT_DIR / f"{TOPIC}_full.mp4"
    concat_clips(slide_videos, full_out)

    dur_total = get_duration(full_out)
    size_mb = full_out.stat().st_size / 1024 / 1024
    print(f"\n완료: {full_out}")
    print(f"  총 길이: {dur_total:.1f}초 ({dur_total/60:.1f}분)")
    print(f"  파일 크기: {size_mb:.1f} MB")

    # 임시 파일 정리 (선택)
    # import shutil
    # shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    main()
