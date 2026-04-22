"""
X (Twitter) 콘텐츠 생성기
트렌드 데이터를 X 스레드로 변환한다
"""
import re
from loguru import logger
from .gemini_generator import generate, SYSTEM_ROLE


# 카테고리별 해시태그 (X는 최대 2개)
HASHTAGS = {
    "AI/테크": ["#AI", "#테크트렌드"],
    "재테크": ["#재테크", "#투자공부"],
}


def generate_thread(trend: dict) -> dict | None:
    """
    트렌드 데이터를 X 스레드로 생성한다

    Args:
        trend: 트렌드 데이터

    Returns:
        {tweets: [...], hashtags: str} 또는 None
    """
    keyword = trend.get("keyword", "")
    category = trend.get("category", "AI/테크")
    title = trend.get("title", keyword)

    prompt = f"""
{SYSTEM_ROLE}

아래 트렌드 주제로 X(트위터) 스레드를 만들어주세요.

주제: {keyword}
카테고리: {category}
참고 제목: {title}

규칙:
- 각 트윗은 반드시 200자 이내
- 트윗1은 훅: 숫자나 강렬한 주장으로 시작, "I"나 "안녕하세요"로 시작 금지
- 트윗2~5: 핵심 포인트 하나씩
- 트윗6: 마무리 + "팔로우하면 매일 이런 인사이트를 드려요 🔔" + 마지막 줄에 "🤖 AI 생성 콘텐츠"
- {'재테크 내용이면 트윗6에 "⚠️ 참고용, 투자 권유 아님" 추가' if category == "재테크" else ""}

다음 형식으로 정확하게 작성해주세요:

[트윗1]
(훅)

[트윗2]
(포인트1)

[트윗3]
(포인트2)

[트윗4]
(포인트3)

[트윗5]
(포인트4)

[트윗6]
(마무리 + CTA)
"""

    logger.info(f"X 스레드 생성 중: {keyword}")
    response = generate(prompt)
    if not response:
        return None

    return _parse_thread(response, trend)


def _parse_thread(response: str, trend: dict) -> dict:
    """생성된 텍스트를 구조화된 스레드 데이터로 파싱한다"""
    tweets = []
    category = trend.get("category", "AI/테크")

    tweet_pattern = re.compile(r'\[트윗\d+\]\s*([\s\S]*?)(?=\[트윗|\Z)')
    for match in tweet_pattern.finditer(response):
        content = match.group(1).strip()
        if content:
            # 280자 초과 시 자르기
            if len(content) > 280:
                content = content[:277] + "..."
            tweets.append(content)

    hashtags = " ".join(HASHTAGS.get(category, []))

    return {
        "keyword": trend.get("keyword", ""),
        "category": category,
        "tweets": tweets,
        "hashtags": hashtags,
        "tweet_count": len(tweets),
    }


if __name__ == "__main__":
    test_trend = {
        "keyword": "ChatGPT",
        "category": "AI/테크",
        "title": "ChatGPT 새로운 기능 업데이트",
        "source": "google_trends",
    }
    result = generate_thread(test_trend)
    if result:
        print(f"\n트윗 수: {result['tweet_count']}")
        for i, tweet in enumerate(result["tweets"], 1):
            print(f"\n[트윗{i}] ({len(tweet)}자)\n{tweet}")
        print(f"\n[해시태그] {result['hashtags']}")
