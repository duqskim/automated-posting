"""
X (Twitter) 트렌드 수집기
한국 트렌딩 토픽과 AI/재테크 관련 트윗을 수집한다
"""
import os
from datetime import datetime
import tweepy
from loguru import logger


def get_client() -> tweepy.Client:
    """Twitter API v2 클라이언트를 반환한다"""
    return tweepy.Client(
        bearer_token=os.getenv("X_BEARER_TOKEN"),
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_SECRET"),
        wait_on_rate_limit=True,
    )


# 검색 쿼리 (한국어 + 관련 키워드)
SEARCH_QUERIES = {
    "AI/테크": [
        "ChatGPT OR GPT OR 인공지능 OR AI도구 lang:ko",
        "클로드 OR Gemini OR AI모델 lang:ko",
    ],
    "재테크": [
        "ETF OR 주식투자 OR 재테크 OR ISA lang:ko",
        "코인 OR 비트코인 OR 배당주 lang:ko",
    ]
}


def fetch_trending_tweets(query: str, max_results: int = 10) -> list[dict]:
    """
    특정 쿼리의 최신 트윗을 수집한다

    Args:
        query: 검색 쿼리
        max_results: 수집할 최대 트윗 수

    Returns:
        트윗 데이터 리스트
    """
    try:
        client = get_client()
        tweets = client.search_recent_tweets(
            query=f"{query} -is:retweet -is:reply",
            max_results=min(max_results, 100),
            tweet_fields=["public_metrics", "created_at", "lang"],
        )

        if not tweets.data:
            logger.warning(f"X 트윗 없음: {query}")
            return []

        results = []
        for tweet in tweets.data:
            metrics = tweet.public_metrics
            engagement = (
                metrics["like_count"] * 1
                + metrics["retweet_count"] * 20
                + metrics["reply_count"] * 13
                + metrics["bookmark_count"] * 10
            )
            results.append({
                "source": "x_trends",
                "keyword": query.split(" OR ")[0].split(" ")[0],
                "tweet_id": tweet.id,
                "text": tweet.text[:100],
                "volume": engagement,
                "collected_at": datetime.now().isoformat(),
                "category": _get_category(query),
            })

        logger.info(f"X 트윗 수집 완료: {len(results)}개")
        return results

    except tweepy.TooManyRequests:
        logger.warning("X API Rate Limit 초과, 스킵")
        return []
    except Exception as e:
        logger.error(f"X 트렌드 수집 실패: {e}")
        return []


def collect_all() -> list[dict]:
    """모든 카테고리의 X 트렌드를 수집한다"""
    all_results = []

    for category, queries in SEARCH_QUERIES.items():
        for query in queries:
            results = fetch_trending_tweets(query)
            all_results.extend(results)

    logger.info(f"X 전체 수집: {len(all_results)}개")
    return all_results


def _get_category(query: str) -> str:
    """쿼리의 카테고리를 반환한다"""
    for category, queries in SEARCH_QUERIES.items():
        if query in queries:
            return category
    return "기타"


if __name__ == "__main__":
    results = collect_all()
    for r in sorted(results, key=lambda x: x["volume"], reverse=True)[:5]:
        print(f"[{r['category']}] {r['keyword']}: {r['volume']} | {r['text'][:50]}")
