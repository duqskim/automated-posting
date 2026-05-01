"""
CinematicShotPlanner — 슬라이드 → ShotFrame 분해

VideoPlannerAgent + VideoDirector 통합 대체:
  - 슬라이드 단위가 아닌 앵커 샷 단위로 계획
  - 각 슬라이드를 N개 ShotFrame으로 분해
  - 샷 타입으로 최적 생성 도구 결정:
      DYNAMIC      → Kling AI (실제 모션, 피사체 움직임)
      ATMOSPHERIC  → Ken Burns (의도적 카메라, 풍경/분위기)
      STATIC_GRAPHIC → ffmpeg (지도, 차트, 텍스트 그래픽)
  - scene_id: 같은 공간/조명 = image_tail 보간 가능
  - duration_target: 이 앵커가 커버해야 하는 시간 (초)
"""
import json
import math
import os
import re
from dataclasses import dataclass, field
from loguru import logger


# ─── 데이터 모델 ──────────────────────────────────────────────

@dataclass
class ShotFrame:
    slide_index: int            # 소속 슬라이드 인덱스
    frame_index: int            # 슬라이드 내 앵커 인덱스 (0-based)
    shot_type: str              # DYNAMIC | ATMOSPHERIC | STATIC_GRAPHIC
    shot_size: str              # extreme_wide | wide | medium | close_up | extreme_close_up
    duration_target: float      # 이 앵커가 커버할 길이 (초)
    camera_start: str           # 카메라 시작 위치 (e.g., "low angle, 20m away")
    camera_movement: str        # 카메라 이동 묘사 (e.g., "slow push forward, ending at eye level")
    subject_action: str         # 피사체 동작 (e.g., "warriors march through fog")
    physics_elements: str       # 물리/환경 요소 (e.g., "torchlight flickers, smoke rises")
    emotional_arc: str          # 감정 흐름 (e.g., "tense → resolved")
    scene_id: str               # 장소/조명 그룹 (같은 scene_id = image_tail 가능)
    composition_hint: str       # 구도 힌트 (e.g., "rule of thirds, subject left third")


@dataclass
class ShotScript:
    platform: str
    total_shots: int
    shots: list[ShotFrame] = field(default_factory=list)

    def shots_for_slide(self, slide_index: int) -> list[ShotFrame]:
        return [s for s in self.shots if s.slide_index == slide_index]

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "total_shots": self.total_shots,
            "shots": [
                {
                    "slide_index": s.slide_index,
                    "frame_index": s.frame_index,
                    "shot_type": s.shot_type,
                    "shot_size": s.shot_size,
                    "duration_target": s.duration_target,
                    "camera_start": s.camera_start,
                    "camera_movement": s.camera_movement,
                    "subject_action": s.subject_action,
                    "physics_elements": s.physics_elements,
                    "emotional_arc": s.emotional_arc,
                    "scene_id": s.scene_id,
                    "composition_hint": s.composition_hint,
                }
                for s in self.shots
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ShotScript":
        shots = [ShotFrame(**s) for s in data.get("shots", [])]
        return cls(
            platform=data["platform"],
            total_shots=data.get("total_shots", len(shots)),
            shots=shots,
        )


# ─── 헬퍼 ─────────────────────────────────────────────────────

def estimate_slide_duration(text: str, platform: str) -> float:
    """슬라이드 텍스트에서 TTS 예상 길이(초) 추정
    한국어 기준: ~4자/초 (평균 말하기 속도)
    """
    if platform in ("youtube_shorts", "tiktok", "instagram"):
        return max(5.0, min(20.0, len(text) * 0.12))
    return max(10.0, min(90.0, len(text) * 0.15))


def _shots_per_slide(duration: float, platform: str) -> int:
    """슬라이드 길이 기반 앵커 샷 수 결정 (최소 1, 최대 5)"""
    if platform in ("youtube_shorts", "tiktok", "instagram"):
        return max(1, min(2, math.ceil(duration / 7)))
    # YouTube 롱폼: 5초마다 1샷 (최대 5개로 제한 — 너무 많은 API 호출 방지)
    return max(1, min(5, math.ceil(duration / 12)))


def _default_shots(body_slides: list[str], platform: str) -> list[ShotFrame]:
    """LLM 실패 시 기본 샷 계획 생성"""
    shots = []
    for i, text in enumerate(body_slides):
        dur = estimate_slide_duration(text, platform)
        n = _shots_per_slide(dur, platform)
        per = round(dur / n, 1)
        for j in range(n):
            shot_type = "DYNAMIC" if j % 2 == 0 else "ATMOSPHERIC"
            shots.append(ShotFrame(
                slide_index=i,
                frame_index=j,
                shot_type=shot_type,
                shot_size="wide" if j == 0 else "medium",
                duration_target=per,
                camera_start="eye level" if j == 0 else "low angle",
                camera_movement="slow push forward" if j == 0 else "slow pan right",
                subject_action=f"scene from: {text[:60]}",
                physics_elements="ambient light",
                emotional_arc="informative",
                scene_id=f"slide_{i}_scene",
                composition_hint="rule of thirds",
            ))
    return shots


# ─── 에이전트 ──────────────────────────────────────────────────

class CinematicShotPlanner:
    """슬라이드 목록 → ShotScript (앵커 샷 분해)"""

    async def plan(
        self,
        topic: str,
        hook: str,
        body_slides: list[str],
        platform: str = "youtube",
    ) -> ShotScript:
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 없음")

        client = genai.Client(api_key=api_key)

        is_short = platform in ("youtube_shorts", "tiktok", "instagram")
        aspect_note = "9:16 vertical" if is_short else "16:9 horizontal"

        # 슬라이드별 예상 길이 계산
        durations = [estimate_slide_duration(t, platform) for t in body_slides]
        shot_counts = [_shots_per_slide(d, platform) for d in durations]

        slides_info = "\n".join(
            f"[Slide {i+1}] ({dur:.0f}s, {nc} shots)\n{text[:200]}"
            for i, (text, dur, nc) in enumerate(zip(body_slides, durations, shot_counts))
        )

        prompt = f"""You are a professional film director decomposing a video into cinematographic shots.

Topic: "{topic}"
Hook: "{hook}"
Platform: {platform} ({aspect_note})

SLIDES (estimated TTS duration and target shot count per slide):
{slides_info}

For each slide, plan EXACTLY the indicated number of anchor shots.
Each anchor shot = one unique image + one video clip generation.

SHOT TYPE RULES:
- DYNAMIC: Physical motion/action scenes → Kling AI generates real motion
  Use when: people/objects moving, dramatic action, emotional climax
  Camera: push forward, orbit, tilt — actively moving camera
- ATMOSPHERIC: Establishing/landscape/contemplative scenes → Ken Burns pan/zoom
  Use when: wide establishing shots, transitions, peaceful/reflective moments
  Camera: slow drift, gentle zoom — minimal camera movement
- STATIC_GRAPHIC: Maps, diagrams, data visualizations → ffmpeg
  Use when: showing maps, charts, text-based data, infographics

CRITICAL: Distribute shot types intelligently per slide content.
For action/dramatic slides: more DYNAMIC. For data/reflection: more ATMOSPHERIC.
Roughly 40-50% DYNAMIC, 35-45% ATMOSPHERIC, 5-20% STATIC_GRAPHIC.

SCENE_ID RULES:
- Shots in the same physical location/lighting get the same scene_id
- Same scene_id = smooth image_tail interpolation between consecutive shots
- Different scene_id = hard cut / scene change

CAMERA MOVEMENT FORMAT:
"[start position]. [direction+speed+end state]"
Examples:
- "low angle from ground. slow tilt up to reveal palace gates, ending at eye level"
- "aerial 45-degree. dolly forward and down into the crowd, landing at eye level"
- "eye level, 5m away. slow push in to extreme close-up of sword hilt"
- "static locked, eye level. no movement, camera observes"

SUBJECT ACTION FORMAT:
What physically MOVES in this 5-second clip:
- "warriors march in formation through gate, armor glinting"
- "royal scribe brushes ink calligraphy on scroll, hand visible"
- "flames burn through ancient documents, curling and blackening"
- "lone figure stands at cliff edge, robes flowing in wind"

Return JSON:
{{
  "slides": [
    {{
      "slide_index": 0,
      "shots": [
        {{
          "frame_index": 0,
          "shot_type": "DYNAMIC|ATMOSPHERIC|STATIC_GRAPHIC",
          "shot_size": "extreme_wide|wide|medium|close_up|extreme_close_up",
          "duration_target": <float, seconds>,
          "camera_start": "<position description>",
          "camera_movement": "<movement description>",
          "subject_action": "<what physically moves, 10-20 words>",
          "physics_elements": "<light/particles/weather/fabric, comma-separated>",
          "emotional_arc": "<mood start → end>",
          "scene_id": "<location_key>",
          "composition_hint": "<framing rule>"
        }}
      ]
    }}
  ]
}}

Rules:
- duration_target per slide must sum to slide's estimated duration (shown above)
- scene_id: use snake_case location names (e.g., "royal_court", "battlefield_dawn")
- Slide 0 (hook): most dramatic opening — DYNAMIC wide establishing shot
- Vary shot_size within each slide for visual rhythm
- Return ONLY valid JSON, no explanation"""

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.7),
            )

            text = response.text.strip()
            text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise ValueError(f"JSON not found: {text[:200]}")

            data = json.loads(match.group())
            slides_data = data.get("slides", [])

            all_shots: list[ShotFrame] = []
            for slide_data in slides_data:
                si = slide_data.get("slide_index", 0)
                if si >= len(body_slides):
                    continue
                for shot_data in slide_data.get("shots", []):
                    all_shots.append(ShotFrame(
                        slide_index=si,
                        frame_index=shot_data.get("frame_index", 0),
                        shot_type=shot_data.get("shot_type", "DYNAMIC"),
                        shot_size=shot_data.get("shot_size", "wide"),
                        duration_target=float(shot_data.get("duration_target", 5.0)),
                        camera_start=shot_data.get("camera_start", "eye level"),
                        camera_movement=shot_data.get("camera_movement", "slow push forward"),
                        subject_action=shot_data.get("subject_action", "scene unfolds"),
                        physics_elements=shot_data.get("physics_elements", "ambient light"),
                        emotional_arc=shot_data.get("emotional_arc", "informative"),
                        scene_id=shot_data.get("scene_id", f"slide_{si}_scene"),
                        composition_hint=shot_data.get("composition_hint", "rule of thirds"),
                    ))

            # 누락된 슬라이드 패딩
            covered = {s.slide_index for s in all_shots}
            for i, text_i in enumerate(body_slides):
                if i not in covered:
                    dur = estimate_slide_duration(text_i, platform)
                    all_shots.extend(_default_shots([text_i], platform)[0:1])

            all_shots.sort(key=lambda s: (s.slide_index, s.frame_index))

            script = ShotScript(
                platform=platform,
                total_shots=len(all_shots),
                shots=all_shots,
            )

            dynamic_count = sum(1 for s in all_shots if s.shot_type == "DYNAMIC")
            logger.info(
                f"[CinematicShotPlanner] {len(all_shots)}샷 계획 완료 "
                f"| DYNAMIC:{dynamic_count} "
                f"| ATMOSPHERIC:{sum(1 for s in all_shots if s.shot_type == 'ATMOSPHERIC')} "
                f"| STATIC:{sum(1 for s in all_shots if s.shot_type == 'STATIC_GRAPHIC')}"
            )
            return script

        except Exception as e:
            logger.error(f"[CinematicShotPlanner] 실패, 기본 계획 사용: {e}")
            fallback = _default_shots(body_slides, platform)
            return ShotScript(
                platform=platform,
                total_shots=len(fallback),
                shots=fallback,
            )
