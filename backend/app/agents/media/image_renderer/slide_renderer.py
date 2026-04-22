"""
슬라이드 이미지 렌더러
Jinja2 HTML 템플릿 + Playwright로 1080x1080 PNG 생성
"""
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from loguru import logger

TEMPLATE_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def _split_slide_text(text: str) -> tuple[str, str]:
    """슬라이드 텍스트를 제목(굵은 부분)과 본문으로 분리한다"""
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return "", ""
    if len(lines) == 1:
        # 한 줄이면 40자 기준으로 자름
        pivot = min(40, len(lines[0]))
        return lines[0][:pivot], lines[0][pivot:].strip()
    # 첫 줄이 짧으면 제목, 나머지를 본문으로
    if len(lines[0]) <= 30:
        return lines[0], " ".join(lines[1:])
    return lines[0][:30], " ".join([lines[0][30:]] + lines[1:])


def render_carousel(carousel: dict, keyword_slug: str) -> list[Path]:
    """
    캐러셀 데이터를 받아 슬라이드 이미지 파일 목록을 반환한다.

    Args:
        carousel: generate_carousel()가 반환한 dict
        keyword_slug: 파일명용 식별자

    Returns:
        생성된 PNG 파일 경로 리스트
    """
    slides = carousel.get("slides", [])
    category = carousel.get("category", "AI/테크")
    total = len(slides)

    # 각 슬라이드의 템플릿 컨텍스트 구성
    contexts = []
    for i, slide_text in enumerate(slides):
        slide_num = i + 1

        if slide_num == 1:
            # 훅 슬라이드
            title, sub = _split_slide_text(slide_text)
            ctx = {
                "slide_type": "hook",
                "category": category,
                "main_text": title or slide_text[:60],
                "sub_text": sub,
            }
        elif slide_num == total:
            # CTA 슬라이드
            title, cta = _split_slide_text(slide_text)
            ctx = {
                "slide_type": "cta",
                "category": category,
                "main_text": title or slide_text[:60],
                "cta_text": cta or "저장해두고 나중에 써먹으세요 🔖",
            }
        else:
            # 콘텐츠 슬라이드
            title, detail = _split_slide_text(slide_text)
            ctx = {
                "slide_type": "content",
                "category": category,
                "slide_index": slide_num,
                "total_slides": total,
                "point_num": slide_num - 1,
                "content_title": title or slide_text[:40],
                "detail_text": detail or "",
            }

        contexts.append(ctx)

    # Playwright로 스크린샷
    image_paths = []
    template = _jinja_env.get_template("slide.html")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1080})

        for i, ctx in enumerate(contexts):
            html = template.render(**ctx)
            page.set_content(html, wait_until="networkidle")

            slug = re.sub(r"[^\w]", "_", keyword_slug)[:30]
            filename = OUTPUT_DIR / f"{slug}_slide{i+1:02d}.png"
            page.screenshot(path=str(filename), clip={"x": 0, "y": 0, "width": 1080, "height": 1080})
            image_paths.append(filename)
            logger.info(f"슬라이드 {i+1}/{len(contexts)} 렌더링: {filename.name}")

        browser.close()

    logger.info(f"캐러셀 렌더링 완료: {len(image_paths)}장")
    return image_paths


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # 테스트용 더미 캐러셀
    dummy = {
        "keyword": "ETF 투자",
        "category": "재테크",
        "slides": [
            "직장인 ETF 투자\n지금 시작해도 늦지 않아요!",
            "ETF란?\nExchange Traded Fund. 주식처럼 거래되는 펀드예요.\n소액으로 수백 개 종목에 분산 투자 가능합니다.",
            "핵심 장점 첫 번째\n분산 투자로 리스크를 낮춰요.\n한 종목이 떨어져도 전체 영향이 작습니다.",
            "핵심 장점 두 번째\n수수료가 매우 저렴해요.\n액티브 펀드 대비 1/10 수준입니다.",
            "핵심 장점 세 번째\n ISA 계좌에 넣으면 절세까지!\n비과세·분리과세 혜택을 챙기세요.",
            "실생활 적용법\n매달 일정 금액을 코스피200 ETF에 적립하는 것부터 시작해보세요.\n복리 효과로 10년 후가 달라집니다.",
            "오늘의 핵심 요약\nETF = 분산 + 저비용 + 절세\n저장해두고 나중에 써먹으세요 🔖",
        ],
        "caption": "ETF 투자 입문 가이드",
        "hashtags": "#ETF #재테크 #투자공부",
        "slide_count": 7,
    }

    paths = render_carousel(dummy, "etf_test")
    print(f"\n생성된 파일:")
    for p in paths:
        print(f"  {p}")
    print(f"\n확인: open {OUTPUT_DIR}")
