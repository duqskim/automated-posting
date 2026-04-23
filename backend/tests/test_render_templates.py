"""
템플릿 6종 렌더링 테스트
실행: cd backend && python tests/test_render_templates.py
"""
import asyncio
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

TEMPLATE_DIR = Path(__file__).parents[1] / "app" / "agents" / "media" / "image_renderer" / "templates"
OUTPUT_DIR = Path(__file__).parents[1] / "output" / "test_renders"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

# 공통 테마
THEME = {
    "bg_primary": "#0F172A",
    "bg_secondary": "#1E293B",
    "text_primary": "#F1F5F9",
    "text_secondary": "#94A3B8",
    "accent": "#3B82F6",
    "accent_secondary": "#8B5CF6",
    "brand_handle": "@allai0011",
    "total_slides": "7",
}

# 각 템플릿별 테스트 데이터
TEST_DATA = {
    "hook_bold": {
        **THEME,
        "main_text": "직장인 73.2%가 모르는\nISA 절세 전략",
        "sub_text": "연 400만원 비과세 혜택, 지금 시작하세요",
        "title_size": 56,
        "category": "재테크",
        "slide_num": "1",
    },
    "editorial": {
        **THEME,
        "point_num": 1,
        "title": "ISA 계좌란 무엇인가요?",
        "body": "개인종합자산관리계좌(ISA)는 하나의 계좌에서<br>예금, 펀드, ETF, 주식을 모아 관리하는 절세 계좌예요.<br><br>연 2,000만원까지 납입 가능하고,<br>순이익 400만원까지 비과세 혜택을 받을 수 있어요.",
        "highlight": "핵심: ISA = 절세 + 분산투자를 한 번에",
        "title_size": 44,
        "body_size": 24,
        "slide_num": "2",
    },
    "data_hero": {
        **THEME,
        "label": "2024년 ISA 가입 증가율",
        "number": "23.7%",
        "unit": "전년 대비",
        "context": "MZ세대 중심으로 ISA 가입이 급증하고 있어요",
        "number_size": 120,
        "change": "+8.2%p",
        "change_direction": "up",
        "source_text": "금융감독원 2024 보고서",
        "slide_num": "3",
    },
    "list_icons": {
        **THEME,
        "title": "ISA 계좌 3가지 유형",
        "items": [
            {"title": "중개형 ISA", "desc": "직접 주식·ETF 매매 가능, 수수료 저렴"},
            {"title": "신탁형 ISA", "desc": "은행이 운용, 안정적이지만 수익률 낮음"},
            {"title": "일임형 ISA", "desc": "전문가 위탁 운용, 초보자에게 적합"},
        ],
        "slide_num": "4",
    },
    "comparison": {
        **THEME,
        "title": "중개형 ISA vs 연금저축",
        "left_title": "중개형 ISA",
        "right_title": "연금저축",
        "left_items": [
            "비과세 400만원",
            "자유로운 인출",
            "3년 의무 보유",
            "ETF + 주식 직접 매매",
        ],
        "right_items": [
            "세액공제 16.5%",
            "55세까지 인출 제한",
            "장기 적립 필수",
            "펀드 위주 운용",
        ],
        "slide_num": "5",
    },
    "summary": {
        **THEME,
        "emoji": "📌",
        "title": "오늘의 핵심 요약",
        "items": [
            "ISA = 비과세 400만원 + 분리과세 혜택",
            "직장인이라면 중개형 ISA 추천",
            "ETF 적립으로 시작하면 리스크 최소화",
            "연금저축과 함께 쓰면 절세 극대화",
        ],
        "cta_text": "저장해두고 나중에 써먹으세요 📌",
        "disclaimer": "⚠️ 본 콘텐츠는 참고용이며 투자 권유가 아닙니다\n🤖 AI 생성 콘텐츠 | 인공지능 기본법 준수",
        "slide_num": "7",
    },
}


async def render_all():
    print(f"템플릿 디렉토리: {TEMPLATE_DIR}")
    print(f"출력 디렉토리: {OUTPUT_DIR}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1350})

        for template_name, data in TEST_DATA.items():
            template_file = f"{template_name}.html"
            try:
                template = env.get_template(template_file)
            except Exception as e:
                print(f"  ✗ {template_name}: 템플릿 로드 실패 — {e}")
                continue

            html = template.render(**data)
            await page.set_content(html, wait_until="networkidle")
            # 폰트 로딩 대기
            await page.wait_for_timeout(1500)

            output_path = OUTPUT_DIR / f"{template_name}.png"
            await page.screenshot(
                path=str(output_path),
                clip={"x": 0, "y": 0, "width": 1080, "height": 1350},
            )
            size_kb = output_path.stat().st_size / 1024
            print(f"  ✓ {template_name}.png — {size_kb:.0f}KB")

        await browser.close()

    print(f"\n렌더링 완료! 확인: open {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(render_all())
