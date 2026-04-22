"""
Hacker News 수집기
AI/테크 관련 인기 게시물을 수집한다
"""
from datetime import datetime
import requests
from loguru import logger


HN_API = "https://hacker-news.firebaseio.com/v0"

# AI/테크 관련 필터 키워드 (너무 짧거나 일반적인 단어 제외)
AI_KEYWORDS = [
    "gpt", "llm", "ai model", "machine learning", "deep learning",
    "openai", "anthropic", "gemini", "claude", "mistral",
    "neural network", "transformer", "ai agent", "rag", "fine-tun",
    "language model", "inference", "gpu cluster", "nvidia", "diffusion"
]


def fetch_top_stories(limit: int = 30) -> list[dict]:
    """
    Hacker News 상위 게시물 중 AI/테크 관련 항목을 수집한다

    Args:
        limit: 검사할 게시물 수 (상위 N개 중 필터링)

    Returns:
        AI/테크 관련 게시물 리스트
    """
    try:
        # 상위 스토리 ID 목록
        response = requests.get(f"{HN_API}/topstories.json", timeout=10)
        response.raise_for_status()
        story_ids = response.json()[:limit]

        results = []
        for story_id in story_ids:
            try:
                story_resp = requests.get(
                    f"{HN_API}/item/{story_id}.json", timeout=5
                )
                story = story_resp.json()

                if not story or story.get("type") != "story":
                    continue

                title = story.get("title", "").lower()
                if not _is_ai_related(title):
                    continue

                results.append({
                    "source": "hacker_news",
                    "keyword": story.get("title", "")[:50],
                    "title": story.get("title", ""),
                    "score": story.get("score", 0),
                    "num_comments": story.get("descendants", 0),
                    "volume": story.get("score", 0) + story.get("descendants", 0) * 3,
                    "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                    "collected_at": datetime.now().isoformat(),
                    "category": "AI/테크",
                })

            except Exception:
                continue

        logger.info(f"Hacker News 수집 완료: {len(results)}개 AI/테크 게시물")
        return results

    except Exception as e:
        logger.error(f"Hacker News 수집 실패: {e}")
        return []


def collect_all() -> list[dict]:
    """Hacker News AI/테크 게시물을 수집한다"""
    return fetch_top_stories(limit=30)


def _is_ai_related(title: str) -> bool:
    """제목이 AI/테크 관련인지 확인한다"""
    return any(keyword in title for keyword in AI_KEYWORDS)


if __name__ == "__main__":
    results = collect_all()
    for r in sorted(results, key=lambda x: x["volume"], reverse=True)[:5]:
        print(f"[HN] {r['title'][:60]} (score: {r['score']})")
