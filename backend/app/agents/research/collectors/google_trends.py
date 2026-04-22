"""
Google Trends 수집기
AI/테크 + 재테크 키워드의 트렌드 데이터를 수집한다
"""
import os
from datetime import datetime
from pytrends.request import TrendReq
from loguru import logger


# 수집 대상 키워드 그룹
KEYWORDS = {
    "AI/테크": [
        "ChatGPT", "AI", "인공지능", "GPT", "클로드",
        "딥러닝", "머신러닝", "AI 도구", "생성 AI"
    ],
    "재테크": [
        "ETF", "주식투자", "재테크", "ISA계좌", "절세",
        "코인", "비트코인", "배당주", "적금", "청년희망적금"
    ]
}


def fetch_trends(keywords: list[str], timeframe: str = "now 1-d") -> list[dict]:
    """
    키워드 리스트의 Google Trends 데이터를 수집한다

    Args:
        keywords: 검색 키워드 리스트 (최대 5개)
        timeframe: 수집 기간 ("now 1-d", "now 7-d", "today 1-m")

    Returns:
        트렌드 데이터 리스트
    """
    try:
        pytrends = TrendReq(hl="ko", tz=540)  # 한국어, KST (UTC+9)
        pytrends.build_payload(keywords[:5], timeframe=timeframe, geo="KR")

        interest_df = pytrends.interest_over_time()
        if interest_df.empty:
            logger.warning(f"Google Trends 데이터 없음: {keywords}")
            return []

        results = []
        latest = interest_df.iloc[-1]

        for keyword in keywords[:5]:
            if keyword in latest:
                results.append({
                    "source": "google_trends",
                    "keyword": keyword,
                    "volume": int(latest[keyword]),
                    "collected_at": datetime.now().isoformat(),
                    "category": _get_category(keyword),
                })

        logger.info(f"Google Trends 수집 완료: {len(results)}개 키워드")
        return results

    except Exception as e:
        logger.error(f"Google Trends 수집 실패: {e}")
        return []


def collect_all() -> list[dict]:
    """모든 카테고리의 트렌드를 수집한다"""
    all_results = []

    for category, keywords in KEYWORDS.items():
        # Google Trends는 한 번에 최대 5개 키워드
        for i in range(0, len(keywords), 5):
            batch = keywords[i:i+5]
            results = fetch_trends(batch)
            all_results.extend(results)

    logger.info(f"Google Trends 전체 수집: {len(all_results)}개")
    return all_results


def _get_category(keyword: str) -> str:
    """키워드의 카테고리를 반환한다"""
    for category, keywords in KEYWORDS.items():
        if keyword in keywords:
            return category
    return "기타"


if __name__ == "__main__":
    results = collect_all()
    for r in sorted(results, key=lambda x: x["volume"], reverse=True)[:5]:
        print(f"[{r['category']}] {r['keyword']}: {r['volume']}")
