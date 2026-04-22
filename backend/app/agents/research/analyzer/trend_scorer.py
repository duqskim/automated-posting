"""
트렌드 분석기
수집된 트렌드에 점수를 부여하고 우선순위를 정렬한다

점수 공식:
  최종 점수 = (검색량 × 0.4) + (반응도 × 0.3) + (신선도 × 0.3)
  신선도: 24시간 이내 = 1.0 / 48시간 이내 = 0.5 / 이후 = 0.1
"""
from datetime import datetime, timedelta
from loguru import logger


def calculate_freshness(collected_at: str) -> float:
    """수집 시각 기준 신선도 점수를 반환한다"""
    try:
        collected = datetime.fromisoformat(collected_at)
        age = datetime.now() - collected
        if age < timedelta(hours=24):
            return 1.0
        elif age < timedelta(hours=48):
            return 0.5
        else:
            return 0.1
    except Exception:
        return 0.5


def normalize(value: float, max_value: float) -> float:
    """값을 0~100 범위로 정규화한다"""
    if max_value == 0:
        return 0
    return min(100, (value / max_value) * 100)


def score_trends(raw_trends: list[dict]) -> list[dict]:
    """
    수집된 트렌드 데이터에 최종 점수를 부여한다

    Args:
        raw_trends: 각 수집기에서 모은 raw 데이터

    Returns:
        점수가 부여된 트렌드 리스트 (내림차순 정렬)
    """
    if not raw_trends:
        return []

    # 최대 volume 기준 정규화
    max_volume = max(t.get("volume", 0) for t in raw_trends) or 1

    scored = []
    for trend in raw_trends:
        volume = trend.get("volume", 0)
        freshness = calculate_freshness(trend.get("collected_at", datetime.now().isoformat()))

        # 반응도: 한국 소스 우선, HN은 낮춤 (영어 기사가 상위 독점 방지)
        source_weight = {
            "google_trends": 1.0,
            "naver_datalab": 0.95,
            "매경 IT·모바일": 0.85,
            "매경 경제일반": 0.85,
            "테크42": 0.85,
            "hankyung": 0.85,      # 한국경제 RSS
            "x_trends": 0.8,
            "hacker_news": 0.55,   # 영어 기사 우선순위 하향
            "reddit": 0.5,
            "naver_finance": 0.75,
            "coingecko": 0.7,
            "yahoo_finance": 0.7,
        }.get(trend.get("source", ""), 0.5)

        # "기타" 카테고리는 점수 페널티
        if trend.get("category") == "기타":
            source_weight *= 0.3

        normalized_volume = normalize(volume, max_volume)
        engagement = normalized_volume * source_weight

        final_score = (
            normalized_volume * 0.4
            + engagement * 0.3
            + freshness * 100 * 0.3
        )

        scored.append({
            **trend,
            "final_score": round(final_score, 2),
            "freshness": freshness,
        })

    # 점수 내림차순 정렬
    scored.sort(key=lambda x: x["final_score"], reverse=True)
    logger.info(f"트렌드 점수 산정 완료: {len(scored)}개")
    return scored


def deduplicate(trends: list[dict], threshold: int = 3) -> list[dict]:
    """
    유사 키워드 중복을 제거한다

    Args:
        trends: 점수가 부여된 트렌드 리스트
        threshold: 중복 판단 최소 글자 수

    Returns:
        중복 제거된 트렌드 리스트
    """
    seen_keywords = []
    unique = []

    for trend in trends:
        keyword = trend.get("keyword", "").lower().strip()
        is_duplicate = any(
            keyword[:threshold] in seen or seen[:threshold] in keyword
            for seen in seen_keywords
        )
        if not is_duplicate:
            seen_keywords.append(keyword)
            unique.append(trend)

    logger.info(f"중복 제거: {len(trends)}개 → {len(unique)}개")
    return unique


def get_top_trends(
    raw_trends: list[dict],
    instagram_limit: int = 2,
    x_limit: int = 5,
) -> dict:
    """
    플랫폼별 발행용 상위 트렌드를 반환한다

    Args:
        raw_trends: 수집된 raw 트렌드
        instagram_limit: Instagram 발행 콘텐츠 수
        x_limit: X 발행 콘텐츠 수

    Returns:
        {"instagram": [...], "x": [...]}
    """
    scored = score_trends(raw_trends)
    unique = deduplicate(scored)

    return {
        "instagram": unique[:instagram_limit],
        "x": unique[:x_limit],
    }


if __name__ == "__main__":
    # 테스트용 더미 데이터
    dummy = [
        {"source": "google_trends", "keyword": "ChatGPT", "volume": 90,
         "collected_at": datetime.now().isoformat(), "category": "AI/테크"},
        {"source": "hacker_news", "keyword": "GPT-5", "volume": 70,
         "collected_at": datetime.now().isoformat(), "category": "AI/테크"},
        {"source": "naver_finance", "keyword": "ETF 투자", "volume": 60,
         "collected_at": datetime.now().isoformat(), "category": "재테크"},
        {"source": "coingecko", "keyword": "Bitcoin", "volume": 50,
         "collected_at": datetime.now().isoformat(), "category": "재테크"},
    ]

    result = get_top_trends(dummy)
    print("\n=== Instagram 발행 대상 ===")
    for t in result["instagram"]:
        print(f"  [{t['category']}] {t['keyword']} (score: {t['final_score']})")
    print("\n=== X 발행 대상 ===")
    for t in result["x"]:
        print(f"  [{t['category']}] {t['keyword']} (score: {t['final_score']})")
