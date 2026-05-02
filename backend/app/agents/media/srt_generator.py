"""
SRT Subtitle Generator

TTS 오디오 파일 duration → 타임스탬프 → SRT 자막 파일 생성

사용 방식:
  - content 언어 primary, EN secondary (KO 콘텐츠)
  - Korea Untold (EN 콘텐츠): EN primary, KO secondary 생략
  - YouTube captions.insert() 용 .srt 파일 출력
"""
import wave
import contextlib
import subprocess
from pathlib import Path
from loguru import logger


def _get_audio_duration(path: Path) -> float:
    """오디오 파일 재생 시간 (초) — WAV는 wave 모듈, 그 외는 ffprobe"""
    if path.suffix.lower() == ".wav":
        try:
            with contextlib.closing(wave.open(str(path))) as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            pass

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"[SRT] duration 측정 실패 ({path.name}): {e}")
        return 5.0  # 기본값 5초


def _seconds_to_srt_timestamp(seconds: float) -> str:
    """초 → SRT 타임스탬프 형식 HH:MM:SS,mmm"""
    ms = int((seconds % 1) * 1000)
    total_s = int(seconds)
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _split_into_lines(text: str, max_chars: int = 42) -> str:
    """긴 자막 텍스트를 2줄 이내로 분리 (SRT 화면 가독성)"""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    # 중간 근처 공백에서 줄 나누기
    mid = len(text) // 2
    best_split = mid
    for i in range(mid, min(mid + 20, len(text))):
        if text[i] == " ":
            best_split = i
            break
    else:
        for i in range(mid, max(mid - 20, 0), -1):
            if text[i] == " ":
                best_split = i
                break

    line1 = text[:best_split].strip()
    line2 = text[best_split:].strip()

    # 3줄 이상 방지 — 2줄 초과 시 그냥 원문 반환
    if len(line1) > max_chars or len(line2) > max_chars:
        return text

    return f"{line1}\n{line2}"


def generate_srt(
    slide_texts: list[str],
    audio_paths: list[Path],
    output_path: Path,
    gap_seconds: float = 0.1,
) -> Path:
    """
    슬라이드 텍스트 + TTS 오디오 → SRT 자막 파일

    Args:
        slide_texts: 슬라이드 텍스트 목록 (자막으로 표시할 내용)
        audio_paths: 슬라이드별 TTS 오디오 파일 경로 목록
        output_path: 저장할 .srt 파일 경로
        gap_seconds: 슬라이드 간 공백 (자막 끊김 방지)

    Returns:
        생성된 SRT 파일 경로
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    entries = []
    cursor = 0.0
    idx = 0

    for i, (text, audio) in enumerate(zip(slide_texts, audio_paths)):
        if not audio or not Path(audio).exists():
            logger.warning(f"[SRT] s{i:02d} 오디오 없음 — 스킵")
            continue

        duration = _get_audio_duration(Path(audio))
        start = cursor
        end = cursor + duration - gap_seconds  # 살짝 일찍 끝내 겹침 방지

        idx += 1
        formatted_text = _split_into_lines(text.strip())

        entries.append(
            f"{idx}\n"
            f"{_seconds_to_srt_timestamp(start)} --> {_seconds_to_srt_timestamp(max(end, start + 0.5))}\n"
            f"{formatted_text}\n"
        )

        cursor += duration

    srt_content = "\n".join(entries)
    output_path.write_text(srt_content, encoding="utf-8")

    logger.info(f"[SRT] {len(entries)}개 항목 → {output_path.name} ({cursor:.1f}초)")
    return output_path


def generate_srt_pair(
    slide_texts_primary: list[str],
    slide_texts_secondary: list[str] | None,
    audio_paths: list[Path],
    output_dir: Path,
    primary_lang: str = "en",
    secondary_lang: str | None = None,
    slug: str = "episode",
) -> dict[str, Path]:
    """
    primary + secondary 언어 SRT 쌍 생성

    Korea Untold (EN 콘텐츠): primary_lang="en", secondary_lang=None
    KO 콘텐츠 → EN 배포:    primary_lang="ko", secondary_lang="en"

    Returns:
        {"en": Path, "ko": Path} 형태 (존재하는 언어만 포함)
    """
    result: dict[str, Path] = {}

    primary_path = output_dir / f"{slug}_{primary_lang}.srt"
    generate_srt(slide_texts_primary, audio_paths, primary_path)
    result[primary_lang] = primary_path

    if slide_texts_secondary and secondary_lang:
        secondary_path = output_dir / f"{slug}_{secondary_lang}.srt"
        generate_srt(slide_texts_secondary, audio_paths, secondary_path)
        result[secondary_lang] = secondary_path

    return result
