"""
Instagram 콘텐츠 생성기
트렌드 데이터를 Instagram 캐러셀 + 캡션 + 해시태그로 변환한다
"""
import re
from loguru import logger
from .gemini_generator import generate, SYSTEM_ROLE


# 카테고리별 해시태그 풀
HASHTAGS = {
    "AI/테크": [
        "#AI", "#인공지능", "#ChatGPT", "#AI도구", "#테크트렌드",
        "#AI공부", "#생성AI", "#딥러닝", "#IT트렌드", "#기술뉴스",
        "#AI활용", "#미래기술", "#GPT", "#LLM", "#AI시대",
    ],
    "재테크": [
        "#재테크", "#주식투자", "#ETF", "#절세", "#ISA계좌",
        "#투자공부", "#주식공부", "#코인", "#비트코인", "#배당주",
        "#직장인재테크", "#돈공부", "#경제공부", "#금융지식", "#투자초보",
    ],
    "공통": [
        "#정보공유", "#공부", "#직장인", "#인사이트", "#알고리즘",
    ],
}


def generate_carousel(trend: dict) -> dict | None:
    """
    트렌드 데이터를 Instagram 캐러셀 콘텐츠로 생성한다

    Args:
        trend: 트렌드 데이터 (keyword, category, source 등)

    Returns:
        {slides: [...], caption: str, hashtags: str} 또는 None
    """
    keyword = trend.get("keyword", "")
    category = trend.get("category", "AI/테크")
    title = trend.get("title", keyword)

    prompt = f"""
{SYSTEM_ROLE}

아래 트렌드 주제로 Instagram 캐러셀 콘텐츠를 만들어주세요.

주제: {keyword}
카테고리: {category}
참고 제목: {title}

다음 형식으로 정확하게 작성해주세요:

[슬라이드1]
(훅 문장 - 10단어 이내, 강렬하게)

[슬라이드2]
(주제 소개 + 오늘 다룰 내용 예고 - 2~3줄)

[슬라이드3]
(핵심 포인트 1 - 2줄 이내)

[슬라이드4]
(핵심 포인트 2 - 2줄 이내)

[슬라이드5]
(핵심 포인트 3 - 2줄 이내)

[슬라이드6]
(실생활 적용법 - 2~3줄)

[슬라이드7]
(마무리 + CTA: "저장해두고 나중에 써먹으세요 🔖" 포함)

[캡션]
(전체 내용 요약 캡션 - 200자 이내, {'재테크 내용이면 마지막에 "⚠️ 본 콘텐츠는 참고용이며 투자 권유가 아닙니다" 추가' if category == "재테크" else ""})
마지막 줄에 반드시 "🤖 AI 생성 콘텐츠 | 인공지능 기본법 준수" 추가
"""

    logger.info(f"Instagram 캐러셀 생성 중: {keyword}")
    response = generate(prompt)
    if not response:
        return None

    return _parse_carousel(response, trend)


def _parse_carousel(response: str, trend: dict) -> dict:
    """생성된 텍스트를 구조화된 캐러셀 데이터로 파싱한다"""
    slides = []
    caption = ""
    category = trend.get("category", "AI/테크")

    # 슬라이드 파싱
    slide_pattern = re.compile(r'\[슬라이드\d+\]\s*([\s\S]*?)(?=\[슬라이드|\[캡션\]|$)')
    for match in slide_pattern.finditer(response):
        content = match.group(1).strip()
        if content:
            slides.append(content)

    # 캡션 파싱
    caption_match = re.search(r'\[캡션\]\s*([\s\S]*?)$', response)
    if caption_match:
        caption = caption_match.group(1).strip()

    # 해시태그 생성
    hashtags = _build_hashtags(category)

    return {
        "keyword": trend.get("keyword", ""),
        "category": category,
        "slides": slides,
        "caption": caption,
        "hashtags": hashtags,
        "slide_count": len(slides),
    }


def _build_hashtags(category: str) -> str:
    """카테고리에 맞는 해시태그 문자열을 생성한다"""
    tags = HASHTAGS.get(category, []) + HASHTAGS["공통"]
    # 최대 5개 (2025 Instagram 해시태그 상한)
    selected = tags[:5]
    return " ".join(selected)


if __name__ == "__main__":
    test_trend = {
        "keyword": "ETF 투자",
        "category": "재테크",
        "title": "직장인이 꼭 알아야 할 ETF 투자 방법",
        "source": "naver_finance",
    }
    result = generate_carousel(test_trend)
    if result:
        print(f"\n슬라이드 수: {result['slide_count']}")
        for i, slide in enumerate(result["slides"], 1):
            print(f"\n[슬라이드{i}]\n{slide}")
        print(f"\n[캡션]\n{result['caption']}")
        print(f"\n[해시태그]\n{result['hashtags']}")
