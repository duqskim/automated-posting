"""
Video Planner Agent — YouTube 씬별 샷 플래닝
역할: 슬라이드 텍스트 + 훅 → 씬별 샷 리스트, 카메라 무브먼트, 전환 효과, 페이싱 전략

일반 영상 제작에서 PD/연출팀이 하는 일:
  1. 전체 영상의 시각적 방향성 결정 (다큐, 소셜미디어, 기업홍보 등)
  2. 씬별 카메라 무브먼트 지정 (줌인, 팬, 달리 등)
  3. 전환 효과 지정 (컷, 페이드, 디졸브)
  4. 씬 길이 + 페이싱 (빠름/느림) 조율
  5. 나레이션 타이밍 큐
"""
import json
import os
import re
from dataclasses import dataclass, field
from loguru import logger

from app.config.market_profile import MarketProfile


@dataclass
class ShotSpec:
    slide_index: int
    visual_concept: str      # 구체적 시각 개념
    camera_movement: str     # slow_zoom_in | pan_left | pan_right | static | dolly_forward | handheld
    mood: str                # energetic | contemplative | dramatic | informative | inspiring
    duration_seconds: int    # 씬 재생 길이 (초)
    transition: str          # cut | fade | dissolve | wipe
    narration_cue: str       # 나레이션 시작 타이밍 힌트 ("즉시" | "0.5초 후" | "1초 후")
    ken_burns: bool = True   # 스틸이미지 Ken Burns 효과 사용 여부


@dataclass
class VideoPlan:
    platform: str
    total_duration_seconds: int
    pacing: str              # fast | moderate | slow
    visual_style: str        # documentary | social_media | corporate | cinematic
    color_theme: str         # warm | cool | neutral | high_contrast | vibrant
    opening_hook_seconds: int  # 첫 씬 길이 (훅이 가장 중요)
    shots: list[ShotSpec] = field(default_factory=list)


class VideoPlannerAgent:
    """씬별 샷 리스트 + 연출 방향 생성 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile

    async def plan(
        self,
        topic: str,
        hook: str,
        body_slides: list[str],
        platform: str = "youtube",
        target_duration_seconds: int = 0,  # 0 = 자동 계산
    ) -> VideoPlan:
        """슬라이드 목록 → VideoPlan (씬별 샷 스펙 포함)"""
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 없음")

        client = genai.Client(api_key=api_key)

        n_slides = len(body_slides)
        # YouTube 롱폼: 슬라이드당 60초 (나레이션 1분 분량), 그 외 7초
        if not target_duration_seconds:
            auto_duration = n_slides * 60 if platform == "youtube" else n_slides * 7
        else:
            auto_duration = target_duration_seconds

        platform_guide = {
            "youtube": f"YouTube long-form ({n_slides} scenes, target ~{auto_duration//60} min). Each scene = ~60s narration. Use moderate pacing, vary camera movements.",
            "youtube_shorts": "YouTube Shorts (under 60s). Use fast, punchy pacing.",
            "tiktok": "TikTok (15-60s). Fast, energetic, immediately engaging.",
            "instagram": "Instagram Reels (15-90s). Dynamic, visually rich.",
        }.get(platform, "Social media short-form video.")

        slides_text = "\n".join(
            f"[Slide {i+1}] {slide}" for i, slide in enumerate(body_slides)
        )

        prompt = f"""You are a professional video director/PD planning a YouTube video shot list.

Topic: "{topic}"
Hook (Opening): "{hook}"
Platform: {platform_guide}
Number of slides: {n_slides}
Target total duration: ~{auto_duration} seconds

Slides:
{slides_text}

Create a detailed shot plan for each slide.

Return JSON:
{{
  "pacing": "fast|moderate|slow",
  "visual_style": "documentary|social_media|corporate|cinematic",
  "color_theme": "warm|cool|neutral|high_contrast|vibrant",
  "opening_hook_seconds": <int, 5-10>,
  "shots": [
    {{
      "slide_index": 0,
      "visual_concept": "<specific visual concept in English, 20-40 words>",
      "camera_movement": "slow_zoom_in|pan_left|pan_right|static|dolly_forward|handheld",
      "mood": "energetic|contemplative|dramatic|informative|inspiring",
      "duration_seconds": <int — youtube: 55-65, shorts/tiktok: 5-10>,
      "transition": "cut|fade|dissolve",
      "narration_cue": "즉시|0.5초 후|1초 후",
      "ken_burns": true|false
    }}
    // ... one per slide
  ]
}}

Rules:
- Slide 0 (hook): most dramatic visual, slow_zoom_in or dolly_forward
- Vary camera movements — avoid repeating the same movement more than 2 slides in a row
- Match mood to slide content (data → informative, emotional claim → dramatic)
- ken_burns: true for still image animation (Veo loops the clip to match narration length)
- duration_seconds = expected narration length for that slide (~60s for youtube long-form)
- Return ONLY valid JSON"""

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.6),
            )

            text = response.text.strip()
            text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise ValueError(f"JSON not found: {text[:200]}")

            data = json.loads(match.group())
            shots_raw = data.get("shots", [])

            shots = []
            for i, s in enumerate(shots_raw[:n_slides]):
                shots.append(ShotSpec(
                    slide_index=s.get("slide_index", i),
                    visual_concept=s.get("visual_concept", f"Cinematic scene for: {body_slides[i][:60]}"),
                    camera_movement=s.get("camera_movement", "slow_zoom_in"),
                    mood=s.get("mood", "informative"),
                    duration_seconds=int(s.get("duration_seconds", 60 if platform == "youtube" else 7)),
                    transition=s.get("transition", "cut"),
                    narration_cue=s.get("narration_cue", "즉시"),
                    ken_burns=bool(s.get("ken_burns", True)),
                ))

            # 슬라이드 수 부족 시 패딩
            while len(shots) < n_slides:
                i = len(shots)
                shots.append(ShotSpec(
                    slide_index=i,
                    visual_concept=f"Cinematic scene: {body_slides[i][:60]}",
                    camera_movement="static",
                    mood="informative",
                    duration_seconds=7,
                    transition="cut",
                    narration_cue="즉시",
                ))

            total = sum(s.duration_seconds for s in shots)
            plan = VideoPlan(
                platform=platform,
                total_duration_seconds=total,
                pacing=data.get("pacing", "moderate"),
                visual_style=data.get("visual_style", "social_media"),
                color_theme=data.get("color_theme", "neutral"),
                opening_hook_seconds=int(data.get("opening_hook_seconds", 8)),
                shots=shots,
            )

            logger.info(
                f"[VideoPlannerAgent] {n_slides}씬 플래닝 완료 "
                f"| 스타일: {plan.visual_style} | 총 {total}초 | 페이싱: {plan.pacing}"
            )
            return plan

        except Exception as e:
            logger.error(f"[VideoPlannerAgent] 실패: {e}")
            # 기본 플랜 반환
            shots = [
                ShotSpec(
                    slide_index=i,
                    visual_concept=f"Cinematic scene: {slide[:60]}",
                    camera_movement="slow_zoom_in" if i == 0 else "static",
                    mood="informative",
                    duration_seconds=60 if platform == "youtube" else (8 if i == 0 else 6),
                    transition="cut",
                    narration_cue="즉시",
                )
                for i, slide in enumerate(body_slides)
            ]
            return VideoPlan(
                platform=platform,
                total_duration_seconds=sum(s.duration_seconds for s in shots),
                pacing="moderate",
                visual_style="social_media",
                color_theme="neutral",
                opening_hook_seconds=8,
                shots=shots,
            )
