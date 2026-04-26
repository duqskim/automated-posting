"""
Metadata Agent — YouTube SEO 메타데이터 생성
역할: ContentPlan + ResearchResult → 제목, 설명, 태그, 챕터, 카드, 엔드스크린 텍스트

YouTube 알고리즘이 메타데이터에서 보는 것:
  1. 제목: 클릭율 + 키워드 (60자 이하, 첫 40자가 핵심)
  2. 설명: 첫 3줄이 검색 노출, 키워드 자연스럽게 포함
  3. 태그: 검색 보조 (현재 가중치 낮음, 하지만 무시 불가)
  4. 챕터: 시청 유지율 향상 + 구글 검색 노출
  5. 카테고리: 추천 알고리즘 분류

SEO 원칙:
  - 제목에 메인 키워드 앞쪽 배치
  - 설명 첫 줄에 구독 유도 + 핵심 키워드
  - 태그는 구체적인 것부터 (long-tail → broad)
  - 챕터는 2분 이상 영상에서 필수
"""
import json
import os
import re
from dataclasses import dataclass, field
from loguru import logger

from app.config.market_profile import MarketProfile


@dataclass
class VideoChapter:
    time_seconds: int
    title: str

    @property
    def time_str(self) -> str:
        m, s = divmod(self.time_seconds, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


@dataclass
class VideoMetadata:
    title: str                           # SEO 최적화 제목 (60자 이하)
    description: str                     # 상세 설명
    tags: list[str] = field(default_factory=list)       # 검색 태그 (15-20개)
    category: str = "Education"         # YouTube 카테고리
    chapters: list[VideoChapter] = field(default_factory=list)  # 타임스탬프 챕터
    end_screen_cta: str = ""            # 엔드스크린 행동 유도 텍스트
    card_texts: list[str] = field(default_factory=list)  # 카드 텍스트 (2-3개)
    thumbnail_title: str = ""           # 썸네일에 넣을 짧은 문구 (thumbnail_agent 연동)


class MetadataAgent:
    """YouTube SEO 메타데이터 생성 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile

    async def generate(
        self,
        topic: str,
        hook: str,
        body_slides: list[str],
        keywords: list[str],
        platform: str = "youtube",
        video_duration_seconds: int = 0,
    ) -> VideoMetadata:
        """전체 YouTube 메타데이터 생성"""
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 없음")

        client = genai.Client(api_key=api_key)

        lang_rules = {
            "ko": "Write title and description in Korean. Tags can mix Korean and English.",
            "en": "Write title and description in English.",
            "ja": "Write title and description in Japanese. Tags can mix Japanese and English.",
        }.get(self.profile.language, "Write in Korean.")

        category_guide = {
            "ko": "Education (교육) or Science & Technology",
            "en": "Education or Science & Technology",
            "ja": "Education or Science & Technology",
        }.get(self.profile.language, "Education")

        slides_summary = "\n".join(f"- {s[:80]}" for s in body_slides[:8])
        keywords_str = ", ".join(keywords[:15])

        # 챕터 계산용 (영상 길이 기반)
        chapter_hint = ""
        if video_duration_seconds > 120:
            per_slide = video_duration_seconds // max(len(body_slides), 1)
            chapter_hint = f"\nVideo duration: {video_duration_seconds}s, ~{per_slide}s per slide. Generate chapters with timestamps."

        prompt = f"""You are a YouTube SEO specialist.{chapter_hint}

Topic: "{topic}"
Hook: "{hook}"
Language rules: {lang_rules}
Research keywords: {keywords_str}
Recommended category: {category_guide}

Content summary:
{slides_summary}

Generate complete YouTube metadata optimized for search and CTR.

Return JSON:
{{
  "title": "<SEO title, under 60 chars, keyword in first 30 chars>",
  "description": "<Full description, 500-1500 chars. First 2 lines = hook + keyword. Include timestamps if chapters. End with subscribe CTA.>",
  "tags": ["<tag1>", "<tag2>", ...],
  "category": "<YouTube category name>",
  "chapters": [
    {{"time_seconds": 0, "title": "<chapter title>"}},
    ...
  ],
  "end_screen_cta": "<20-30 char call to action for end screen>",
  "card_texts": ["<card text 1>", "<card text 2>"],
  "thumbnail_title": "<very short punchy text for thumbnail, max 15 chars>"
}}

Title rules:
- Put main keyword in first 30 characters
- Create curiosity or urgency
- No clickbait that doesn't match content
- Use numbers when possible

Description rules:
- First 2 lines: most compelling hook (shown in search results)
- Natural keyword placement (not stuffed)
- Timestamps for chapters if applicable
- Subscribe + notification bell CTA at end

Tags rules:
- 15-20 tags
- Mix: exact match (specific), phrase match (broader), related topics
- Include both language keywords if bilingual

Chapters rules:
- First chapter always at 0:00
- Meaningful titles (not just "Part 1")
- Only if video is over 2 minutes

Return ONLY valid JSON."""

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

            chapters = [
                VideoChapter(
                    time_seconds=int(c.get("time_seconds", 0)),
                    title=c.get("title", ""),
                )
                for c in data.get("chapters", [])
            ]

            meta = VideoMetadata(
                title=data.get("title", f"{topic} — 완전 정리"),
                description=data.get("description", f"{hook}\n\n{topic}에 대해 알아봅니다."),
                tags=data.get("tags", keywords[:15]),
                category=data.get("category", "Education"),
                chapters=chapters,
                end_screen_cta=data.get("end_screen_cta", "구독하고 다음 영상도 놓치지 마세요"),
                card_texts=data.get("card_texts", []),
                thumbnail_title=data.get("thumbnail_title", hook[:15]),
            )

            logger.info(
                f"[MetadataAgent] 완료 | 제목: '{meta.title}' | "
                f"태그: {len(meta.tags)}개 | 챕터: {len(meta.chapters)}개"
            )
            return meta

        except Exception as e:
            logger.error(f"[MetadataAgent] 실패: {e}")
            return VideoMetadata(
                title=f"{topic} — 핵심 정리",
                description=f"{hook}\n\n{topic}에 대해 자세히 알아봅니다.",
                tags=keywords[:15],
                category="Education",
            )


def metadata_to_dict(meta: VideoMetadata) -> dict:
    return {
        "title": meta.title,
        "description": meta.description,
        "tags": meta.tags,
        "category": meta.category,
        "chapters": [
            {"time_seconds": c.time_seconds, "time_str": c.time_str, "title": c.title}
            for c in meta.chapters
        ],
        "end_screen_cta": meta.end_screen_cta,
        "card_texts": meta.card_texts,
        "thumbnail_title": meta.thumbnail_title,
    }
