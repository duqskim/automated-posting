"""
Researcher Agent — 주제 기반 동적 리서치
역할: 주제 → 키워드 확장 → 플랫폼별 상위 콘텐츠 분석 → winning formula 추출
"""
import os
from dataclasses import dataclass, field
from functools import lru_cache
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile


@dataclass
class TopContent:
    platform: str
    title: str
    url: str | None = None
    engagement: dict | None = None  # views, likes, saves, etc.
    hook_used: str | None = None
    format_notes: str | None = None


@dataclass
class WinningFormula:
    hook_patterns: list[str]
    content_structure: str
    avg_length: str
    hashtag_strategy: str
    thumbnail_style: str
    content_gaps: list[str]  # 경쟁자가 놓친 각도


@dataclass
class ResearchResult:
    topic: str
    keywords: list[str]
    top_content: list[TopContent]
    winning_formula: WinningFormula
    raw_data: dict = field(default_factory=dict)


@lru_cache(maxsize=64)
def _cached_youtube_search(query: str, max_results: int = 5) -> list[dict]:
    """YouTube Data API v3 search.list — 결과 캐시 (quota: 100 units/call)"""
    import requests
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return []
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": max_results,
                "order": "viewCount",
                "relevanceLanguage": "en",
                "key": api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [
            {
                "title": it["snippet"]["title"],
                "channel": it["snippet"]["channelTitle"],
                "video_id": it["id"]["videoId"],
                "url": f"https://www.youtube.com/watch?v={it['id']['videoId']}",
                "description": it["snippet"]["description"][:200],
                "published_at": it["snippet"]["publishedAt"],
            }
            for it in items
        ]
    except Exception as e:
        logger.warning(f"[ResearcherAgent] YouTube API 검색 실패: {e}")
        return []


class ResearcherAgent:
    """주제 기반 동적 리서치 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile
        self.llm = get_llm_client("research")

    async def expand_keywords(self, topic: str) -> list[str]:
        """주제 → 관련 키워드 15~20개 확장"""
        LANG_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese"}
        lang_name = LANG_NAMES.get(self.profile.language, self.profile.language)

        prompt = f"""Topic: "{topic}"
Market: {self.profile.display_name}
Language: {lang_name}
Target platforms: {', '.join(self.profile.active_platforms)}

Generate 15-20 search keywords related to this topic.
- Keywords people actually search for
- Include long-tail keywords
- WRITE ALL KEYWORDS IN {lang_name.upper()}

Respond in JSON:
{{"keywords": ["keyword1", "keyword2", ...]}}"""

        result = await self.llm.generate_json(prompt)
        if result and "keywords" in result:
            logger.info(f"키워드 확장 완료: {len(result['keywords'])}개")
            return result["keywords"]
        return [topic]

    async def analyze_top_content(self, topic: str, keywords: list[str]) -> list[TopContent]:
        """플랫폼별 상위 콘텐츠 분석 (YouTube는 Data API v3 실제 결과 사용)"""
        platforms = self.profile.active_platforms
        platform_list = ", ".join(platforms)

        LANG_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese"}
        lang_name = LANG_NAMES.get(self.profile.language, self.profile.language)

        # YouTube가 활성 플랫폼이면 실제 검색 결과 가져오기
        yt_results: list[dict] = []
        if any(p.startswith("youtube") for p in platforms):
            search_query = f"{topic} {keywords[0] if keywords else ''}".strip()
            yt_results = _cached_youtube_search(search_query, max_results=5)
            if yt_results:
                logger.info(f"[ResearcherAgent] YouTube 실검색 {len(yt_results)}개 결과")

        yt_context = ""
        if yt_results:
            yt_lines = "\n".join(
                f"  - [{r['channel']}] \"{r['title']}\" ({r['url']})"
                for r in yt_results
            )
            yt_context = f"\nACTUAL YouTube search results for \"{topic}\" (use these as real data):\n{yt_lines}\n"

        prompt = f"""Topic: "{topic}"
Related keywords: {', '.join(keywords[:10])}
Platforms: {platform_list}
Market: {self.profile.display_name}
{yt_context}
Analyze the most successful content patterns for this topic on each platform.
{"For YouTube, base your analysis on the actual search results above." if yt_results else "Describe characteristics of top-performing content (realistic examples):"}

Respond in JSON:
{{
  "top_content": [
    {{
      "platform": "platform name",
      "title": "successful content title/hook example (in {lang_name})",
      "url": "video URL if from real data, else null",
      "hook_used": "hook pattern used",
      "format_notes": "format characteristics (length, structure, visuals)",
      "engagement": {{"estimated_views": "estimated view range", "key_metric": "key success metric"}}
    }}
  ]
}}

2-3 per platform, total {len(platforms) * 2}~{len(platforms) * 3} items. All text in {lang_name.upper()}."""

        result = await self.llm.generate_json(prompt)
        if result and "top_content" in result:
            contents = []
            for item in result["top_content"]:
                contents.append(TopContent(
                    platform=item.get("platform", ""),
                    title=item.get("title", ""),
                    url=item.get("url"),
                    hook_used=item.get("hook_used"),
                    format_notes=item.get("format_notes"),
                    engagement=item.get("engagement"),
                ))
            logger.info(f"상위 콘텐츠 분석 완료: {len(contents)}개 (YouTube 실데이터: {len(yt_results)}개)")
            return contents
        return []

    async def extract_winning_formula(
        self, topic: str, top_content: list[TopContent]
    ) -> WinningFormula:
        """상위 콘텐츠에서 winning formula 추출"""
        content_summary = "\n".join([
            f"- [{c.platform}] {c.title} | 훅: {c.hook_used} | 포맷: {c.format_notes}"
            for c in top_content
        ])

        LANG_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese"}
        lang_name = LANG_NAMES.get(self.profile.language, self.profile.language)

        prompt = f"""Topic: "{topic}"
Market: {self.profile.display_name}
Default hook style: {self.profile.hook_style}

Top content analysis for this topic:
{content_summary}

Extract the winning formula from this data:

Respond in JSON (all text values in {lang_name.upper()}):
{{
  "hook_patterns": ["winning hook pattern 1", "pattern 2", "pattern 3"],
  "content_structure": "common structure of successful content",
  "avg_length": "optimal length/slide count/tweet count",
  "hashtag_strategy": "winning hashtag strategy",
  "thumbnail_style": "winning thumbnail style",
  "content_gaps": ["angle competitors are missing 1", "gap 2", "gap 3"]
}}"""

        result = await self.llm.generate_json(prompt)
        if result:
            return WinningFormula(
                hook_patterns=result.get("hook_patterns", []),
                content_structure=result.get("content_structure", ""),
                avg_length=result.get("avg_length", ""),
                hashtag_strategy=result.get("hashtag_strategy", ""),
                thumbnail_style=result.get("thumbnail_style", ""),
                content_gaps=result.get("content_gaps", []),
            )
        return WinningFormula(
            hook_patterns=self.profile.hook_examples[:3],
            content_structure="",
            avg_length="",
            hashtag_strategy="",
            thumbnail_style="",
            content_gaps=[],
        )

    async def research(self, topic: str) -> ResearchResult:
        """전체 리서치 파이프라인 실행"""
        logger.info(f"=== Researcher Agent: '{topic}' 리서치 시작 ({self.profile.display_name}) ===")

        # 1. 키워드 확장
        keywords = await self.expand_keywords(topic)

        # 2. 상위 콘텐츠 분석
        top_content = await self.analyze_top_content(topic, keywords)

        # 3. Winning formula 추출
        winning_formula = await self.extract_winning_formula(topic, top_content)

        result = ResearchResult(
            topic=topic,
            keywords=keywords,
            top_content=top_content,
            winning_formula=winning_formula,
        )

        logger.info(f"리서치 완료: {len(keywords)}개 키워드, "
                     f"{len(top_content)}개 상위 콘텐츠, "
                     f"{len(winning_formula.hook_patterns)}개 훅 패턴, "
                     f"{len(winning_formula.content_gaps)}개 빈틈 발견")

        return result
