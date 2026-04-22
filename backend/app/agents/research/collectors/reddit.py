"""
Reddit 수집기
r/MachineLearning, r/artificial, r/investing, r/personalfinance에서
인기 게시물을 수집한다
"""
import os
from datetime import datetime
import praw
from loguru import logger


# 수집 대상 서브레딧
SUBREDDITS = {
    "AI/테크": ["MachineLearning", "artificial", "ChatGPT", "LocalLLaMA"],
    "재테크": ["investing", "personalfinance", "stocks", "CryptoCurrency"],
}


def get_client() -> praw.Reddit:
    """Reddit API 클라이언트를 반환한다"""
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        user_agent="shadow-meteorite/1.0 content-collector",
    )


def fetch_hot_posts(subreddit_name: str, limit: int = 5) -> list[dict]:
    """
    서브레딧의 인기 게시물을 수집한다

    Args:
        subreddit_name: 서브레딧 이름
        limit: 수집할 게시물 수

    Returns:
        게시물 데이터 리스트
    """
    try:
        reddit = get_client()
        subreddit = reddit.subreddit(subreddit_name)
        results = []

        for post in subreddit.hot(limit=limit):
            if post.stickied:
                continue
            results.append({
                "source": "reddit",
                "keyword": post.title[:50],
                "subreddit": subreddit_name,
                "post_id": post.id,
                "title": post.title,
                "score": post.score,
                "num_comments": post.num_comments,
                # Reddit 점수 + 댓글 수로 volume 산정
                "volume": post.score + post.num_comments * 5,
                "url": f"https://reddit.com{post.permalink}",
                "collected_at": datetime.now().isoformat(),
                "category": _get_category(subreddit_name),
            })

        logger.info(f"Reddit r/{subreddit_name} 수집: {len(results)}개")
        return results

    except Exception as e:
        logger.error(f"Reddit r/{subreddit_name} 수집 실패: {e}")
        return []


def collect_all() -> list[dict]:
    """모든 서브레딧에서 인기 게시물을 수집한다"""
    all_results = []

    for category, subreddits in SUBREDDITS.items():
        for subreddit in subreddits:
            results = fetch_hot_posts(subreddit)
            all_results.extend(results)

    logger.info(f"Reddit 전체 수집: {len(all_results)}개")
    return all_results


def _get_category(subreddit_name: str) -> str:
    """서브레딧의 카테고리를 반환한다"""
    for category, subreddits in SUBREDDITS.items():
        if subreddit_name in subreddits:
            return category
    return "기타"


if __name__ == "__main__":
    results = collect_all()
    for r in sorted(results, key=lambda x: x["volume"], reverse=True)[:5]:
        print(f"[{r['category']}] r/{r['subreddit']}: {r['title'][:60]} (score: {r['score']})")
