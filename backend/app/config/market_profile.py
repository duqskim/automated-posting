"""
Market Profile 로더
시장(KR/US/JP) 선택 시 해당 프로필을 로드하여 파이프라인 전체에 주입
"""
from pathlib import Path
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel

MarketCode = Literal["kr", "us", "jp"]

PROFILES_DIR = Path(__file__).parent / "market_profiles"


class HashtagConfig(BaseModel):
    count: int
    language: str
    mix: str
    note: str | None = None


class ThumbnailConfig(BaseModel):
    style: str
    text_ratio: float
    preferred_colors: list[str] = []
    note: str | None = None


class ContentRules(BaseModel):
    disclaimer_finance: str
    ai_disclosure: str
    trend_window_hours: int


class PostingHours(BaseModel):
    best: list[str]
    good: list[str] = []


class ResearchSource(BaseModel):
    type: str
    region: str | None = None
    language: str | None = None
    subreddits: list[str] | None = None
    feeds: list[dict] | None = None


class MarketProfile(BaseModel):
    """시장별 전체 설정"""
    market: MarketCode
    language: str
    display_name: str

    # 콘텐츠 스타일
    tone: str
    hook_style: str
    hook_examples: list[str] = []
    info_density: Literal["low", "medium", "high"]
    slide_text_limit_chars: int | None = None
    slide_text_limit_words: int | None = None
    caption_style: str

    # 플랫폼
    platforms: dict[str, list[str]]  # primary, secondary, optional

    # 리서치
    research_sources: list[dict] = []

    # SEO & 공유
    seo_engine: str
    sharing_optimization: str

    # 해시태그
    hashtag: HashtagConfig

    # 콘텐츠 규칙
    content_rules: ContentRules

    # 썸네일
    thumbnail: ThumbnailConfig

    # 발행 시간
    timezone: str = "Asia/Seoul"
    posting_hours: dict[str, PostingHours] = {}

    # AI 티 검출
    ai_detection: dict = {}

    # KPI
    kpi_priority: dict[str, list[str]] = {}

    # 플랫폼별 추가 설정
    linkedin: dict | None = None
    reddit: dict | None = None

    @property
    def all_platforms(self) -> list[str]:
        """primary + secondary + optional 전체 플랫폼 목록"""
        result = []
        for tier in ["primary", "secondary", "optional"]:
            result.extend(self.platforms.get(tier, []))
        return result

    @property
    def active_platforms(self) -> list[str]:
        """primary + secondary (실제 발행 대상)"""
        result = []
        for tier in ["primary", "secondary"]:
            result.extend(self.platforms.get(tier, []))
        return result

    def get_text_limit(self) -> str:
        """정보 밀도에 맞는 텍스트 제한 설명"""
        if self.slide_text_limit_chars:
            return f"{self.slide_text_limit_chars}자 이내"
        elif self.slide_text_limit_words:
            return f"{self.slide_text_limit_words} words max"
        return "no limit"


@lru_cache(maxsize=3)
def load_market_profile(market: MarketCode) -> MarketProfile:
    """시장 프로필 로드 (캐시됨)"""
    profile_path = PROFILES_DIR / f"{market}.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(f"Market profile not found: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # posting_hours를 PostingHours 모델로 변환
    if "posting_hours" in data:
        for platform, hours in data["posting_hours"].items():
            if isinstance(hours, dict) and not isinstance(hours, PostingHours):
                data["posting_hours"][platform] = PostingHours(**hours)

    return MarketProfile(**data)


def get_available_markets() -> list[dict]:
    """사용 가능한 시장 목록"""
    markets = []
    for profile_path in sorted(PROFILES_DIR.glob("*.yaml")):
        market_code = profile_path.stem
        with open(profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        markets.append({
            "code": market_code,
            "display_name": data.get("display_name", market_code),
            "language": data.get("language", ""),
        })
    return markets
