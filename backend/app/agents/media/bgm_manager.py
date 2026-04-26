"""
BGM Manager — 배경음악 선택 및 믹싱

BGM 파일은 backend/assets/bgm/{category}/ 에 .mp3/.wav 형식으로 추가하면 됩니다.
파일이 없으면 ffmpeg로 ambient 톤을 자동 생성합니다 (fallback).

카테고리:
  cinematic  — 역사/다큐 (orchestral, epic) → Korea Untold 기본값
  ambient    — 잔잔한 배경음 (lo-fi, soft)
  upbeat     — 밝고 경쾌한 (corporate, motivational)
  dramatic   — 긴장감 (thriller, suspense)
"""
import os
import random
import subprocess
from pathlib import Path
from loguru import logger

BGM_DIR = Path(__file__).parents[3] / "assets" / "bgm"
BGM_DIR.mkdir(parents=True, exist_ok=True)

# 콘텐츠 카테고리 → BGM 카테고리 매핑
CATEGORY_MAP: dict[str, str] = {
    "history":  "cinematic",
    "finance":  "ambient",
    "kids":     "upbeat",
    "drama":    "dramatic",
    "science":  "ambient",
    "custom":   "cinematic",
}

# BGM 볼륨 (0.0 ~ 1.0, 나레이션 대비 배경음 비율)
BGM_VOLUME = 0.18


def get_bgm_category(series_category: str | None) -> str:
    """시리즈 카테고리 → BGM 카테고리"""
    return CATEGORY_MAP.get(series_category or "custom", "cinematic")


def list_bgm_files(category: str) -> list[Path]:
    """카테고리 디렉토리의 .mp3/.wav 파일 목록"""
    cat_dir = BGM_DIR / category
    if not cat_dir.exists():
        return []
    return [
        f for f in cat_dir.iterdir()
        if f.suffix.lower() in (".mp3", ".wav", ".m4a") and f.stat().st_size > 0
    ]


def generate_ambient_bgm(output_path: Path, duration: float, category: str = "cinematic") -> Path | None:
    """ffmpeg로 ambient BGM 자동 생성 (실제 파일 없을 때 fallback)

    cinematic : 저음 드론 + 5도 화음 (D2 + A2)
    ambient   : 부드러운 고음 패드 (A4 + E5)
    upbeat    : 밝은 중음 (C4 + G4 + E4)
    dramatic  : 낮고 긴장된 드론 (C2)
    """
    freq_map = {
        "cinematic": [("sine=f=73.4:r=44100", 0.25), ("sine=f=110:r=44100", 0.15)],   # D2 + A2
        "ambient":   [("sine=f=440:r=44100", 0.12), ("sine=f=659.3:r=44100", 0.08)],  # A4 + E5
        "upbeat":    [("sine=f=261.6:r=44100", 0.20), ("sine=f=392:r=44100", 0.15)],  # C4 + G4
        "dramatic":  [("sine=f=65.4:r=44100", 0.30)],                                 # C2
    }
    freqs = freq_map.get(category, freq_map["cinematic"])

    # 각 sine 레이어를 amix로 합성
    filter_parts = []
    inputs = []
    for i, (f, vol) in enumerate(freqs):
        inputs += ["-f", "lavfi", "-i", f"{f},volume={vol}"]
        filter_parts.append(f"[{i}:a]")

    if len(freqs) > 1:
        amix = f"{''.join(filter_parts)}amix=inputs={len(freqs)}:duration=longest[out]"
        filter_complex = ["-filter_complex", amix, "-map", "[out]"]
    else:
        filter_complex = []

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        *filter_complex,
        "-t", str(int(duration) + 5),          # 영상보다 5초 여유
        "-af", "afade=t=in:st=0:d=3,afade=t=out:st=" + str(int(duration)),  # fade in/out
        str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"  [BGM] ambient 생성 완료: {output_path.name} ({category})")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.warning(f"  [BGM] ambient 생성 실패: {e.stderr.decode()[:200]}")
        return None


def select_bgm(category: str, duration: float, slug: str) -> Path | None:
    """BGM 파일 선택 (실제 파일 우선 → fallback 자동 생성)"""
    files = list_bgm_files(category)

    if files:
        chosen = random.choice(files)
        logger.info(f"  [BGM] 파일 선택: {chosen.name} ({category})")
        return chosen

    # fallback: ambient 톤 생성
    fallback_dir = BGM_DIR / "generated"
    fallback_dir.mkdir(exist_ok=True)
    fallback_path = fallback_dir / f"{slug}_{category}_bgm.wav"

    if fallback_path.exists() and fallback_path.stat().st_size > 0:
        return fallback_path

    logger.info(f"  [BGM] 실제 파일 없음 → ambient 톤 자동 생성 ({category})")
    return generate_ambient_bgm(fallback_path, duration, category)


def mix_bgm_into_video(video_path: Path, bgm_path: Path, output_path: Path, bgm_volume: float = BGM_VOLUME) -> Path | None:
    """ffmpeg로 영상에 BGM 믹싱 (기존 오디오 유지 + BGM 추가)"""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(bgm_path),
        "-filter_complex",
        f"[0:a]volume=1.0[a0];[1:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
        f"[a0][bgm]amix=inputs=2:duration=first:dropout_transition=3[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"  [BGM] 믹싱 완료: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.warning(f"  [BGM] 믹싱 실패: {e.stderr.decode()[:300]}")
        return None
