"""
Shorts Extractor Agent — 롱폼 영상 → Shorts/Reels 자동 추출
역할: 전체 YouTube 영상에서 최고 임팩트 구간 자동 추출 → 9:16 크롭 → Shorts/Reels 파일 생성

추출 전략:
  1. Hook-first: 훅 씬 (0번 슬라이드) 반드시 포함
  2. 최고 점수 씬 우선: 슬라이드 텍스트 기반 임팩트 점수
  3. 길이 제한: 60초 이하 (YouTube Shorts/TikTok/Instagram Reels 공통)
  4. 9:16 크롭: 16:9 영상 중앙을 9:16으로 크롭

임팩트 점수 계산:
  - 숫자/통계 포함: +2점
  - 의문문/흥미 유발: +1.5점
  - 짧고 강렬한 문장 (30자 이하): +1점
  - 행동 유도 키워드: +1점
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger


MAX_SHORTS_DURATION = 58  # 60초 제한에 여유 2초
MIN_SCENE_DURATION = 3.0


@dataclass
class ShortsSpec:
    selected_slide_indices: list[int]
    estimated_duration: float
    extraction_strategy: str  # "hook_first" | "best_scenes" | "sequential"


def _score_slide(text: str) -> float:
    """슬라이드 텍스트 임팩트 점수 계산"""
    score = 1.0

    # 숫자/통계 포함
    if re.search(r"\d+", text):
        score += 2.0

    # 의문문
    if "?" in text or "?" in text:
        score += 1.5

    # 짧고 강렬한 문장
    if len(text.strip()) <= 30:
        score += 1.0

    # 행동 유도 / 임팩트 키워드
    impact_keywords = [
        "비밀", "충격", "진짜", "처음", "최고", "최악", "폭발", "역대",
        "secret", "shocking", "revealed", "exclusive", "never", "first",
        "秘密", "衝撃", "最高", "初めて",
    ]
    text_lower = text.lower()
    for kw in impact_keywords:
        if kw.lower() in text_lower:
            score += 1.0
            break

    return score


def select_shorts_scenes(
    slide_texts: list[str],
    scene_durations: list[float],
    max_duration: float = MAX_SHORTS_DURATION,
) -> ShortsSpec:
    """
    슬라이드 목록에서 Shorts용 최적 씬 선택

    Args:
        slide_texts: 슬라이드 텍스트 목록
        scene_durations: 씬별 재생 시간 (초)
        max_duration: 최대 Shorts 길이

    Returns:
        ShortsSpec (선택된 슬라이드 인덱스 포함)
    """
    if not slide_texts:
        return ShortsSpec([], 0.0, "empty")

    n = len(slide_texts)
    durations = list(scene_durations) if scene_durations else [6.0] * n
    while len(durations) < n:
        durations.append(6.0)

    # 점수 계산
    scores = [_score_slide(text) for text in slide_texts]

    # Hook (슬라이드 0) 항상 포함
    selected = [0]
    total_dur = durations[0]

    # 나머지 씬을 점수 내림차순으로 추가
    remaining = sorted(
        range(1, n),
        key=lambda i: scores[i],
        reverse=True,
    )

    for idx in remaining:
        scene_dur = durations[idx]
        if total_dur + scene_dur > max_duration:
            continue
        selected.append(idx)
        total_dur += scene_dur
        if total_dur >= max_duration * 0.85:  # 85% 채우면 종료
            break

    # 시간순 정렬 (훅 → 선택된 씬 순서)
    selected = sorted(selected)

    strategy = "hook_first" if len(selected) < n else "sequential"

    logger.info(
        f"[ShortsExtractor] 씬 선택 완료: {len(selected)}/{n}개 "
        f"| 예상 길이: {total_dur:.1f}초 | 전략: {strategy}"
    )

    return ShortsSpec(
        selected_slide_indices=selected,
        estimated_duration=total_dur,
        extraction_strategy=strategy,
    )


def extract_shorts(
    full_video_path: Path,
    output_path: Path,
    clip_paths: list[Path | None],
    slide_texts: list[str],
    scene_durations: list[float] | None = None,
    audio_paths: list[Path | None] | None = None,
    crop_to_vertical: bool = True,
) -> Path | None:
    """
    롱폼 영상 클립들 → Shorts 파일 생성

    두 가지 경로:
    a) clip_paths 있음: 개별 씬 클립에서 선택해서 합치기 (품질 최고)
    b) full_video_path: 전체 영상에서 구간 추출 (fallback)
    """
    try:
        from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip

        durations = scene_durations or [6.0] * len(slide_texts)
        spec = select_shorts_scenes(slide_texts, durations)

        if not spec.selected_slide_indices:
            logger.warning("[ShortsExtractor] 선택된 씬 없음")
            return None

        # 경로 a: 개별 클립에서 선택
        valid_clips = [p for p in (clip_paths or []) if p and Path(p).exists()]

        if valid_clips:
            segments = []
            for idx in spec.selected_slide_indices:
                if idx >= len(clip_paths) or not clip_paths[idx]:
                    continue
                cp = Path(clip_paths[idx])
                if not cp.exists():
                    continue
                try:
                    clip = VideoFileClip(str(cp))

                    # 오디오 추가
                    if audio_paths and idx < len(audio_paths) and audio_paths[idx]:
                        ap = Path(audio_paths[idx])
                        if ap.exists():
                            audio = AudioFileClip(str(ap))
                            audio = audio.with_duration(min(audio.duration, clip.duration))
                            clip = clip.with_audio(audio)

                    # 9:16 크롭 (16:9 → 세로)
                    if crop_to_vertical and clip.w > clip.h:
                        new_w = int(clip.h * 9 / 16)
                        x_offset = (clip.w - new_w) // 2
                        clip = clip.cropped(x1=x_offset, x2=x_offset + new_w)

                    segments.append(clip)
                except Exception as e:
                    logger.warning(f"  씬 {idx} 로드 실패: {e}")

            if not segments:
                logger.warning("[ShortsExtractor] 유효한 세그먼트 없음")
                return None

            shorts = concatenate_videoclips(segments, method="compose")

        else:
            # 경로 b: 전체 영상에서 구간 추출
            if not full_video_path or not full_video_path.exists():
                logger.warning("[ShortsExtractor] 영상 파일 없음")
                return None

            full_clip = VideoFileClip(str(full_video_path))

            # 시작~추정 길이만큼 추출
            end_time = min(spec.estimated_duration, full_clip.duration)
            shorts = full_clip.subclipped(0, end_time)

            if crop_to_vertical and shorts.w > shorts.h:
                new_w = int(shorts.h * 9 / 16)
                x_offset = (shorts.w - new_w) // 2
                shorts = shorts.cropped(x1=x_offset, x2=x_offset + new_w)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shorts.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            ffmpeg_params=["-movflags", "faststart"],
        )

        logger.info(
            f"[ShortsExtractor] Shorts 저장 완료: {output_path.name} "
            f"({shorts.duration:.1f}초, {shorts.w}x{shorts.h})"
        )
        return output_path

    except Exception as e:
        logger.error(f"[ShortsExtractor] 실패: {e}")
        return None
