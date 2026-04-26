"""
Video Reviewer Agent — 영상 품질 검수
역할: 생성된 영상 파일의 기술적 품질 검증 (코드 기반, LLM 없음)

검수 항목:
  1. 파일 존재 및 최소 크기 (빈 파일 감지)
  2. 영상 길이 (플랫폼 최소/최대 기준)
  3. 해상도 (플랫폼별 최소 해상도)
  4. FPS (24fps 이상 권장)
  5. 씬 수 대비 길이 (씬당 최소 3초 이상)
  6. 오디오 트랙 존재 여부 (TTS 활성화 시)
"""
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger


# 플랫폼별 영상 스펙 기준
PLATFORM_SPECS = {
    "youtube": {
        "min_duration": 60,       # YouTube 최소 60초 (Shorts 기준 이상)
        "recommended_duration": 480,  # 8분
        "max_duration": 3600,
        "min_width": 1280,
        "min_height": 720,
        "min_fps": 24,
        "aspect_ratio": "16:9",
    },
    "youtube_shorts": {
        "min_duration": 15,
        "max_duration": 60,
        "min_width": 1080,
        "min_height": 1920,
        "min_fps": 24,
        "aspect_ratio": "9:16",
    },
    "tiktok": {
        "min_duration": 5,
        "max_duration": 180,
        "min_width": 1080,
        "min_height": 1920,
        "min_fps": 24,
        "aspect_ratio": "9:16",
    },
    "instagram": {
        "min_duration": 3,
        "max_duration": 90,
        "min_width": 1080,
        "min_height": 1080,
        "min_fps": 24,
        "aspect_ratio": "1:1",
    },
}


@dataclass
class VideoIssue:
    severity: str   # "error" | "warning"
    category: str   # "file" | "duration" | "resolution" | "fps" | "audio" | "pacing"
    message: str


@dataclass
class VideoReviewResult:
    passed: bool
    score: float        # 0~100
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    file_size_mb: float = 0.0
    issues: list[VideoIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class VideoReviewerAgent:
    """영상 기술 품질 검수 에이전트"""

    def review(
        self,
        video_path: Path,
        platform: str = "youtube",
        expected_slide_count: int = 0,
        tts_enabled: bool = False,
    ) -> VideoReviewResult:
        """영상 파일 품질 검수"""
        issues: list[VideoIssue] = []
        recommendations: list[str] = []

        # 1. 파일 존재 및 크기
        if not video_path.exists():
            return VideoReviewResult(
                passed=False,
                score=0.0,
                issues=[VideoIssue("error", "file", f"파일 없음: {video_path.name}")],
            )

        file_size_mb = video_path.stat().st_size / (1024 * 1024)
        if file_size_mb < 0.1:
            issues.append(VideoIssue("error", "file", f"파일 크기 {file_size_mb:.2f}MB — 렌더링 실패 가능성"))

        # 2. moviepy로 메타데이터 읽기
        duration = 0.0
        width = height = fps = 0
        has_audio = False

        try:
            from moviepy import VideoFileClip
            with VideoFileClip(str(video_path)) as clip:
                duration = clip.duration
                width = clip.w
                height = clip.h
                fps = clip.fps or 0
                has_audio = clip.audio is not None
        except Exception as e:
            issues.append(VideoIssue("error", "file", f"영상 읽기 실패: {e}"))
            return VideoReviewResult(
                passed=False, score=0.0,
                file_size_mb=file_size_mb,
                issues=issues,
            )

        specs = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["youtube"])

        # 3. 영상 길이 검수
        min_dur = specs.get("min_duration", 10)
        max_dur = specs.get("max_duration", 3600)

        if duration < min_dur:
            issues.append(VideoIssue(
                "error", "duration",
                f"영상 길이 {duration:.1f}초 — {platform} 최소 {min_dur}초 미달"
            ))
            recommendations.append(f"슬라이드 수를 늘리거나 씬당 재생 시간을 늘려주세요 (현재 평균 {duration/max(expected_slide_count,1):.1f}초/씬)")
        elif duration > max_dur:
            issues.append(VideoIssue(
                "warning", "duration",
                f"영상 길이 {duration:.1f}초 — {platform} 최대 {max_dur}초 초과"
            ))

        # 4. 해상도 검수
        min_w = specs.get("min_width", 1280)
        min_h = specs.get("min_height", 720)

        if width < min_w or height < min_h:
            issues.append(VideoIssue(
                "warning", "resolution",
                f"해상도 {width}x{height} — {platform} 권장 {min_w}x{min_h} 미달"
            ))

        # 5. FPS 검수
        min_fps = specs.get("min_fps", 24)
        if fps > 0 and fps < min_fps:
            issues.append(VideoIssue(
                "warning", "fps",
                f"FPS {fps:.1f} — {min_fps}fps 미달, 영상이 끊겨 보일 수 있음"
            ))

        # 6. 오디오 검수
        if tts_enabled and not has_audio:
            issues.append(VideoIssue(
                "error", "audio",
                "TTS 활성화됐으나 오디오 트랙 없음 — TTS 생성 실패 가능성"
            ))
        elif not has_audio:
            recommendations.append("배경음악 또는 TTS 나레이션 추가를 권장합니다 (무음 영상은 시청 유지율 저하)")

        # 7. 페이싱 검수
        if expected_slide_count > 0:
            avg_per_slide = duration / expected_slide_count
            if avg_per_slide < 3:
                issues.append(VideoIssue(
                    "warning", "pacing",
                    f"씬당 평균 {avg_per_slide:.1f}초 — 너무 빠름 (최소 3초 권장)"
                ))
            elif avg_per_slide > 15 and platform == "youtube_shorts":
                issues.append(VideoIssue(
                    "warning", "pacing",
                    f"Shorts 씬당 {avg_per_slide:.1f}초 — 너무 느림 (Shorts는 빠른 페이싱 권장)"
                ))

        # 점수 산정
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        score = max(0.0, 100.0 - (error_count * 30) - (warning_count * 10))
        passed = error_count == 0 and score >= 60

        result = VideoReviewResult(
            passed=passed,
            score=score,
            duration=round(duration, 1),
            width=width,
            height=height,
            fps=round(fps, 1),
            has_audio=has_audio,
            file_size_mb=round(file_size_mb, 2),
            issues=issues,
            recommendations=recommendations,
        )

        logger.info(
            f"[VideoReviewerAgent] {'PASS' if passed else 'FAIL'} "
            f"({score:.0f}/100) | {width}x{height} {fps:.0f}fps {duration:.1f}s "
            f"| {error_count}errors {warning_count}warnings"
        )
        return result


def video_review_to_dict(result: VideoReviewResult) -> dict:
    return {
        "passed": result.passed,
        "score": result.score,
        "duration": result.duration,
        "resolution": f"{result.width}x{result.height}",
        "fps": result.fps,
        "has_audio": result.has_audio,
        "file_size_mb": result.file_size_mb,
        "issues": [
            {"severity": i.severity, "category": i.category, "message": i.message}
            for i in result.issues
        ],
        "recommendations": result.recommendations,
    }
